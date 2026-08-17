# Coordinating Intelligence Evidence Ledger

**Status:** Deep verification annex added; interpretation intentionally limited

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

Sections 4-16 preserve the verification depth assigned during the first pass.
Sections 18-27 record the additional verification performed afterward.

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
The deep pass below preserves that distinction and does not describe one as the
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
| `KG-03` | No controlled positive effect of the existing knowledge graph on the later Prime/Qwen Grasshopper tasks was located in the searched current, historical, branch-local, or retained evidence. | `observed` absence in the searched corpus | This does not prove that no such evidence exists outside the searched corpus. | First-pass source inventory plus section 26 deep search | `C+H+B+L` | `primary-read` |

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

## 17. Deep-Pass Verification Checklist

The first-pass commit was
`189abb045ae6440468f9f83e49feb48f15b06b7f`. The following checklist was then
completed without making architecture recommendations:

1. Exact commit reachability and PR lineage for each row.
2. Declared manifest hashes versus observed manifest-file hashes.
3. Raw result classification and terminal lifecycle for each principal local run.
4. Model identity, reasoning settings, prompts, adapters, skills, and runtime custody.
5. Exact tool-call counts and mutation/receipt sequences where not already in a merged milestone.
6. Current-code ownership for every mechanism described as retained.
7. Contradictions between current code, current documentation, historical documents, and branch-local proposals.
8. Any controlled knowledge-graph or knowledge-injection efficacy evidence omitted from this first inventory.
9. Any relevant negative or interrupted result not represented above.

The results of that verification follow. A separate interpretive document may
later compare architectural alternatives or propose a comprehensive target
architecture.

## 18. Deep-Pass Method And Scope

The deep pass was performed against the same inventory baseline and retained
local roots. It did not contact Rhino, Grasshopper, MCP providers, Ollama, or a
model. It did not rerun any live qualification.

The pass performed these additional checks:

1. resolved sampled Rook and Prime commits against their observed repositories;
2. classified each sampled commit as current-main, branch-local, or external to
   the observed upstream;
3. read current implementation owners for discovery, authoring admission,
   solve receipts, fenced snapshots, and behavioral acceptance;
4. ran focused current Python and managed tests;
5. rehashed the principal retained manifests and every referenced manifest
   entry;
6. read raw lifecycle, evaluation, probe, and adjudication artifacts for the
   principal model runs;
7. extracted frozen model, reasoning, prompt, adapter, skill, target, and
   runtime settings where retained; and
8. searched current and historical sources for controlled evidence of knowledge
   retrieval efficacy in these workflows.

This remains a collection and verification pass. It does not convert the
observations below into a target architecture.

## 19. Repository And Commit Lineage

### 19.1 Rook lineage

Every sampled Rook commit below exists and is an ancestor of the inventory
baseline `f840069a58d0a5ee297ae817f0b3efe7a9287512`.

| Area | Current-main commit or merge | Recorded subject or PR |
|---|---|---|
| Script mutation receipts | `e5624d50` | PR #284, LM1D script receipts. |
| MCP receipt unwrapping | `7a1f8b1b` | PR #333. |
| Solve-readiness design | `425acaf8` | PR #481. |
| Receipt verifier design | `3dddf920` | PR #483. |
| Live diagnostic substring | `0d02180a` | PR #431. |
| Planner shape guidance | `8ce8e042` | PR #453. |
| Live planner splice | `0a3506b9` | PR #456. |
| Structured MCP results | `4bf6fad8` | PR #553. |
| Native discovery design/report | `a867f8e0` | PR #555. |
| User-object provenance | `a0f2a12e` | PR #556. |
| Discovery production | `5584b324` | PR #557. |
| Proxy-owned Exposure | `a54eee32` | PR #558. |
| Candidate-shape contract | `364bd50c` | PR #559. |
| Discovery live milestone | `06534f37` | PR #560. |
| Strict tool admission | `c1343bac` | PR #561. |
| Offline critic boundary | `ad4d3b27` | PR #562. |
| Authoring capability routing | `bc5c0b15` | PR #564. |
| Solve-fenced acceptance | `61c686c5` | PR #565. |
| Structured MCP failure admission | `7d6920d4` | Direct Rook commit. |
| `gh_edit` admission hints | `4a2adfa3` | PR #566. |
| Runtime empiricism principle | `f840069a` | PR #567. |

This reachability check establishes that the sampled Rook mechanisms are not
merely disposable-lane code. It does not establish that every historical
document still describes their current contract.

### 19.2 Prime lineage

| Prime state | Commit | Deep-pass observation |
|---|---|---|
| Working checkout | `c98941a2a5cf40faecf9b4648ac3c304abf48fd3` | Clean `main`; dated 2026-08-05. |
| Observed upstream | `9bf49d897c22563f3e4483d28149c1aac452a6f9` | `origin/main`; dated 2026-08-13. |
| Structured-error change | `30a6621bca698ef14f64e5e45c5b1b6364148789` | Adds structured content to `McpToolError` and corresponding tests. |
| Reviewed fork merge | `27b5be22cf0e0e81e324a59ebabbb41edfee6ec0` | Contains `30a6621b`; used by later experimental rows. |

`30a6621b` is an ancestor of `27b5be22`. The reviewed fork merge is not an
ancestor of the observed Prime upstream. Reading both trees showed the enriched
`McpToolError.structured_content` behavior in the fork and the earlier
text-only behavior in the observed upstream. Later structured-error and
payload-first rows froze the reviewed fork merge, not the older working
checkout.

### 19.3 Phase A/B branch lineage

The Phase A/B worktree is clean at
`8a4572543f4e7a55fc13b41f985124e02a2523b4`. Its merge base with the inventory
baseline is `4a2adfa39657118924d57468b77ec0aa1c4b8991`. The branch contains 18 commits after that merge
base. Current Rook main contains three commits after the same point, including
the empirical-model principle, runtime-empiricism principle, and PR #567 merge.

Therefore the Phase A/B documents are reviewed branch-local evidence. Their
diff against current main also presents the later empirical-principle document
as absent because of branch divergence. That absence is a lineage fact, not
evidence that Phase A/B evaluated or rejected that principle.

## 20. Current Implementation Ownership

### 20.1 Current owners

| Mechanism | Current owner on the inventory baseline | Observed responsibility |
|---|---|---|
| Component candidate projection | `mcp_server/src/rook/grasshopper_component_contract.py` | Canonical GUID and closed catalog/search/ambiguity candidate shapes. |
| Script authoring admission | `mcp_server/src/rook/gh_authoring_contract.py` | Script identity classification and canonical handoff construction. |
| Behavioral acceptance | `mcp_server/src/rook/gh_behavioral_acceptance.py` | Source-trace admission, terminal receipt selection, perturb/restore custody, and predicate evaluation. |
| Solve-receipt state | `src/Rook/InternalBridge/GhSolveReceiptRegistry.cs` | Receipt issue, readiness, supersession, document replacement, solver lock, expiry, and fenced-read checks. |
| Managed readiness routes | `src/Rook/Handlers/GrasshopperHandler.Readiness.cs` | Begin/finalize mutation receipts and readiness/wait responses. |
| Fenced snapshot | `src/Rook/Handlers/GrasshopperHandler.cs` | Receipt fence checked before snapshot/output reads. |
| Knowledge injection skip | `mcp_server/src/rook/knowledge_injector.py` | `gh_library` and `gh_batch_component_info` are skipped at the injection boundary. |

Observed source sizes are descriptive, not quality scores:

| File | Physical lines | Nonblank lines |
|---|---:|---:|
| `grasshopper_component_contract.py` | 111 | 99 |
| `gh_authoring_contract.py` | 162 | 136 |
| `gh_behavioral_acceptance.py` | 2,349 | 2,177 |
| `GhSolveReceiptRegistry.cs` | 739 | 646 |
| `GrasshopperHandler.Readiness.cs` | 382 | 338 |

The current `_predicate_passes` implementation contains seven recognized
predicate names. This is a current-code count, not a claim of semantic
coverage.

### 20.2 Fresh focused verification

| Seam | Result | Notes |
|---|---|---|
| Structured results, containment, discovery, authoring routing, and script receipts | 249 passed | 11 warnings. |
| Common behavioral acceptance | 105 passed | 11 warnings. |
| Managed discovery, snapshot, readiness, terminal mutation receipt, and registry tests | 168 passed | Restore was required in the fresh worktree; compilation/analyzer warnings remained. |
| Knowledge injector | 72 passed, 2 failed | Failures assert stale operation mappings, including removed `gh_component -> create` and the older category set. |
| Legacy point-row wrapper | 3 passed, 4 failed | Failures are current-checkout newline custody mismatches, described below. |

The two tracked JSON artifacts used by the legacy point-row wrapper are indexed
with LF but checked out as CRLF on this Windows worktree. `git ls-files --eol`
reports `i/lf w/crlf attr/` and no explicit `eol` attribute. The worktree remains
Git-clean. The historical 20/20 result and the current 3/4 result are therefore
different observations under different byte custody; neither is silently
substituted for the other.

## 21. Retained Manifest Reverification

The following manifest files and all entries referenced by them were rehashed
without contacting a runtime. `Mismatch` counts include missing paths, size
disagreement, and digest disagreement.

| Evidence row | Entries | Mismatches | Manifest-file SHA-256 |
|---|---:|---:|---|
| Operational comparison, control | 21 | 0 | `BB4CF747...BE518` |
| Operational comparison, Qwen | 21 | 0 | `C0A257F6...BC4C7` |
| Qwen strict retest | 21 | 0 | `FC1EE04A...8FFB9` |
| Point row V1 | 33 | 0 | `776D36F9...0C2D7` |
| Point row V2 | 33 | 0 | `7C5A0BFD...F17E1` |
| Point row V3 | 33 | 0 | `69EEF6B6...06A0C` |
| XY grid V1 | 37 | 0 | `E84121EE...358D` |
| Native discovery Task 0 V2 | 4 | 0 | `2D652AF3...03B64` |
| User-object provenance V2 | 4 | 0 | `A3BD7271...1B624` |
| Post-merge discovery | 9 | 0 | `FA1E4D0E...CEF0E2` |
| Solve-fenced Gate A | 12 | 0 | `0675FC95...FFDCC` |
| Solve-fenced Gate B V2 | 37 | 0 | `03016521...E3AD3` |
| Structured-error Gate B V3 | 37 | 0 | `02C09541...B29057` |
| Repair loop V3 | 32 | 0 | `6A2EBE9B...F869B6` |
| Repair loop V4 | 32 | 0 | `5565EB18...63285` |
| Payload-first repair loop V5 | 33 | 0 | `D8D6FC12...D3E53` |
| Qwen3.8 campaign, exact row | 33 | 0 | `7BF5A02F...00DD3` |
| Qwen3.8 campaign, open row | 33 | 0 | `81F31C02...70AA5` |
| Qwen3.8 campaign, open grid | 33 | 0 | `2E0EA697...9ADD6` |
| Helix V1 | 34 | 0 | `FC8C6840...E0136` |
| Helix V2 | 34 | 0 | `40C3F6FA...EC555C` |
| Contract handoff V1 evidence prefix | 9 | 0 | `758E33DD...E7433` |
| Contract handoff V2 | 32 | 0 | `38AC6B48...F81E` |
| Semantic Phase A V4 | 12 | 0 | `FB8A376B...B5F46` |
| Reviewer Phase B public | 32 | 0 | `1D2656F3...354C0A` |
| Reviewer Phase B private | 1 | 0 | `8B0443D0...B8C0F9` |

The Nemotron manifest has 24 entries and file SHA-256
`6142B71933E7F19583545B974ADFFE2E4491425D82EFC4082EAB3638FAC4D652`.
Twenty-one entries resolve from the row-local root. Three `runtime/...` entries
resolve one directory higher and match their recorded hashes there. No single
documented root resolves all 24 keys. The retained files are present and hash
correct, while the manifest path-base convention is ambiguous.

## 22. Raw Lifecycle And Result Matrix

### 22.1 Operational control and local rows

| Row | Terminal lifecycle | Final mechanical evidence | Recorded semantic result |
|---|---|---|---|
| Opus control | 159 Prime JSONL lines; exactly one final `agent_end` | 6 components, 5 flows, zero errors/warnings | Pass. |
| Qwen3.6 local | 15,977 Prime JSONL lines; exactly one final `agent_end` | 15 components, 15 flows, zero errors/warnings | Fail: hard-coded points and adjustable Y/Z. |
| Qwen3.6 strict retest | Complete terminal evidence | 8 components, 7 flows, zero errors/warnings | Fail: Range/EndX substituted for Series/Step. |
| Nemotron | 7,217 Prime JSONL lines; zero `agent_end`; last event `message_update` | Retained graph had Series but no Construct Point or points | Incomplete. |

Raw hashes independently read in this pass include:

- Opus Prime JSONL: `96CD825E...FB7`;
- Opus final snapshot: `BD25176E...F48`;
- Qwen Prime JSONL: `EB6D43A5...1FF6`;
- Qwen final snapshot: `C1207DA4...FA3`;
- Qwen strict final snapshot: `4B3E44B8...7AE8`; and
- Nemotron Prime JSONL: `95B7FD99...5111`.

### 22.2 Receipt-fenced and repair-loop rows

| Row | Initial result | Later result | Deep-pass observation |
|---|---|---|---|
| Point row V1 | Fail | Pass | One bounded repair. |
| Point row V2 | Pass | None | Initial pass. |
| Point row V3 | Fail | Pass | One bounded repair. |
| XY grid V1 | Fail | Fail | One repair consumed; final acceptance remained failed. |
| Gate B V2 | Incomplete | None | Earlier undifferentiated `McpToolError` invalidated trace admission. |
| Structured-error Gate B V3 | Incomplete | None | Failure evidence and latest receipt were retained; exact control binding failed. |
| Repair loop V3 | Incomplete | None | `later_unfenced_mutation` after a group-only edit. |
| Repair loop V4 | Incomplete | None | `latest_terminal_receipt_missing`; no mutation occurred. |
| Payload-first V5 | Incomplete | Pass | Initial `control_binding_failed`; one repair then passed all eight criteria. |

These classifications are the recorded boundaries of the respective rows. For
example, V3's visually plausible graph is not reclassified as a semantic pass,
and V4's lack of mutation is not reclassified as a model-semantic failure.

### 22.3 Qwen3.8 capability campaign and helix

| Row | Recorded result | Raw behavioral observation |
|---|---|---|
| Exact point row | Pass | Common evaluator passed. |
| Open point row | Pass | Three controls were perturbed and restored; final output contained six points at X = 0, 50, ..., 250. |
| Open XY grid | Pass | Four independent controls were perturbed and restored; final output contained a 5 by 4 grid. |
| Helix V1 | Incomplete | Missing terminal lifecycle after an interrupted host application; no semantic classification. |
| Helix V2 | Pass | Exactly one final `agent_end`; all seven criteria passed after ten fenced perturb/restore receipts. |

The open-grid canvas used abbreviated control labels `C`, `R`, `X`, and `Y`.
Its pass was behavioral, not an exact-label match. Helix V2's raw evaluation
records an adjustable radial-periodic XY path with monotonic Z and restored
Radius, Height, Turns, Points-per-turn, and Start-angle controls.

### 22.4 Handoff and reviewer rows

| Row | Recorded result | Raw boundary |
|---|---|---|
| Contract handoff V1 | Incomplete | Constructor referenced undeclared role IDs. |
| Contract handoff V2 | Completed | One diagnostic continuation produced an admitted replacement; Reviewer transport/envelope passed but later review found missed underspecification. |
| Semantic Phase A V4 | Completed | Compiler coherence: two valid examples and 23 causal mutations. |
| Reviewer Phase B | `not_qualified_on_corpus` | Six calls completed; public reconstruction and private adjudication passed. |

## 23. Frozen Inputs And Runtime Dimensions

### 23.1 Opus/Qwen operational comparison

The two original operational rows shared:

- the exact point-row intent;
- adapter SHA-256 `E7577F0E...2996`;
- skill SHA-256 `0F7C8D1F...D36E`;
- checkpoint SHA-256 `76A7C0CF...8964`;
- Prime commit `c98941a2...`;
- Rook commit `06534f37...`; and
- explicit Prime thinking level `medium`.

The control used `claude-opus-4-6` with Anthropic adaptive thinking and medium
effort. The local row used `qwen3.6:35b`, Ollama manifest SHA-256
`07D35212...522`, and medium reasoning effort. Provider-native reasoning and
token accounting were intentionally not claimed to be identical.

### 23.2 Later Prime/Qwen rows

The structured-error and payload-first rows changed identified harness inputs:

- Prime structured-error commit `30a6621b...`, contained in fork merge
  `27b5be22...`;
- payload-first adapter SHA-256 `9B22757E...C371`;
- skill SHA-256 `96F24F89...1DA2C`; and
- the unchanged checkpoint family `76A7C0CF...8964`.

The Qwen3.8 rows used tag `qwen3.8:27b`, Ollama manifest SHA-256
`22130167C4C20E20C7B71454612966CA8E8171E9B3CC8AB6CE8AA6CBFEC79643`,
and medium reasoning. Retained identity records describe an approximately
16.81-GiB model blob and an approximately 931-MiB projector layer. The campaign
used Rook `61c686c5...`; the helix used later Rook `4a2adfa3...`.

The three campaign intents were separately frozen as exact point row, open
point row, and open XY grid. The helix intent requested an adjustable helical
curve using native components with useful principal-dimension and resolution
controls.

### 23.3 Phase B direct model settings

Phase B did not use the Grasshopper runtime or Prime. It made six direct Ollama
`/api/chat` calls with:

```text
model       qwen3.8:27b
think       medium
seed        2026081502
temperature 0.0
top_p       0.9
num_ctx     32768
num_predict 8192
stream      false
```

The frozen order was `c04`, `c01`, `c06`, `c02`, `c05`, `c03`. The model
identity record names Ollama `0.32.13` and records tag/blob identities; this
deep pass did not recompute complete blob digests.

## 24. Discovery And Identity Evidence

### 24.1 Native discovery Task 0

The retained native-discovery artifact has SHA-256
`254A9BF5A8EEE5DCCA72A37AD08DF20EDF63271F55E2F14AC4587BC180481988`.
It records:

- 1,890 live proxies;
- 53 duplicate exact-name groups;
- complete legacy-predicate comparisons;
- three stable native orderings for each fixed query;
- candidate counts of 261 (`Series`), 228 (`Range`), 18
  (`Multiplication`), 91 (`Addition`), 58 (`Construct Point`), 112
  (`Add`), and 371 (`Point`); and
- two retained affirmative third-party specimens.

### 24.2 User-object provenance

The V2 artifact SHA-256 is
`E7BC4124D1029D9F50721FB45B3E1079317CDC1901A0332B635532681CCE04BD`.
It records six complete `.ghuser` specimens, canvas count `0 -> 0`,
`FindAssemblyByObject(proxy GUID) = not_found` for all six, and temporary
instance assembly `GhPython` for all six. The retained interpretation separates
path/content fingerprint provenance from `BaseGuid` and runtime-assembly
implementation metadata.

### 24.3 Post-merge qualification

The post-merge summary records `qualification_passed` with five host calls,
zero model calls, zero mutations, and zero retries. It observed:

- two exact eligible `Angle` candidates and preserved ambiguity;
- `Range` returned 10 of 204 matches with `truncated=true`;
- the first selected live user object at rank index 2;
- two successful compiled/user-object metadata outcomes and zero errors;
- user-object content length 2,869 and SHA-256 `B8FB2F2B...B14000`; and
- an unchanged audit shape over 1,890 proxies, with 775 deprecated, 487 hidden,
  and 198 obsolete entries in stable GUID order.

## 25. Phase A And Phase B Evidence

### 25.1 Phase A compiler boundary

Phase A V4 classified the coherent artifact as compiled and applied 23 isolated
mutations. Twenty-one were invalid and two were unsupported
(`known_unavailable_operation` and `known_unavailable_role_kind`). The corpus
covered reference, typing, projection, quantification, scoping, null-expression,
tolerance, nonfinite-number, depth, node, and budget diagnostics.

Its report explicitly does not establish intent adequacy, Reviewer sensitivity,
runtime evaluation, evidence collection, router ownership, provider behavior,
or live behavior. No model, Prime, Rook, Rhino, Grasshopper, or network calls
occurred.

### 25.2 Phase B Reviewer boundary

The six independently adjudicated cases were:

| Case | Frozen condition | Sensitivity | Restraint | Residual recognition |
|---|---|---:|---:|---:|
| `c01` | Coherent control | N/A | Pass | Pass |
| `c02` | Requirement omission | Pass | Pass | Pass |
| `c03` | Invented assumption | Pass | Pass | Pass |
| `c04` | Material weakening | Pass | Pass | Pass |
| `c05` | Authority misrouting | Fail | Pass | Pass |
| `c06` | Hidden unresolved risk | Fail | Fail | Pass |

For `c06`, the Reviewer recognized a semantic defect but assigned the wrong
frozen category and produced one unsupported additional finding. The overall
status was `not_qualified_on_corpus`. This is evidence of mixed sensitivity and
restraint on this six-case corpus, prompt, model, and configuration. It is not
a general Reviewer accuracy estimate.

## 26. Knowledge And Retrieval Evidence Search

Current architecture and code retain multiple knowledge mechanisms. Current
`knowledge_injector.py` also excludes the two authoritative discovery tools
from knowledge injection. The focused current test result is 72 passes and two
stale mapping failures.

The deep pass searched merged reports, milestones, probes, branch-local Phase
A/B sources, current code/tests, and the retained model-run evidence for a
controlled positive comparison in which knowledge retrieval or DSPy
optimization improved these Prime/Grasshopper outcomes. No such result was
located.

Relevant negative boundaries were located instead:

- several Worker, compiler, and compositional slices explicitly excluded
  knowledge retrieval or DSPy from their tested boundary;
- authoritative component discovery was qualified with unrelated knowledge
  hints suppressed;
- the 2026-07-23 semantic accounting document describes DSPy as a provisional
  hypothesis and specifies a future three-arm comparison; and
- the empirical-model principle characterizes stored knowledge as a prior, not
  runtime authority.

Accordingly, this ledger records the current knowledge system's presence and
its exclusion from specific authoritative paths. It records no controlled
positive efficacy result for the later Prime/Qwen workflows because none was
found in the searched evidence set.

## 27. Verified Divergences And Remaining Unknowns

### 27.1 Verified divergences

| Divergence | Verified fact |
|---|---|
| Prime structured errors | Required fork behavior exists in `27b5be22` but was not present in observed Prime upstream `9bf49d89`. |
| Phase A/B and current main | Phase A/B diverged before the merged empirical-principle documents. |
| Point-row historical/current tests | Historical 20/20 evidence coexists with current 3-pass/4-fail newline-custody behavior. |
| Knowledge architecture/tests | Knowledge mechanisms remain documented and implemented, while two current tests encode stale operation mappings. |
| Nemotron manifest | All retained files hash correctly, but three entries require a second path base. |

### 27.2 Remaining unknowns after the deep pass

- Complete model blobs were not rehashed.
- No live runtime was contacted, so current installed/deployed custody was not
  requalified.
- The full Rook Python and managed suites were not rerun; verification was
  focused on the mechanisms in this ledger.
- Phase A and Phase B remain branch-local and have no production-router
  implementation.
- No qualified general-purpose acceptance-contract Constructor was located.
- No controlled knowledge-retrieval efficacy result was located for these
  workflows.
- No claim is made that the retained predicate vocabulary covers open-ended
  user intents.
- No architectural disposition is assigned here to the Worker box, Prime,
  Phase A, Phase B, deterministic acceptance, or intelligent judgment.

These unknowns bound the ledger. They are inputs to a later interpretive pass,
not defects silently converted into recommendations here.
