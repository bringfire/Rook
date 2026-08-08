# Prime Agent Explicit Rook Gateway Interface Design

**Status:** Proposed qualification design; no implementation or live contact is authorized.

## Objective

Test one question:

> Does a clear Prime-native Python capability interface produce disciplined progressive discovery and execution?

V4 repeats the V3 mutation qualification with one changed experimental dimension: the disposable `rook_full` Python package exposes only three supported public functions:

```python
__all__ = ("search", "read", "call")

async def search(query: str):
    return await _integration.call_tool("rook_tools_search", {"query": query})

async def read(name: str):
    return await _integration.call_tool("rook_tools_read", {"name": name})

async def call(name: str, arguments: dict):
    return await _integration.call_tool(
        "rook_tools_call",
        {"name": name, "arguments": arguments},
    )
```

The selected model, natural intent, Rook profile, target custody, execution-skill body, kernel, launcher, and final-inspection evidence contract remain frozen.

## Evidence That Motivates V4

The single authorized V3 run established that Prime and Qwen could:

- load the reviewed execution skill;
- inspect Rook's live MCP capability surface;
- create and wire a native Grasshopper definition;
- observe a missing edge and stale epoch;
- apply a bounded correction; and
- verify authentic point previews with zero Grasshopper errors or warnings.

V3 produced seven components, six wires, and ten point values. It did not fully satisfy the intent because Y and Z were adjustable sliders rather than fixed values.

The run also exposed an API/documentation mismatch. The skill said to import `rook_full` and use `rook_tools_search`, `rook_tools_read`, and `rook_tools_call`, but did not show that those were attributes of the imported module. Qwen attempted to import nonexistent modules named after the tools, then used the inherited `list_tools()` and `call_tool()` escape hatches.

Every live operation still traversed Rook MCP, the full Rook profile, panel-locked targeting, and Rook-owned tool validation. V3 bypassed progressive-disclosure meta-tools; it did not bypass Rook authority.

## Disposable Boundary

V4 uses a fresh sibling directory:

```text
C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification-v4
```

No Rook or Prime product code changes are permitted. The V3 directory and all retained V3 evidence remain unchanged.

The V4 package is an experiment-specific affordance over Prime's existing `McpIntegration`, not a product API, security boundary, or permanent architecture decision.

## Supported Public API

The module's supported public API is exactly:

```python
__all__ = ("search", "read", "call")
```

It has:

- no module-level `__getattr__`;
- no exported integration instance;
- no public `list_tools()` or `call_tool()`;
- no arbitrary dynamic MCP methods; and
- no copied schemas, catalog, cache, retry, or fallback.

These are public-API constraints, not security claims. The IPython kernel retains normal user-level Python introspection and process permissions. The private integration necessarily retains its inherited lower-level methods internally.

## Private Integration And Transport Custody

One private `McpIntegration` subclass owns the existing stdio transport. Its `_open_session()` implementation and transport custody remain byte-identical to V3, including:

- deployed `python -m rook` command and working directory;
- stack-owned real `errlog` handle;
- MCP client initialization and closure order;
- full Rook profile;
- panel-locked process/document targeting; and
- deployed Rook environment variables.

No session pooling or performance change enters V4. Prime's existing per-call MCP-session behavior remains observable telemetry, not part of this experiment.

The private integration is not exported through `__all__` or a supported module attribute. V4 does not claim that Python introspection makes it unreachable.

## Exact Delegation

The public functions construct only these canonical envelopes:

```text
search(query)
-> private.call_tool("rook_tools_search", {"query": query})

read(name)
-> private.call_tool("rook_tools_read", {"name": name})

call(name, arguments)
-> private.call_tool(
     "rook_tools_call",
     {"name": name, "arguments": arguments},
   )
```

For `call()`, the exact caller-supplied `arguments` object reaches the private integration ingress as the envelope's `arguments` value. Python object identity is not claimed across JSON or MCP transport.

The wrappers do not parse, validate, normalize, catch, translate, or retry. Existing MCP result parsing remains authoritative. Returned values and raised exceptions pass through the wrappers unchanged.

`call()` may request any capability admitted by Rook. V4 adds no tool allowlist or Grasshopper topology knowledge; Rook retains schema validation, profiles, targeting, dispatch, and execution authority.

## Derived Execution Skill

The V4 skill receives one minimal Prime invocation preamble showing executable syntax:

```python
import rook_full

await rook_full.search("gh_edit")
await rook_full.read("gh_edit")
await rook_full.call("gh_edit", edit_arguments)
```

The preamble explains that live Grasshopper inspection and mutation use these three functions and that returned Rook evidence is required before reporting completion.

The reviewed execution body remains byte-identical to V3 from its first unchanged execution heading onward. V4 adds no witness topology, component choices, Y/Z hint, expected tool sequence, retry instruction, or semantic acceptance rule.

## Frozen Qualification Row

V4 preserves the V3 row except for sibling paths and fresh target values:

- model: `ollama/qwen3.6:35b`;
- API base: exact credential-free loopback Ollama endpoint;
- intent: exact unchanged natural request for adjustable Start, Step, and Count with Y and Z fixed at zero;
- skill and checkpoint paths plus hashes;
- full Rook profile; and
- complete panel-locked Rhino process/document target.

The target is frozen only after a fresh disposable canvas is prepared. Implementation and inert review authorize no Prime, Ollama, Rook MCP, Rhino, or Grasshopper contact.

## Deterministic No-Contact Tests

Inert tests prove:

1. `__all__` is exactly `("search", "read", "call")`;
2. the supported module API has no `__getattr__`, exported integration, `list_tools`, `call_tool`, or arbitrary dynamic methods;
3. `_open_session()` and its transport custody are byte-identical to V3;
4. each public function makes exactly one delegation to its corresponding canonical meta-tool envelope;
5. `call()` preserves the exact arguments object at private integration ingress;
6. returned object identity is preserved by the wrapper;
7. the exact raised exception object propagates without translation;
8. no wrapper parsing, schema copy, catalog, cache, retry, or fallback exists;
9. the V4 preamble uses only `rook_full.search/read/call`;
10. the appended execution body and checkpoint reference remain byte-identical to V3;
11. model, intent, kernel, launcher, targeting, and evidence behavior differ only by reviewed sibling paths and package identity;
12. the final inspector's sole Rook invocation changes only from V3's dynamic `rook_tools_call` attribute to `rook_full.call("gh_snapshot", arguments)`, while its request, eligibility, custody, and evidence writing remain unchanged; and
13. the entire suite performs zero external contact.

The delegation tests use one causal private-integration fake. They establish adapter structure before live contact; they do not fabricate a live qualification result.

## Evidence And Assessment

V4 adds no recorder. Prime's native JSON/session evidence, existing Rook evidence, and the one operator-owned final snapshot retain their current ownership.

### Gateway discipline

The assessment reports:

- visible IPython use of public `rook_full.search`, `rook_full.read`, and `rook_full.call`;
- any attempted lower-level, dynamic, or private bypass;
- whether a full tool catalog reached model context; and
- the exact focused search/read/call inputs and returned observations visible in retained evidence.

Prime's trace can directly prove calls to the three public Python functions. It cannot independently observe which internal MCP meta-tool the wrapper dispatched. Given the pre-contact verified adapter hash and exact delegation tests, those calls are structurally bound to the corresponding canonical meta-tool envelopes. No independent runtime event directly observes that internal dispatch.

If evidence cannot establish an exact live fact, the assessment reports it as unknown rather than reconstructing it.

### Mechanical Grasshopper outcome

The independent final snapshot retains exact components, wires, previews, errors, and warnings. It is taken under the existing V3 eligibility and custody rules and remains evidence rather than a verdict.

### Semantic fidelity

Assessment separately asks whether retained evidence establishes:

- adjustable Start, Step, and Count controls;
- the requested point row along X;
- Y and Z fixed rather than adjustable; and
- no runtime errors.

Clean diagnostics and plausible wiring do not establish semantic fidelity. V4 adds no critic or automatic score.

### Observational telemetry

IPython call count, elapsed time, cumulative input/output tokens, stale-epoch events, and model corrections are reported as observations only. Cost and latency are not truth criteria.

Gateway discipline, mechanical outcome, and semantic fidelity remain independent conclusions.

## Anti-Quagmire Boundary

Stop and return for review if V4 would require:

- a Rook or Prime repository code change;
- a native Prime extension;
- copied Rook schemas or tool catalogs;
- session pooling or transport optimization;
- model-facing enforcement beyond the supported public API;
- a new recorder, event vocabulary, result taxonomy, or scoring system;
- witness-specific instructions;
- another model or intent; or
- more than one separately authorized live run and one final inspection.

## Authorization And Stop Condition

After implementation, inert verification, and independent pre-contact review, V4 requires a fresh frozen row and explicit authorization for exactly one live run.

The experiment stops after retaining and assessing that run. No operator rerun, adapter retry, cleanup, or additional inspection is implied.

Interpretation follows this gate:

- disciplined gateway use permits evaluation of Grasshopper competence;
- a semantic miss remains model evidence and does not authorize witness-specific prompting;
- persistent latency is investigated separately without changing V4; and
- abandonment of the explicit public API would justify considering native Prime tools in a separately designed experiment.
