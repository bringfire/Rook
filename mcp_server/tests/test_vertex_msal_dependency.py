"""Pinned MSAL public-client contract and actual packaged import probe."""
from __future__ import annotations

import ast
import builtins
import json
from pathlib import Path
import subprocess
from urllib.parse import parse_qs, urlsplit

import pytest


ROOT = Path(__file__).resolve().parents[2]


class DiscoveryTransport:
    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        assert url == "https://login.microsoftonline.com/11111111-1111-1111-1111-111111111111/v2.0/.well-known/openid-configuration"
        authority = "https://login.microsoftonline.com/11111111-1111-1111-1111-111111111111/oauth2/v2.0"
        payload = {"authorization_endpoint": authority + "/authorize", "token_endpoint": authority + "/token", "issuer": authority}
        return type("Response", (), {"status_code": 200, "headers": {}, "text": json.dumps(payload), "json": lambda self: payload})()

    def post(self, *args, **kwargs):
        pytest.fail("The auth-code setup must not dispatch a token request")


def test_msal_required_scopes_are_added_without_graph():
    import msal

    transport = DiscoveryTransport()
    app = msal.PublicClientApplication(
        "22222222-2222-2222-2222-222222222222",
        authority="https://login.microsoftonline.com/11111111-1111-1111-1111-111111111111",
        http_client=transport, instance_discovery=False, enable_broker_on_windows=False,
    )
    flow = app.initiate_auth_code_flow([], response_mode="form_post", redirect_uri="http://localhost:45678")
    query = parse_qs(urlsplit(flow["auth_uri"]).query)
    assert set(query["scope"][0].split()) == {"openid", "profile", "offline_access"}
    assert query["code_challenge_method"] == ["S256"]
    assert query["state"][0] and query["nonce"][0]
    assert query["response_mode"] == ["form_post"]
    assert len(transport.calls) == 1


def _packaged_probe():
    builder = (ROOT / "scripts/python-runtime/build-rook-python-wheelhouse.ps1").read_text(encoding="utf-8-sig")
    source = builder.split("$verificationScript =", 1)[1].split("@'", 1)[1].split("'@", 1)[0]
    tree = ast.parse(source)
    probe = next((node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "firm_auth_probe"), None)
    assert probe is not None, "Packaged runtime needs a real MSAL import/version probe"
    namespace = {}
    exec(compile(ast.Module(body=[probe], type_ignores=[]), "packaged-probe", "exec"), namespace)
    return namespace["firm_auth_probe"]()


def test_packaged_import_gate_requires_msal():
    probe = _packaged_probe()
    assert probe[:2] == ["-I", "-c"]
    original_import = builtins.__import__

    def missing_msal(name, *args, **kwargs):
        if name == "msal":
            raise ModuleNotFoundError("synthetic missing package")
        return original_import(name, *args, **kwargs)

    with pytest.raises(SystemExit, match="^vertex_auth_dependency_missing$"):
        exec(probe[2], {"__builtins__": dict(vars(builtins), __import__=missing_msal)})


def test_packaged_import_gate_verifies_installed_versions(capsys):
    exec(_packaged_probe()[2], {})
    assert json.loads(capsys.readouterr().out) == {"msal": "1.39.0", "google-auth": "2.56.3"}


@pytest.mark.parametrize("mutation", ["none", "missing", "version", "digest", "verification", "broker"])
def test_packaged_manifest_gate_rejects_unqualified_auth(mutation):
    record = {"project": "msal", "version": "1.39.0", "file": "msal-1.39.0-py3-none-any.whl", "sha256": "2d2577886906cd7293850dffa2da29119966c213bfc6ec0cecf8bf7621e1ca77"}
    manifest = {"wheelhouse": {"wheels": [record]}, "verification": {"rook": {"firm_auth_dependencies": {"msal": "1.39.0", "google-auth": "2.56.3"}}}}
    if mutation == "missing":
        manifest["wheelhouse"]["wheels"] = []
    elif mutation == "version":
        record["version"] = "0.0.0"
    elif mutation == "digest":
        record["sha256"] = "0" * 64
    elif mutation == "verification":
        manifest["verification"] = {}
    elif mutation == "broker":
        manifest["wheelhouse"]["wheels"].append({"project": "pymsalruntime"})
    validator = str(ROOT / "scripts/validate-python-wheelhouse.ps1").replace("'", "''")
    fixture = json.dumps(manifest).replace("'", "''")
    script = f"""
$ErrorActionPreference='Stop'
$tokens=$null; $errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile('{validator}',[ref]$tokens,[ref]$errors)
if ($errors.Count) {{ throw 'Validator syntax failed' }}
foreach ($name in @('Fail','Get-NormalizedPackageName','Assert-FirmAuthPayload')) {{
  $f=$ast.Find({{param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $name}},$true)
  if ($null -eq $f) {{ throw 'Missing validation function' }}
  . ([scriptblock]::Create($f.Extent.Text))
}}
$fixture='{fixture}' | ConvertFrom-Json
Assert-FirmAuthPayload -Manifest $fixture
"""
    result = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True, timeout=15)
    assert (result.returncode == 0) == (mutation == "none"), result.stderr
    if mutation != "none":
        assert "Python wheelhouse validation failed:" in result.stderr
