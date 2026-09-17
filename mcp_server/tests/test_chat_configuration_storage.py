"""Windows storage admission. All paths and credentials are disposable fixtures."""
import ctypes
import importlib
import os
import json
import sys
import subprocess
from pathlib import Path

import pytest


def storage():
    name = 'rook.agent.chat.configuration_storage'
    assert importlib.util.find_spec(name) is not None, 'storage admission helper is missing'
    return importlib.import_module(name)


def test_owned_object_rejects_untrusted_access():
    s = storage()
    trusted = {'user', 'system', 'admin'}
    for right in (0x120089, 0x10000, 0x40000, 0x80000, 0x40, 0x2, 0x10000000, 0x40000000):
        with pytest.raises(s.ConfigurationStorageRefused):
            s._admit_aces([('other', right, 0)], trusted)


def set_acl(path, sddl):
    """Fixture-only ACL setup, never called on installed/user configuration."""
    from ctypes import wintypes as w
    adv = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    adv.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [w.LPCWSTR, w.DWORD, ctypes.POINTER(w.LPVOID), w.LPVOID]
    adv.GetSecurityDescriptorDacl.argtypes = [w.LPVOID, ctypes.POINTER(w.BOOL), ctypes.POINTER(w.LPVOID), ctypes.POINTER(w.BOOL)]
    adv.SetNamedSecurityInfoW.argtypes = [w.LPWSTR, w.DWORD, w.DWORD, w.LPVOID, w.LPVOID, w.LPVOID, w.LPVOID]
    kernel.LocalFree.argtypes = [w.LPVOID]
    sd = w.LPVOID()
    assert adv.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(sd), None)
    try:
        present, defaulted, acl = w.BOOL(), w.BOOL(), w.LPVOID()
        assert adv.GetSecurityDescriptorDacl(sd, ctypes.byref(present), ctypes.byref(acl), ctypes.byref(defaulted))
        assert adv.SetNamedSecurityInfoW(str(path), 1, 4 | 0x80000000, None, None, acl, None) == 0
    finally:
        kernel.LocalFree(sd)


@pytest.fixture
def private_parent(tmp_path):
    if os.name != 'nt':
        pytest.skip('requires Windows discretionary ACLs')
    s = storage()
    sid = s._Windows().user_sid
    parent = tmp_path / 'data'
    parent.mkdir()
    acl = f'D:P(A;OICI;FA;;;{sid})(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)'
    set_acl(parent, acl + '(A;OICI;FR;;;WD)')
    return s, parent, acl


@pytest.mark.parametrize('rights', ['FR', 'DC', 'FA'])
def test_fresh_private_directory_under_broad_ancestors(private_parent, monkeypatch, rights):
    s, parent, acl = private_parent
    # Only disposable fixture ACLs are changed. The ordinary Temp/profile
    # ancestors are neither inspected nor altered by the product admission.
    set_acl(parent, acl + f'(A;OICI;{rights};;;WD)')
    root = parent / 'prime-config'
    original = s._Windows.open
    opened = []
    def observe_open(windows, path, **kwargs):
        opened.append(path)
        return original(windows, path, **kwargs)
    monkeypatch.setattr(s._Windows, 'open', observe_open)
    s.admit_configuration_storage(root)
    assert root.is_dir()
    assert not list(root.iterdir())  # admission does not manufacture auth/settings
    s.admit_configuration_storage(root)
    assert set(opened) == {root, *(root / name for name in ('auth.json', 'settings.json', 'models.json'))}


@pytest.mark.parametrize('name', ['auth.json', 'settings.json', 'models.json'])
def test_existing_unsafe_file_refuses_without_repair(private_parent, name):
    s, parent, acl = private_parent
    root = parent / 'prime-config'
    s.admit_configuration_storage(root)
    file = root / name
    file.write_text('synthetic-only', encoding='utf8')
    set_acl(file, acl.replace('OICI', '') + '(A;;FR;;;WD)')
    before = file.read_bytes()
    with pytest.raises(s.ConfigurationStorageRefused):
        s.admit_configuration_storage(root)
    assert file.read_bytes() == before
    with pytest.raises(s.ConfigurationStorageRefused):
        s.admit_configuration_storage(root)


def test_existing_unsafe_root_refuses_unchanged(private_parent):
    s, parent, _ = private_parent
    root = parent / 'prime-config'
    root.mkdir()  # inherits extra read
    with pytest.raises(s.ConfigurationStorageRefused):
        s.admit_configuration_storage(root)
    assert root.is_dir() and not list(root.iterdir())


def test_hardlinked_file_refuses(private_parent):
    s, parent, _ = private_parent
    root = parent / 'prime-config'
    s.admit_configuration_storage(root)
    file = root / 'auth.json'
    file.write_text('synthetic-only')
    os.link(file, parent / 'alias')
    with pytest.raises(s.ConfigurationStorageRefused):
        s.admit_configuration_storage(root)


def test_regular_file_cannot_stand_in_for_directory(private_parent):
    s, parent, _ = private_parent
    root = parent / 'prime-config'
    root.write_text('synthetic-only')
    with pytest.raises(s.ConfigurationStorageRefused):
        s.admit_configuration_storage(root)


def test_reparse_directory_refuses_without_following_target(private_parent, tmp_path):
    s, parent, _ = private_parent
    target = tmp_path / 'target'
    target.mkdir()
    root = parent / 'prime-config'
    env = dict(os.environ, STORAGE_TEST_LINK=str(root), STORAGE_TEST_TARGET=str(target))
    result = subprocess.run(['C:/Program Files/PowerShell/7/pwsh.exe','-NoProfile','-NonInteractive','-Command',
        "$ErrorActionPreference='Stop';New-Item -ItemType Junction -Path $env:STORAGE_TEST_LINK -Target $env:STORAGE_TEST_TARGET | Out-Null"],
        env=env,capture_output=True,timeout=10)
    assert result.returncode == 0 and not result.stderr
    with pytest.raises(s.ConfigurationStorageRefused):
        s.admit_configuration_storage(root)
    assert not list(target.iterdir())
    result = repair(s, root)
    assert result['outcome'] == 'refused'
    assert not any(row['attempted'] for row in result['objects'])
    assert not list(target.iterdir())


def test_relative_path_refuses():
    s = storage()
    with pytest.raises(s.ConfigurationStorageRefused):
        s.admit_configuration_storage(Path('relative/prime-config'))


def test_unknown_owner_refuses_from_real_security_read(private_parent, monkeypatch):
    s, parent, _ = private_parent
    root = parent / 'prime-config'
    s.admit_configuration_storage(root)
    w = s._Windows()
    # Substitute only the owner SID result; real handle/descriptor acquisition
    # runs. Changing an object's owner to another user requires extra privilege.
    monkeypatch.setattr(w, 'sid', lambda pointer: 'S-1-5-21-1-2-3-9999')
    with w.open(root) as handle, pytest.raises(s.ConfigurationStorageRefused):
        w.inspect(handle, directory=True)


def test_creation_is_protected_before_admission_readback(private_parent, monkeypatch):
    s, parent, _ = private_parent
    original = s._Windows.create
    checked = []
    def observe_created(windows, path):
        original(windows, path)
        with windows.open(path) as handle:
            windows.inspect(handle, directory=True)
        checked.append(path)
    monkeypatch.setattr(s._Windows, 'create', observe_created)
    s.admit_configuration_storage(parent / 'prime-config')
    assert checked == [parent / 'prime-config']


def test_privacy_error_has_safe_http_classification():
    from rook.agent.chat import server
    error = storage().ConfigurationStorageRefused()
    response = server._exception_response(error)
    assert response.status == 409
    value = json.loads(response.text)
    assert value['error']['code'] == 'configuration_storage_refused'
    assert 'Operation not started' in value['error']['message']


@pytest.mark.parametrize('policy', ['missing_inheritance', 'inherit_only_read'])
def test_root_must_protect_future_files(private_parent, policy):
    s, parent, acl = private_parent
    root = parent / 'prime-config'
    s.admit_configuration_storage(root)
    set_acl(root, acl.replace('OICI','') if policy == 'missing_inheritance' else acl + '(A;OIIO;FR;;;WD)')
    with pytest.raises(s.ConfigurationStorageRefused):
        s.admit_configuration_storage(root)


def descriptor(path):
    """Metadata-only fixture oracle, including protection and inherited ACE flags."""
    w = storage()._Windows()
    w.adv.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [
        w.w.LPVOID, w.w.DWORD, w.w.DWORD, ctypes.POINTER(w.w.LPWSTR), w.w.LPVOID]
    sd, owner, acl = w.w.LPVOID(), w.w.LPVOID(), w.w.LPVOID()
    text = w.w.LPWSTR()
    with w.open(path) as handle:
        assert w.adv.GetSecurityInfo(handle, 1, 5, ctypes.byref(owner), None,
                                    ctypes.byref(acl), None, ctypes.byref(sd)) == 0
        try:
            assert w.adv.ConvertSecurityDescriptorToStringSecurityDescriptorW(sd, 1, 5, ctypes.byref(text), None)
            return text.value
        finally:
            w.kernel.LocalFree(ctypes.cast(text, w.w.LPVOID))
            w.kernel.LocalFree(sd)


@pytest.fixture
def exposed_store(private_parent):
    s, parent, acl = private_parent
    root = parent / 'prime-config'
    root.mkdir()
    for name in ('auth.json', 'settings.json', 'models.json'):
        (root / name).write_bytes(b'synthetic\x00unchanged\xff')
    return s, root


def repair(s, root):
    assert hasattr(s, 'repair_configuration_storage'), 'explicit repair is not implemented'
    return s.repair_configuration_storage(root)


def test_repair_preserves_bytes_identity_and_surroundings(exposed_store, monkeypatch):
    s, root = exposed_store
    before = {p.name: (p.stat().st_ino, p.read_bytes()) for p in root.iterdir()}
    identity, parent_acl = root.stat().st_ino, descriptor(root.parent)
    sibling = root.parent / 'unrelated.txt'
    sibling.write_bytes(b'not selected')
    sibling_acl = descriptor(sibling)
    # Any production content read/write or copying would fail this control.
    with monkeypatch.context() as m:
        m.setattr(Path, 'read_bytes', lambda *_: pytest.fail('production content read'))
        m.setattr(Path, 'write_bytes', lambda *_: pytest.fail('production content write'))
        result = repair(s, root)
    assert result['outcome'] == 'repaired' and result['admission'] == 'passed'
    assert result['cleanup'] == 'closed'
    assert all(row['write_completed'] and row['verified'] for row in result['objects'])
    assert root.stat().st_ino == identity
    assert {p.name: (p.stat().st_ino, p.read_bytes()) for p in root.iterdir()} == before
    assert descriptor(root.parent) == parent_acl and descriptor(sibling) == sibling_acl
    s.admit_configuration_storage(root)
    after_acl = {p: descriptor(p) for p in [root, *root.iterdir()]}
    again = repair(s, root)
    assert again['outcome'] == 'unchanged' and again['admission'] == 'passed'
    assert not any(row['attempted'] for row in again['objects'])
    assert {p: descriptor(p) for p in after_acl} == after_acl


def test_repair_private_store_is_noop_and_missing_files_stay_absent(private_parent, monkeypatch):
    s, parent, _ = private_parent
    root = parent / 'prime-config'
    s.admit_configuration_storage(root)
    original = descriptor(root)
    assert hasattr(s._Windows, 'protect'), 'repair setter is not implemented'
    monkeypatch.setattr(s._Windows, 'protect', lambda *_args, **_kwargs: pytest.fail('unexpected ACL write'))
    result = repair(s, root)
    assert result['outcome'] == 'unchanged' and result['admission'] == 'passed'
    assert not any(row['attempted'] for row in result['objects'])
    assert [r['present'] for r in result['objects']] == [True, False, False, False]
    assert descriptor(root) == original and not list(root.iterdir())


@pytest.mark.parametrize('problem', ['unknown_file', 'directory', 'hardlink', 'owner', 'identity', 'elevated'])
def test_repair_prewrite_refusals_preserve_storage(exposed_store, monkeypatch, problem):
    s, root = exposed_store
    assert hasattr(s._Windows, 'protect'), 'repair setter is not implemented'
    if problem == 'unknown_file':
        (root / 'unexpected.txt').write_bytes(b'unchanged')
    elif problem == 'directory':
        (root / 'auth.json').unlink()
        (root / 'auth.json').mkdir()
    elif problem == 'hardlink':
        os.link(root / 'auth.json', root.parent / 'alias')
    w = s._Windows()
    before = {p: descriptor(p) for p in [root, *root.iterdir()]}
    if problem == 'owner':
        sid, calls = w.sid, []
        def changed_owner(pointer):
            calls.append(pointer)
            return 'S-1-5-21-1-2-3-9999' if len(calls) == 4 else sid(pointer)
        monkeypatch.setattr(w, 'sid', changed_owner)  # Last selected file, not just root.
    elif problem == 'elevated':
        monkeypatch.setattr(w, 'require_unelevated', lambda: w.check(False))
    elif problem == 'identity':
        original = w.inspect
        seen = set()
        def changed(handle, **kwargs):
            value = original(handle, **kwargs)
            if handle in seen:
                return (value[0], value[1], value[2] + 1)
            seen.add(handle)
            return value
        monkeypatch.setattr(w, 'inspect', changed)
    monkeypatch.setattr(s, '_Windows', lambda: w)
    monkeypatch.setattr(w, 'protect', lambda *_args, **_kwargs: pytest.fail('write before complete admission'))
    result = repair(s, root)
    assert result['outcome'] == 'refused' and result['cleanup'] == 'closed'
    assert not any(row['attempted'] for row in result['objects'])
    monkeypatch.undo()
    assert {p: descriptor(p) for p in before} == before


def test_repair_partial_failure_retains_actual_completion(exposed_store, monkeypatch):
    s, root = exposed_store
    assert hasattr(s._Windows, 'protect'), 'repair setter is not implemented'
    original = s._Windows.protect
    calls = []
    def fail_second(w, handle, **kwargs):
        calls.append(handle)
        if len(calls) == 2:
            raise RuntimeError('synthetic-private-value-must-not-escape')
        return original(w, handle, **kwargs)
    before = {p: (p.read_bytes(), descriptor(p)) for p in root.iterdir()}
    monkeypatch.setattr(s._Windows, 'protect', fail_second)
    result = repair(s, root)
    assert result['outcome'] == 'partial' and result['cleanup'] == 'closed'
    assert result['admission'] == 'not_run'
    first, second, *rest = result['objects']
    assert first['write_completed'] and first['verified']
    assert second['attempted'] and not second['write_completed']
    assert not any(row['attempted'] for row in rest)
    assert {p: (p.read_bytes(), descriptor(p)) for p in before} == before
    assert 'synthetic-private' not in json.dumps(result)
    with pytest.raises(s.ConfigurationStorageRefused):
        s.admit_configuration_storage(root)


def test_repair_setter_does_not_propagate_to_unselected_child(exposed_store):
    s, root = exposed_store
    assert hasattr(s._Windows, 'protect'), 'repair setter is not implemented'
    before = {p: descriptor(p) for p in root.iterdir()}
    w = s._Windows()
    with w.open(root, repair=True, directory=True) as handle:
        w.inspect(handle, directory=True, permissions=False)
        w.protect(handle, directory=True)
        w.inspect(handle, directory=True)
    assert {p: descriptor(p) for p in before} == before


def test_repair_readback_failure_preserves_write_evidence(exposed_store, monkeypatch):
    s, root = exposed_store
    original, inspect = s._Windows.protect, s._Windows.inspect
    written = set()
    def protect(w, handle, **kwargs):
        original(w, handle, **kwargs)
        written.add(handle)
    def refuse_readback(w, handle, **kwargs):
        if handle in written and kwargs.get('permissions', True):
            raise s.ConfigurationStorageRefused()
        return inspect(w, handle, **kwargs)
    monkeypatch.setattr(s._Windows, 'protect', protect)
    monkeypatch.setattr(s._Windows, 'inspect', refuse_readback)
    result = repair(s, root)
    assert result['outcome'] == 'partial' and result['cleanup'] == 'closed'
    assert result['objects'][0]['write_completed'] and not result['objects'][0]['verified']
    assert not any(row['attempted'] for row in result['objects'][1:])


def test_repair_cleanup_failure_does_not_erase_verified_writes(exposed_store, monkeypatch):
    from contextlib import contextmanager
    s, root = exposed_store
    original = s._Windows.open
    @contextmanager
    def failing_close(w, path, **kwargs):
        with original(w, path, **kwargs) as handle:
            yield handle
        if kwargs.get('repair'):
            raise RuntimeError('synthetic-private-cleanup-error')
    monkeypatch.setattr(s._Windows, 'open', failing_close)
    result = repair(s, root)
    assert result['outcome'] == 'failed' and result['cleanup'] == 'unconfirmed'
    assert result['admission'] == 'passed'
    assert all(row['write_completed'] and row['verified'] for row in result['objects'])
    assert 'synthetic-private' not in json.dumps(result)


def test_repair_missing_store_is_not_created(private_parent):
    s, parent, _ = private_parent
    root = parent / 'prime-config'
    assert repair(s, root)['outcome'] == 'refused'
    assert not root.exists()


@pytest.mark.parametrize('case,expected', [('unconfirmed', 2), ('repair', 0), ('wrong_binding', 1), ('unsafe_shape', 1), ('bad_arguments', 2)])
def test_repair_real_cli_requires_explicit_selection(exposed_store, case, expected):
    s, root = exposed_store
    env = dict(os.environ, ROOK_MODE='release', ROOK_INSTALL_ROOT=str(root.parent / 'app'),
               ROOK_DATA_DIR=str(root.parent))
    src = Path(__file__).parents[1] / 'src'
    entry = f"import sys,runpy;sys.path.insert(0,{str(src)!r});runpy.run_module('rook.agent.chat.configuration_storage',run_name='__main__')"
    target = root.parent / 'elsewhere' if case == 'wrong_binding' else root
    argv = [sys.executable, '-I', '-B', '-c', entry, '--repair-permissions', '--expected-directory', str(target)]
    if case != 'unconfirmed':
        argv.append('--confirm-closed')
    if case == 'bad_arguments':
        argv.append('--unknown=synthetic-private-value')
    if case == 'unsafe_shape':
        (root / 'unexpected.txt').write_bytes(b'synthetic')
    before = descriptor(root)
    result = subprocess.run(argv, env=env, capture_output=True, timeout=15)
    assert result.returncode == expected
    assert len(result.stdout) + len(result.stderr) < 8192
    assert b'synthetic' not in result.stdout + result.stderr
    if case == 'repair':
        value = json.loads(result.stdout)
        assert value['outcome'] == 'repaired' and value['cleanup'] == 'closed'
        assert not result.stderr
        s.admit_configuration_storage(root)
    else:
        assert descriptor(root) == before
        if expected == 1:
            value = json.loads(result.stdout)
            assert value['outcome'] == 'refused' and value['cleanup'] == 'closed'
            assert not result.stderr


@pytest.mark.asyncio
@pytest.mark.parametrize('runtime', ['node', 'bun'])
@pytest.mark.parametrize('initial_store', ['fresh', 'repaired'])
async def test_real_prime_writes_refresh_and_replacement_preserve_acl(private_parent, tmp_path, runtime, initial_store):
    s, parent, _ = private_parent
    root = parent / 'prime-config'
    if initial_store == 'repaired':
        root.mkdir()  # Inherited exposure is corrected before any synthetic credential write.
        assert repair(s, root)['outcome'] == 'repaired'
    s.admit_configuration_storage(root)
    prime = Path('D:/prime-agent/.worktrees/rookchat-configuration')
    fixture = Path(__file__).parent / 'fixtures/prime_configuration_storage.mjs'
    common_path = Path(__file__).parents[2] / 'scripts/qualification/rookchat_prime_acp_common.py'
    spec = importlib.util.spec_from_file_location('storage_test_common', common_path)
    common = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = common
    spec.loader.exec_module(common)
    if runtime == 'node':
        argv = ('C:/Program Files/nodejs/node.exe','--import',(prime/'node_modules/tsx/dist/loader.mjs').as_uri(),str(fixture))
    else:
        argv = ('C:/Users/bring/.bun/bin/bun.exe','--no-install','--no-env-file',str(fixture))
    env = {'SystemRoot':os.environ['SystemRoot'], 'WINDIR':os.environ['SystemRoot'], 'PATH':'',
           'HOME':str(tmp_path),'USERPROFILE':str(tmp_path),'TEMP':str(tmp_path),'TMP':str(tmp_path),
           'ROOK_STORAGE_PRIME_SOURCE':str(prime),'PRIME_AGENT_CODING_AGENT_DIR':str(root),
           'TSX_TSCONFIG_PATH':str(prime/'tsconfig.json'),'TSX_DISABLE_CACHE':'1','DO_NOT_TRACK':'1',
           'ESBUILD_BINARY_PATH':str(prime/'node_modules/@esbuild/win32-x64/esbuild.exe')}
    result = await common.run_bounded_process(common.ProcessSpec(argv,tmp_path,env,90,10,65536))
    assert result.direct_child_exit_observed and not result.timed_out and not result.output_overflow
    assert result.exit_code == 0 and not result.stderr, result.stderr.decode(errors='replace')
    report = json.loads(result.stdout)
    assert report['outcome'] == 'passed' and report['contacts'] == 0
    sid = s._Windows().user_sid
    phases = set()
    temporary = set()
    for observation in report['reports']:
        phases.add(observation['phase'])
        acl = observation['acl']
        assert acl['aces']
        assert all(ace['type'] == 'Allow' and ace['sid'] in {sid,'S-1-5-18','S-1-5-32-544'} for ace in acl['aces'])
        assert any(ace['sid'] == sid and ace['rights'] & 0x1F01FF == 0x1F01FF for ace in acl['aces'])
        if observation['name'].endswith('.tmp'):
            temporary.add(observation['phase'])
    assert {'sync-create','async-replace','oauth-refresh','settings-replace','models-replace'} <= phases
    assert temporary == {'settings-replace','models-replace'}
    s.admit_configuration_storage(root)
