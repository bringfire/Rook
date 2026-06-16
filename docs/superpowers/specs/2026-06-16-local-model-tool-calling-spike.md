# Local Model Tool-Calling Spike

> **Status:** Proposed (not yet run). Investigative spike, not a build slice.
> **Phase:** Model Control (same phase as the RookChat Model Visibility work —
> see `2026-06-16-rook-chat-model-visibility-design.md`).
> **Gates:** Slice 3 (autonomous-local agents: running planner/worker/guardian on
> local models). **Does NOT gate** Slice 1 (visibility, shipped in PR #257) or
> Slice 2 (per-conversation, human-in-the-loop local override).

## Claim Under Test

This spike exists to adjudicate a **load-bearing assumption of the Rook
north-star topology** (`2026-06-03-rook-north-star-topology.md`), whose bottom
tier is "many cheap local-model agents, ideally at ~$0, doing in-file micro work."

> **CLAIM:** Local models can drive Rook's in-file agent loops *unattended*,
> reliably enough that the "~$0 local bottom tier" is a real operating mode — not
> an aspiration.

- **Validated** if ≥1 *accessible* model+runtime+hardware cell reaches
  *autonomous-grade* (see Pass/Fail). The Chooser then routes users to those cells.
- **Falsified** (at current model maturity) if no accessible cell clears
  autonomous-grade. Then the topology's bottom tier must be hybrid/cloud, not
  pure-local, and the economic premise is revised — a strategically important
  finding **either way**.

This is why the spike is not a model bake-off: it tests whether a core
architectural premise is true.

## The Question

Rook agents are tool-calling agents, not chat toys: the planner/worker loop is
multi-turn and many-tool. Does local-model tool-calling hold up well enough to
run that loop **unattended** on a local backend? Until we have evidence, the
honest product stance is:

> Local models for **assist-mode chat** (light tool use, human in the loop);
> **cloud for autonomous build** — until a specific model+runtime+hardware
> combination is *proven* agent-grade.

This spike produces that evidence.

## Landscape (reframing "which app")

The axis is not LM Studio vs Ollama vs llama.cpp. Rook routes everything through
LiteLLM, and there are only **two routing shapes**, both already supported:

1. **Native Ollama** — `ollama_chat/*`, no `api_base`. First-class; best UX
   (single binary, scriptable, server-side tool-call parsing for tool-templated
   models).
2. **Generic OpenAI-compatible** — `openai/<id>` + `api_base`. This bucket is
   large and already covered by one code path: **LM Studio, llama.cpp's
   `llama-server`, vLLM, LocalAI**, etc. LM Studio is merely the *named
   exemplar*; "supporting llama.cpp" is a docs + validation task, not new
   provider code.

For serious agentic local use, **vLLM** has the most robust OpenAI-compatible
tool-calling and is the deployment-grade option.

### Two distinct failure layers (this is the real risk)

- **Model capability.** Even strong local models (Qwen2.5/3-Coder-32B,
  Llama-3.3-70B) are markedly weaker at long multi-tool loops than
  Claude/GPT-4-class. Failure mode is *degraded*, not absent: malformed args,
  wrong tool, premature give-up, looping.
- **Runtime / template config.** The sneaky one. Tool-call *parsing* depends on
  the server chat template. Misconfigured (e.g. `llama-server` without `--jinja`
  or a tool-capable template), the model emits a tool call as **plain text in
  `content`** and LiteLLM never surfaces it as `tool_calls`. This looks like
  "the model can't use tools" but is a config trap.

## Two Axes: Fit (llmfit) vs Capability (this spike)

`llmfit` (`C:/Users/aryan/source/repos/Rook_llmfit`, fork of MIT
[AlexsJones/llmfit](https://github.com/AlexsJones/llmfit)) is a hardware-fit
recommender: a 5,355-model catalog with VRAM/RAM/quant/context, architecture
fields for VRAM math, real-world tok/s benchmarks, hardware presets +
simulation (RTX 5090 → M1), and a `capabilities` list that includes a
`tool_use` tag. It ships a Python package and JSON CLI
(`llmfit recommend --use-case coding`).

It answers the **fit axis** — *what runs on this hardware, how fast, and does it
claim tool_use*. It does **not** answer the **capability axis** — whether a
`tool_use`-tagged model actually drives Rook's agent loop. (`tool_use` is a
static HF metadata tag; `benchmarks.yaml` scores quality by regex-matching
free-text answers — neither tests tool calling.)

The two compose as a **two-stage filter**:

1. **llmfit narrows** — "models that fit the target hardware AND claim
   `tool_use`." Cheap, data-driven, spans the whole spectrum without owning the
   machines.
2. **This spike validates** — of those survivors, which actually do agentic
   tool-calling well enough for autonomous (Slice 3) vs. assist-only (Slice 2).

**Do not** shortcut the spike with llmfit's tag or quality score: a model can
fit, claim `tool_use`, score well on regex-quality, and still fail Rook's worker
loop via either failure layer above. llmfit picks candidates; the spike is the
gate.

## Hardware Is a Parameter

Tool-calling fitness is entangled with model size, and model size is bounded by
VRAM. The spike must declare its hardware tier(s):

| Tier | VRAM | Realistic models | Expectation |
|------|------|------------------|-------------|
| **Small** | ~8 GB (e.g. RTX 4070 Laptop — this dev box) | Qwen2.5-Coder-7B, Llama-3.1-8B, Mistral-7B (Q4) | Tool calls *parse*; agentic loops *shaky*. Likely chat-only. |
| **Capable** | 24–32 GB (e.g. RTX 4090/5090 workstation) | Qwen2.5/3-Coder-32B, Gemma-class, Mixtral (Q4/Q5) | The tier where autonomous-local *might* be viable. |
| **Server** | 48 GB+ / multi-GPU | Llama-3.3-70B, vLLM-served | Best case; out of scope for typical users. |

**Open item before running:** confirm which hardware the spike runs on. The dev
box observed on 2026-06-16 is 8 GB (small tier only). The profile reference to
`ollama_chat/qwen3-coder:30b-a3b-q8_0` implies a separate capable/server machine
— the capable tier is where the gating question is actually decided, so the spike
needs access to it.

## Hypotheses

- H1: Small-tier (7–8B) models parse tool calls but fail autonomous multi-tool
  loops reliably → **chat-only**.
- H2: Capable-tier (32B) models can complete a representative worker task most of
  the time → candidate for **autonomous-local**, pending variance.
- H3: A meaningful share of "local can't use tools" reports are actually the
  runtime/template parse-as-text trap, not model capability.
- H4: vLLM > llama-server > LM Studio > Ollama for *tool-call robustness* at equal
  model/quant (Ollama wins on UX, not robustness).

## Candidate Matrix

Backends × models, scoped to available hardware. **Select candidates via llmfit**
(`llmfit recommend` / the Python package), filtered to the target hardware tier
AND `tool_use` capability, so the matrix is data-grounded rather than guessed.
Run at least one model on each of two backends to separate the *model* axis from
the *runtime* axis (tests H3).

- **Ollama** (native): the model already in `model_profiles.json`
  (`qwen3-coder:30b-a3b-q8_0`) on capable hardware; a 7–8B coder model on small
  hardware.
- **llama.cpp `llama-server`** (`--jinja`, tool-capable template): the *same*
  GGUF as Ollama, to isolate the runtime/template axis.
- **vLLM** (OpenAI-compat): one tool-capable model on capable/server hardware.
- **LM Studio** (optional): same shape as `llama-server`, lower automation —
  include only if it's the user's actual environment.

## The Task

One **representative multi-tool worker task** that forces a 4–6 step tool loop.
Use the **worker / batch path** (`gh_snapshot` → `gh_edit`), because that is the
loop Slice 3 risks — not the chat persona's lighter, human-supervised tool use.

Proposed task (GH, deterministic, verifiable):

> "Create a number slider (0–10, value 5), feed it as the radius of a circle at
> the origin, then extrude that circle into a cylinder of height 10."

This requires: read canvas (`gh_snapshot`), select correct components by GUID
(knowledge query), emit a well-formed `gh_edit` with create + connect + set_values,
read the result, and stop. Success is **mechanically checkable** by a follow-up
snapshot (does a cylinder of the right dimensions exist?).

A Rhino-geometry variant (box → transform → boolean) is an acceptable alternative
if GH knowledge retrieval adds too much noise to the signal.

## Method

For each matrix cell:
1. Point a Rook **worker** at the candidate (`ROOK_WORKER_MODEL` + profile /
   `api_base`; for OpenAI-compat, set `api_base` to the server).
2. Run the same task **5×** (variance matters more than a single run).
3. Capture per run: tool-call parse success, task completion (snapshot check),
   count of malformed/incorrect tool calls, loop behavior (turns to completion or
   give-up), wall-clock latency.

## Instrumentation

- **Parse-as-text detector (tests H3):** log whether the LiteLLM response carried
  `tool_calls` vs. a tool-call-shaped string in `content`. This distinguishes the
  runtime/template trap from genuine model failure.
- **Trajectory:** reuse Guardian trajectory data where available.
- **Completion oracle:** post-run `gh_snapshot` assertion on the expected geometry,
  not the agent's self-report.

## Pass/Fail Criteria

- **Agent-grade** (clears the Slice 3 gate for that cell): ≥4/5 runs complete the
  task, **zero** malformed tool calls in passing runs, no runaway loops.
- **Chat-only:** tool calls parse, but completion is unreliable (≤3/5) or frequent
  malformed args. Safe for Slice 2 (human-in-loop), not Slice 3.
- **Unfit:** tool calls don't parse (parse-as-text) or frequent hard failures.
  Document the config tried (template/flags) before concluding.

## Decision Mapping

- Results **gate Slice 3**: only model+runtime+hardware cells that score
  agent-grade are eligible to drive the autonomous planner/worker stack on local.
- Results **inform docs**: a recommended-backends/models table for users, plus the
  explicit "assist-mode local OK / autonomous build needs cloud-or-vetted-local"
  stance.
- A failed parse-as-text cell becomes a **config doc** (the exact
  `llama-server --jinja` / template incantation), not a "local doesn't work"
  conclusion.

## Out of Scope

- Performance tuning, quantization sweeps, fine-tuning.
- Multi-agent swarm behavior (single-worker task is the unit here).
- Cost/throughput modeling.

## Links

- **North star:** `../../rook_docs/2026-06-16-rookllm-chooser-vision.md` — the
  RookLLM Chooser this spike's capability axis feeds.
- Model-control phase design: `2026-06-16-rook-chat-model-visibility-design.md`
- Routing source of truth: `mcp_server/src/rook/agent/model_profiles.py`
  (`api_base_for_model`, `detect_ollama_models`, `detect_lmstudio_models`).
