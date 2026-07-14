# RookVisionDirector Curve Samples Implementation Plan

> **PARTIALLY SUPERSEDED — Director MCP retirement (2026-07-13):** The general
> non-Director architecture and dated evidence in this document remain available.
> All `rhino_director_*`, `/director`, VisionDirector, and Director-domain examples,
> allowlist entries, count assumptions, acceptance criteria, and positive dispatch
> tests are superseded as of 2026-07-13. Replace those examples with
> non-Director fixtures when maintaining or replaying this work. This document must
> not be used to restore a Director MCP tool. See the
> [Director MCP Surface Retirement Design][director-mcp-retirement].

[director-mcp-retirement]: ../specs/2026-07-13-director-mcp-surface-retirement-design.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only Director curve-sampling primitive that returns a canonical per-frame sequence of normalized-parameter curve points and tangents for future camera strategies.

**Architecture:** RookNative owns the Rhino curve read, parameter mapping, geometry validation, and provenance for `POST /director/curve-samples`. Python exposes the route as an MCP read-only Director tool but does not feed it into `run_director` or change existing timing/camera/frame-capture behavior in this PR.

**Tech Stack:** Rhino 8 C++ SDK, MFC/v143 native plugin, `httplib`, `nlohmann::json`, Python MCP server, pytest.

---

## Constraints

- Do not implement `curve_follow_target`, FFmpeg/MP4 assembly, artifact publishing, UI/gallery changes, or changes to `/director/frame-capture`.
- Do not reuse `/analysis/curve-point-at` or `/analysis/curve-tangent`; the Director contract owns this sampled sequence and provenance.
- Do not modify `.vcxproj` or `.vcxproj.filters`.
- Use only `sampling.mode == "normalized_parameter"` in v1.
- Require `sampling`, `sampling.mode`, `sampling.start`, and `sampling.end`; no defaults.
- Add a named native upper bound constant: `kMaxDirectorCurveSampleFrameCount = 5000`.
- Preserve Director error envelope style: `SendErrorData(res, {"code": "...", "message": "..."})`.
- Return `curve_not_found` and `not_curve` as expected contract errors.
- Reserve `director_read_failed` for unexpected native read failures.
- Treat `!obj || obj->IsDeleted()` as `curve_not_found`.
- Treat bad evaluated geometry as `invalid_curve_sample`: nonfinite mapped curve parameter, nonfinite point, nonfinite tangent, or failed tangent `Unitize()`.
- Add MCP tool to both `director` and `director_readonly`; the user specifically required `director_readonly`.
- Do not claim native build verification unless the Rhino/MFC build command is actually run.

## File Structure

- Modify `src/RookNative/Handlers/DirectorHandler.h`
  Declare `HandleDirectorCurveSamples`.
- Modify `src/RookNative/Handlers/DirectorHandler.cpp`
  Add parsing, validation, sampling, provenance, and route handler.
- Modify `src/RookNative/RookServer.h`
  Add the CRookServer delegate declaration.
- Modify `src/RookNative/RookServer.cpp`
  Register `/director/curve-samples` and add the delegate implementation.
- Modify `mcp_server/src/rook/server.py`
  Add `rhino_director_curve_samples` tool schema and dispatch to native.
- Modify `mcp_server/src/rook/agent/tool_groups.py`
  Add the read-only tool to `director` and `director_readonly`.
- Modify `mcp_server/tests/test_director_mcp_tools.py`
  Add schema, dispatch, and group membership tests.
- Modify `mcp_server/tests/test_director_native_source.py`
  Add source-level contract tests for route registration, required sampling fields, upper bound, and error codes.
- Modify `mcp_server/tests/test_director_routes_live.py`
  Add live route smoke and contract rejection tests when Rhino is available.

---

### Task 1: Native Source Contract Tests

**Files:**
- Modify: `mcp_server/tests/test_director_native_source.py`
- Read: `src/RookNative/Handlers/DirectorHandler.cpp`
- Read: `src/RookNative/Handlers/DirectorHandler.h`
- Read: `src/RookNative/RookServer.cpp`
- Read: `src/RookNative/RookServer.h`

- [ ] **Step 1: Add source paths and contract tests**

Append these constants after `DIRECTOR_HANDLER`:

```python
DIRECTOR_HEADER = REPO_ROOT / "src" / "RookNative" / "Handlers" / "DirectorHandler.h"
ROOK_SERVER_CPP = REPO_ROOT / "src" / "RookNative" / "RookServer.cpp"
ROOK_SERVER_HEADER = REPO_ROOT / "src" / "RookNative" / "RookServer.h"
```

Append these tests to the file:

```python
def test_director_curve_samples_route_is_registered_and_delegated():
    handler_header = DIRECTOR_HEADER.read_text(encoding="utf-8")
    server_header = ROOK_SERVER_HEADER.read_text(encoding="utf-8")
    server_source = ROOK_SERVER_CPP.read_text(encoding="utf-8")

    assert "HandleDirectorCurveSamples" in handler_header
    assert "void HandleDirectorCurveSamples(const httplib::Request& req, httplib::Response& res);" in server_header
    assert 'm_server->Post("/director/curve-samples"' in server_source
    assert "Rook::Handlers::HandleDirectorCurveSamples(req, res);" in server_source


def test_director_curve_samples_has_required_contract_guards():
    source = DIRECTOR_HANDLER.read_text(encoding="utf-8")
    handler_body = _extract_function(source, "void HandleDirectorCurveSamples")

    assert "kMaxDirectorCurveSampleFrameCount = 5000" in source
    assert "sampling must be an object" in source
    assert "sampling.mode is required" in source
    assert "sampling.start is required" in source
    assert "sampling.end is required" in source
    assert "normalized_parameter" in source
    assert "curve_not_found" in source
    assert "not_curve" in source
    assert "invalid_curve_sample" in source
    assert "director_read_failed" in handler_body
    assert "MakeErrorData(ex.code, ex.what())" in handler_body
```

- [ ] **Step 2: Run source tests and verify they fail**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_native_source.py -q
```

Expected: the two new tests fail because `HandleDirectorCurveSamples`, the route, and the contract strings are not implemented yet.

- [ ] **Step 3: Commit the failing tests**

```powershell
git add mcp_server/tests/test_director_native_source.py
git commit -m "test: pin Director curve sample native contract"
```

---

### Task 2: Native Curve Sampling Handler

**Files:**
- Modify: `src/RookNative/Handlers/DirectorHandler.h`
- Modify: `src/RookNative/Handlers/DirectorHandler.cpp`

- [ ] **Step 1: Declare the handler**

Add this declaration to `src/RookNative/Handlers/DirectorHandler.h` beside the other Director handlers:

```cpp
void HandleDirectorCurveSamples(const httplib::Request& req, httplib::Response& res);
```

- [ ] **Step 2: Add native request structs and upper bound**

In the anonymous namespace of `DirectorHandler.cpp`, add the upper-bound constant beside the existing Director constants:

```cpp
constexpr int kMaxDirectorCurveSampleFrameCount = 5000;
```

Add these structs near the existing Director request structs:

```cpp
struct CurveSampleRequest
{
    std::string curveId;
    ON_UUID curveUuid = ON_nil_uuid;
    int frameCount = 0;
    std::string samplingMode;
    double samplingStart = 0.0;
    double samplingEnd = 0.0;
};
```

- [ ] **Step 3: Add finite numeric parsing helpers**

Add these helpers in the anonymous namespace near the existing parse helpers:

```cpp
double RequireFiniteNumber(const nlohmann::json& object, const std::string& key, const std::string& displayPath)
{
    if (!object.contains(key))
        throw DirectorFrameValidationError("invalid_input", displayPath + " is required");
    if (!object[key].is_number())
        throw DirectorFrameValidationError("invalid_input", displayPath + " must be a finite number");

    const double value = object[key].get<double>();
    if (!std::isfinite(value))
        throw DirectorFrameValidationError("invalid_input", displayPath + " must be a finite number");
    return value;
}

std::string RequireString(const nlohmann::json& object, const std::string& key, const std::string& displayPath)
{
    if (!object.contains(key))
        throw DirectorFrameValidationError("invalid_input", displayPath + " is required");
    if (!object[key].is_string() || object[key].get<std::string>().empty())
        throw DirectorFrameValidationError("invalid_input", displayPath + " must be a non-empty string");
    return object[key].get<std::string>();
}
```

- [ ] **Step 4: Add curve-sample request parsing**

Add this parser in the anonymous namespace:

```cpp
CurveSampleRequest ParseCurveSampleRequest(const nlohmann::json& body)
{
    CurveSampleRequest request;
    request.curveId = RequireString(body, "curve_id", "curve_id");
    request.curveUuid = ON_UuidFromString(request.curveId.c_str());
    if (ON_UuidIsNil(request.curveUuid))
        throw DirectorFrameValidationError("invalid_input", "curve_id must be a valid UUID string");

    if (!body.contains("frame_count") || !body["frame_count"].is_number_integer())
        throw DirectorFrameValidationError("invalid_input", "frame_count must be an integer");
    request.frameCount = body["frame_count"].get<int>();
    if (request.frameCount < 1 || request.frameCount > kMaxDirectorCurveSampleFrameCount)
        throw DirectorFrameValidationError(
            "invalid_input",
            "frame_count must be between 1 and " + std::to_string(kMaxDirectorCurveSampleFrameCount));

    if (!body.contains("sampling") || !body["sampling"].is_object())
        throw DirectorFrameValidationError("invalid_input", "sampling must be an object");
    const auto& sampling = body["sampling"];

    request.samplingMode = RequireString(sampling, "mode", "sampling.mode");
    if (request.samplingMode != "normalized_parameter")
        throw DirectorFrameValidationError("invalid_input", "sampling.mode must be normalized_parameter");

    request.samplingStart = RequireFiniteNumber(sampling, "start", "sampling.start");
    request.samplingEnd = RequireFiniteNumber(sampling, "end", "sampling.end");
    if (request.samplingStart < 0.0 || request.samplingStart > 1.0)
        throw DirectorFrameValidationError("invalid_input", "sampling.start must be between 0 and 1");
    if (request.samplingEnd < 0.0 || request.samplingEnd > 1.0)
        throw DirectorFrameValidationError("invalid_input", "sampling.end must be between 0 and 1");

    return request;
}
```

- [ ] **Step 5: Add validated curve evaluation**

Add this function in the anonymous namespace:

```cpp
nlohmann::json SampleDirectorCurve(CRhinoDoc* pDoc, const CurveSampleRequest& request)
{
    if (!pDoc)
        throw std::runtime_error("No active document");

    const CRhinoObject* obj = pDoc->LookupObject(request.curveUuid);
    if (!obj || obj->IsDeleted())
        throw DirectorFrameValidationError("curve_not_found", "Curve not found: " + request.curveId);

    const ON_Curve* curve = ON_Curve::Cast(obj->Geometry());
    if (!curve)
        throw DirectorFrameValidationError("not_curve", "Object is not a curve: " + request.curveId);

    nlohmann::json samples = nlohmann::json::array();
    samples.get_ref<nlohmann::json::array_t&>().reserve(static_cast<size_t>(request.frameCount));

    for (int frameIndex = 1; frameIndex <= request.frameCount; ++frameIndex)
    {
        const double u = request.frameCount == 1
            ? 0.0
            : static_cast<double>(frameIndex - 1) / static_cast<double>(request.frameCount - 1);
        const double normalizedParameter = request.samplingStart +
            (request.samplingEnd - request.samplingStart) * u;
        const double curveParameter = curve->Domain().ParameterAt(normalizedParameter);
        if (!std::isfinite(curveParameter))
            throw DirectorFrameValidationError("invalid_curve_sample", "Mapped curve parameter is not finite");

        ON_3dPoint point = curve->PointAt(curveParameter);
        ON_3dVector tangent = curve->TangentAt(curveParameter);
        if (!IsFinitePoint(point))
            throw DirectorFrameValidationError("invalid_curve_sample", "Curve sample point is not finite");
        if (!IsFiniteVector(tangent))
            throw DirectorFrameValidationError("invalid_curve_sample", "Curve sample tangent is not finite");
        if (!tangent.Unitize())
            throw DirectorFrameValidationError("invalid_curve_sample", "Curve sample tangent is degenerate");

        nlohmann::json sample;
        sample["frame_index"] = frameIndex;
        sample["normalized_parameter"] = RoundTo(normalizedParameter, 6);
        sample["curve_parameter"] = RoundTo(curveParameter, 6);
        sample["point"] = PointToJson(point);
        sample["tangent"] = VectorToJson(tangent);
        samples.push_back(std::move(sample));
    }

    nlohmann::json provenance;
    provenance["sampling_mode"] = "normalized_parameter";
    provenance["parameter_mapping"] = "curve_domain_parameter_at";
    provenance["frame_count_source"] = "caller_canonical_frame_count";
    provenance["arc_length_sampled"] = false;
    provenance["validation_strength"] = "curve_parameter_sampled";

    nlohmann::json result;
    result["schema_version"] = 1;
    result["curve_id"] = request.curveId;
    result["frame_count"] = request.frameCount;
    result["samples"] = std::move(samples);
    result["provenance"] = std::move(provenance);
    return result;
}
```

- [ ] **Step 6: Add the HTTP handler**

Add this handler near the other Director handlers:

```cpp
void HandleDirectorCurveSamples(const httplib::Request& req, httplib::Response& res)
{
    try
    {
        auto [docSn, body] = ParseBodyAndDocSn(req);
        CurveSampleRequest request = ParseCurveSampleRequest(body);

        auto future = CMainThreadDispatcher::Instance().Dispatch(
            [docSn, request]() -> nlohmann::json
        {
            CRhinoDoc* pDoc = ResolveDoc(docSn);
            return SampleDirectorCurve(pDoc, request);
        });

        CRookServer::SendSuccess(res, future.get());
    }
    catch (const DirectorFrameValidationError& ex)
    {
        CRookServer::SendErrorData(res, MakeErrorData(ex.code, ex.what()));
    }
    catch (const nlohmann::json::exception& ex)
    {
        CRookServer::SendErrorData(res, MakeErrorData("invalid_input", ex.what()));
    }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendErrorData(res, MakeErrorData("invalid_input", ex.what()));
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendErrorData(res, MakeErrorData("director_read_failed", ex.what()));
    }
}
```

- [ ] **Step 7: Run source tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_native_source.py -q
```

Expected: source tests still fail only on route registration until Task 3 is complete.

---

### Task 3: Native Route Registration

**Files:**
- Modify: `src/RookNative/RookServer.h`
- Modify: `src/RookNative/RookServer.cpp`

- [ ] **Step 1: Add the server delegate declaration**

In `RookServer.h`, add this declaration beside other Director delegates:

```cpp
void HandleDirectorCurveSamples(const httplib::Request& req, httplib::Response& res);
```

- [ ] **Step 2: Register the route**

In `RookServer.cpp`, register the route after `/director/view-state` and before `/director/frame-capture`:

```cpp
m_server->Post("/director/curve-samples", [this](const httplib::Request& req, httplib::Response& res) {
    HandleDirectorCurveSamples(req, res);
});
```

- [ ] **Step 3: Add the delegate implementation**

Near the other Director delegate implementations in `RookServer.cpp`, add:

```cpp
void CRookServer::HandleDirectorCurveSamples(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleDirectorCurveSamples(req, res);
}
```

- [ ] **Step 4: Run native source contract tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_native_source.py -q
```

Expected: all tests in `test_director_native_source.py` pass.

- [ ] **Step 5: Commit native route work**

```powershell
git add src/RookNative/Handlers/DirectorHandler.h src/RookNative/Handlers/DirectorHandler.cpp src/RookNative/RookServer.h src/RookNative/RookServer.cpp mcp_server/tests/test_director_native_source.py
git commit -m "feat: add Director curve sample native route"
```

---

### Task 4: MCP Tool Schema And Dispatch Tests

**Files:**
- Modify: `mcp_server/tests/test_director_mcp_tools.py`

- [ ] **Step 1: Add schema assertions**

Append this test:

```python
@pytest.mark.asyncio
async def test_director_curve_samples_tool_registered_as_readonly_schema():
    tools = await server.list_tools()
    by_name = {tool.name: tool for tool in tools}
    assert "rhino_director_curve_samples" in by_name

    schema = by_name["rhino_director_curve_samples"].inputSchema
    assert schema["type"] == "object"
    assert schema["required"] == ["curve_id", "frame_count", "sampling"]
    assert _find_rejected_schema_keywords(schema) == []

    properties = schema["properties"]
    assert properties["curve_id"]["type"] == "string"
    assert properties["frame_count"]["type"] == "integer"
    assert properties["frame_count"]["minimum"] == 1
    assert properties["frame_count"]["maximum"] == 5000

    sampling = properties["sampling"]
    assert sampling["type"] == "object"
    assert sampling["required"] == ["mode", "start", "end"]
    assert sampling["properties"]["mode"]["type"] == "string"
    assert "normalized_parameter" in sampling["properties"]["mode"]["description"]
    assert sampling["properties"]["start"]["minimum"] == 0
    assert sampling["properties"]["start"]["maximum"] == 1
    assert sampling["properties"]["end"]["minimum"] == 0
    assert sampling["properties"]["end"]["maximum"] == 1
```

- [ ] **Step 2: Add dispatch assertion**

Append this test:

```python
@pytest.mark.asyncio
async def test_director_curve_samples_tool_dispatches_to_native_route(monkeypatch):
    calls = []

    async def fake_call_rhino(endpoint, method="GET", data=None, port=None):
        calls.append((endpoint, method, data, port))
        return {
            "success": True,
            "data": {
                "schema_version": 1,
                "curve_id": data["curve_id"],
                "frame_count": data["frame_count"],
                "samples": [],
                "provenance": {
                    "sampling_mode": "normalized_parameter",
                    "validation_strength": "curve_parameter_sampled",
                },
            },
        }

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    request = {
        "curve_id": "00000000-0000-0000-0000-000000000001",
        "frame_count": 3,
        "sampling": {"mode": "normalized_parameter", "start": 0.0, "end": 1.0},
    }

    result = await server.call_tool("rhino_director_curve_samples", request)

    assert calls == [("/director/curve-samples", "POST", request, None)]
    assert "curve_parameter_sampled" in result[0].text
```

- [ ] **Step 3: Update group test expectations**

Replace `test_director_tool_groups_are_mcp_only` with:

```python
def test_director_tool_groups_include_curve_samples_readonly():
    assert "director" in tool_groups.TOOL_GROUPS
    assert "rhino_director_run" in tool_groups.TOOL_GROUPS["director"]
    assert "rhino_director_curve_samples" in tool_groups.TOOL_GROUPS["director"]
    assert "director_readonly" in tool_groups.TOOL_GROUPS
    assert "rhino_director_curve_samples" in tool_groups.TOOL_GROUPS["director_readonly"]
    assert "director" in tool_groups.MCP_ONLY_GROUPS
```

- [ ] **Step 4: Run tests and verify they fail**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_mcp_tools.py -q
```

Expected: the new tests fail because the MCP tool and group entries are not implemented yet.

- [ ] **Step 5: Commit failing MCP tests**

```powershell
git add mcp_server/tests/test_director_mcp_tools.py
git commit -m "test: pin Director curve samples MCP contract"
```

---

### Task 5: MCP Tool Schema, Dispatch, And Tool Groups

**Files:**
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/src/rook/agent/tool_groups.py`

- [ ] **Step 1: Add the MCP tool schema**

In `server.py`, add this `Tool` near `rhino_director_run`:

```python
Tool(
    name="rhino_director_curve_samples",
    description=(
        "Read-only RookVisionDirector primitive: sample a Rhino curve once per "
        "canonical frame using normalized curve parameters. This does not perform "
        "arc-length sampling and does not create cameras or capture frames."
    ),
    inputSchema={
        "type": "object",
        "required": ["curve_id", "frame_count", "sampling"],
        "properties": {
            "curve_id": {
                "type": "string",
                "description": "Rhino curve object GUID.",
            },
            "frame_count": {
                "type": "integer",
                "minimum": 1,
                "maximum": 5000,
                "description": (
                    "Canonical Director frame count produced by timeline or legacy "
                    "frame_count resolution. Native rejects values above 5000."
                ),
            },
            "sampling": {
                "type": "object",
                "required": ["mode", "start", "end"],
                "properties": {
                    "mode": {
                        "type": "string",
                        "description": "Must be normalized_parameter for v1.",
                    },
                    "start": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                        "description": "Start normalized curve parameter in [0, 1].",
                    },
                    "end": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                        "description": "End normalized curve parameter in [0, 1].",
                    },
                },
            },
        },
    },
),
```

- [ ] **Step 2: Add dispatch**

In `_call_tool_dispatch`, add this case beside `rhino_director_run`:

```python
case "rhino_director_curve_samples":
    result = await call_rhino("/director/curve-samples", "POST", arguments, port=port)
```

- [ ] **Step 3: Add tool groups**

In `mcp_server/src/rook/agent/tool_groups.py`, update the Director groups:

```python
"director": [
    "rhino_director_run",
    "rhino_director_curve_samples",
],
"director_readonly": [
    "rhino_objects",
    "rhino_views",
    "rhino_display_modes",
    "rhino_document",
    "rhino_director_curve_samples",
],
```

- [ ] **Step 4: Run MCP tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_mcp_tools.py -q
```

Expected: all tests in `test_director_mcp_tools.py` pass.

- [ ] **Step 5: Commit MCP implementation**

```powershell
git add mcp_server/src/rook/server.py mcp_server/src/rook/agent/tool_groups.py mcp_server/tests/test_director_mcp_tools.py
git commit -m "feat: expose Director curve samples MCP tool"
```

---

### Task 6: Live Director Route Tests

**Files:**
- Modify: `mcp_server/tests/test_director_routes_live.py`

- [ ] **Step 1: Add a curve creation helper**

Add this helper near `_create_brep` imports and local helpers:

```python
async def _create_line_curve(name: str) -> str:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "rhino_create",
        {
            "type": "LINE",
            "start": [0.0, 0.0, 0.0],
            "end": [10.0, 0.0, 0.0],
            "name": name,
        },
    )
    assert "id" in res, f"rhino_create returned no id: {res!r}"
    return res["id"]
```

- [ ] **Step 2: Add live success smoke**

Append this test:

```python
async def test_director_curve_samples_live_smoke_samples_line_curve(fresh_document):
    curve_id = await _create_line_curve(f"director_curve_samples_{uuid4().hex}")

    _, envelope = await _post_director(
        "curve-samples",
        {
            "curve_id": curve_id,
            "frame_count": 3,
            "sampling": {"mode": "normalized_parameter", "start": 0.0, "end": 1.0},
        },
    )

    assert envelope["success"] is True
    data = envelope["data"]
    assert data["schema_version"] == 1
    assert data["curve_id"] == curve_id
    assert data["frame_count"] == 3
    assert data["provenance"]["sampling_mode"] == "normalized_parameter"
    assert data["provenance"]["parameter_mapping"] == "curve_domain_parameter_at"
    assert data["provenance"]["frame_count_source"] == "caller_canonical_frame_count"
    assert data["provenance"]["arc_length_sampled"] is False
    assert data["provenance"]["validation_strength"] == "curve_parameter_sampled"

    samples = data["samples"]
    assert [sample["frame_index"] for sample in samples] == [1, 2, 3]
    assert [sample["normalized_parameter"] for sample in samples] == [0.0, 0.5, 1.0]
    _assert_vector_close(samples[0]["point"], [0.0, 0.0, 0.0])
    _assert_vector_close(samples[1]["point"], [5.0, 0.0, 0.0])
    _assert_vector_close(samples[2]["point"], [10.0, 0.0, 0.0])
    for sample in samples:
        _assert_vector_close(sample["tangent"], [1.0, 0.0, 0.0])
```

- [ ] **Step 3: Add required-field and upper-bound rejections**

Append this test:

```python
async def test_director_curve_samples_rejects_missing_sampling_fields_and_over_limit():
    curve_id = "00000000-0000-0000-0000-000000000001"

    for body, message in [
        ({"curve_id": curve_id, "frame_count": 1}, "sampling"),
        ({"curve_id": curve_id, "frame_count": 1, "sampling": {"start": 0.0, "end": 1.0}}, "sampling.mode"),
        ({"curve_id": curve_id, "frame_count": 1, "sampling": {"mode": "normalized_parameter", "end": 1.0}}, "sampling.start"),
        ({"curve_id": curve_id, "frame_count": 1, "sampling": {"mode": "normalized_parameter", "start": 0.0}}, "sampling.end"),
        ({"curve_id": curve_id, "frame_count": 5001, "sampling": {"mode": "normalized_parameter", "start": 0.0, "end": 1.0}}, "5000"),
    ]:
        _, envelope = await _post_director("curve-samples", body)
        assert envelope["success"] is False
        assert envelope["data"]["code"] == "invalid_input"
        assert message in envelope["data"]["message"]
```

- [ ] **Step 4: Add not-found and not-curve rejections**

Append this test:

```python
async def test_director_curve_samples_reports_expected_curve_contract_errors(fresh_document):
    missing_id = "00000000-0000-0000-0000-000000000001"
    _, missing_envelope = await _post_director(
        "curve-samples",
        {
            "curve_id": missing_id,
            "frame_count": 1,
            "sampling": {"mode": "normalized_parameter", "start": 0.0, "end": 1.0},
        },
    )
    assert missing_envelope["success"] is False
    assert missing_envelope["data"]["code"] == "curve_not_found"

    brep_id = await _create_brep(
        [0.0, 0.0, 0.0],
        [1.0, 1.0, 1.0],
        f"director_curve_samples_not_curve_{uuid4().hex}",
    )
    _, not_curve_envelope = await _post_director(
        "curve-samples",
        {
            "curve_id": brep_id,
            "frame_count": 1,
            "sampling": {"mode": "normalized_parameter", "start": 0.0, "end": 1.0},
        },
    )
    assert not_curve_envelope["success"] is False
    assert not_curve_envelope["data"]["code"] == "not_curve"
```

- [ ] **Step 5: Run live tests when Rhino is available**

Run:

```powershell
python -m pytest -m requires_rhino mcp_server/tests/test_director_routes_live.py -q
```

Expected when Rhino is available with the new native build loaded: the Director live route tests pass. Expected when Rhino is unavailable: tests skip through the existing `requires_rhino` path.

- [ ] **Step 6: Commit live tests**

```powershell
git add mcp_server/tests/test_director_routes_live.py
git commit -m "test: cover Director curve samples live route"
```

---

### Task 7: Focused Regression Pass

**Files:**
- No source edits expected.

- [ ] **Step 1: Run focused Python tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_mcp_tools.py mcp_server/tests/test_director_native_source.py mcp_server/tests/test_director.py mcp_server/tests/test_camera_planner.py mcp_server/tests/test_timeline.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run live route tests if Rhino is available**

Run:

```powershell
python -m pytest -m requires_rhino mcp_server/tests/test_director_routes_live.py -q
```

Expected: pass with Rhino/new native build available, or skip cleanly if Rhino is not discoverable outside the harness.

- [ ] **Step 3: Check whitespace**

Run:

```powershell
git diff --check
```

Expected: no output.

- [ ] **Step 4: Optional native build verification**

Run this only in the proper Windows/Rhino/MFC developer environment:

```powershell
cmd /c "call \"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat\" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

Expected: native build succeeds. If this command is not run, final status must say native build was not verified.

- [ ] **Step 5: Final commit if verification required additional fixes**

If Task 7 required fixes, commit only those scoped changes:

```powershell
git add src/RookNative/Handlers/DirectorHandler.h src/RookNative/Handlers/DirectorHandler.cpp src/RookNative/RookServer.h src/RookNative/RookServer.cpp mcp_server/src/rook/server.py mcp_server/src/rook/agent/tool_groups.py mcp_server/tests/test_director_mcp_tools.py mcp_server/tests/test_director_native_source.py mcp_server/tests/test_director_routes_live.py
git commit -m "fix: stabilize Director curve sample contract"
```

---

## Self-Review

- Spec coverage: the plan covers the native route, MCP exposure, read-only group membership, required sampling fields, upper bound, normalized-parameter-only mode, provenance, expected contract errors, invalid evaluated geometry, and focused verification.
- Scope check: no task changes `run_director`, `camera_planner`, `timeline`, `/director/frame-capture`, video, artifacts, or UI.
- Placeholder scan: no task uses incomplete marker text or vague "add tests" instructions.
- Type consistency: native uses `curve_id` externally, `curveUuid` internally, `frame_count` externally, `frameCount` internally, and the MCP schema matches native upper bound `5000`.
