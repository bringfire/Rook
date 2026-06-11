# Release Runtime Smoke Checklist And Evidence Notes

Date: 2026-06-08

Status: working release-smoke checklist plus evidence notes. Updated
2026-06-10 after the `v1.5.10` testing-laptop smoke.

## Current Evidence

On 2026-06-09, the public `v1.5.10` installer was smoke-tested on the testing
laptop. The reported result was that the release install was in order.

This document does not yet contain the full evidence manifest from that run. The
next documentation task is to fill in:

- exact installer asset name and hash
- testing laptop identity or environment description
- Windows/Rhino/Revit versions used
- install mode: fresh install, repair, upgrade, or reinstall
- Claude/Codex clients checked
- surfaces exercised
- skipped checks and why
- failures or warnings, if any

Until a contradictory run appears, the 2026-06-09 smoke should be treated as the
release confidence baseline for the already-published `v1.5.10` artifact.

## Purpose

Capture the release-confidence surface for installed-runtime smoke testing and
provide a place to record concrete release evidence.

The goal is to prove the installed public Rook package works from the same
paths, runtimes, configs, and host processes a user will actually run.

## Installer Identity

- Install into a clean Windows user profile.
- Require no user Python on PATH, or prove PATH Python is ignored.
- Prefer at least one run with network blocked or disabled.
- Confirm installer exits cleanly.
- Confirm installed paths exist:
  - `%LOCALAPPDATA%\Rook\app`
  - `%LOCALAPPDATA%\Rook\python\cpython-3.11.9`
  - `%LOCALAPPDATA%\Rook\venv`
  - `%LOCALAPPDATA%\Rook\app\chirp\.venv`
  - `%APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative`

## Python Runtime

- Private Python version matches the runtime manifest.
- Rook venv imports `rook` from `venv\Lib\site-packages`, not source.
- Chirp venv imports `chirp` from `app\chirp\.venv\Lib\site-packages`.
- `pip check` passes in both venvs.
- `cv2`, `PIL`, `numpy`, and `skimage` import from the Rook venv.
- Install evidence proves `--no-index` and bundled wheelhouse use.
- OCR/Tesseract is not release-gated unless intentionally packaged.

## Client Configs

- Claude config points to the private Rook venv Python.
- Codex config points to the private Rook venv Python.
- `RookChatService.json` points to the private Rook venv Python.
- MCP env clears `PYTHONHOME` and `PYTHONPATH`.
- `CHIRP_HOME` points to `%LOCALAPPDATA%\Rook\app\chirp`.
- No generated config references repo/source paths or user Python.

## Standalone Rhino

- Rhino 8 launches after install.
- RookNative loads.
- Managed companion loads.
- Plugin Manager lists RookNative/Rook.
- Native discovery file appears under `%LOCALAPPDATA%\Rook\discovery`.
- `rhino_ping` succeeds.
- Companion self-report records process identity, runtime child, assembly
  location, startup completion, bridge registration, and a fresh status
  timestamp.

## Core Native Routes

Run a representative route suite in a temporary Rhino document:

- document info
- layer list/create/delete temp layer
- material list/create temp material
- object create/select/query/delete
- viewport/camera query
- safe command execution
- undo/redo around a temp object
- invalid ID and malformed request error handling

## MCP Server

From a Claude/Codex-style stdio launch:

- MCP starts from the private Rook venv.
- Tool list loads.
- `rhino_ping` succeeds.
- Representative Rhino tools succeed.
- Timeout/cancellation behavior does not leave orphaned processes.
- Invalid tool arguments return structured errors rather than crashing.

## Chat Panel

- `ShowRookChat` opens the panel.
- Chat service starts from the private Rook venv.
- Chat service health passes.
- Restart command works.
- Chat service death/recovery behaves cleanly.
- No stale manifest, source path, or user-Python fallback is used.

## Grasshopper And Chirp

- Grasshopper opens.
- GH bridge health passes.
- Basic GH document operations work.
- `chirp_create` succeeds in deterministic mode.
- Created component compiles.
- `gh_errors` reports no created-component errors.
- Chirp sidecar starts from `%LOCALAPPDATA%\Rook\app\chirp\.venv`.
- Restart/cleanup does not leave stale Chirp sidecars.

## Vision And Media

- Bundled FFmpeg provenance validates.
- FFmpeg fixture operation works, such as video sidecar/frame extraction.
- Shipped image libraries import.
- Any shipped non-OCR vision operation runs on a fixture.
- OCR reports unavailable or is skipped unless Tesseract is packaged.

## Rhino.Inside.Revit

This should remain mandatory because it exercises the hardest load context.

- Launch Revit.
- Start Rhino.Inside.
- RookNative loads.
- Managed companion loads from the expected runtime child.
- `RookBim.dll` is present in the `net48` payload.
- `rhino_ping` succeeds.
- Companion self-report says `rhinoInside=true`.
- No CLR binding or type-load errors appear.
- A non-mutating BIM/Rhino bridge operation succeeds if available.

## Upgrade, Reinstall, And Uninstall

- Install over the previous version.
- Venv invalidation works when runtime or lock identity changes.
- Stale configs are rewritten.
- Stale source-path manifests are rejected.
- Uninstall removes app, venvs, discovery, and plugin files.
- Reinstall after uninstall succeeds.

## Negative Contamination

Run with:

- fake user Python on PATH
- bad `PYTHONPATH`
- bad `PYTHONHOME`
- pip index environment variables
- stale Claude/Codex configs
- network blocked

Expected result: public install still uses only private Python and the local
wheelhouse.

## Evidence Manifest

The release manifest should record actual evidence, not only booleans:

- installed paths
- private Python path/version
- Rook and Chirp venv paths
- `rook.__file__`
- `chirp.__file__`
- `pip check` results
- generated config paths and command identities
- native port and discovery path
- `rhino_ping` result
- chat service health
- Chirp component result
- standalone Rhino companion self-report
- Rhino.Inside.Revit companion self-report

## Failure Policy Seed

Mandatory gates should block release on failure. Optional or future features,
such as OCR without bundled Tesseract, should be explicitly skipped with
evidence rather than silently ignored.
