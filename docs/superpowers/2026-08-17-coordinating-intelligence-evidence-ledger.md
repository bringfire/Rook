# Coordinating Intelligence Evidence Ledger

**Status:** First-pass evidence inventory; interpretation intentionally limited

**Inventory date:** 2026-08-17

**Rook inventory baseline:** `f840069a58d0a5ee297ae817f0b3efe7a9287512`

**Purpose:** Collect and organize the evidence that bears on Rook's coordinating-intelligence architecture before producing a new architecture synthesis.

## 1. Reading Rule

This document is an inventory, not an architecture decision.

It records:

- what a source proposed;
- what an experiment or runtime artifact observed;
- the result classification used by that source;
- what the source explicitly did not establish;
- where the evidence currently resides; and
- whether the relevant implementation is present on the inventory baseline.

It does not yet decide which mechanisms should be retained, reframed, suspended,
or retired. Those dispositions remain `unassessed` until a separate interpretive
pass.

Passing tests establish the tested contract, not broader semantic adequacy.
Design documents establish intended contracts, not runtime success. A model
failure, harness failure, operator error, runtime-custody error, and product
defect remain separate observations.

## 2. Scope

The ledger covers the evidence most directly related to:

- local and frontier model allocation;
- the bounded Worker box;
- Planner and compiler behavior;
- Prime as a persistent reasoning runtime;
- Rook's model-facing gateway and Grasshopper capability surface;
- component discovery and identity handoff;
- mutation receipts and solve-fenced observation;
- deterministic behavioral acceptance and repair;
- empirical model qualification;
- the knowledge system where it intersects these paths; and
- Phase A and Phase B of the proposed acceptance workflow router.

The chronological center of gravity is 2026-06-19 through 2026-08-17. Earlier
knowledge and topology documents are included where they directly supplied a
premise used by the later work. Unrelated BIM, media, release, and product UI
work is outside this ledger.

## 3. Evidence And Verification Vocabulary

### 3.1 Source classes

| Code | Source class | Meaning |
|---|---|---|
| `C` | Current canonical | Live code or current architecture documentation on the inventory baseline. |
| `H` | Historical merged | Merged specification, plan, report, milestone, probe summary, or commit retained as history. |
| `B` | Reviewed branch-local | Reviewed work in a clean worktree that is not reachable from the inventory baseline. |
| `L` | Retained local | Disposable runtime artifacts outside Git, normally under `AppData/Local/Temp` or `.rook`. |
| `D` | Design-only | An intended architecture or contract without corresponding runtime qualification. |

Source classes can be combined. For example, `H+L` means a merged milestone
describes retained local evidence.

### 3.2 Result terms

The `recorded result` column preserves the source's own bounded result whenever
possible:

| Term | Meaning in this ledger |
|---|---|
| `pass` or `accepted` | The stated acceptance boundary passed. |
| `fail` or `not_qualified` | The stated acceptance boundary completed and did not pass. |
| `incomplete` or `inconclusive` | The evidence boundary did not authorize a semantic pass/fail conclusion. |
| `observed` | A fact was measured without a pass/fail claim. |
| `design-only` | A proposal or intended contract, not a runtime result. |
| `current-state` | Presence or behavior read from current code/documentation. |
| `superseded` | The source remains historical but no longer governs active sequencing. |
| `unassessed` | The inventory has located a question or absence but has not adjudicated it. |

These terms are not normalized into a score.

### 3.3 Verification depth

| Value | Meaning |
|---|---|
| `primary-read` | This pass read the primary report, milestone, code, or retained result. |
| `source-located` | The source and custody identifiers were located, but the full raw run was not replayed. |
| `reported` | The result is retained in a reviewed source; independent raw-artifact reconstruction remains for the deep pass. |

## 4. Custody Snapshot

### 4.1 Repository state

| Repository/lane | Observed state on 2026-08-17 |
|---|---|
| Rook inventory worktree | Clean at `f840069a58d0a5ee297ae817f0b3efe7a9287512`. |
| Active Rook roadmap | `docs/roadmaps/2026-08-02-compositional-agent-harness-roadmap.md`. |
| Phase A/B worktree | Clean at `8a4572543f4e7a55fc13b41f985124e02a2523b4`; not reachable from the inventory baseline. |
| Prime working checkout | Clean `main` at `c98941a2a5cf40faecf9b4648ac3c304abf48fd3`. |
| Prime reviewed fork merge | `27b5be22cf0e0e81e324a59ebabbb41edfee6ec0`, containing structured-error commit `30a6621bca698ef14f64e5e45c5b1b6364148789`. |
| Prime upstream observed | `origin/main` at `9bf49d897c22563f3e4483d28149c1aac452a6f9`; no compatibility conclusion is made here. |

### 4.2 Retained local evidence

A name-filtered inventory found 41 principal experiment roots containing
332,558 files and approximately 8.36 GiB. Much of that size is duplicated
runtime and environment material; it is not equivalent to 8.36 GiB of unique
evidence. The roots were last written between 2026-08-08 and 2026-08-17.

The principal families are:

| Family | Retained roots | Representative custody artifact |
|---|---:|---|
| Prime full-mutation V3-V7 | 5 | V4 `operator/manifest.json`, file SHA-256 `72A9CF8E6370E39DC14F0E7984F14187061BA36D33F8B2F1F6722CC38BC64D59` |
| Native discovery and user-object provenance | 5 | Discovery V2 `manifest.json`; provenance V2 `manifest.json` |
| Post-merge discovery | 2 | `evidence-hashes.json`, SHA-256 `FA1E4D0EFF0BFA4A40FDE47505AAF2A13CA6D24352DF4B8598ACCE8B28CEF0E2` |
| Opus/Qwen and Nemotron comparisons | 3 principal roots | Operational-comparison control/local manifests and runtime manifest |
| Point-row and XY-grid repair loops | 8 principal roots | Per-run `operator/manifest.json` and evaluation artifacts |
| Solve-fenced Gate B and repair loops | 9 principal roots | Gate B evidence manifests and V3-V5 evaluation artifacts |
| Qwen3.8 campaign and helix | 3 | Campaign report SHA-256 `7989E3CC2A1C68DF2CDCE7D42C445B7DD07F4995DA4750C13309D3799891B560`; helix V2 manifest file SHA-256 `40C3F6FA9189DD337D7982A3B808275DECDDB6269916A8C99242315790EC555C` |
| Acceptance handoff and Phase A/B | 10 | Phase A V4 evidence manifest `FB8A376BD9EBA48AE1BC904A6F4CA2701B6E2596E71E0EC711F3E278618B5F46`; Phase B public/private manifests |

Manifest-file hashes and hashes declared inside manifests are separate facts.
The deep pass must preserve that distinction and must not describe one as the
other.

## 5. Current Runtime And Program Documents

| ID | Observation | Recorded result | Explicit boundary/nonclaim | Source | Class | Verification |
|---|---|---|---|---|---|---|
| `CUR-01` | RookNative is the sole public Rhino plugin and HTTP server. Grasshopper remains companion-backed through managed callbacks. | `current-state` | This is runtime ownership, not an agent-quality result. | `docs/CURRENT_ARCHITECTURE.md` | `C` | `primary-read` |
| `CUR-02` | MCP and Chat are separate public model-facing paths that converge at the HTTP bridge. Internal agent modules call native endpoints directly through `bridge.py`. | `current-state` | MCP behavior does not automatically establish internal-agent behavior, or vice versa. | `docs/AGENT_ARCHITECTURE.md` | `C` | `primary-read` |
| `CUR-03` | The repository retains Planner, Worker, Guardian, Conductor, PlanGraph, semantic-graph, and local-worker modules. Autonomous MCP creation entry points are lifecycle-contained. | `current-state` | Module presence does not establish that a general Planner path is active in the product. | Current code; `docs/CURRENT_ARCHITECTURE.md`; `docs/AGENT_ARCHITECTURE.md` | `C` | `primary-read` |
| `CUR-04` | The active roadmap separates a Planner-owned semantic design graph from a deterministic execution PlanGraph. | `design-only` | The roadmap explicitly excludes a universal IR and does not itself prove general semantic planning. | `docs/roadmaps/2026-08-02-compositional-agent-harness-roadmap.md` | `C+D` | `primary-read` |
| `CUR-05` | The roadmap index says live code/current architecture govern existence, while active roadmaps govern sequencing and historical experiments do not authorize work. | `current-state` | Historical evidence remains relevant but is not current authorization. | `docs/roadmaps/README.md` | `C` | `primary-read` |

## 6. Architecture And Knowledge Precursors

| ID | Observation | Recorded result | Explicit boundary/nonclaim | Source | Class | Verification |
|---|---|---|---|---|---|---|
| `ARC-01` | The June multi-file North Star proposed one scarce cloud coordinator and many cheap/local file workers, with recomposition across Rhino files. | `design-only` | Its initial read-only session slice did not establish multi-file mutation, fan-in, or cross-machine coordination. | `docs/superpowers/specs/2026-06-03-rook-north-star-topology.md` | `H+D` | `primary-read` |
| `ARC-02` | That North Star described the knowledge graph as an intelligence subsidy for the cheap tier. | `design-only` | The statement is an architectural premise, not a measured knowledge-effectiveness result. | Same source, section 2 | `H+D` | `primary-read` |
| `ARC-03` | The local/internal-model North Star classified local models as bounded executors whose plan, contracts, memory, and verification are held outside the model. | `design-only` | It did not establish the limits of any particular model or the sufficiency of the proposed scaffold. | `docs/superpowers/specs/2026-06-19-rook-local-internal-models-north-star.md` | `H+D` | `primary-read` |
| `ARC-04` | The three-box Planner/Runner/Worker document allocated semantic authoring to a Planner, runtime advancement to deterministic code, and bounded implementation work to Workers. | `superseded` | The document identifies itself as historical and not independently implementation-authorizing. | `docs/superpowers/specs/2026-07-02-rook-planner-harness-north-star.md` | `H+D` | `primary-read` |
| `ARC-05` | The July semantic-harness accounting described the architecture as directionally complete but transitionally incomplete. | `observed` in architecture accounting | The LM9 ladder is historical and no longer governs active product sequencing. | `docs/superpowers/specs/2026-07-23-rook-semantic-harness-architecture-accounting.md` | `H+D` | `primary-read` |
| `KG-01` | Rook contains a knowledge graph, knowledge visualizer work, and four documented knowledge seams in `RookAgent`. | `current-state` | Presence and integration do not establish useful retrieval quality. | `docs/rook_docs/2026-04-10-knowledge-graph-visualizer-spec.md`; `docs/AGENT_ARCHITECTURE.md` | `C+H` | `primary-read` |
| `KG-02` | Production Grasshopper discovery explicitly excludes knowledge from component identity, native ranking, provenance, and ambiguity decisions. | `pass` for the qualified discovery specimen | This does not remove knowledge as possible advisory context and does not establish knowledge or DSPy effectiveness. | Discovery specification and live milestone | `H+L` | `primary-read` |
| `KG-03` | No reviewed source in this first pass establishes a controlled positive effect of the existing knowledge graph on the later Prime/Qwen Grasshopper tasks. | `unassessed` | Absence from this inventory is not proof that no such evidence exists; the deep pass must search specifically for it. | First-pass source inventory | `C+H+B+L` | `source-located` |

## 7. Bounded Worker Evidence

| ID | Observation | Recorded result | Explicit boundary/nonclaim | Source | Class | Verification |
|---|---|---|---|---|---|---|
| `WRK-01` | In LM5K rounds 1/1b, Qwen3:14b and Sonnet produced strict schema-correct responses while refusing or clarifying an incoherent fixture. The fixture expected a repair action before the graph made that work ready. | Fixture defect; bounded-worker safety behavior passed | The original 0/5 spine result was not a model or prompt failure. | `docs/superpowers/probes/2026-07-02-lm5k-first-worker-model-probe.md`, lines 75-110 | `H` | `primary-read` |
| `WRK-02` | In the paired LM5N evidence test, Qwen3:14b produced 5/5 clarification responses without repair evidence and 5/5 action requests with repair evidence; Sonnet showed the same behavior modulo one allowed refusal in the absent condition. | `pass` for the paired evidence question | One fixture did not establish broad Worker competence. Haiku and Gemma had separate output-envelope failures in adjacent tests. | Same probe summary, LM5N section | `H` | `primary-read` |
| `WRK-03` | LM6A joined a real failed Grasshopper compile receipt to one Gemma Worker action and a verified `gh_update_script` repair. Hidden answer markers were absent. | `accepted` once | One forced repair fixture did not establish arbitrary repair ability. | Same probe summary, LM6A section; merge `0d02180a` | `H` | `primary-read` |
| `WRK-04` | LM6C reached the Worker path 5/5, accepted 4/5, and recorded one clean decline. LM6E then accepted 5/5 with the retry variant enabled but never exercised the retry. | Pooled 9/10 accepted, 1/10 clean decline | The evidence did not prove retry recovery or broad reliability. | Same probe summary, LM6C/LM6E sections | `H` | `primary-read` |
| `WRK-05` | LM8C opened a scalar task family; LM8F/LM8G added scalar-transform pressure and repeatability. | Narrow accepted scalar-family results | These runs did not establish topology, wiring, batch editing, or Planner competence. | Same probe summary, LM8C-LM8G sections | `H` | `primary-read` |
| `WRK-06` | LM8J's affine scalar fixture accepted 20/20. The Worker repeatedly derived editable value `3.0` from expected output `7.5`, factor `2.0`, and offset `1.5`. | `accepted` 20/20 | Publication-support recovery was available but unexercised; broad scalar reasoning was not established. | Same probe summary, LM8J section | `H` | `primary-read` |
| `WRK-07` | LM8M repeated the affine fixture 20/20 using one managed readiness wait and one fenced read per attempt, with zero settle reads. | `accepted` 20/20 | This did not establish receipt coverage for other mutators or larger definitions. | Same probe summary, LM8M section; merge `3dddf920` | `H` | `primary-read` |
| `WRK-08` | Current main retains the local Worker context, prompt artifact, adapter, response, disposition, harness, acceptance-source, PlanGraph, and Worker action modules. | `current-state` | Retention does not mean every historical experiment remains an active product path. | `mcp_server/src/rook/agent/` | `C` | `primary-read` |

## 8. Planner, Compiler, And Composition Evidence

| ID | Observation | Recorded result | Explicit boundary/nonclaim | Source | Class | Verification |
|---|---|---|---|---|---|---|
| `PLN-01` | LM7C's GPT-5.5 Planner emitted parseable JSON 10/10 but passed `workflow_validate` 0/10 under sparse field guidance. It invented no missing intent values. | Request-surface learnability failure; safety restraint held | This was not a general Planner failure. | LM5K probe summary, LM7C section | `H` | `primary-read` |
| `PLN-02` | With isolated shape guidance and no solved request exemplar, the same Planner configuration passed parse, validation, intent classification, and canonical-success checks 10/10. | `pass` for the constrained request surface | This did not establish broad Planner reliability or live integration. | Same source, LM7D section; merge `8ce8e042` | `H` | `primary-read` |
| `PLN-03` | LM7E joined one model-authored valid Planner request to the existing bounded Worker path and reached `verify_repair_succeeded`. | `accepted` once | It did not establish arbitrary workflow authorship or a new Worker protocol. | Same source, LM7E section; merge `0a3506b9` | `H` | `primary-read` |
| `CMP-01` | LM9B-C first demonstrated semantic lowering but emitted the wrong C# representation. A bounded follow-up using the unchanged semantic contract passed Rook's exact script signature boundary, compiled through the live path, and satisfied four compiler-authored obligations. | Bounded lowering demonstrated once | It did not establish Planner authorship, compiler reliability, or product authorization. | `docs/superpowers/probes/2026-07-19-lm9b-c-compiler-sufficiency-result.md` | `H+L` | `primary-read` |
| `CMP-02` | LM9B-P's planned Planner recipe-transfer attempt failed provider configuration before the first model turn. No recipe existed and the compiler stage was not entered. | `probe_inconclusive` | It supplies no evidence for or against Planner recipe authorship or unchanged transfer. | `docs/superpowers/probes/2026-07-20-lm9b-p-planner-recipe-transfer-result.md` | `H+L` | `primary-read` |
| `CMP-03` | The minimal intent-to-Worker real compile specimen joined one frontier Planner call, one local Worker repair, deterministic orchestration, a real failed compile receipt, and final clean compilation. | `pass` once for a fixed no-input, one-output C# specimen | It did not establish output correctness, repeatability, arbitrary interfaces, or product entry. | `docs/superpowers/2026-07-31-minimal-intent-worker-real-compile-milestone.md` | `H+L` | `primary-read` |
| `CMP-04` | A representation audit found the retrospective v2 recipe graph omitted authoritative GUID/port semantics and allowed partial runtime mutation. It recommended a small prospective semantic representation. | Audit decision | This was a design audit, not live qualification of the replacement. | `docs/superpowers/reports/2026-08-02-compositional-harness-representation-fit-audit.md` | `H+D` | `primary-read` |
| `CMP-05` | Compositional Slice 1 used one Planner call and one `gh_edit` per witness to materialize a point row and a structurally different square grid. | `pass` for two structural witnesses | No output-value correctness, repeatability, Worker participation, or broad intent coverage was established. | `docs/superpowers/2026-08-03-compositional-harness-slice1-live-qualification-milestone.md` | `H+L` | `primary-read` |
| `CMP-06` | Compositional Slice 2 partitioned one Planner-authored graph into one C# Worker leaf and one deterministic region, then connected the receipt-derived C# output identity to Construct Point. | `pass` once | It did not establish runtime value correctness, variable interfaces, multiple Worker leaves, or repair. | `docs/superpowers/2026-08-03-compositional-harness-slice2-live-qualification-milestone.md` | `H+L` | `primary-read` |

## 9. Prime, Gateway, Discovery, And Tool-Surface Evidence

| ID | Observation | Recorded result | Explicit boundary/nonclaim | Source | Class | Verification |
|---|---|---|---|---|---|---|
| `PRM-01` | A local model in Prime loaded an explicit skill, discovered one Rook capability without the full catalog, called it through the canonical MCP gateway, and interpreted a readonly result. | `pass` for one supervised readonly specimen | Mutation, arbitrary intent, repeatability, delegation, and OS isolation were not established. | `docs/superpowers/2026-08-05-prime-agent-readonly-qualification-milestone.md` | `H+L` | `primary-read` |
| `GWY-01` | PR #553 added additive structured MCP success/failure envelopes and truthful `isError` while retaining legacy text. | Merged and test-qualified | This corrected protocol projection, not model semantic judgment. | Merge `4bf6fad8`; structured-result specification/tests | `C+H` | `source-located` |
| `DSC-01` | Native discovery Task 0 observed 1,890 proxies, stable native order for seven fixed queries, 53 duplicate exact-name groups, and eligible third-party specimens. | Qualification report recommends native search | It did not settle all user-object provenance from the first probe. | `docs/superpowers/reports/2026-08-08-grasshopper-native-component-discovery-qualification.md`; retained V2 root | `H+L` | `primary-read` |
| `DSC-02` | The separate user-object qualification established installation-local `.ghuser` identity from proxy GUID, exact path, description, and content fingerprint; runtime assembly/BaseGuid were not treated as package identity. | `pass` for six retained specimens | It did not establish portable package identity. | `docs/superpowers/reports/2026-08-09-grasshopper-user-object-provenance-qualification-v2.md`; retained V2 root | `H+L` | `reported` |
| `DSC-03` | The post-merge five-call qualification returned duplicate Angle candidates without guessing, truthful Range truncation, a live `.ghuser` candidate, compiled and `.ghuser` metadata, and an unchanged audit shape. | `pass` | It did not establish model efficiency, every plugin, or cross-install identity. | `docs/superpowers/2026-08-11-grasshopper-component-discovery-live-qualification-milestone.md`; evidence hash manifest | `H+L` | `primary-read` |
| `DSC-04` | The qualification path exposed three separate pre-pass defects: stale runtime deployment custody, reading `Exposure` from the wrong host owner, and mismatched catalog/search/ambiguity candidate shapes. Each received a bounded correction before the final pass. | Sequential defects corrected | The final pass does not erase the defect history. | PRs #558 and #559; failed qualification artifacts and reviewed reports | `H+L` | `reported` |
| `GWY-02` | PR #561 changed contained calls so unknown top-level arguments are rejected before dispatch instead of silently degrading into another operation mode. | Merged; direct live rejection observed | It did not guarantee models would read schemas or succeed semantically. | Merge `c1343bac`; strict-admission artifacts | `C+H+L` | `source-located` |
| `GWY-03` | The current model-facing creation boundary redirects Python/C# script identities from ordinary component creation to canonical script helpers. | `current-state` | Raw `/gh/create-component` remains capability-neutral and unadvertised; the guard is not hostile-code containment. | `docs/CURRENT_ARCHITECTURE.md`; merge `bc5c0b15` | `C` | `primary-read` |
| `PRM-02` | Prime commit `30a6621b` preserves exact structured MCP failure content in `McpToolError` while retaining exception control flow. Rook records authentic structured failures before re-raising. | Infrastructure boundary `pass` | This does not establish semantic acceptance. | Prime fork merge `27b5be22`; Rook commit `7d6920d4`; structured-error milestone | `C+H+L` | `primary-read` |

## 10. Receipt And Solve-Fenced Evidence

| ID | Observation | Recorded result | Explicit boundary/nonclaim | Source | Class | Verification |
|---|---|---|---|---|---|---|
| `RCP-01` | Script post-mutation receipts and MCP receipt unwrapping predate the managed solve-readiness work. | Merged contract slices | Script receipt evidence and solve-readiness evidence are distinct. | LM1D and LM4F specifications/plans; merges `e5624d50`, `7a1f8b1b` | `H` | `source-located` |
| `RCP-02` | LM8K issued one pending receipt for `gh_set_value`, correlated it to `solution_end`, and admitted one receipt-fenced output read. | `accepted` once without a model | It did not establish other mutators, document replacement, registry capacity, or heavier definitions. | LM5K probe summary, LM8K section; merge `425acaf8` | `H` | `primary-read` |
| `RCP-03` | LM8M repeated the affine Worker fixture 20/20 with one readiness wait and one fenced read per attempt. | `accepted` 20/20 | Scope remained one scalar fixture and one mutation route. | LM5K probe summary, LM8M section | `H` | `primary-read` |
| `RCP-04` | PR #565 expanded the receipt/fence boundary to covered terminal authoring routes and introduced a caller-owned trace plus deterministic behavioral acceptance. | Merged and test-qualified | Freshness is bounded to the closed trace and managed fence; unobserved out-of-band mutation remains outside the claim. | Merge `61c686c5`; `docs/CURRENT_ARCHITECTURE.md`; solve-fenced specification | `C+H` | `primary-read` |
| `RCP-05` | Model-free Gate A exercised a real receipt, wait, fenced snapshot, perturbation/restoration path, and stale-receipt refusal. | Reported `pass` | Gate A did not establish Qwen behavior. | `rook-solve-fenced-live-20260813-070216` retained artifacts | `L` | `reported` |
| `RCP-06` | The first Gate B attempt was incomplete because a qualification adapter import failed after Qwen activity; no authentic terminal receipt was retained. | `incomplete` | It was classified as orchestration failure, not deployed receipt failure. | Same retained root, `gate-b-result.json` SHA-256 `AC127E42AF45231E0723AFFAF0242AFCFBDEA39E432A718182CE03B56CC59A4F` | `L` | `primary-read` |
| `RCP-07` | Gate B V2 was incomplete because an earlier `McpToolError` invalidated the complete trace even though a later authentic terminal receipt existed. | `incomplete` | No behavioral probe calls were authorized. | `rook-solve-fenced-gate-b-v2`; evidence manifest `030165216D5D1AF56ABCA2F4195D8424AB0EA6FAF65915CBDB5D915AF35E3AD3` | `L` | `primary-read` |
| `RCP-08` | After structured-error custody, Gate B V3 selected the latest committed receipt and reached a fenced snapshot. Evaluation stopped because `S/P/C` did not satisfy exact Start/Step/Count bindings. | Infrastructure `pass`; semantic result `incomplete` | No control-role inference or semantic reinterpretation was authorized. | Structured-error milestone; V3 evidence manifest `02C0954151A7AAF6A8751120552CEA665F96796C84B7BD5F5C5CD6D369B29057` | `H+L` | `primary-read` |
| `RCP-09` | A later repair-loop V3 run ended with a group-only `gh_edit` after the last solve receipt. The frozen rule classified the run `later_unfenced_mutation`. | `incomplete` | The mechanically plausible graph was not behaviorally admitted. | `rook-solve-fenced-repair-loop-v3/operator/initial-evaluation.json`, SHA-256 `DE5B955B43A370F5677ABF0472ECA3D09685B1973031BA32570ACEC727517D44` | `L` | `primary-read` |

## 11. Deterministic Acceptance And Repair Evidence

| ID | Observation | Recorded result | Explicit boundary/nonclaim | Source | Class | Verification |
|---|---|---|---|---|---|---|
| `ACC-01` | The first committed offline point-row evaluator used one JSON artifact, one Python evaluator, and one focused test file. It classified retained Opus evidence `pass` and retained Qwen evidence `fail`. | Historical qualification reported 20/20 focused tests after authority repairs | It covered one task and reviewed primitive semantics; it was not a general acceptance language. Current-checkout test behavior is recorded separately in `ACC-08`. | `scripts/grasshopper_point_row_acceptance.json`; `scripts/grasshopper_point_row_acceptance.py`; focused tests | `H+C` | `primary-read` |
| `ACC-02` | In point-row V1, deterministic feedback rejected abbreviated controls and one same-session Qwen continuation repaired them. V2 passed initially. V3 repaired the same label class. | V1 `repaired_pass`; V2 `initial_pass`; V3 `repaired_pass` | Three successes did not establish repair of wrong topology or a different intent. | Point-row V1-V3 retained evaluations and manifests | `L` | `primary-read` |
| `ACC-03` | The XY-grid V1 evaluator stopped before perturbation because required control binding failed. After one repair only `Rows` was admitted; the final result had one point and diagnostics. | `fail` after one repair | The run showed gate behavior but not general grid competence. Its evaluator added substantial task-specific logic. | `prime-rook-qwen-xy-grid-repair-loop-v1/operator/evaluation-2.json`, SHA-256 `361E8978886B2502BBB7BA7E6E7A325C277013B0A4320DE5F2FD42347F2A0CC5` | `L` | `primary-read` |
| `ACC-04` | Current `gh_behavioral_acceptance.py` combines source custody, trace closure, receipt selection, probing, restoration, projection, and evaluation in one module. | `current-state`; 105/105 focused module tests passed on the inventory worktree | Module size observed in this pass: 2,177 nonblank lines (2,349 physical lines). Size alone is not a correctness or design verdict. | `mcp_server/src/rook/gh_behavioral_acceptance.py`; `mcp_server/tests/test_gh_behavioral_acceptance.py` | `C` | `primary-read` |
| `ACC-05` | The current evaluator's closed predicate switch contains seven predicates: controls present, diagnostic-error count, point count equals one control, point count equals a product, one axis equals a constant, one axis equals a sequence, and axes form a Cartesian product. | `current-state` | Unsupported predicates return `None` and become unproven through the evaluation boundary. Coverage beyond this vocabulary is not established. | Same module, `_predicate_passes` | `C` | `primary-read` |
| `ACC-06` | Solve-fenced V4 made zero mutations after Qwen misread the adapter's `{success,data}` envelope and used an invalid metadata argument without first reading that schema. | `incomplete`, `latest_terminal_receipt_missing` | The lifecycle instruction was not exercised; this was not a semantic verdict on a graph. | `rook-solve-fenced-repair-loop-v4/operator/initial-evaluation.json`, SHA-256 `5ADA70A76B1BE7F43E4DEAD8465062DCB357B3F687B51DA35CE3A47C3C7A8FF0` | `L` | `primary-read` |
| `ACC-07` | Disposable V5 changed the Prime-facing adapter to record the full envelope but return the exact payload. Qwen then built a correct graph after one same-session control-label repair. | Initial `incomplete`; final `pass`, 8/8 criteria | This changed a disposable adapter/skill, not Rook or Prime product code, and did not establish generality. | V5 initial/final evaluations; precontact manifest `926691EA7520A5BD66E3C8ED8E85A776D47CF79C79D855486F7466E4DCA3ACC1` | `L` | `primary-read` |
| `ACC-08` | On the clean inventory worktree, the current point-row wrapper test ran 3/7 and failed four canonical-byte checks because tracked LF JSON artifacts were checked out as CRLF with no `eol` attribute. | Current focused wrapper test `fail`; 3 passed, 4 failed | This is a Windows checkout/canonical-custody observation. The 105-test common evaluator seam passed separately, so this result does not by itself classify evaluator semantics. | `mcp_server/tests/test_grasshopper_point_row_acceptance.py`; `git ls-files --eol` | `C` | `primary-read` |

## 12. Empirical Model Evidence

| ID | Observation | Recorded result | Explicit boundary/nonclaim | Source | Class | Verification |
|---|---|---|---|---|---|---|
| `MOD-01` | Under one frozen Prime/Rook task, Opus produced the requested Series topology in 8 IPython cells and 9 gateway calls. Qwen3.6 produced a mechanically valid but semantically wrong graph in 54 cells and 95 calls. | Opus semantic `pass`; Qwen semantic `fail` | The comparison was operational, not weights-only. It did not establish a universal model ranking. | `docs/superpowers/2026-08-11-prime-opus-qwen-operational-comparison-milestone.md` | `H+L` | `primary-read` |
| `MOD-02` | That Qwen run used `query` instead of `search`; Rook silently entered catalog mode. The same run also ignored relevant schemas and falsely claimed success. | Interface defect and model defect recorded separately | Strict admission was not predicted to guarantee Qwen success. | Same milestone | `H+L` | `primary-read` |
| `MOD-03` | After strict admission, a controlled Qwen retest used correct ranked discovery but substituted Range/EndX/steps for Series/Step/Count and produced 11 points for Count 10. | Semantic `fail`; gateway discipline passed | The result removed malformed argument acceptance as the explanation for the semantic substitution. | `prime-rook-qwen-strict-retest-v1` retained root | `L` | `reported` |
| `MOD-04` | Nemotron 3.5 Lightning created Start/Step/Count and Series, then failed to resolve ambiguous Construct Point and falsely reported completion. Its Prime stream lacked final lifecycle events. | Mechanical partial result; row `incomplete` | Ambiguity protection prevented a guessed component. No final operator inspection was authorized. | `prime-rook-nemotron-strict-qualification-v1` retained root | `L` | `reported` |
| `MOD-05` | Informal direct Ollama probes changed only model/reasoning setting. Qwen3.6 low/medium/high produced canonical, incorrect-contract, and workaround answers respectively; Nemotron low/medium/high produced three different correct/overbuilt variants. | Single-sample observations | They are not benchmark scores or a universal reasoning-level ordering. | `docs/superpowers/2026-08-14-empirical-model-intelligence-principle.md`, motivating observation | `H` | `primary-read` |
| `MOD-06` | The empirical principle separates raw capability, grounded capability, and operational capability, and describes model capability as contextual and partially observed. | Guiding principle | This is a methodological conclusion, not a measured model capability by itself. | Same document | `C+D` | `primary-read` |
| `MOD-07` | Qwen3.8 completed exact point row, open point row, and open XY grid tasks on fresh canvases. The grid used receipt-fenced perturbation/restoration and recovered from partial edits within the Actor turn. | Three observed behavioral successes | No general reliability, efficiency, universal topology competence, or untested-component performance was established. | `docs/superpowers/2026-08-15-qwen38-grasshopper-capability-campaign-milestone.md`; retained campaign root | `H+L` | `primary-read` |
| `MOD-08` | Qwen3.8 helix V1 was interrupted without `agent_end`; V2 produced an adjustable 72-point helix and curve, passed seven criteria, and restored five perturbed controls. | V1 `incomplete`; V2 `initial_pass` | V1 causation was suspected but not proven. V2 is one helix specimen, not general geometry competence. | `rook-qwen38-gh-helix-qualification-v1/v2`; V2 evaluation SHA-256 `63E114F13C55402164BD47A2710211784C816F3E69756401C0276FBA94ED7738` | `L` | `primary-read` |

## 13. Acceptance Workflow Router Phase A And B

These sources are branch-local and do not alter the inventory baseline.

| ID | Observation | Recorded result | Explicit boundary/nonclaim | Source | Class | Verification |
|---|---|---|---|---|---|---|
| `PH-01` | The first Constructor handoff produced a closed artifact whose claims referenced undeclared role IDs. Mechanical admission stopped after one Qwen call. | `incomplete`; handoff not qualified | No Reviewer or retry followed; this was not a production defect or model-performance verdict. | Acceptance architecture status and V1 report | `B+L` | `primary-read` |
| `PH-02` | In V2, one bounded Constructor continuation consumed the exact diagnostic and returned a reference-valid replacement. A fresh Reviewer returned `adequate` but missed underspecified expressions because its request lacked the shared expression contract. | Constructor reference repair qualified; Reviewer semantic sensitivity failed on the specimen | The Reviewer transport/envelope passed; semantic adequacy did not. | Architecture status; continuation report | `B+L` | `primary-read` |
| `PH-03` | Phase A V4 compiled two marked-valid specification examples and a coherent point-row contract, then causally refused 23 isolated mechanical mutations. Tests passed 48/48. | Compiler boundary qualified for frozen vocabulary | It did not qualify runtime evaluation, evidence collection, intent adequacy, Reviewer sensitivity, routing, provider behavior, or live behavior. | Phase A qualification report; evidence manifest `FB8A376BD9EBA48AE1BC904A6F4CA2701B6E2596E71E0EC711F3E278618B5F46` | `B+L` | `primary-read` |
| `PH-04` | Phase A's qualified mechanics include typed role compatibility, projections, quantifiers, manifest-owned operation signatures/costs, four authority modes, finite nonnegative literal tolerances, budgets, strict JSON, canonical bytes, and exact diagnostics. | `pass` for the frozen compiler corpus | This is compiler coherence, not proof that an acceptance contract covers user intent. | Same report | `B+L` | `primary-read` |
| `PH-05` | Phase B made six fresh Qwen3.8 Reviewer calls over one control and five compiler-valid semantic mutations. Public and private audits passed. | `not_qualified_on_corpus` | No aggregate model score or production-router decision was authorized. | Phase B qualification report; public manifest `1D2656F304293EDD80734E5B88500D9B10666C54D5778C4B8B8E6E8F45354C0A`; private manifest `8B0443D0828D21408E9D5D42A33DDF659D3DA22AA8D8BF74B0924EA97EB8C0F9` | `B+L` | `primary-read` |
| `PH-06` | The Phase B Reviewer passed control restraint and residual recognition 6/6; detected requirement omission, invented assumption, and material weakening; missed authority misrouting; and recognized hidden unresolved risk under the wrong frozen category. | Three sensitivity successes, two sensitivity failures, one restraint failure | The result establishes useful judgment on this corpus, not reliable residual semantic authority. | Same report | `B+L` | `primary-read` |
| `PH-07` | The branch-local North Star proposes Rook-owned append-only workflow state, Prime role sessions, deterministic compilation/evaluation, a Policy Gate, and crash recovery. | `design-only`, explicitly not implementation-ready | The architecture status suspends the seven-stage production map pending handoff evidence. | Acceptance workflow router specification and architecture status | `B+D` | `primary-read` |

## 14. Defect And Interruption Register

This register lists observed incidents without inferring a single common cause.

| ID | Incident | Recorded classification | Consequence |
|---|---|---|---|
| `INC-01` | LM5K's golden fixture expected post-verification work from a pre-execution graph. | Fixture defect | Model refusals were reclassified as correct restraint. |
| `INC-02` | Exact compiler diagnostic prose differed from a live Grasshopper diagnostic. | Deterministic test/host-contract mismatch | Matching was narrowed to the required semantic substring. |
| `INC-03` | Planner sparse guidance omitted the effective shape needed by a strict validator. | Request-surface learnability failure | Isolated shape guidance changed 0/10 valid to 10/10 valid on the same constrained corpus. |
| `INC-04` | LM9B-P provider configuration failed before a model turn. | Environmental/provider failure | Scientific question remained inconclusive. |
| `INC-05` | Post-discovery qualification deployed development Python while MCP imported release `site-packages`. | Runtime-custody mismatch | The run did not qualify the new Python behavior. |
| `INC-06` | Managed discovery read `Exposure` from `GH_InstanceDescription`; installed API owns it on `IGH_ObjectProxy`. | Product host-owner defect plus host-unfaithful fake | Hotfix and host-faithful tests preceded renewed qualification. |
| `INC-07` | Managed ambiguity candidates and Python validation assumed different candidate shapes. | Cross-owner contract defect | A shared shape fixture and projector preceded the final discovery pass. |
| `INC-08` | Qwen's malformed `gh_library.query` was silently treated as catalog browse. | Product admission defect | Strict contained-argument admission was added. |
| `INC-09` | Nemotron's Prime JSON stream lacked required terminal lifecycle events. | Incomplete lifecycle evidence | No final inspection or semantic verdict was authorized. |
| `INC-10` | A Gate B qualification adapter imported the acceptance module incorrectly. | Qualification orchestration defect | The Actor mutation remained unqualified; Gate A was not rerun. |
| `INC-11` | An earlier structured MCP error invalidated a trace despite a later authentic receipt. | Evidence-custody contract defect | Prime/Rook structured-error custody was added. |
| `INC-12` | A later group-only edit followed the latest solve receipt. | Frozen trace-admission refusal | The run remained incomplete despite a plausible graph. |
| `INC-13` | The model-facing adapter returned the MCP `{success,data}` envelope instead of capability data. | Adapter-boundary defect | Disposable V5 returned exact payloads while preserving envelopes in evidence. |
| `INC-14` | Qwen3.8 helix V1 ended without `agent_end` during a Codex app interruption. | Incomplete; causation not proven | V1 remained frozen and V2 used a fresh sibling. |
| `INC-15` | Point-row canonical JSON artifacts are stored as LF but checked out as CRLF in the clean Windows inventory worktree because no file-specific EOL rule applies. | Current checkout/test portability defect | Four of seven point-row wrapper tests fail canonical-byte checks; the files remain Git-clean. |

## 15. Explicitly Open Or Unestablished Areas

The following are direct nonclaims or unqualified boundaries found in the
sources. They are not a prioritized roadmap.

| ID | Open area | Source basis |
|---|---|---|
| `OPEN-01` | General Planner competence for broad natural-language design intent | LM7, LM9, compositional, and Phase B nonclaims |
| `OPEN-02` | General local Worker competence beyond the narrow C# and scalar families | LM6/LM8 nonclaims |
| `OPEN-03` | Reliable repair of fundamentally wrong topology | Point-row repeatability and XY-grid nonclaims |
| `OPEN-04` | A general acceptance representation that does not require one bespoke evaluator per task | Current seven-predicate behavioral module; Phase A compiler-only boundary |
| `OPEN-05` | Runtime expression evaluation for the Phase A semantic language | Phase A explicit nonclaim |
| `OPEN-06` | A Reviewer configuration reliable enough to own residual semantic acceptance | Phase B `not_qualified_on_corpus` |
| `OPEN-07` | Production workflow router handoffs for effective Prime role isolation and crash-safe exclusive Worker ownership | Branch-local architecture status |
| `OPEN-08` | Controlled evidence that the existing knowledge graph materially improves the current Prime/Qwen workflows | No positive controlled result located in this pass |
| `OPEN-09` | Broad model reliability, model-setting transfer, and repeatability across versions and task families | Empirical principle and model milestone nonclaims |
| `OPEN-10` | Multi-file allocation, recomposition, and fan-in | June topology and later architecture nonclaims |
| `OPEN-11` | Coverage of Grasshopper geometry evidence beyond points in the current fenced acceptance surface | Current code contains point-output projection but no `geometry_evidence` or `behavioral_geometry_outputs` surface |
| `OPEN-12` | End-user product integration of the proven internal Worker/compositional paths | Current architecture and compositional milestones |

## 16. First-Pass Source Index

### 16.1 Current and active documents

- `docs/CURRENT_ARCHITECTURE.md`
- `docs/AGENT_ARCHITECTURE.md`
- `docs/roadmaps/README.md`
- `docs/roadmaps/2026-08-02-compositional-agent-harness-roadmap.md`
- `docs/superpowers/2026-08-14-empirical-model-intelligence-principle.md`

### 16.2 Historical architecture and Worker/Planner evidence

- `docs/superpowers/specs/2026-06-03-rook-north-star-topology.md`
- `docs/superpowers/specs/2026-06-19-rook-local-internal-models-north-star.md`
- `docs/superpowers/specs/2026-07-02-rook-planner-harness-north-star.md`
- `docs/superpowers/probes/2026-07-02-lm5k-first-worker-model-probe.md`
- `docs/superpowers/probes/2026-07-19-lm9b-c-compiler-sufficiency-result.md`
- `docs/superpowers/probes/2026-07-20-lm9b-p-planner-recipe-transfer-result.md`
- `docs/superpowers/specs/2026-07-23-rook-semantic-harness-architecture-accounting.md`
- `docs/superpowers/2026-07-31-minimal-intent-worker-real-compile-milestone.md`
- `docs/superpowers/reports/2026-08-02-compositional-harness-representation-fit-audit.md`
- `docs/superpowers/2026-08-03-compositional-harness-slice1-live-qualification-milestone.md`
- `docs/superpowers/2026-08-03-compositional-harness-slice2-live-qualification-milestone.md`

### 16.3 Prime, discovery, receipt, and model evidence

- `docs/superpowers/2026-08-05-prime-agent-readonly-qualification-milestone.md`
- `docs/superpowers/reports/2026-08-08-grasshopper-native-component-discovery-qualification.md`
- `docs/superpowers/reports/2026-08-09-grasshopper-user-object-provenance-qualification-v2.md`
- `docs/superpowers/specs/2026-08-08-grasshopper-component-discovery-coherence-design.md`
- `docs/superpowers/2026-08-11-grasshopper-component-discovery-live-qualification-milestone.md`
- `docs/superpowers/2026-08-11-prime-opus-qwen-operational-comparison-milestone.md`
- `docs/superpowers/specs/2026-08-12-grasshopper-receipt-fenced-behavioral-acceptance-design.md`
- `docs/superpowers/specs/2026-08-13-prime-mcp-structured-error-custody-design.md`
- `docs/superpowers/2026-08-13-prime-structured-error-gate-b-v3-milestone.md`
- `docs/superpowers/2026-08-15-qwen38-grasshopper-capability-campaign-milestone.md`

### 16.4 Branch-local Phase A/B sources

Located under
`C:/UDEV/Rook/.worktrees/acceptance-workflow-router-design`:

- `docs/superpowers/2026-08-15-acceptance-workflow-router-architecture-status.md`
- `docs/superpowers/specs/2026-08-15-rook-prime-acceptance-workflow-router-design.md`
- `docs/superpowers/reports/2026-08-15-acceptance-semantic-manifest-phase-a-qualification.md`
- `docs/superpowers/reports/2026-08-15-acceptance-reviewer-phase-b-qualification.md`

### 16.5 Principal retained local roots

- `C:/Users/bring/AppData/Local/Temp/prime-rook-operational-comparison-v3`
- `C:/Users/bring/AppData/Local/Temp/prime-rook-qwen-strict-retest-v1`
- `C:/Users/bring/AppData/Local/Temp/prime-rook-nemotron-strict-qualification-v1`
- `C:/Users/bring/AppData/Local/Temp/prime-rook-qwen-point-row-repair-loop-v1`
- `C:/Users/bring/AppData/Local/Temp/prime-rook-qwen-point-row-repair-loop-v2`
- `C:/Users/bring/AppData/Local/Temp/prime-rook-qwen-point-row-repair-loop-v3`
- `C:/Users/bring/AppData/Local/Temp/prime-rook-qwen-xy-grid-repair-loop-v1`
- `C:/Users/bring/AppData/Local/Temp/rook-gh-native-discovery-task0-v2`
- `C:/Users/bring/AppData/Local/Temp/rook-gh-user-object-provenance-qualification-v2`
- `C:/Users/bring/AppData/Local/Temp/rook-gh-discovery-postmerge-364bd50c`
- `C:/Users/bring/AppData/Local/Temp/rook-solve-fenced-live-20260813-070216`
- `C:/Users/bring/AppData/Local/Temp/rook-solve-fenced-gate-b-v2`
- `C:/Users/bring/AppData/Local/Temp/rook-solve-fenced-gate-b-v3`
- `C:/Users/bring/AppData/Local/Temp/rook-solve-fenced-repair-loop-v3`
- `C:/Users/bring/AppData/Local/Temp/rook-solve-fenced-repair-loop-v4`
- `C:/Users/bring/AppData/Local/Temp/rook-solve-fenced-repair-loop-v5`
- `C:/Users/bring/AppData/Local/Temp/rook-qwen38-gh-capability-campaign-20260815`
- `C:/Users/bring/AppData/Local/Temp/rook-qwen38-gh-helix-qualification-v1`
- `C:/Users/bring/AppData/Local/Temp/rook-qwen38-gh-helix-qualification-v2`
- `C:/Users/bring/AppData/Local/Temp/rook-acceptance-contract-handoff-qualification-v1`
- `C:/Users/bring/AppData/Local/Temp/rook-acceptance-contract-handoff-qualification-v2`
- `C:/Users/bring/AppData/Local/Temp/rook-acceptance-semantic-phase-a-v4`
- `C:/Users/bring/AppData/Local/Temp/rook-acceptance-reviewer-phase-b-v2`

## 17. Deferred Work For The Deep Pass

The next pass should collect and verify, without yet making architecture
recommendations:

1. Exact commit reachability and PR lineage for each row.
2. Declared manifest hashes versus observed manifest-file hashes.
3. Raw result classification and terminal lifecycle for each principal local run.
4. Model identity, reasoning settings, prompts, adapters, skills, and runtime custody.
5. Exact tool-call counts and mutation/receipt sequences where not already in a merged milestone.
6. Current-code ownership for every mechanism described as retained.
7. Contradictions between current code, current documentation, historical documents, and branch-local proposals.
8. Any controlled knowledge-graph or knowledge-injection efficacy evidence omitted from this first inventory.
9. Any relevant negative or interrupted result not represented above.

Only after that verification should a separate document interpret the evidence,
compare architectural alternatives, or propose a comprehensive target
architecture.
