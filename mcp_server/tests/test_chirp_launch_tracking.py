"""Private launch receipts and conservative Windows job settlement."""
import json
from types import SimpleNamespace

import pytest

from rook import chirp_launch_tracking as tracking
from rook.providers.vertex_auth import VertexAuthError


@pytest.fixture
def registry(tmp_path, monkeypatch):
    monkeypatch.setattr(tracking, 'process_identity', lambda _: {'pid': 10, 'created': 100})
    active = {}
    monkeypatch.setattr(tracking, 'job_is_active', lambda name: active.get(name, False))
    return tracking.LaunchRegistry(SimpleNamespace(path=tmp_path/'vertex.json', _mutex_name='synthetic-mutex')), active


def test_incomplete_intent_remains_blocked_after_owner_exit(registry, monkeypatch):
    launches, _ = registry
    path = launches.begin()
    monkeypatch.setattr(tracking, 'process_identity', lambda _: None)
    assert launches.pending()
    assert path.exists()


def test_job_membership_survives_missing_intermediate_ancestry(registry):
    launches, active = registry
    path = launches.begin()
    launches.contained(path)
    name = json.loads(path.read_text())['job_name']
    active[name] = True
    assert launches.pending()
    active[name] = False
    assert not launches.pending()
    assert not path.exists()


def test_failed_inspection_never_discards_receipt(registry, monkeypatch):
    launches, _ = registry
    path = launches.begin()
    launches.contained(path)
    def denied(*args): raise VertexAuthError('vertex_restart_required', 'Synthetic inspection failure')
    monkeypatch.setattr(tracking, 'job_is_active', denied)
    with pytest.raises(VertexAuthError): launches.pending()
    assert path.exists()


def test_missing_job_name_without_settlement_receipt_stays_blocked(registry, monkeypatch):
    launches, _ = registry
    path = launches.begin()
    launches.contained(path)
    monkeypatch.setattr(tracking, 'job_is_active', lambda _: None)
    assert launches.pending()
    value = launches._read(path)
    value['settled'] = True
    launches._write(path, value)
    assert not launches.pending()
    assert not path.exists()


@pytest.mark.parametrize('raw', ['{}', '[]', '{"schema_version":1,"schema_version":1}', 'x'*4097])
def test_malformed_receipt_is_retained_and_blocks_settlement(registry, raw):
    launches, _ = registry
    path = launches.begin()
    path.write_text(raw)
    with pytest.raises(VertexAuthError): launches.pending()
    assert path.exists()


def test_launch_limit_blocks_new_intent_without_unbounded_growth(registry):
    launches, _ = registry
    for _ in range(128): launches.begin()
    with pytest.raises(VertexAuthError): launches.begin()
    assert len(list(launches.folder.glob('*.json'))) == 128


def test_metadata_contains_only_process_identity_and_containment_receipt(registry):
    launches, _ = registry
    path = launches.begin()
    launches.contained(path)
    value = json.loads(path.read_text())
    assert set(value) == {'schema_version', 'owner', 'job_name', 'contained', 'settled'}
    assert value['contained'] is True
    assert value['owner'] == {'pid': 10, 'created': 100}


def test_directory_inspection_failure_cannot_look_like_settlement(registry, monkeypatch):
    from pathlib import Path
    launches, _ = registry
    path = launches.begin()
    def denied(_): raise PermissionError('Synthetic directory inspection failure')
    monkeypatch.setattr(Path, 'iterdir', denied)
    with pytest.raises(VertexAuthError): launches.pending()
    assert path.exists()


@pytest.mark.parametrize('failure', ['assign', 'commit', 'keeper', 'resume'])
def test_containment_failure_terminates_only_new_child_before_return(registry, monkeypatch, failure):
    launches, _ = registry
    path = launches.begin()
    calls = []
    process = SimpleNamespace(terminate=lambda: calls.append('terminate'), wait=lambda **kwargs: calls.append('wait'))
    def step(name):
        calls.append(name)
        if failure == name: raise VertexAuthError('vertex_restart_required', 'Synthetic containment failure')
    monkeypatch.setattr(tracking, 'ProcessJob', lambda _: SimpleNamespace(assign=lambda _: step('assign'), close=lambda: calls.append('close')))
    monkeypatch.setattr(tracking.subprocess, 'Popen', lambda *args, **kwargs: process)
    monkeypatch.setattr(launches, 'contained', lambda _: step('commit'))
    monkeypatch.setattr(tracking, 'resume_process', lambda _: step('resume'))
    monkeypatch.setattr(tracking, 'keep_job_open', lambda *args: step('keeper'))
    with pytest.raises(VertexAuthError): launches.launch(path).start(['synthetic'])
    assert calls[-3:] == ['terminate', 'wait', 'close']
    assert path.exists()


def test_suspended_containment_receipt_commits_before_resume(registry, monkeypatch):
    launches, _ = registry
    path = launches.begin()
    calls = []
    process = object()
    def popen(*args, **kwargs):
        assert kwargs['creationflags'] & tracking.CREATE_SUSPENDED
        calls.append('create')
        return process
    def resume(selected):
        assert selected is process and json.loads(path.read_text())['contained']
        calls.append('resume')
    monkeypatch.setattr(tracking.subprocess, 'Popen', popen)
    monkeypatch.setattr(tracking, 'ProcessJob', lambda _: SimpleNamespace(assign=lambda _: calls.append('assign'), close=lambda: calls.append('close')))
    monkeypatch.setattr(tracking, 'resume_process', resume)
    monkeypatch.setattr(tracking, 'keep_job_open', lambda *args: None)
    assert launches.launch(path).start(['synthetic']) is process
    assert calls == ['create', 'assign', 'resume', 'close']
