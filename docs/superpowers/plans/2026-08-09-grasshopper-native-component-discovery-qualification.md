# Grasshopper Native Component Discovery Task 0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Qualify the installed Grasshopper component server's native discovery, eligibility, ordering, third-party visibility, and provenance fields without changing production code or mutating a Rhino or Grasshopper document.

**Architecture:** Build one disposable operator probe outside the repository, verify it inertly, and stop for pre-contact review. After fresh target corroboration and separate authorization, send the exact reviewed probe once through the existing native `/execute` route so it runs inside the loaded Rhino/Grasshopper process and writes one raw JSON artifact. Convert that evidence into one committed Task 0 report and stop for independent policy review; do not amend production code or write the production implementation plan.

**Tech Stack:** Windows PowerShell 7, Rhino 8 CPython/Python.NET, installed `Grasshopper.dll`, existing RookNative `/execute`, Python standard library, Markdown, Git.

## Global Constraints

- Baseline is exact `origin/main` commit `4bf6fad8418d90590f3ecb4e7cc7921d7894deae`. The approved design dependency is exact commit `d840f70d3aa40ab77374ef72cd6e152557c4effa` on branch `codex/grasshopper-component-discovery-coherence-design`.
- This plan covers Task 0 qualification only. It does not authorize production implementation or a production implementation plan.
- Make no production or repository test-code change.
- Add no product endpoint, registry, persistent catalog, fixture authority, benchmark framework, or reusable probe module.
- Contact no model, provider, Ollama, Prime Agent, Worker, or ChatRunner.
- Make no Rhino geometry or Grasshopper canvas mutation.
- Use exactly one externally dispatched native `/execute` request after separate authorization; do not retry or rerun.
- `/execute` is a mutation-capable native route and opens its ordinary undo scope. This authorization is therefore specific to the reviewed source. Qualification success additionally requires the route to report zero created Rhino objects and the probe to report unchanged non-null Grasshopper canvas counts.
- The probe may enumerate `ObjectProxies`, call `FindObjects`, `FindObjectByName`, `AliasTargets`, `CompareProxies`, `FindAssembly`, and `FindAssemblyByObject` only.
- The probe must never call `CreateInstance`, `EmitObject`, a document-object mutation API, solution expiration, or a Rook mutation tool.
- Use the exact seven query strings: `Series`, `Range`, `Multiplication`, `Addition`, `Construct Point`, `Add`, and `Point`.
- Pass every query to `FindObjects` as one unchanged string in a one-element array.
- For each query call `FindObjects(query, ObjectProxies.Count)` exactly three times. The total native `FindObjects` budget is exactly 21.
- Call `FindObjectByName` and `AliasTargets` exactly once per fixed query. Each budget is exactly seven.
- Enumerate live proxies once. Cache `FindAssembly` by `LibraryGuid`.
- Do not instantiate components. Metadata-side provenance uses `FindAssemblyByObject(Guid)` only for bounded selected specimens.
- Evaluate the legacy predicate over every live proxy, never the current truncated endpoint response. Label the comparison complete only when every property required by that evaluation was read successfully.
- Preserve the current category predicate exactly: case-insensitive substring across `Category` or `SubCategory`.
- Treat native scores as observations. Do not infer a semantic match reason or stable cross-version scale.
- Select third-party specimens from the live catalog. Do not create a core/plugin allowlist or durable product fixture.
- Preserve host provenance as exactly `core`, `third_party`, or `unknown`. Select a third-party specimen only when `IsCoreLibrary == false` was read successfully; missing or failed provenance remains `unknown` evidence.
- Optional proxy/plugin provenance failures are per-proxy or per-GUID observations. Only component-server absence, the reflected/native search contract, target identity, or evidence writing may abort the complete capture.
- Before authorization, prove the installed reflected four-parameter `FindObjects` signature and pin the only accepted Python.NET out/ref projection as `(count, proxies, weights)` through inert tests. The authorized Task 0 call—not the synthetic tuple test—qualifies whether the live binding actually produces that shape and fails closed on disagreement.
- Every legacy-predicate input retains `value`, `missing`, or `error` state. Any incomplete fixed-query or category comparison forces the report recommendation to `qualification incomplete`.
- Keep raw evidence outside Git. Commit only the bounded Markdown report produced from it.
- Stop after the report commit for mandatory independent review. Do not choose eligibility or provenance policy autonomously.
- Retain the two existing knowledge-test failures separately; do not modify knowledge code or tests.
- Later production-amendment reminders remain deferred: add invalid-GUID and metadata-instantiation-failure identity outcomes; define Opus credential variable names and generation settings, with a URL containing no embedded credentials.

## File map

### Repository

- Create now: `docs/superpowers/plans/2026-08-09-grasshopper-native-component-discovery-qualification.md` — this Task 0-only plan.
- Create during authorized execution: `docs/superpowers/reports/2026-08-08-grasshopper-native-component-discovery-qualification.md` — the only committed Task 0 evidence artifact.
- Preserve unchanged: `docs/superpowers/specs/2026-08-08-grasshopper-component-discovery-coherence-design.md` until independent Task 0 review supplies the production decisions.

### Disposable operator lane

Use exactly:

```text
C:/Users/bring/AppData/Local/Temp/rook-gh-native-discovery-task0/
```

Create:

- `probe.py` — in-process read-only `GH_ComponentServer` qualification.
- `run.ps1` — one-shot target custody and one-request launcher.
- `test_probe.py` — inert tests for predicates, fixed budget, hashes, and mutation exclusions.
- `target.json` — fresh PID, native port, and document serial; create only after pre-contact approval.
- `manifest.json` — exact SHA-256 values for `probe.py`, `run.ps1`, `test_probe.py`, and later `target.json`.

The live run may create exactly:

- `native-discovery.json` — raw in-process evidence.
- `invoke-result.json` — exact native HTTP status/body retained after the one request.
- `stderr.txt` — bounded launcher stderr, possibly empty.

The presence of any live evidence before authorization causes refusal. Never overwrite,
truncate, repair, or reuse a consumed operator lane.

---

### Task 1: Construct and inertly qualify the disposable probe

**Files:**
- Create outside Git: `C:/Users/bring/AppData/Local/Temp/rook-gh-native-discovery-task0/probe.py`
- Create outside Git: `C:/Users/bring/AppData/Local/Temp/rook-gh-native-discovery-task0/run.ps1`
- Create outside Git: `C:/Users/bring/AppData/Local/Temp/rook-gh-native-discovery-task0/test_probe.py`
- Create outside Git: `C:/Users/bring/AppData/Local/Temp/rook-gh-native-discovery-task0/manifest.json`
- Test: disposable `test_probe.py`

**Interfaces:**
- Consumes: installed Rhino/Grasshopper APIs only when `probe.py` runs inside Rhino; deployed `rook.bridge.discover_instances()` only when `run.ps1` performs target preflight.
- Produces: a hash-frozen operator lane whose source can be independently reviewed before any live contact.

- [ ] **Step 1: Verify lane and repository custody**

Run:

```powershell
$Lane = 'C:/UDEV/Rook/.worktrees/mcp-structured-tool-results-merged'
$Root = 'C:/Users/bring/AppData/Local/Temp/rook-gh-native-discovery-task0'

Set-Location $Lane
git rev-parse HEAD
git status --short

if (Test-Path -LiteralPath $Root) {
    throw "Disposable Task 0 lane already exists: $Root"
}
New-Item -ItemType Directory -Path $Root | Out-Null
```

Expected:

```text
HEAD is the reviewed design branch head.
git status --short is empty.
The disposable directory is created once.
```

- [ ] **Step 2: Create the exact read-only probe**

Use `apply_patch` to create `probe.py` with this complete source. Do not use a shell
redirection or here-string to write it.

```python
from __future__ import annotations

import functools
import hashlib
import json
import os
import time
from datetime import datetime, timezone


OUTPUT_PATH = (
    "C:/Users/bring/AppData/Local/Temp/rook-gh-native-discovery-task0/"
    "native-discovery.json"
)
QUERIES = (
    "Series",
    "Range",
    "Multiplication",
    "Addition",
    "Construct Point",
    "Add",
    "Point",
)
NATIVE_RUNS_PER_QUERY = 3
PUBLIC_LIMIT = 50
EXPECTED_FIND_OBJECTS_SIGNATURE = (
    "Int32 FindObjects(System.String[], Int32, "
    "Grasshopper.Kernel.IGH_ObjectProxy[] ByRef, Double[] ByRef)"
)


def _text(value):
    if value is None:
        return None
    try:
        return str(value)
    except Exception:
        return None


def _lower(value):
    return (_text(value) or "").lower()


def _category_matches(fact, category):
    if not category:
        return True
    needle = category.lower()
    return needle in _lower(fact.get("category")) or needle in _lower(
        fact.get("subcategory")
    )


def _legacy_matches(fact, query, exact=False, category=None):
    evaluation = _legacy_evaluation(fact, query, exact, category)
    return evaluation["matches"] if evaluation["complete"] else None


def _legacy_property_state(fact, field):
    explicit = (fact.get("legacy_properties") or {}).get(field)
    if explicit is not None:
        return explicit
    value = fact.get(field)
    return {
        "status": "missing" if value is None else "value",
        "value": value,
        "error": None,
    }


def _legacy_evaluation(fact, query, exact=False, category=None):
    obsolete = _legacy_property_state(fact, "obsolete")
    if obsolete["status"] != "value":
        return {"complete": False, "matches": None, "incomplete_fields": ["obsolete"]}
    if obsolete["value"]:
        return {"complete": True, "matches": False, "incomplete_fields": []}

    required = ["name"] if exact else ["name", "nickname", "description"]
    if category:
        required.extend(("category", "subcategory"))
    states = {field: _legacy_property_state(fact, field) for field in required}
    incomplete = sorted(
        field for field, state in states.items() if state["status"] != "value"
    )
    if incomplete:
        return {"complete": False, "matches": None, "incomplete_fields": incomplete}

    if category and not _category_matches(fact, category):
        return {"complete": True, "matches": False, "incomplete_fields": []}
    needle = query.lower()
    if exact:
        matches = _lower(fact.get("name")) == needle
    else:
        matches = any(
            needle in _lower(fact.get(field))
            for field in ("name", "nickname", "description")
        )
    return {"complete": True, "matches": matches, "incomplete_fields": []}


def _legacy_set_observation(facts, query, exact=False, category=None):
    matches = []
    incomplete = []
    for fact in facts:
        evaluation = _legacy_evaluation(fact, query, exact, category)
        if not evaluation["complete"]:
            incomplete.append(
                {
                    "guid": fact["guid"],
                    "fields": evaluation["incomplete_fields"],
                }
            )
        elif evaluation["matches"]:
            matches.append(fact["guid"])
    return {
        "complete": not incomplete,
        "guids": sorted(matches),
        "incomplete": incomplete,
    }


def _duplicate_exact_groups(facts):
    groups = {}
    for fact in facts:
        if fact.get("obsolete") is not False:
            continue
        groups.setdefault(_lower(fact.get("name")), []).append(fact["guid"])
    return {
        name: sorted(guids)
        for name, guids in sorted(groups.items())
        if name and len(guids) > 1
    }


def _choose_category_case(query_rows):
    for row in query_rows:
        for candidate in row["candidates"][PUBLIC_LIMIT:]:
            for field in ("category", "subcategory"):
                value = candidate.get(field)
                if value:
                    matches = [
                        item
                        for item in row["candidates"]
                        if _category_matches(item, value)
                    ]
                    if matches:
                        return {
                            "query": row["query"],
                            "category": value,
                            "first_displaced_rank": candidate["native_rank"],
                            "native_guids": [item["guid"] for item in matches],
                        }
    return None


def _error_observation(error, field=None):
    return {
        "field": field,
        "error_type": type(error).__name__,
        "error": _text(error),
    }


def _safe_get(obj, name, errors=None):
    try:
        return getattr(obj, name)
    except Exception as error:
        if errors is not None:
            errors.append(_error_observation(error, name))
        return None


def _read_property(obj, name, coerce):
    if obj is None:
        return None, {"status": "missing", "value": None, "error": None}
    try:
        raw = getattr(obj, name)
    except Exception as error:
        return None, {
            "status": "error",
            "value": None,
            "error": _error_observation(error, name),
        }
    if raw is None:
        return None, {"status": "missing", "value": None, "error": None}
    try:
        value = coerce(raw)
    except Exception as error:
        return raw, {
            "status": "error",
            "value": None,
            "error": _error_observation(error, name + ".coerce"),
        }
    return raw, {"status": "value", "value": value, "error": None}


def _assembly_info(info):
    if info is None:
        return None
    errors = []
    assembly = _safe_get(info, "Assembly", errors)
    assembly_name = None
    assembly_full_name = None
    assembly_location = None
    if assembly is not None:
        try:
            name = assembly.GetName()
            assembly_name = _text(name.Name)
            assembly_full_name = _text(assembly.FullName)
            assembly_location = _text(assembly.Location)
        except Exception as error:
            errors.append(_error_observation(error, "Assembly.GetName"))
    is_core = _safe_get(info, "IsCoreLibrary", errors)
    classification = (
        "unknown"
        if is_core is None
        else ("core" if bool(is_core) else "third_party")
    )
    return {
        "id": _text(_safe_get(info, "Id", errors)),
        "name": _text(_safe_get(info, "Name", errors)),
        "version": _text(_safe_get(info, "Version", errors)),
        "assembly_name": _text(_safe_get(info, "AssemblyName", errors))
        or assembly_name,
        "assembly_version": _text(_safe_get(info, "AssemblyVersion", errors)),
        "assembly_full_name": assembly_full_name,
        "is_core_library": None if is_core is None else bool(is_core),
        "classification": classification,
        "location": _text(_safe_get(info, "Location", errors)) or assembly_location,
        "loading_mechanism": _text(_safe_get(info, "LoadingMechanism", errors)),
        "property_errors": errors,
    }


def _find_assembly_observation(server, library_guid):
    if library_guid is None:
        return {"status": "missing_library_guid", "info": None, "error": None}
    try:
        info = server.FindAssembly(library_guid)
    except Exception as error:
        return {
            "status": "error",
            "info": None,
            "error": _error_observation(error, "FindAssembly"),
        }
    if info is None:
        return {"status": "not_found", "info": None, "error": None}
    return {"status": "found", "info": _assembly_info(info), "error": None}


def _find_assembly_by_object_observation(server, guid_text, parse_guid):
    try:
        info = server.FindAssemblyByObject(parse_guid(guid_text))
    except Exception as error:
        return {
            "guid": guid_text,
            "status": "error",
            "assembly_by_object": None,
            "error": _error_observation(error, "FindAssemblyByObject"),
        }
    return {
        "guid": guid_text,
        "status": "not_found" if info is None else "found",
        "assembly_by_object": _assembly_info(info),
        "error": None,
    }


def _proxy_fact(proxy, server, assembly_cache):
    errors = []
    desc, desc_state = _read_property(proxy, "Desc", lambda _value: True)
    if desc_state["error"] is not None:
        errors.append(desc_state["error"])
    _, name_state = _read_property(desc, "Name", str)
    _, nickname_state = _read_property(desc, "NickName", str)
    _, description_state = _read_property(desc, "Description", str)
    _, category_state = _read_property(desc, "Category", str)
    _, subcategory_state = _read_property(desc, "SubCategory", str)
    _, obsolete_state = _read_property(proxy, "Obsolete", bool)
    legacy_properties = {
        "name": name_state,
        "nickname": nickname_state,
        "description": description_state,
        "category": category_state,
        "subcategory": subcategory_state,
        "obsolete": obsolete_state,
    }
    for state in legacy_properties.values():
        if state["error"] is not None:
            errors.append(state["error"])
    raw_library_guid = _safe_get(proxy, "LibraryGuid", errors)
    library_guid = _text(raw_library_guid)
    if library_guid is None:
        assembly_observation = _find_assembly_observation(server, None)
    else:
        if library_guid not in assembly_cache:
            assembly_cache[library_guid] = _find_assembly_observation(
                server, raw_library_guid
            )
        assembly_observation = assembly_cache[library_guid]
    proxy_type = _safe_get(proxy, "Type", errors)
    type_assembly = (
        _safe_get(proxy_type, "Assembly", errors) if proxy_type else None
    )
    type_name = None
    type_version = None
    type_full_name = None
    type_location = None
    if type_assembly is not None:
        try:
            name = type_assembly.GetName()
            type_name = _text(name.Name)
            type_version = _text(name.Version)
            type_full_name = _text(type_assembly.FullName)
            type_location = _text(type_assembly.Location)
        except Exception as error:
            errors.append(_error_observation(error, "Type.Assembly.GetName"))
    keywords_value = _safe_get(desc, "Keywords", errors) if desc else None
    if keywords_value is None:
        keywords = []
    else:
        try:
            keywords = [_text(item) for item in keywords_value]
        except Exception as error:
            errors.append(_error_observation(error, "Desc.Keywords.iteration"))
            keywords = []
    exposure = _safe_get(proxy, "Exposure", errors)
    try:
        exposure_value = None if exposure is None else int(exposure)
    except Exception as error:
        errors.append(_error_observation(error, "Exposure.int"))
        exposure_value = None
    return {
        "guid": _text(proxy.Guid),
        "name": name_state["value"],
        "nickname": nickname_state["value"],
        "description": description_state["value"],
        "category": category_state["value"],
        "subcategory": subcategory_state["value"],
        "keywords": keywords,
        "obsolete": obsolete_state["value"],
        "legacy_properties": legacy_properties,
        "exposure": exposure_value,
        "exposure_text": _text(exposure),
        "kind": _text(_safe_get(proxy, "Kind", errors)),
        "sdk_compliant": bool(_safe_get(proxy, "SDKCompliant", errors)),
        "library_guid": library_guid,
        "proxy_location": _text(_safe_get(proxy, "Location", errors)),
        "assembly_lookup": assembly_observation,
        "type_assembly_name": type_name,
        "type_assembly_version": type_version,
        "type_assembly_full_name": type_full_name,
        "type_assembly_location": type_location,
        "property_errors": errors,
    }


def _coerce_find_objects_result(returned):
    if not isinstance(returned, tuple) or len(returned) != 3:
        raise RuntimeError(
            "unexpected FindObjects Python.NET out/ref projection; expected "
            "(count, proxies, weights)"
        )
    count, proxies, weights = returned
    proxies = list(proxies)
    weights = [float(weight) for weight in weights]
    if int(count) != len(proxies) or len(proxies) != len(weights):
        raise RuntimeError("inconsistent FindObjects result lengths")
    return proxies, weights


def _find_objects(server, query, maximum_results, Array, String):
    started = time.perf_counter()
    returned = server.FindObjects(Array[String]([query]), maximum_results)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    proxies, weights = _coerce_find_objects_result(returned)
    return proxies, weights, elapsed_ms


def _find_object_by_name_observation(server, query):
    try:
        proxy = server.FindObjectByName(query, False, True)
    except Exception as error:
        return {
            "status": "error",
            "guid": None,
            "error": _error_observation(error, "FindObjectByName"),
        }
    return {
        "status": "not_found" if proxy is None else "found",
        "guid": None if proxy is None else _text(proxy.Guid),
        "error": None,
    }


def _alias_targets_observation(server, query):
    try:
        targets = server.AliasTargets(query)
        return {
            "status": "found",
            "guids": sorted(_text(guid) for guid in (targets or [])),
            "error": None,
        }
    except Exception as error:
        return {
            "status": "error",
            "guids": [],
            "error": _error_observation(error, "AliasTargets"),
        }


def _compare_guid_rows(
    left, right, proxy_by_guid, compare_proxies, comparison_errors
):
    try:
        comparison = int(compare_proxies(proxy_by_guid[left], proxy_by_guid[right]))
    except Exception as error:
        comparison_errors.append(
            {
                "left_guid": left,
                "right_guid": right,
                "error": _error_observation(error, "CompareProxies"),
            }
        )
        comparison = 0
    if comparison:
        return comparison
    return (left > right) - (left < right)


def main():
    if os.path.exists(OUTPUT_PATH):
        raise RuntimeError("native-discovery.json already exists")

    import clr

    clr.AddReference("Grasshopper")
    clr.AddReference("RhinoCommon")

    import Grasshopper
    import Rhino
    import System
    from Grasshopper import Instances
    from Grasshopper.Kernel import GH_ComponentServer
    from System import Array, String

    server = Instances.ComponentServer
    if server is None:
        raise RuntimeError("Grasshopper ComponentServer unavailable")

    proxies = list(server.ObjectProxies)
    if not proxies:
        raise RuntimeError("Grasshopper ObjectProxies empty")

    active_rhino_document = Rhino.RhinoDoc.ActiveDoc
    if active_rhino_document is None:
        raise RuntimeError("active Rhino document unavailable")

    canvas = Instances.ActiveCanvas
    document = None if canvas is None else canvas.Document
    objects = None if document is None else document.Objects
    canvas_count_before = None if objects is None else int(objects.Count)
    if canvas_count_before is None:
        raise RuntimeError("active Grasshopper document unavailable")

    assembly_cache = {}
    facts = [_proxy_fact(proxy, server, assembly_cache) for proxy in proxies]
    fact_by_guid = {fact["guid"]: fact for fact in facts}
    proxy_by_guid = {_text(proxy.Guid): proxy for proxy in proxies}

    query_rows = []
    for query_index, query in enumerate(QUERIES):
        runs = []
        first_proxies = None
        first_weights = None
        for run_index in range(NATIVE_RUNS_PER_QUERY):
            found, weights, elapsed_ms = _find_objects(
                server, query, len(proxies), Array, String
            )
            guids = [_text(proxy.Guid) for proxy in found]
            runs.append(
                {
                    "run": run_index + 1,
                    "elapsed_ms": elapsed_ms,
                    "guids": guids,
                    "weights": weights,
                }
            )
            if run_index == 0:
                first_proxies = found
                first_weights = weights

        candidates = []
        for rank, (proxy, weight) in enumerate(
            zip(first_proxies, first_weights), start=1
        ):
            fact = dict(fact_by_guid[_text(proxy.Guid)])
            fact["native_rank"] = rank
            fact["native_score"] = weight
            candidates.append(fact)

        stable = all(
            runs[0]["guids"] == run["guids"]
            and runs[0]["weights"] == run["weights"]
            for run in runs[1:]
        )
        exact_observation = _find_object_by_name_observation(server, query)
        alias_observation = _alias_targets_observation(server, query)
        query_rows.append(
            {
                "query": query,
                "is_global_cold_call": query_index == 0,
                "runs": runs,
                "stable": stable,
                "native_count": len(candidates),
                "candidates": candidates,
                "find_object_by_name": exact_observation,
                "alias_targets": alias_observation,
                "legacy_nonexact": _legacy_set_observation(
                    facts, query, exact=False
                ),
                "legacy_exact": _legacy_set_observation(
                    facts, query, exact=True
                ),
            }
        )

    category_case = _choose_category_case(query_rows)
    if category_case is not None:
        matching_query = next(
            row for row in query_rows if row["query"] == category_case["query"]
        )
        category_case["legacy_nonexact"] = _legacy_set_observation(
            facts,
            matching_query["query"],
            exact=False,
            category=category_case["category"],
        )

    duplicate_groups = _duplicate_exact_groups(facts)
    selected_guids = set()
    for guids in duplicate_groups.values():
        selected_guids.update(guids)

    third_party = []
    seen_libraries = set()
    for fact in sorted(
        facts,
        key=lambda item: (
            _lower(
                ((item.get("assembly_lookup") or {}).get("info") or {}).get("name")
            ),
            _lower(
                ((item.get("assembly_lookup") or {}).get("info") or {}).get(
                    "version"
                )
            ),
            item["guid"],
        ),
    ):
        assembly = ((fact.get("assembly_lookup") or {}).get("info") or {})
        library_guid = fact.get("library_guid")
        if (
            fact.get("obsolete") is not False
            or assembly.get("classification") != "third_party"
            or not library_guid
        ):
            continue
        if library_guid in seen_libraries:
            continue
        seen_libraries.add(library_guid)
        third_party.append(fact)
        selected_guids.add(fact["guid"])
        if len(third_party) == 5:
            break

    metadata_provenance = []
    for guid_text in sorted(selected_guids):
        metadata_provenance.append(
            _find_assembly_by_object_observation(
                server, guid_text, System.Guid.Parse
            )
        )

    comparison_errors = []
    tie_groups = []
    for row in query_rows:
        by_score = {}
        for candidate in row["candidates"]:
            by_score.setdefault(candidate["native_score"], []).append(candidate["guid"])
        for score, guids in by_score.items():
            if len(guids) < 2:
                continue
            ordered = sorted(
                guids,
                key=functools.cmp_to_key(
                    lambda left, right: _compare_guid_rows(
                        left,
                        right,
                        proxy_by_guid,
                        GH_ComponentServer.CompareProxies,
                        comparison_errors,
                    )
                ),
            )
            tie_groups.append(
                {
                    "query": row["query"],
                    "score": score,
                    "native_order": guids,
                    "compare_proxies_then_guid_order": ordered,
                }
            )

    catalog_order = sorted(
        [fact["guid"] for fact in facts if fact["obsolete"] is False],
        key=functools.cmp_to_key(
            lambda left, right: _compare_guid_rows(
                left,
                right,
                proxy_by_guid,
                GH_ComponentServer.CompareProxies,
                comparison_errors,
            )
        ),
    )

    objects_after = None if document is None else document.Objects
    canvas_count_after = None if objects_after is None else int(objects_after.Count)
    legacy_observations = [
        observation
        for row in query_rows
        for observation in (row["legacy_nonexact"], row["legacy_exact"])
    ]
    if category_case is not None:
        legacy_observations.append(category_case["legacy_nonexact"])
    legacy_comparisons_complete = category_case is not None and all(
        observation["complete"] for observation in legacy_observations
    )

    payload = {
        "schema": "rook.task0.gh_native_discovery.v1",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "process_id": int(System.Diagnostics.Process.GetCurrentProcess().Id),
            "rhino_document_serial_number": int(
                active_rhino_document.RuntimeSerialNumber
            ),
            "rhino_version": _text(Rhino.RhinoApp.Version),
            "grasshopper_assembly_full_name": _text(
                server.GetType().Assembly.FullName
            ),
            "grasshopper_assembly_location": _text(
                server.GetType().Assembly.Location
            ),
            "proxy_count": len(proxies),
            "canvas_object_count_before": canvas_count_before,
            "canvas_object_count_after": canvas_count_after,
        },
        "budgets": {
            "find_objects": len(QUERIES) * NATIVE_RUNS_PER_QUERY,
            "find_object_by_name": len(QUERIES),
            "alias_targets": len(QUERIES),
            "create_instance": 0,
            "emit_object": 0,
            "find_assembly_by_object": len(selected_guids),
        },
        "assembly_inventory": assembly_cache,
        "catalog": facts,
        "catalog_compare_proxies_then_guid_order": catalog_order,
        "queries": query_rows,
        "category_case": category_case,
        "legacy_comparisons_complete": legacy_comparisons_complete,
        "duplicate_exact_name_groups": duplicate_groups,
        "third_party_specimens": third_party,
        "metadata_provenance": metadata_provenance,
        "equal_score_groups": tie_groups,
        "compare_proxies_errors": comparison_errors,
    }

    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8", errors="strict")
    with open(OUTPUT_PATH, "xb") as stream:
        count = stream.write(encoded)
        if count != len(encoded):
            raise RuntimeError("short native-discovery write")
        stream.flush()
        os.fsync(stream.fileno())
    print("ROOK_TASK0_OK " + hashlib.sha256(encoded).hexdigest().upper())


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Create the exact one-shot launcher**

Use `apply_patch` to create `run.ps1` with this complete source:

```powershell
param(
    [Parameter(Mandatory = $true)]
    [string]$TargetPath,
    [switch]$ValidateTargetOnly
)

$ErrorActionPreference = 'Stop'
$Root = 'C:/Users/bring/AppData/Local/Temp/rook-gh-native-discovery-task0'
$Probe = Join-Path $Root 'probe.py'
$ManifestPath = Join-Path $Root 'manifest.json'
$FrozenTargetPath = Join-Path $Root 'target.json'
$Raw = Join-Path $Root 'native-discovery.json'
$InvokeResult = Join-Path $Root 'invoke-result.json'
$Stderr = Join-Path $Root 'stderr.txt'
$Python = 'C:/Users/bring/AppData/Local/Rook/venv/Scripts/python.exe'
$ExpectedKeys = 'document_serial_number,port,process_id'

function Refuse([string]$Reason) {
    [Console]::Out.WriteLine("refused $Reason")
    exit 2
}

function Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}

function WriteNewUtf8([string]$Path, [string]$Text) {
    $bytes = [Text.Encoding]::UTF8.GetBytes($Text)
    $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
    try {
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush($true)
    }
    finally {
        $stream.Dispose()
    }
}

if (-not (Test-Path -LiteralPath $TargetPath)) { Refuse 'required_file_missing' }
if (
    -not $ValidateTargetOnly -and
    [IO.Path]::GetFullPath($TargetPath) -cne [IO.Path]::GetFullPath($FrozenTargetPath)
) { Refuse 'target_path_mismatch' }

try {
    $Target = Get-Content -Raw -LiteralPath $TargetPath | ConvertFrom-Json
    $TargetKeys = @($Target.PSObject.Properties.Name | Sort-Object)
    if (($TargetKeys -join ',') -cne $ExpectedKeys) { Refuse 'invalid_target' }
    if (
        $Target.process_id -isnot [long] -or
        $Target.process_id -le 0 -or
        $Target.process_id -gt [uint32]::MaxValue
    ) { Refuse 'invalid_target' }
    if (
        $Target.port -isnot [long] -or
        $Target.port -le 0 -or
        $Target.port -gt 65535
    ) { Refuse 'invalid_target' }
    if (
        $Target.document_serial_number -isnot [long] -or
        $Target.document_serial_number -le 0 -or
        $Target.document_serial_number -gt [uint32]::MaxValue
    ) { Refuse 'invalid_target' }
    if ($ValidateTargetOnly) {
        [Console]::Out.WriteLine('validated')
        exit 0
    }

    foreach ($path in @($Raw, $InvokeResult, $Stderr)) {
        if (Test-Path -LiteralPath $path) { Refuse 'evidence_exists' }
    }
    foreach ($path in @($Probe, $ManifestPath, $Python)) {
        if (-not (Test-Path -LiteralPath $path)) { Refuse 'required_file_missing' }
    }

    $Manifest = Get-Content -Raw -LiteralPath $ManifestPath | ConvertFrom-Json
    foreach ($relative in @('probe.py', 'run.ps1', 'test_probe.py', 'target.json')) {
        $entry = $Manifest.PSObject.Properties[$relative]
        if ($null -eq $entry) { Refuse 'manifest_invalid' }
        $actual = Sha256 (Join-Path $Root $relative)
        if ($actual -cne [string]$entry.Value) { Refuse 'manifest_mismatch' }
    }

    $instancesText = & $Python -c 'import json; from rook.bridge import discover_instances; print(json.dumps(discover_instances()))'
    if ($LASTEXITCODE -ne 0) { Refuse 'discovery_failed' }
    $instances = @($instancesText | ConvertFrom-Json)
    $matches = @(
        $instances | Where-Object {
            $_.pluginType -ceq 'native' -and
            $_.processId -eq $Target.process_id -and
            $_.port -eq $Target.port
        }
    )
    if ($matches.Count -ne 1) { Refuse 'target_mismatch' }

    $listeners = @(
        Get-NetTCPConnection -State Listen -LocalPort $Target.port |
            Where-Object { $_.OwningProcess -eq $Target.process_id }
    )
    if ($listeners.Count -lt 1) { Refuse 'listener_mismatch' }

    $code = [IO.File]::ReadAllText($Probe, [Text.Encoding]::UTF8)
    $body = @{
        code = $code
        documentSerialNumber = $Target.document_serial_number
    } | ConvertTo-Json -Compress

    $client = [Net.Http.HttpClient]::new()
    try {
        $content = [Net.Http.StringContent]::new(
            $body,
            [Text.Encoding]::UTF8,
            'application/json'
        )
        $response = $client.PostAsync(
            "http://127.0.0.1:$($Target.port)/execute",
            $content
        ).GetAwaiter().GetResult()
        $responseBody = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        $record = @{
            status_code = [int]$response.StatusCode
            body = $responseBody
        } | ConvertTo-Json -Depth 20 -Compress
        WriteNewUtf8 $InvokeResult $record
    }
    finally {
        $client.Dispose()
    }

    if (-not $response.IsSuccessStatusCode) { Refuse 'invoke_failed' }
    try {
        $responseDocument = $responseBody | ConvertFrom-Json
    }
    catch {
        Refuse 'invoke_response_invalid'
    }
    if ($responseDocument.success -ne $true) { Refuse 'invoke_failed' }
    if ($null -eq $responseDocument.data) { Refuse 'invoke_response_invalid' }
    if ($responseDocument.data.objectsCreated -ne 0) { Refuse 'rhino_changed' }
    if (@($responseDocument.data.objectIds).Count -ne 0) { Refuse 'rhino_changed' }

    if (-not (Test-Path -LiteralPath $Raw)) { Refuse 'raw_evidence_missing' }
    $rawDocument = Get-Content -Raw -LiteralPath $Raw | ConvertFrom-Json
    if ($rawDocument.schema -cne 'rook.task0.gh_native_discovery.v1') {
        Refuse 'raw_evidence_invalid'
    }
    if ($rawDocument.environment.process_id -ne $Target.process_id) {
        Refuse 'target_mismatch'
    }
    if (
        $rawDocument.environment.rhino_document_serial_number -ne
        $Target.document_serial_number
    ) {
        Refuse 'target_mismatch'
    }
    if (
        $null -eq $rawDocument.environment.canvas_object_count_before -or
        $null -eq $rawDocument.environment.canvas_object_count_after
    ) {
        Refuse 'raw_evidence_invalid'
    }
    if (
        $rawDocument.environment.canvas_object_count_before -ne
        $rawDocument.environment.canvas_object_count_after
    ) {
        Refuse 'canvas_changed'
    }
    if ($rawDocument.budgets.find_objects -ne 21) { Refuse 'budget_mismatch' }
    if ($rawDocument.budgets.find_object_by_name -ne 7) { Refuse 'budget_mismatch' }
    if ($rawDocument.budgets.alias_targets -ne 7) { Refuse 'budget_mismatch' }
    if ($rawDocument.budgets.create_instance -ne 0) { Refuse 'budget_mismatch' }
    if ($rawDocument.budgets.emit_object -ne 0) { Refuse 'budget_mismatch' }

    WriteNewUtf8 $Stderr ''
    [Console]::Out.WriteLine("completed $Raw")
    exit 0
}
catch {
    if (-not (Test-Path -LiteralPath $Stderr)) {
        WriteNewUtf8 $Stderr 'operator_failed'
    }
    [Console]::Out.WriteLine("failed $Root")
    exit 1
}
```

- [ ] **Step 4: Create inert causal tests**

Use `apply_patch` to create `test_probe.py` with this complete source:

```python
import hashlib
import importlib.util
import json
import pathlib
import py_compile
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(
    "C:/Users/bring/AppData/Local/Temp/rook-gh-native-discovery-task0"
)
PROBE = ROOT / "probe.py"
RUNNER = ROOT / "run.ps1"
TEST = ROOT / "test_probe.py"
MANIFEST = ROOT / "manifest.json"
TARGET = ROOT / "target.json"
EVIDENCE = (
    ROOT / "native-discovery.json",
    ROOT / "invoke-result.json",
    ROOT / "stderr.txt",
)
QUERIES = (
    "Series",
    "Range",
    "Multiplication",
    "Addition",
    "Construct Point",
    "Add",
    "Point",
)


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _load_probe():
    spec = importlib.util.spec_from_file_location("task0_probe", PROBE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PredicateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.probe = _load_probe()

    def test_exact_queries_and_call_budget_are_frozen(self):
        self.assertEqual(self.probe.QUERIES, QUERIES)
        self.assertEqual(self.probe.NATIVE_RUNS_PER_QUERY, 3)
        self.assertEqual(len(QUERIES) * self.probe.NATIVE_RUNS_PER_QUERY, 21)

    def test_legacy_predicate_is_complete_literal_behavior(self):
        fact = {
            "guid": "g1",
            "name": "Construct Point",
            "nickname": "Pt",
            "description": "Create a point",
            "category": "Vector",
            "subcategory": "Point",
            "obsolete": False,
        }
        self.assertTrue(self.probe._legacy_matches(fact, "point"))
        self.assertFalse(self.probe._legacy_matches(fact, "Point", exact=True))
        self.assertTrue(self.probe._legacy_matches(fact, "Construct Point", exact=True))
        self.assertTrue(self.probe._legacy_matches(fact, "point", category="POI"))
        self.assertFalse(self.probe._legacy_matches(fact, "point", category="mesh"))
        incomplete = dict(fact)
        incomplete["description"] = None
        self.assertIsNone(self.probe._legacy_matches(incomplete, "point"))
        observation = self.probe._legacy_set_observation(
            [fact, incomplete], "point"
        )
        self.assertFalse(observation["complete"])
        self.assertEqual(observation["incomplete"][0]["guid"], "g1")
        fact["obsolete"] = True
        self.assertFalse(self.probe._legacy_matches(fact, "point"))

    def test_duplicate_names_preserve_all_guids(self):
        facts = [
            {"guid": "native", "name": "Shared", "obsolete": False},
            {"guid": "plugin", "name": "shared", "obsolete": False},
            {"guid": "old", "name": "Shared", "obsolete": True},
        ]
        self.assertEqual(
            self.probe._duplicate_exact_groups(facts),
            {"shared": ["native", "plugin"]},
        )

    def test_category_case_requires_a_candidate_below_public_limit(self):
        candidates = [
            {
                "guid": str(index),
                "native_rank": index + 1,
                "category": "Early" if index < 50 else "LatePlugin",
                "subcategory": "",
            }
            for index in range(51)
        ]
        result = self.probe._choose_category_case(
            [{"query": "Point", "candidates": candidates}]
        )
        self.assertEqual(result["query"], "Point")
        self.assertEqual(result["category"], "LatePlugin")
        self.assertEqual(result["first_displaced_rank"], 51)

    def test_installed_find_objects_signature_and_pythonnet_projection_are_pinned(self):
        reflection = r"""
[void][Reflection.Assembly]::LoadFrom(
  'C:/Program Files/Rhino 8/System/RhinoCommon.dll'
)
$assembly = [Reflection.Assembly]::LoadFrom(
  'C:/Program Files/Rhino 8/Plug-ins/Grasshopper/Grasshopper.dll'
)
$type = $assembly.GetType('Grasshopper.Kernel.GH_ComponentServer', $true)
$methods = @(
  $type.GetMethods() | Where-Object {
    $_.Name -ceq 'FindObjects' -and $_.GetParameters().Count -eq 4
  }
)
if ($methods.Count -ne 1) { throw 'unexpected FindObjects overload count' }
[Console]::Out.Write($methods[0].ToString())
"""
        completed = subprocess.run(
            ["pwsh", "-NoProfile", "-Command", reflection],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            completed.stdout,
            self.probe.EXPECTED_FIND_OBJECTS_SIGNATURE,
        )
        proxies, weights = self.probe._coerce_find_objects_result(
            (2, ("p1", "p2"), (10.0, 5.0))
        )
        self.assertEqual(proxies, ["p1", "p2"])
        self.assertEqual(weights, [10.0, 5.0])
        with self.assertRaisesRegex(RuntimeError, "out/ref projection"):
            self.probe._coerce_find_objects_result((2, ("p1", "p2")))

    def test_optional_provenance_is_tristate_and_failures_are_observations(self):
        class ThirdPartyInfo:
            IsCoreLibrary = False

        class Description:
            Name = "Plugin Example"
            NickName = "PE"
            Description = "Plugin specimen"
            Category = "Plugin"
            SubCategory = "Example"
            Keywords = None

        class Proxy:
            Guid = "00000000-0000-0000-0000-000000000001"
            LibraryGuid = "00000000-0000-0000-0000-000000000002"
            Desc = Description()
            Type = None
            Exposure = 1
            Obsolete = False
            Kind = "CompiledObject"
            SDKCompliant = True
            Location = "plugin.gha"

        class Server:
            def FindAssembly(self, _guid):
                return ThirdPartyInfo()

        fact = self.probe._proxy_fact(Proxy(), Server(), {})
        self.assertEqual(fact["keywords"], [])
        self.assertEqual(
            fact["assembly_lookup"]["info"]["classification"], "third_party"
        )
        self.assertEqual(
            self.probe._assembly_info(object())["classification"], "unknown"
        )

        class BrokenObsolete:
            @property
            def Obsolete(self):
                raise RuntimeError("obsolete read failure")

        _, obsolete_state = self.probe._read_property(
            BrokenObsolete(), "Obsolete", bool
        )
        self.assertEqual(obsolete_state["status"], "error")
        incomplete_legacy = self.probe._legacy_set_observation(
            [
                {
                    "guid": "broken",
                    "legacy_properties": {"obsolete": obsolete_state},
                }
            ],
            "Point",
        )
        self.assertFalse(incomplete_legacy["complete"])
        self.assertEqual(incomplete_legacy["incomplete"][0]["fields"], ["obsolete"])

        class FailingServer:
            def FindAssembly(self, _guid):
                raise RuntimeError("assembly failure")

            def FindAssemblyByObject(self, _guid):
                raise RuntimeError("metadata failure")

            def FindObjectByName(self, *_args):
                raise RuntimeError("exact lookup failure")

            def AliasTargets(self, _query):
                raise RuntimeError("alias lookup failure")

        assembly_failure = self.probe._find_assembly_observation(
            FailingServer(), "library-guid"
        )
        self.assertEqual(assembly_failure["status"], "error")
        metadata_failure = self.probe._find_assembly_by_object_observation(
            FailingServer(), "component-guid", lambda value: value
        )
        self.assertEqual(metadata_failure["status"], "error")
        self.assertEqual(metadata_failure["guid"], "component-guid")
        self.assertEqual(
            self.probe._find_object_by_name_observation(FailingServer(), "Series")[
                "status"
            ],
            "error",
        )
        self.assertEqual(
            self.probe._alias_targets_observation(FailingServer(), "Series")[
                "status"
            ],
            "error",
        )
        comparison_errors = []
        order = self.probe._compare_guid_rows(
            "a",
            "b",
            {"a": object(), "b": object()},
            lambda *_args: (_ for _ in ()).throw(RuntimeError("compare failure")),
            comparison_errors,
        )
        self.assertEqual(order, -1)
        self.assertEqual(len(comparison_errors), 1)


class CustodyTests(unittest.TestCase):
    def test_probe_compiles_without_importing_rhino(self):
        py_compile.compile(str(PROBE), doraise=True)

    def test_probe_contains_no_mutation_or_instantiation_surface(self):
        source = PROBE.read_text(encoding="utf-8")
        forbidden = (
            "CreateInstance(",
            "EmitObject(",
            "ExpireSolution(",
            "ScheduleSolution(",
            "Objects.Add(",
            "AddObject(",
            "gh_edit",
            "gh_create",
            "gh_snapshot",
        )
        for token in forbidden:
            self.assertNotIn(token, source)

    def test_runner_contains_exactly_one_native_execute_request_and_no_retry(self):
        source = RUNNER.read_text(encoding="utf-8")
        self.assertEqual(source.count(".PostAsync("), 1)
        self.assertEqual(source.count("/execute"), 1)
        for token in ("Start-Sleep", "while (", "for (;;", "Retry", "retry"):
            self.assertNotIn(token, source)

    def test_runner_checks_route_and_host_nonmutation_evidence(self):
        source = RUNNER.read_text(encoding="utf-8")
        for token in (
            "IsSuccessStatusCode",
            "objectsCreated",
            "objectIds",
            "rhino_document_serial_number",
            "canvas_object_count_before",
            "canvas_object_count_after",
        ):
            self.assertIn(token, source)

    def test_runner_type_exact_target_admission_is_no_contact(self):
        cases = (
            (
                {
                    "process_id": 4242,
                    "port": 65000,
                    "document_serial_number": 268435457,
                },
                0,
                "validated",
            ),
            (
                {
                    "process_id": 0,
                    "port": 65000,
                    "document_serial_number": 268435457,
                },
                2,
                "refused invalid_target",
            ),
            (
                {
                    "process_id": 4294967296,
                    "port": 65000,
                    "document_serial_number": 268435457,
                },
                2,
                "refused invalid_target",
            ),
            (
                {
                    "process_id": 4242,
                    "port": 0,
                    "document_serial_number": 268435457,
                },
                2,
                "refused invalid_target",
            ),
            (
                {
                    "process_id": 4242,
                    "port": 65536,
                    "document_serial_number": 268435457,
                },
                2,
                "refused invalid_target",
            ),
            (
                {
                    "process_id": 4242,
                    "port": 65000,
                    "document_serial_number": 0,
                },
                2,
                "refused invalid_target",
            ),
            (
                {
                    "process_id": 4242,
                    "port": 65000,
                    "document_serial_number": 4294967296,
                },
                2,
                "refused invalid_target",
            ),
            (
                {
                    "process_id": 4242,
                    "port": [65000],
                    "document_serial_number": 268435457,
                },
                2,
                "refused invalid_target",
            ),
            (
                {
                    "process_id": 4242,
                    "port": 65000,
                    "document_serial_number": 268435457,
                    "extra": 1,
                },
                2,
                "refused invalid_target",
            ),
        )
        with tempfile.TemporaryDirectory() as temp_directory:
            target = pathlib.Path(temp_directory) / "target.json"
            for payload, expected_code, expected_stdout in cases:
                target.write_text(json.dumps(payload), encoding="utf-8")
                completed = subprocess.run(
                    [
                        "pwsh",
                        "-NoProfile",
                        "-File",
                        str(RUNNER),
                        "-TargetPath",
                        str(target),
                        "-ValidateTargetOnly",
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(completed.returncode, expected_code)
                self.assertEqual(completed.stdout.strip(), expected_stdout)
        for path in EVIDENCE:
            self.assertFalse(path.exists(), path)

    def test_live_evidence_is_absent_before_authorization(self):
        for path in EVIDENCE:
            self.assertFalse(path.exists(), path)

    def test_manifest_matches_inert_sources(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        expected = {"probe.py", "run.ps1", "test_probe.py"}
        if TARGET.exists():
            expected.add("target.json")
        self.assertEqual(set(manifest), expected)
        for name in manifest:
            self.assertEqual(manifest[name], _sha256(ROOT / name))


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 5: Create the inert manifest**

Run this read-only hash computation and use `apply_patch` to create `manifest.json` with
the exact three reported values:

```powershell
$Root = 'C:/Users/bring/AppData/Local/Temp/rook-gh-native-discovery-task0'
foreach ($name in @('probe.py', 'run.ps1', 'test_probe.py')) {
    "$name $((Get-FileHash -LiteralPath (Join-Path $Root $name) -Algorithm SHA256).Hash)"
}
```

Create a closed JSON object with exactly those three filenames as keys and their actual
reported uppercase SHA-256 strings as values. Do not add descriptive fields or any value
other than the hashes emitted by the preceding command.

- [ ] **Step 6: Run the inert seam**

Run:

```powershell
$Root = 'C:/Users/bring/AppData/Local/Temp/rook-gh-native-discovery-task0'
$Python = 'C:/Users/bring/AppData/Local/Rook/venv/Scripts/python.exe'
& $Python "$Root/test_probe.py" -v
```

Expected:

```text
13 tests pass.
No Rhino, Grasshopper, model, MCP, or HTTP contact occurs.
No target or live evidence file exists.
```

- [ ] **Step 7: Static source review and mandatory stop**

Run:

```powershell
$Root = 'C:/Users/bring/AppData/Local/Temp/rook-gh-native-discovery-task0'
$Python = 'C:/Users/bring/AppData/Local/Rook/venv/Scripts/python.exe'

& $Python -m py_compile "$Root/probe.py" "$Root/test_probe.py"
Get-FileHash "$Root/probe.py", "$Root/run.ps1", "$Root/test_probe.py", "$Root/manifest.json" -Algorithm SHA256
Get-ChildItem $Root -File | Select-Object Name, Length
git -C 'C:/UDEV/Rook/.worktrees/mcp-structured-tool-results-merged' status --short
```

Report:

- exact four hashes;
- exact inert passing count;
- the installed reflected `FindObjects` signature and the inertly pinned accepted
  projection `(count, proxies, weights)`, explicitly without claiming the live binding
  has produced it yet;
- the successful representative `Int64` target-admission regression and rejected upper
  bounds;
- the fixed external and internal call budgets;
- static absence of mutation/instantiation calls;
- absence of `target.json` and all live evidence;
- clean repository worktree.

**Mandatory review boundary:** stop for independent pre-contact review. Do not create
`target.json`, edit the manifest, start the launcher, or contact Rhino/Grasshopper.

---

### Task 2: Freeze one target and perform the separately authorized read-only capture

**Files:**
- Create outside Git: `C:/Users/bring/AppData/Local/Temp/rook-gh-native-discovery-task0/target.json`
- Modify outside Git: `C:/Users/bring/AppData/Local/Temp/rook-gh-native-discovery-task0/manifest.json`
- Produce outside Git: `native-discovery.json`, `invoke-result.json`, `stderr.txt`

**Interfaces:**
- Consumes: independently approved Task 1 hashes; one currently open Rhino process with Grasshopper loaded; exact panel PID, native port, and document serial.
- Produces: one raw, hashable native-discovery observation from exactly one external request.

- [ ] **Step 1: Confirm the pre-contact approval and prepare the host**

Require explicit reviewer approval of Task 1 before continuing. Ask the operator to:

1. Open Rhino and Grasshopper with the installed third-party plugins loaded normally.
2. Keep one disposable Grasshopper document open; its contents are irrelevant because
   the probe reads the component server and makes no document edit.
3. Open the RookChat panel so the exact Rhino PID, native port, and document serial can be
   corroborated.

Do not contact the host yet.

- [ ] **Step 2: Freeze target identity without HTTP contact**

Use deployed `rook.bridge.discover_instances()` and Windows listener ownership to obtain
one exact native instance. After observing the current values, use `apply_patch` to write
`target.json` as a closed object containing exactly `process_id`, `port`, and
`document_serial_number`, each as the fresh observed positive integer. Do not use sample,
historical, or previously retained target values.

Run the non-contact corroboration:

```powershell
$Root = 'C:/Users/bring/AppData/Local/Temp/rook-gh-native-discovery-task0'
$Python = 'C:/Users/bring/AppData/Local/Rook/venv/Scripts/python.exe'
$Target = Get-Content -Raw "$Root/target.json" | ConvertFrom-Json

& $Python -c 'import json; from rook.bridge import discover_instances; print(json.dumps(discover_instances(), indent=2))'
Get-NetTCPConnection -State Listen -LocalPort $Target.port |
    Select-Object LocalAddress, LocalPort, OwningProcess, State
```

Require one native discovery record matching PID/port and at least one listener owned by
the exact PID. Document serial remains the exact panel-owned row value.

- [ ] **Step 3: Add and verify the frozen target hash**

Compute:

```powershell
$Root = 'C:/Users/bring/AppData/Local/Temp/rook-gh-native-discovery-task0'
(Get-FileHash "$Root/target.json" -Algorithm SHA256).Hash
```

Use `apply_patch` to add exactly one `target.json` entry to `manifest.json`. Then rerun:

```powershell
$Python = 'C:/Users/bring/AppData/Local/Rook/venv/Scripts/python.exe'
& $Python "$Root/test_probe.py" -v
```

The Task 1 test is already phase-aware: it requires exactly three manifest entries while
`target.json` is absent and exactly four after it exists. Do not edit `test_probe.py`,
`probe.py`, or `run.ps1` in Task 2. Their independently reviewed hashes remain unchanged;
Task 2 changes only `target.json` and the one new manifest entry.

Expected: the updated inert seam passes and all live evidence remains absent.

- [ ] **Step 4: Report the frozen row and stop for authorization**

Report:

- target PID, native port, and document serial;
- SHA-256 of `target.json` and the complete manifest;
- exact inert passing count;
- exact probe/runner/test hashes;
- absence of live evidence;
- the closed budget: one `/execute`, 21 `FindObjects`, seven `FindObjectByName`, seven
  `AliasTargets`, zero component instantiations, zero canvas edits, zero retries.

Obtain explicit authorization that repeats the actual reported target SHA-256 and grants
exactly one Task 0 read-only native component-discovery qualification. It must explicitly
deny model calls, canvas mutation, operator reruns, adapter retries, a second `/execute`
request, and any additional host call. Do not accept an authorization that omits or
mistypes the frozen hash.

- [ ] **Step 5: Execute exactly once**

Only after authorization, run:

```powershell
$Root = 'C:/Users/bring/AppData/Local/Temp/rook-gh-native-discovery-task0'
& "$Root/run.ps1" -TargetPath "$Root/target.json"
```

Do not invoke the command a second time for any reason. The launcher and exclusive files
will also refuse reuse.

Expected success stdout:

```text
completed C:/Users/bring/AppData/Local/Temp/rook-gh-native-discovery-task0/native-discovery.json
```

Any other status is a truthful incomplete Task 0 result. Preserve the entire lane and
stop; do not patch or rerun autonomously.

- [ ] **Step 6: Verify raw evidence without host contact**

Run only local reads:

```powershell
$Root = 'C:/Users/bring/AppData/Local/Temp/rook-gh-native-discovery-task0'
$Python = 'C:/Users/bring/AppData/Local/Rook/venv/Scripts/python.exe'

Get-FileHash "$Root/native-discovery.json", "$Root/invoke-result.json", "$Root/stderr.txt" -Algorithm SHA256
& $Python -c "import json, pathlib; p=pathlib.Path(r'$Root/native-discovery.json'); d=json.loads(p.read_text(encoding='utf-8')); print(json.dumps({'schema':d['schema'],'environment':d['environment'],'budgets':d['budgets'],'query_count':len(d['queries']),'legacy_comparisons_complete':d['legacy_comparisons_complete'],'category_case_present':d['category_case'] is not None,'duplicate_group_count':len(d['duplicate_exact_name_groups']),'third_party_count':len(d['third_party_specimens'])}, indent=2))"
```

Require:

- schema `rook.task0.gh_native_discovery.v1`;
- process ID equals target;
- positive proxy count;
- canvas object count unchanged;
- exact `21/7/7/0/0` internal budgets;
- seven query rows, each with three runs;
- `legacy_comparisons_complete` plus every per-GUID incomplete-field observation;
- successful raw-artifact creation as the evidence that the live Python.NET call produced
  the accepted `(count, proxies, weights)` projection;
- raw JSON and invocation response parse successfully;
- exactly one external request occurred;
- no model or canvas tool was called.

If `category_case` is absent, fewer than three third-party libraries are available, or a
query order is unstable, record that fact. Do not fabricate success or rerun.

---

### Task 3: Write the bounded qualification report and stop for policy review

**Files:**
- Create: `docs/superpowers/reports/2026-08-08-grasshopper-native-component-discovery-qualification.md`
- Preserve: all production and test files
- Preserve: `docs/superpowers/specs/2026-08-08-grasshopper-component-discovery-coherence-design.md`

**Interfaces:**
- Consumes: exact raw and invocation hashes from Task 2.
- Produces: one human-reviewable evidence report that proposes, but does not enact, eligibility, native adoption, or provenance decisions.

- [ ] **Step 1: Derive the fixed report tables locally**

Use a read-only Python command or short disposable analysis command to print, without
rewriting raw evidence:

- environment and proxy count;
- each query's three elapsed times, count, stability, top ten GUID/name/library tuples,
  and alias targets;
- the rank of `Series`, `Range`, `Multiplication`, `Addition`, and every exact duplicate;
- complete legacy-minus-native and native-minus-legacy GUID sets only when their source
  legacy observation has `complete=true`; otherwise label the partial sets and enumerate
  every incomplete GUID/field;
- exposure, tri-state obsolete/name/description/category inputs, library, and assembly
  facts for every legacy-only or incompletely classified item;
- category case query/filter, displaced rank, complete native GUID set, and the legacy
  observation with its completeness flag and incomplete fields;
- all duplicate exact-name groups;
- five third-party specimens or the exact lower available count;
- all proxy and `FindAssemblyByObject` provenance field values for selected specimens;
- equal-score native order versus `CompareProxies`/GUID order;
- cold first-call and warm repeated-call elapsed times.

Do not call Rhino, Grasshopper, Rook, or the network during analysis.

- [ ] **Step 2: Write the report with an explicit evidence/decision split**

Use `apply_patch` to create the report with exactly these sections:

```markdown
# Grasshopper Native Component Discovery Qualification

## Baseline and custody
## Exact call budget and non-mutation evidence
## Host and catalog inventory
## Fixed-query latency and ordering
## Complete legacy predicate versus native candidates
## Eligibility deltas
## Category-filter completeness
## Exact-name duplicates
## Third-party visibility
## Host provenance inventory
## Candidate identity handoff assessment
## Recommended post-Task 0 decisions
## Explicit unresolved or blocked findings
## Non-claims
## Raw evidence paths and SHA-256
```

The report must state separately:

1. What raw evidence directly establishes.
2. What is inferred from that evidence.
3. What policy is recommended for independent review.

It must propose one exact minimal provenance field set with exact JSON names, source
properties, null behavior, and canonical string formatting. It must not enact that
proposal or edit the specification.

It must recommend one of:

```text
adopt native FindObjects
do not adopt native FindObjects
qualification incomplete
```

If `legacy_comparisons_complete` is false, `qualification incomplete` is the only allowed
recommendation. The report may still describe native timing and ordering evidence, but
it must not recommend adoption from a partial compatibility comparison.

When `legacy_comparisons_complete` is true, it must also recommend one exact ordinary
eligibility policy and enumerate every GUID whose visibility would change from the
complete legacy predicate. When false, it records the unresolved policy and the observed
partial deltas without presenting them as complete.

- [ ] **Step 3: Verify documentation-only scope**

Run:

```powershell
$Lane = 'C:/UDEV/Rook/.worktrees/mcp-structured-tool-results-merged'
Set-Location $Lane

git status --short
git diff --check
git diff --name-only
rg -n 'TBD|TODO|FIXME|PLACEHOLDER' 'docs/superpowers/reports/2026-08-08-grasshopper-native-component-discovery-qualification.md'
```

Require the report to be the only uncommitted file. The placeholder scan returns no
matches. `git diff --check` passes.

- [ ] **Step 4: Commit only the report**

Run:

```powershell
git add -- 'docs/superpowers/reports/2026-08-08-grasshopper-native-component-discovery-qualification.md'
git diff --cached --check
git diff --cached --name-only
git commit -m 'docs: qualify native Grasshopper discovery'
git show --check --stat --oneline HEAD
git status --short
```

Require:

```text
Exactly one report is committed.
The worktree is clean.
No production, test, specification, or raw evidence file changed.
```

- [ ] **Step 5: Mandatory final stop**

Report:

- report commit SHA;
- raw evidence and invocation SHA-256 values;
- exact external/internal call counts;
- exact observed proxy and third-party counts;
- cold/warm timings;
- category and duplicate-name findings;
- recommended native adoption, eligibility, and provenance decisions;
- final clean worktree status.

Stop for independent evidence review.

Do not:

- amend the specification;
- implement production behavior;
- write a production implementation plan;
- run the Opus control;
- rerun the probe;
- contact any live system.

The next authorized sequence after review is:

```text
independent Task 0 evidence decision
-> specification amendment pinning exact policy and provenance
-> independent specification review
-> production implementation plan
```
