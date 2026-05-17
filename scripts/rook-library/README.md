# Rook Script Library

This directory contains repo-shipped durable script artifacts.

V1 execution policy:

- Only repo artifacts with `state: "validated"` are eligible for `run_library_script`.
- Only `mutation: "read_only"` scripts are executable in v1.
- Project-local `.rook/scripts` artifacts are searchable references only.
- Manifest `content_hash` is not self-certifying. Executable artifacts must also match `rook-library.lock.json`.
- Skills and agents must call `run_library_script` for validated library execution.

Artifact layout:

```text
scripts/rook-library/
  rook-library.lock.json
  rhino/
    <script-id>/
      manifest.json
      script.py
```
