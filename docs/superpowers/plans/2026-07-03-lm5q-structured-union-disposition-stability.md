# LM5Q Structured Union Disposition Stability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the LM5P direct Ollama spike just enough to repeat the Gemma structured-union disposition phenomenon and write local grouped evidence.

**Architecture:** LM5Q remains diagnostic evidence-only. It adds an excerpt-length CLI knob and local `summary.json` aggregation to `scripts/lm5p_ollama_think_format_spike.py`, with deterministic tests in the existing spike test file. No production `mcp_server/src` code, LM5K runner code, prompt text, response parser, evidence packet, or transport API changes are allowed.

**Tech Stack:** Python 3.10-compatible script code, stdlib `argparse`/`json`/`collections`, pytest tests, direct Ollama REST remains live/manual only.

---

## File Structure

Modify only:

```text
scripts/lm5p_ollama_think_format_spike.py
mcp_server/tests/test_lm5p_ollama_think_format_spike.py
docs/superpowers/plans/2026-07-03-lm5q-structured-union-disposition-stability.md
```

Already committed spec:

```text
docs/superpowers/specs/2026-07-03-lm5q-structured-union-disposition-stability-design.md
```

Do not modify:

```text
mcp_server/src/rook/**/*.py
scripts/lm5k_worker_probe.py
docs/superpowers/probes/*.md
docs/superpowers/specs/2026-07-03-lm5q-structured-union-disposition-stability-design.md
```

`probe_runs/` artifacts are local evidence only and must remain untracked.

---

## Task 1: Add Configurable Excerpt Length

**Files:**
- Modify: `scripts/lm5p_ollama_think_format_spike.py`
- Modify: `mcp_server/tests/test_lm5p_ollama_think_format_spike.py`

- [ ] **Step 1: Write failing tests for `--excerpt-chars` parsing and custom excerpt use**

Add these tests near the existing argument and excerpt tests in `mcp_server/tests/test_lm5p_ollama_think_format_spike.py`:

```python
def test_args_default_excerpt_chars() -> None:
    args = SPIKE._args([])

    assert args.excerpt_chars == SPIKE.EXCERPT_CHARS


def test_args_custom_excerpt_chars() -> None:
    args = SPIKE._args(["--excerpt-chars", "1200"])

    assert args.excerpt_chars == 1200


def test_args_invalid_excerpt_chars_fails_during_parse() -> None:
    with pytest.raises(SystemExit):
        SPIKE._args(["--excerpt-chars", "0"])


def test_excerpt_uses_configured_limit() -> None:
    text = "abcdef" * 120

    assert SPIKE._excerpt(text, 12) == "abcdefabcdef"
    assert SPIKE._excerpt(None, 12) is None
```

Replace `test_excerpt_and_sha256_text_handle_text_and_none` with this version so the old default behavior stays pinned:

```python
def test_excerpt_and_sha256_text_handle_text_and_none() -> None:
    text = "abcdef" * 120

    assert SPIKE._excerpt(text) == text[:500]
    assert (
        SPIKE._sha256_text(text)
        == "a774b01707c1f8c098d7f16731417bc41f269298ffb4a896b716ce5829c8ce7d"
    )
    assert SPIKE._excerpt(None) is None
    assert SPIKE._sha256_text(None) is None
```

Add this classification test after `test_classifies_lm5g_loadable_response_with_thinking`:

```python
def test_classifies_provider_text_uses_configured_excerpt_chars() -> None:
    content = json.dumps(
        {
            "schema": "rook.local_worker_turn_response:v1",
            "kind": "observation",
            "message": "x" * 80,
            "data": None,
        }
    )
    thinking = "thinking-" * 20
    provider_text = json.dumps(
        {
            "message": {
                "content": content,
                "thinking": thinking,
            }
        }
    )

    row = SPIKE._classify_provider_text(
        provider_text,
        {"scenario": "demo"},
        excerpt_chars=40,
    )

    assert row["message_content_excerpt"] == content[:40]
    assert row["thinking_excerpt"] == thinking[:40]
```

- [ ] **Step 2: Run the new tests to verify RED**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5p_ollama_think_format_spike.py::test_args_default_excerpt_chars `
  mcp_server\tests\test_lm5p_ollama_think_format_spike.py::test_args_custom_excerpt_chars `
  mcp_server\tests\test_lm5p_ollama_think_format_spike.py::test_args_invalid_excerpt_chars_fails_during_parse `
  mcp_server\tests\test_lm5p_ollama_think_format_spike.py::test_excerpt_uses_configured_limit `
  mcp_server\tests\test_lm5p_ollama_think_format_spike.py::test_classifies_provider_text_uses_configured_excerpt_chars `
  -q
```

Expected: failures because `_args` has no `excerpt_chars`, `_excerpt` does not accept a custom limit, and `_classify_provider_text` does not accept `excerpt_chars`.

- [ ] **Step 3: Implement the excerpt parameter**

In `scripts/lm5p_ollama_think_format_spike.py`, replace `_excerpt` with:

```python
def _excerpt(value: str | None, excerpt_chars: int = EXCERPT_CHARS) -> str | None:
    if value is None:
        return None
    return value[:excerpt_chars]
```

Change `_classify_provider_text` signature from:

```python
def _classify_provider_text(
    provider_text: str,
    base_row: Mapping[str, Any],
) -> dict[str, Any]:
```

to:

```python
def _classify_provider_text(
    provider_text: str,
    base_row: Mapping[str, Any],
    *,
    excerpt_chars: int = EXCERPT_CHARS,
) -> dict[str, Any]:
```

Inside `_classify_provider_text`, change the two excerpt calls:

```python
row["message_content_excerpt"] = _excerpt(content, excerpt_chars)
```

and:

```python
row["thinking_excerpt"] = _excerpt(thinking, excerpt_chars)
```

Leave `_model_metadata` using the default `_excerpt(text)` because model metadata snippets do not need the LM5Q 1200-character diagnostic knob.

In `_run_matrix`, add a keyword-only parameter:

```python
    excerpt_chars: int,
```

Pass it into classification:

```python
row = _classify_provider_text(
    provider_text,
    base_row,
    excerpt_chars=excerpt_chars,
)
```

Add the CLI argument in `_args` after `--attempts`:

```python
    parser.add_argument(
        "--excerpt-chars",
        type=_positive_int,
        default=EXCERPT_CHARS,
    )
```

Pass it from `main` into `_run_matrix`:

```python
        excerpt_chars=args.excerpt_chars,
```

Update every existing test call to `_run_matrix(...)` to include:

```python
        excerpt_chars=SPIKE.EXCERPT_CHARS,
```

- [ ] **Step 4: Run the Task 1 test set to verify GREEN**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5p_ollama_think_format_spike.py::test_args_default_excerpt_chars `
  mcp_server\tests\test_lm5p_ollama_think_format_spike.py::test_args_custom_excerpt_chars `
  mcp_server\tests\test_lm5p_ollama_think_format_spike.py::test_args_invalid_excerpt_chars_fails_during_parse `
  mcp_server\tests\test_lm5p_ollama_think_format_spike.py::test_excerpt_uses_configured_limit `
  mcp_server\tests\test_lm5p_ollama_think_format_spike.py::test_classifies_provider_text_uses_configured_excerpt_chars `
  -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 1**

```powershell
cd C:\UDEV\Rook
git add scripts\lm5p_ollama_think_format_spike.py mcp_server\tests\test_lm5p_ollama_think_format_spike.py
git commit -m "test(lm5q): parameterize spike excerpts"
```

---

## Task 2: Add Pure Summary Aggregation Helpers

**Files:**
- Modify: `scripts/lm5p_ollama_think_format_spike.py`
- Modify: `mcp_server/tests/test_lm5p_ollama_think_format_spike.py`

- [ ] **Step 1: Write failing tests for grouped summary counts**

Add these helper functions near the middle of `mcp_server/tests/test_lm5p_ollama_think_format_spike.py`, before the `_run_matrix` tests:

```python
def _summary_row(
    *,
    model: str = "gemma4:12b-it-qat",
    scenario: str = "evidence_absent_like",
    mode: str = "format_default",
    provider_status: str = "ok",
    lm5g_loadable: bool = True,
    response_kind: str | None = "action_request",
    thinking_present: bool = True,
    thinking_sha256: str | None = "think-a",
    thinking_chars: int = 100,
    message_content_sha256: str | None = "content-a",
    failure_reason: str | None = None,
) -> dict:
    return {
        "model": model,
        "scenario": scenario,
        "mode": mode,
        "provider_status": provider_status,
        "lm5g_loadable": lm5g_loadable,
        "response_kind": response_kind,
        "thinking_present": thinking_present,
        "thinking_sha256": thinking_sha256,
        "thinking_chars": thinking_chars,
        "message_content_sha256": message_content_sha256,
        "failure_reason": failure_reason,
    }
```

Add this test:

```python
def test_build_summary_groups_rows_by_model_scenario_mode() -> None:
    rows = [
        _summary_row(
            mode="format_default",
            response_kind="action_request",
            thinking_sha256="think-a",
            message_content_sha256="content-a",
        ),
        _summary_row(
            mode="format_default",
            provider_status="error",
            lm5g_loadable=False,
            response_kind=None,
            thinking_present=False,
            thinking_sha256=None,
            message_content_sha256=None,
            failure_reason="provider_error:TimeoutError",
        ),
        _summary_row(
            mode="free_think_true",
            lm5g_loadable=False,
            response_kind="clarification_request",
            thinking_sha256="think-b",
            message_content_sha256="content-b",
            failure_reason="lm5g_load_failed:ValueError",
        ),
    ]

    summary = SPIKE._build_summary(
        run_id="lm5p-demo",
        git_commit="abc1234",
        models=["gemma4:12b-it-qat"],
        scenarios=["evidence_absent_like"],
        modes=["free_think_true", "format_default"],
        attempts_per_cell=5,
        rows=rows,
    )

    assert summary["run_id"] == "lm5p-demo"
    assert summary["git_commit"] == "abc1234"
    assert summary["models"] == ["gemma4:12b-it-qat"]
    assert summary["scenarios"] == ["evidence_absent_like"]
    assert summary["modes"] == ["free_think_true", "format_default"]
    assert summary["attempts_per_cell"] == 5
    assert summary["groups"] == [
        {
            "model": "gemma4:12b-it-qat",
            "scenario": "evidence_absent_like",
            "mode": "free_think_true",
            "attempts": 1,
            "provider_errors": 0,
            "lm5g_loadable_count": 0,
            "response_kind_counts": {"clarification_request": 1},
            "thinking_present_count": 1,
            "unique_thinking_hash_count": 1,
            "unique_content_hash_count": 1,
            "failure_reason_counts": {"lm5g_load_failed:ValueError": 1},
        },
        {
            "model": "gemma4:12b-it-qat",
            "scenario": "evidence_absent_like",
            "mode": "format_default",
            "attempts": 2,
            "provider_errors": 1,
            "lm5g_loadable_count": 1,
            "response_kind_counts": {"action_request": 1},
            "thinking_present_count": 1,
            "unique_thinking_hash_count": 1,
            "unique_content_hash_count": 1,
            "failure_reason_counts": {"provider_error:TimeoutError": 1},
        },
    ]
```

- [ ] **Step 2: Write failing tests for exact `thinking_hash_groups`**

Add this test after the grouped summary test:

```python
def test_build_summary_groups_exact_thinking_hashes_across_modes() -> None:
    rows = [
        _summary_row(
            mode="free_think_true",
            lm5g_loadable=False,
            response_kind="clarification_request",
            thinking_sha256="shared-think",
            thinking_chars=3361,
            failure_reason="lm5g_load_failed:ValueError",
        ),
        _summary_row(
            mode="format_default",
            lm5g_loadable=True,
            response_kind="action_request",
            thinking_sha256="shared-think",
            thinking_chars=3361,
            failure_reason=None,
        ),
        _summary_row(
            mode="format_think_true",
            lm5g_loadable=True,
            response_kind="action_request",
            thinking_sha256="shared-think",
            thinking_chars=3361,
            failure_reason=None,
        ),
        _summary_row(
            mode="format_think_false",
            lm5g_loadable=True,
            response_kind="clarification_request",
            thinking_present=False,
            thinking_sha256=None,
            thinking_chars=0,
            failure_reason=None,
        ),
    ]

    summary = SPIKE._build_summary(
        run_id="lm5p-demo",
        git_commit="abc1234",
        models=["gemma4:12b-it-qat"],
        scenarios=["evidence_absent_like"],
        modes=[
            "free_think_true",
            "format_default",
            "format_think_true",
            "format_think_false",
        ],
        attempts_per_cell=5,
        rows=rows,
    )

    assert summary["thinking_hash_groups"] == [
        {
            "model": "gemma4:12b-it-qat",
            "scenario": "evidence_absent_like",
            "thinking_sha256": "shared-think",
            "thinking_chars": 3361,
            "attempts": 3,
            "modes": [
                "free_think_true",
                "format_default",
                "format_think_true",
            ],
            "response_kind_counts": {
                "action_request": 2,
                "clarification_request": 1,
            },
            "lm5g_loadable_count": 2,
            "failure_reason_counts": {"lm5g_load_failed:ValueError": 1},
        }
    ]
```

This test proves null `thinking_sha256` rows are excluded and mode ordering follows the requested run order.

- [ ] **Step 3: Run the new summary tests to verify RED**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5p_ollama_think_format_spike.py::test_build_summary_groups_rows_by_model_scenario_mode `
  mcp_server\tests\test_lm5p_ollama_think_format_spike.py::test_build_summary_groups_exact_thinking_hashes_across_modes `
  -q
```

Expected: failures because `_build_summary` does not exist.

- [ ] **Step 4: Implement pure summary helpers**

In `scripts/lm5p_ollama_think_format_spike.py`, add the import:

```python
from collections import Counter, defaultdict
```

Keep the existing:

```python
from collections.abc import Mapping
```

Add these helpers after `_build_manifest`:

```python
def _count_strings(rows: list[Mapping[str, Any]], key: str) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        value = row.get(key)
        if isinstance(value, str) and value:
            counts[value] += 1
    return dict(sorted(counts.items()))


def _mode_order_index(modes: list[str]) -> dict[str, int]:
    return {mode: index for index, mode in enumerate(modes)}


def _sort_modes(values: set[str], mode_order: Mapping[str, int]) -> list[str]:
    return sorted(values, key=lambda value: (mode_order.get(value, len(mode_order)), value))
```

Then add `_build_summary`:

```python
def _build_summary(
    *,
    run_id: str,
    git_commit: str,
    models: list[str],
    scenarios: list[str],
    modes: list[str],
    attempts_per_cell: int,
    rows: list[Mapping[str, Any]],
) -> dict[str, Any]:
    mode_order = _mode_order_index(modes)

    grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    thinking_grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        model = row.get("model")
        scenario = row.get("scenario")
        mode = row.get("mode")
        if isinstance(model, str) and isinstance(scenario, str) and isinstance(mode, str):
            grouped[(model, scenario, mode)].append(row)

        thinking_sha256 = row.get("thinking_sha256")
        if (
            isinstance(model, str)
            and isinstance(scenario, str)
            and isinstance(thinking_sha256, str)
            and thinking_sha256
        ):
            thinking_grouped[(model, scenario, thinking_sha256)].append(row)

    groups: list[dict[str, Any]] = []
    for (model, scenario, mode), group_rows in sorted(
        grouped.items(),
        key=lambda item: (
            item[0][0],
            item[0][1],
            mode_order.get(item[0][2], len(mode_order)),
            item[0][2],
        ),
    ):
        thinking_hashes = {
            row.get("thinking_sha256")
            for row in group_rows
            if isinstance(row.get("thinking_sha256"), str) and row.get("thinking_sha256")
        }
        content_hashes = {
            row.get("message_content_sha256")
            for row in group_rows
            if isinstance(row.get("message_content_sha256"), str)
            and row.get("message_content_sha256")
        }
        groups.append(
            {
                "model": model,
                "scenario": scenario,
                "mode": mode,
                "attempts": len(group_rows),
                "provider_errors": sum(
                    1 for row in group_rows if row.get("provider_status") != "ok"
                ),
                "lm5g_loadable_count": sum(
                    1 for row in group_rows if row.get("lm5g_loadable") is True
                ),
                "response_kind_counts": _count_strings(group_rows, "response_kind"),
                "thinking_present_count": sum(
                    1 for row in group_rows if row.get("thinking_present") is True
                ),
                "unique_thinking_hash_count": len(thinking_hashes),
                "unique_content_hash_count": len(content_hashes),
                "failure_reason_counts": _count_strings(group_rows, "failure_reason"),
            }
        )

    thinking_hash_groups: list[dict[str, Any]] = []
    for (model, scenario, thinking_sha256), group_rows in sorted(
        thinking_grouped.items(),
        key=lambda item: (item[0][0], item[0][1], item[0][2]),
    ):
        modes_seen = {
            row.get("mode")
            for row in group_rows
            if isinstance(row.get("mode"), str) and row.get("mode")
        }
        thinking_chars = 0
        for row in group_rows:
            value = row.get("thinking_chars")
            if isinstance(value, int) and not isinstance(value, bool):
                thinking_chars = value
                break

        thinking_hash_groups.append(
            {
                "model": model,
                "scenario": scenario,
                "thinking_sha256": thinking_sha256,
                "thinking_chars": thinking_chars,
                "attempts": len(group_rows),
                "modes": _sort_modes(modes_seen, mode_order),
                "response_kind_counts": _count_strings(group_rows, "response_kind"),
                "lm5g_loadable_count": sum(
                    1 for row in group_rows if row.get("lm5g_loadable") is True
                ),
                "failure_reason_counts": _count_strings(group_rows, "failure_reason"),
            }
        )

    return {
        "run_id": run_id,
        "git_commit": git_commit,
        "models": models,
        "scenarios": scenarios,
        "modes": modes,
        "attempts_per_cell": attempts_per_cell,
        "groups": groups,
        "thinking_hash_groups": thinking_hash_groups,
    }
```

- [ ] **Step 5: Run the Task 2 tests to verify GREEN**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5p_ollama_think_format_spike.py::test_build_summary_groups_rows_by_model_scenario_mode `
  mcp_server\tests\test_lm5p_ollama_think_format_spike.py::test_build_summary_groups_exact_thinking_hashes_across_modes `
  -q
```

Expected: both selected tests pass.

- [ ] **Step 6: Commit Task 2**

```powershell
cd C:\UDEV\Rook
git add scripts\lm5p_ollama_think_format_spike.py mcp_server\tests\test_lm5p_ollama_think_format_spike.py
git commit -m "feat(lm5q): aggregate spike summary counts"
```

---

## Task 3: Write `summary.json` From Matrix Runs

**Files:**
- Modify: `scripts/lm5p_ollama_think_format_spike.py`
- Modify: `mcp_server/tests/test_lm5p_ollama_think_format_spike.py`

- [ ] **Step 1: Extend the existing `_run_matrix` test to require `summary.json`**

In `test_run_matrix_writes_manifest_and_attempt_rows`, after the existing `rows` assertions, add:

```python
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["run_id"] == run_dir.name
    assert summary["git_commit"] == "abc1234"
    assert summary["models"] == ["gemma4:12b"]
    assert summary["scenarios"] == ["evidence_absent_like"]
    assert summary["modes"] == ["format_think_true"]
    assert summary["attempts_per_cell"] == 2
    assert summary["groups"] == [
        {
            "model": "gemma4:12b",
            "scenario": "evidence_absent_like",
            "mode": "format_think_true",
            "attempts": 2,
            "provider_errors": 0,
            "lm5g_loadable_count": 2,
            "response_kind_counts": {"observation": 2},
            "thinking_present_count": 0,
            "unique_thinking_hash_count": 0,
            "unique_content_hash_count": 1,
            "failure_reason_counts": {},
        }
    ]
    assert summary["thinking_hash_groups"] == []
```

- [ ] **Step 2: Add a test that summary-write failures propagate**

Add this test after `test_run_matrix_records_http_and_provider_failures`:

```python
def test_run_matrix_propagates_summary_write_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    provider_text = json.dumps({"message": {"content": "not json"}})
    original_write_json_file = SPIKE._write_json_file

    def fake_write_json_file(path: Path, payload: dict) -> None:
        if path.name == "summary.json":
            raise RuntimeError("summary write failed")
        original_write_json_file(path, payload)

    monkeypatch.setattr(SPIKE, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(SPIKE, "_git_short_sha", lambda: "abc1234")
    monkeypatch.setattr(SPIKE, "_ollama_version", lambda: "ollama version is 0.9.0")
    monkeypatch.setattr(
        SPIKE,
        "_model_metadata",
        lambda model: {
            "model": model,
            "model_id": None,
            "model_quantization": None,
            "ollama_show_status": "ok",
            "ollama_show_excerpt": "",
        },
    )
    monkeypatch.setattr(
        SPIKE,
        "_messages_for_scenario",
        lambda scenario: [{"role": "user", "content": scenario}],
    )
    monkeypatch.setattr(
        SPIKE,
        "_post_ollama_chat",
        lambda endpoint, body, timeout_s: provider_text,
    )
    monkeypatch.setattr(SPIKE, "_write_json_file", fake_write_json_file)

    with pytest.raises(RuntimeError, match="summary write failed"):
        SPIKE._run_matrix(
            models=["gemma4:12b"],
            scenarios=["evidence_absent_like"],
            modes=["free_think_true"],
            endpoint="http://fake.local/api/chat",
            temperature=0,
            attempts_per_cell=1,
            timeout_s=9,
            excerpt_chars=SPIKE.EXCERPT_CHARS,
        )
```

- [ ] **Step 3: Run the Task 3 tests to verify RED**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5p_ollama_think_format_spike.py::test_run_matrix_writes_manifest_and_attempt_rows `
  mcp_server\tests\test_lm5p_ollama_think_format_spike.py::test_run_matrix_propagates_summary_write_failure `
  -q
```

Expected: failures because `summary.json` and `_write_json_file` do not exist yet.

- [ ] **Step 4: Add a JSON writer helper**

In `scripts/lm5p_ollama_think_format_spike.py`, add this helper after `_post_ollama_chat`:

```python
def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
```

Replace the manifest write block:

```python
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
```

with:

```python
    _write_json_file(run_dir / "manifest.json", manifest)
```

- [ ] **Step 5: Collect rows and write `summary.json` after attempts**

Inside `_run_matrix`, before opening `attempts.jsonl`, add:

```python
    rows: list[dict[str, Any]] = []
```

Inside the attempt loop, immediately before writing the JSONL line, append:

```python
                        rows.append(row)
```

After the `with attempts_path.open(...)` block ends, before printing, add:

```python
    summary = _build_summary(
        run_id=run_dir.name,
        git_commit=git_commit,
        models=models,
        scenarios=scenarios,
        modes=modes,
        attempts_per_cell=attempts_per_cell,
        rows=rows,
    )
    _write_json_file(run_dir / "summary.json", summary)
```

Do not catch exceptions from `_write_json_file`; a summary write failure must fail the script.

- [ ] **Step 6: Run the Task 3 tests to verify GREEN**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5p_ollama_think_format_spike.py::test_run_matrix_writes_manifest_and_attempt_rows `
  mcp_server\tests\test_lm5p_ollama_think_format_spike.py::test_run_matrix_propagates_summary_write_failure `
  -q
```

Expected: both selected tests pass.

- [ ] **Step 7: Commit Task 3**

```powershell
cd C:\UDEV\Rook
git add scripts\lm5p_ollama_think_format_spike.py mcp_server\tests\test_lm5p_ollama_think_format_spike.py
git commit -m "feat(lm5q): write local spike summary"
```

---

## Task 4: Pin Canonical LM5Q Command and Boundary Guards

**Files:**
- Modify: `mcp_server/tests/test_lm5p_ollama_think_format_spike.py`
- Modify: `scripts/lm5p_ollama_think_format_spike.py` only if test failures require a tiny help-text or parser fix

- [ ] **Step 1: Add parser coverage for the canonical LM5Q command shape**

Add this test near the existing argument tests:

```python
def test_args_accept_lm5q_canonical_matrix_options() -> None:
    args = SPIKE._args(
        [
            "--model",
            "gemma4:12b-it-qat",
            "--scenario",
            "evidence_absent_like",
            "--scenario",
            "evidence_present_like",
            "--mode",
            "free_think_true",
            "--mode",
            "format_default",
            "--mode",
            "format_think_true",
            "--mode",
            "format_think_false",
            "--attempts",
            "5",
            "--excerpt-chars",
            "1200",
        ]
    )

    assert args.models == ["gemma4:12b-it-qat"]
    assert args.scenarios == ["evidence_absent_like", "evidence_present_like"]
    assert args.modes == [
        "free_think_true",
        "format_default",
        "format_think_true",
        "format_think_false",
    ]
    assert args.attempts == 5
    assert args.excerpt_chars == 1200
```

- [ ] **Step 2: Update the help-text test if needed**

If `test_script_help_runs_from_repo_root` still asserts the old text:

```python
assert "LM5P Ollama think/format diagnostic spike scaffold." in result.stdout
```

change it to:

```python
assert "LM5P Ollama think/format diagnostic spike." in result.stdout
```

Then update the parser description in `scripts/lm5p_ollama_think_format_spike.py` from:

```python
description="LM5P Ollama think/format diagnostic spike scaffold."
```

to:

```python
description="LM5P Ollama think/format diagnostic spike."
```

This removes the stale scaffold wording without changing behavior.

- [ ] **Step 3: Run targeted parser/static tests**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5p_ollama_think_format_spike.py::test_args_accept_lm5q_canonical_matrix_options `
  mcp_server\tests\test_lm5p_ollama_think_format_spike.py::test_script_help_runs_from_repo_root `
  mcp_server\tests\test_lm5p_ollama_think_format_spike.py::test_script_static_import_and_call_guards `
  -q
```

Expected: selected tests pass.

- [ ] **Step 4: Run a static diff scan for forbidden scope drift**

Run:

```powershell
cd C:\UDEV\Rook
git diff --name-only main..HEAD
```

Expected changed paths are limited to:

```text
docs/superpowers/specs/2026-07-03-lm5q-structured-union-disposition-stability-design.md
docs/superpowers/plans/2026-07-03-lm5q-structured-union-disposition-stability.md
scripts/lm5p_ollama_think_format_spike.py
mcp_server/tests/test_lm5p_ollama_think_format_spike.py
```

Run:

```powershell
cd C:\UDEV\Rook
git diff --name-only main..HEAD -- mcp_server\src
```

Expected: no output.

Run:

```powershell
cd C:\UDEV\Rook
git diff -U0 main..HEAD -- scripts\lm5p_ollama_think_format_spike.py mcp_server\tests\test_lm5p_ollama_think_format_spike.py |
  rg "scripts/lm5k_worker_probe.py|parser leniency|schema ordering|two-pass|llama\\.cpp|LiteLLMWorkerTransport"
```

Expected: no output. The existing AST guard remains the authoritative check for forbidden imports and calls; this quick scan only catches broad LM5Q scope drift.

- [ ] **Step 5: Commit Task 4**

```powershell
cd C:\UDEV\Rook
git add scripts\lm5p_ollama_think_format_spike.py mcp_server\tests\test_lm5p_ollama_think_format_spike.py
git commit -m "test(lm5q): pin canonical spike options"
```

---

## Task 5: Deterministic Gates

**Files:**
- No intended edits

- [ ] **Step 1: Run LM5Q targeted tests**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5p_ollama_think_format_spike.py `
  -q
```

Expected: all tests in the file pass.

- [ ] **Step 2: Run nearby probe/transport gate**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5p_ollama_think_format_spike.py `
  mcp_server\tests\test_local_worker_model_transport.py `
  mcp_server\tests\test_lm5k_worker_probe.py `
  -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Run Python 3.10 compile gate**

Run:

```powershell
cd C:\UDEV\Rook
py -3.10 -m py_compile `
  scripts\lm5p_ollama_think_format_spike.py `
  mcp_server\tests\test_lm5p_ollama_think_format_spike.py
```

Expected: exits 0 with no output.

- [ ] **Step 4: Run whitespace and scope checks**

Run:

```powershell
cd C:\UDEV\Rook
git diff --check main..HEAD
git diff --name-only main..HEAD
git diff --name-only main..HEAD -- mcp_server\src
git status --short --branch
```

Expected:

```text
git diff --check: no output
diff paths: only LM5Q spec/plan/script/test
mcp_server/src diff: no output
status: clean except unrelated untracked items such as .understand-anything/
```

- [ ] **Step 5: Commit only if a gate fix was required**

If a gate required a source/test fix:

```powershell
cd C:\UDEV\Rook
git add scripts\lm5p_ollama_think_format_spike.py mcp_server\tests\test_lm5p_ollama_think_format_spike.py
git commit -m "test(lm5q): complete deterministic gates"
```

If no gate fix was required, make no Task 5 commit.

---

## Task 6: Manual Canonical LM5Q Evidence Run

**Files:**
- No committed edits
- Local ignored artifacts under `probe_runs/`

- [ ] **Step 1: Confirm clean tracked state before live run**

Run:

```powershell
cd C:\UDEV\Rook
git status --short --branch
ollama --version
ollama show gemma4:12b-it-qat
```

Expected:

```text
tracked state clean
Ollama responds
gemma4:12b-it-qat metadata is available
```

If `ollama show gemma4:12b-it-qat` fails, stop and report the exact failure. Do not substitute another model for the canonical LM5Q run.

- [ ] **Step 2: Run the canonical 40-row matrix**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe scripts\lm5p_ollama_think_format_spike.py `
  --model "gemma4:12b-it-qat" `
  --scenario evidence_absent_like `
  --scenario evidence_present_like `
  --mode free_think_true `
  --mode format_default `
  --mode format_think_true `
  --mode format_think_false `
  --attempts 5 `
  --excerpt-chars 1200
```

Expected:

```text
LM5P matrix complete: run_dir=... ok=... error=... loadable=...
```

Do not commit anything under `probe_runs/`.

- [ ] **Step 3: Inspect the local summary**

Replace `<RUN_DIR>` with the printed run directory:

```powershell
cd C:\UDEV\Rook
Get-Content <RUN_DIR>\summary.json
```

Report:

```text
run directory
git commit
Ollama version
row count, inferred from attempts.jsonl line count
summary groups for evidence_absent_like and evidence_present_like
thinking_hash_groups with more than one response_kind
failure_reason_counts
```

Use this PowerShell line count:

```powershell
(Get-Content <RUN_DIR>\attempts.jsonl).Count
```

Expected canonical row count:

```text
40
```

- [ ] **Step 4: Pull bounded excerpts for representative rows**

Use a small local Python snippet to inspect only local ignored evidence:

```powershell
cd C:\UDEV\Rook
@'
import json
from pathlib import Path

run_dir = Path(r"<RUN_DIR>")
rows = [json.loads(line) for line in (run_dir / "attempts.jsonl").read_text(encoding="utf-8").splitlines()]

for scenario in ("evidence_absent_like", "evidence_present_like"):
    print(f"## {scenario}")
    for mode in ("free_think_true", "format_default", "format_think_true", "format_think_false"):
        picked = None
        for row in rows:
            if row["scenario"] == scenario and row["mode"] == mode:
                picked = row
                break
        if picked is None:
            print(f"{mode}: missing")
            continue
        print(f"{mode}: kind={picked['response_kind']} loadable={picked['lm5g_loadable']} failure={picked['failure_reason']}")
        print((picked.get("message_content_excerpt") or "")[:1200])
        print()
'@ | .\mcp_server\.venv\Scripts\python.exe -
```

Report bounded excerpts for:

```text
evidence_absent_like action_request rows, if present
evidence_present_like action_request rows, if present
one free_think_true row for contrast
```

- [ ] **Step 5: Confirm ignored artifacts remain uncommitted**

Run:

```powershell
cd C:\UDEV\Rook
git status --short --ignored
git diff --name-only --cached
```

Expected:

```text
probe_runs/ may appear as ignored
git diff --name-only --cached does not include probe_runs files
```

No curated evidence doc update belongs in LM5Q implementation. Wait for review of the local evidence results before writing any summary doc.
