# Durable Rhino Script Artifacts Design

Date: 2026-05-17

## Goal

Build a v1 durable script artifact system for Rhino workflows that reduces repeated ad hoc scripting while preserving Rook's safety model. The system should support trusted execution of reviewed repo-shipped scripts and explicit project-local intake of useful session scripts without treating fresh local artifacts as trusted code.

Core invariant:

```text
Discovery is broad.
Execution is narrow.
Manifest state is not self-certifying.
```

## Architecture

V1 is a durable script artifact system, not a scripts folder.

The filesystem is the source of truth. Repo-shipped artifacts live under a domain-aware library path such as `scripts/rook-library/rhino/<script-id>/`. Project-local intake lives under `.rook/scripts/<script-id>/`. Each artifact has a manifest plus one or more source or support files. The manifest carries `domain`, so the folder layout can stay practical without becoming the long-term taxonomy.

Repo-shipped artifacts are eligible for trust, not inherently trusted forever. They still need a valid manifest, known hash or package provenance, and passing scan before execution.

The knowledge store is only an index. It can summarize, rank, and suggest script artifacts, but it cannot authorize execution. Skills reference scripts by stable id, such as `extract-layers`, and the MCP layer resolves that id to an artifact.

Execution always goes through `run_library_script`. Skills and agents must call `run_library_script` for validated library use. Direct `rhino_execute` remains only for ad hoc fallback and capture workflows.

`run_library_script` computes trust from source location, explicit source enum, manifest, static scan result, evidence, state, package provenance, content hash, and mutation level. It must not simply believe `"state": "validated"` in a project-local manifest.

## Lifecycle

Artifacts move through explicit states:

```text
session script -> captured -> candidate -> validated -> promoted
```

For v1, only two transitions are implemented:

- Explicit intake creates `captured` project-local artifacts.
- Repo-shipped artifacts can be `validated` and eligible for execution through `run_library_script`.

Deferred transitions:

- `captured -> candidate`: cleaned metadata, static scan passed, adaptation points identified.
- `candidate -> validated`: parameterized, structured output, Rhino safety scan passed, smoke-tested.
- `validated -> promoted`: maintainer or user review, versioned, release-managed, optionally bundled or shared.

State meanings:

- `captured`: project-local evidence artifact. Searchable, never executable.
- `candidate`: cleaned and scanned reference. Searchable and usable as an adapt-reference, but never executable by `run_library_script` in v1.
- `validated`: executable only when repo-sourced, read-only, hash or provenance verified, schema-valid, scan-passing, and smoke-tested.
- `promoted`: release-managed distribution state used when a script is bundled or shared beyond one project.

V1 executable scripts are read-only only. Mutation scripts may be captured, searched, and used as adaptation references, but `run_library_script` refuses them regardless of `allow_mutation`. The `expected_mutation` or `allow_mutation` argument can exist in v1 to keep the API shape future-proof, but mutation execution is not enabled.

Promotion should require evidence, not inference. A later `validate_script_artifact` gate should require static scan, parameterization, structured output, output schema, at least one smoke recipe, and recorded validation evidence. A later `promote_script_artifact` gate should require maintainer or user review, versioning, release provenance, and package-level hash tracking.

## Manifest

A captured artifact stores evidence, not just source code. Capture should include the script body, original prompt or session id, observed inputs and outputs, mutation or read-only intent, selected objects or layers when relevant, error history, and agent notes about adaptation points. Its default state is always `captured`, and it is not executable as trusted library code.

The manifest is enforcement-oriented. Minimal v1 fields:

```json
{
  "id": "extract-layers",
  "version": "0.1.0",
  "state": "validated",
  "source": "repo",
  "domain": "rhino",
  "entrypoint": "script.py",
  "execution": "run_as_is",
  "mutation": "read_only",
  "content_hash": "sha256:<hash>",
  "parameters_schema": {},
  "output_schema": {},
  "requires": {
    "rhino": "8",
    "rook_capabilities": ["rhino_execute"]
  },
  "safety": {
    "static_scan": "passed",
    "blocking_ui": "none",
    "network": "none",
    "filesystem": "none"
  },
  "evidence": {
    "validated_at": "2026-05-17",
    "validation_method": "live_smoke"
  }
}
```

`source` is an enum. V1 requires at least:

- `repo`
- `project`

`parameters_schema` and `output_schema` are required even when empty.

For every executable artifact, `run_library_script` must verify matching hash or provenance before execution. For v1, that mostly applies to repo-shipped validated scripts. Project-local captured scripts may have best-effort content hashes for audit, but those hashes do not make them executable.

## MCP Surface

V1 exposes three MCP tools.

### `script_library_search`

Permissive discovery across repo library and project-local intake. It returns matching artifacts with source, state, domain, execution mode, mutation level, description, validation summary, and whether the artifact is executable by policy.

If `executable` is false, the tool also returns `refusal_reason`, such as:

- `captured_state`
- `candidate_state`
- `project_source_not_executable`
- `missing_hash`
- `failed_static_scan`
- `mutation_not_executable_in_v1`
- `ambiguous_id`

The tool may include knowledge-store ranking hints, but filesystem manifest policy remains authoritative.

### `capture_script_artifact`

Explicit local intake only. It writes `.rook/scripts/<script-id>/manifest.json`, the captured script source, and evidence files. It always creates state `captured` and source `project`.

Inputs should include code plus evidence:

- original prompt or session id
- observed inputs and outputs
- mutation or read-only intent
- selected object or layer context
- error history
- adaptation notes

The tool computes a content hash for audit. That hash does not make the artifact executable.

Static checks during capture should record findings while still allowing capture unless the artifact cannot be safely persisted. Capture is evidence collection, not trust promotion.

### `run_library_script`

Strict execution gate. It resolves a stable script id, loads the artifact, validates the manifest schema, verifies `source` is an allowed enum value, verifies executable state and source policy, verifies content hash or provenance for every executable artifact, runs or checks static scan status, checks capability requirements, checks declared mutation level against call intent, applies parameters through `parameters_schema`, executes the entrypoint through the appropriate Rhino or Rook substrate, parses JSON output, validates it against `output_schema`, and records the outcome.

For v1, `run_library_script` allows repo-sourced `validated` read-only run-as-is artifacts only.

It refuses:

- `project` plus `captured`
- `project` plus `candidate`
- any mutation script
- missing or malformed manifest
- missing `parameters_schema` or `output_schema`
- missing content hash or provenance for executable artifact
- undeclared mutation
- blocking UI risk
- network or filesystem access unless declared and allowed by future policy
- raw script ids that resolve ambiguously across repo and project sources

`run_library_script` defaults to `expected_mutation: "read_only"` or equivalent `allow_mutation: false`. In v1, mutation is refused even when the caller allows mutation, but the argument preserves the future API shape.

Resolution is deterministic but strict. If an id exists in both repo and project, `run_library_script(id="x")` fails with `ambiguous_id`. The caller must specify `source: "repo"` or `source: "project"`. Since v1 only executes repo validated scripts, the practical executable path is `source: "repo"`.

## Safety And Runtime Verification

Static checks should reject executable use for:

- blocking `rhinoscriptsyntax.Get*` prompts
- Rhino command prompt UI flows
- undeclared document mutation
- file or network access unless declared and allowed by future policy
- dynamic execution patterns such as `exec`, `eval`, string-built imports, or shell/process launch
- hidden or invisible text
- oversized files
- symlinks
- binary files
- path traversal
- missing schemas
- missing hash or provenance
- manifest/source mismatch

For `capture_script_artifact`, these can be recorded as findings. For `run_library_script`, they are hard rejects.

Runtime behavior:

- Execute through the existing Rhino execution substrate.
- Capture stdout or result JSON.
- Validate output against `output_schema`.
- Treat output schema validation failure as `success: false` or at least `verified: false`; a script running is not enough for a library call to succeed.
- After modal-risk substrates, reuse the existing command-prompt polling and verification pattern from the chat execution policy.
- For read-only scripts, capture a document object count or cheap document snapshot before and after execution where feasible so undeclared mutation can be detected.

The runtime envelope should include:

- `success`
- `verified`
- `script_id`
- `version`
- `source`
- `content_hash`
- `policy_decision`
- `static_scan_summary`
- `validated_output`
- `mutation`
- `execution_substrate`
- `verification_result`
- `refusal_reason` or error details when applicable

## Skills And Knowledge Indexing

Skills reference durable scripts by stable id, not by copying script bodies. A skill step should call `run_library_script(id="extract-layers", source="repo", expected_mutation="read_only", parameters={...})`.

This keeps execution policy centralized and prevents drift between skill docs and script code.

The knowledge store indexes artifacts for retrieval only. It may store summaries, domains, trigger phrases, known failure modes, usage evidence, and relationships to skills. It must not store the executable source of truth, and it must not authorize execution. If the filesystem manifest and knowledge index disagree, filesystem registry policy wins.

## Deferred Background Review

Hermes-style background review is deferred until after the artifact substrate exists.

V2 may add a post-session reviewer that suggests or writes `captured` or `candidate` artifacts after complex sessions. It must not promote to executable trust. The reviewer is an evidence collector and candidate generator only.

The policy remains:

```text
V1: explicit capture plus trusted read-only execution.
V2: background reviewer suggests captures.
Never: automatic trust promotion without validation evidence.
```

## Open Questions For Implementation Planning

- Exact repo library path: `scripts/rook-library/rhino/<script-id>/` versus `scripts/rhino/<script-id>/`.
- Whether the first repo-shipped validated artifact should be `extract-layers`, `document-summary`, or another read-only extractor.
- Whether content hashes are stored in each artifact manifest, a repo-level registry index, or both.
- How much document snapshotting is cheap enough for read-only verification in live Rhino.
- Whether v1 should include a separate static scan CLI for maintainers before release packaging.
