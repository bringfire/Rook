# Grasshopper as a Non-Linear Video Editor via SA_Banana

**Date:** 2026-04-09
**Status:** Design proposal / pre-implementation
**Authors:** Claude (Opus 4.6) — drafted in-session with aryan after completing the SA_Banana Video tab end-to-end
**Related:**
- `C:\Users\aryan\source\repos\SA_Banana` — the plugin that already owns the Veo video pipeline
- `C:\Users\aryan\source\repos\SA_Banana\src\SA_Banana\Services\VeoClient.cs` — the HTTP client whose shape fixes make this possible
- `C:\Users\aryan\source\repos\SA_Banana\src\SA_Banana\Services\VideoJobManager.cs` — the 2-concurrent job queue we'll reuse as a render farm
- `C:\Users\aryan\source\repos\SA_Banana\src\SA_Banana\Services\MediaStorage.cs` — the disk layout for videos + frames + sidecars
- `C:\Users\aryan\source\repos\SA_Banana\src\SA_Banana\Services\VideoCapabilities.cs` — the per-model capability matrix
- `C:\Users\aryan\source\repos\rook_docs\2026-04-08-sa-banana-integration.md` — the prior Rook integration doc, which this proposal complements but does not replace

---

## TL;DR

Grasshopper is already a visual dataflow engine with lazy evaluation, typed ports, topological sorting, expression nodes, timeline sliders, undo, and a solver that Rhino users know by muscle memory. SA_Banana's freshly-debugged Veo backend is already a job queue with on-disk caching, cost gating, and async polling. Bridge the two: a small companion `.gha` plugin turns Grasshopper into a **node-based non-linear video editor** where wires carry `VideoClip` and `VideoFrame` *descriptors*, not pixels, and a single `Render` sink component triggers real work. Every other node is a pure descriptor transformation that re-solves in milliseconds. Deterministic content-hash caching means identical subgraphs always hit cache; any wire-wiggle that changes one clip invalidates only that clip, not the whole timeline. The Rhino 3D model becomes a first-class input — viewport state, named views, layer visibility, display modes, and sun position are all parameter nodes that can drive video generation.

**Proof-of-concept in one session: three components (`Prompt → Clip`, `Trim`, `Render`), ~400 lines of C#, 100% reuse of the existing SA_Banana web server.**

---

## 1. Why this is not a gimmick

Three load-bearing observations:

**1. Every serious compositor is already a node graph.** Nuke, Natron, TouchDesigner, DaVinci Fusion, Houdini COPs — they all model video editing as a DAG of operators. Timeline-based NLEs (Premiere, Resolve edit page) are a convenience skin over the same primitive. Grasshopper is a general-purpose DAG editor with fifteen years of Rhino-user muscle memory behind it. It has already won the visual-programming war inside the AEC world. We don't need to build a node editor; we need to ship nodes.

**2. The Rhino model becomes a first-class video input.** Every other NLE treats your 3D scene as external footage — you render frames out of Rhino, import them as a clip, then lose the live connection. In this architecture, a `Viewport → Frame` component reads directly from the active Rhino document. If the user moves the sun, changes the camera, toggles a layer, or switches display modes, the component invalidates, and anything downstream regenerates automatically. **The video is a function of the model, not a snapshot of it.** That is a genuine novel capability — not a faster Premiere, but a different shape of thing entirely.

**3. Grasshopper's expression language is already a keyframe engine.** Number sliders, graph mapper, expression components, and the existing Timeline plugin give you animation curves for free. Want a prompt to interpolate over the duration of a clip? Feed a slider into the prompt input. Want I2V motion to follow a sine wave? Plug in a GH expression. We inherit an animation system without writing one.

Put the three together and you get: *a video DAG where every node can be driven by the parametric 3D model it lives inside, with animation curves that cost zero to implement.* That is not something Premiere can do. It is barely something TouchDesigner can do — and TouchDesigner doesn't have a native Rhino bridge.

---

## 2. The core insight: wires carry tokens, not pixels

The hardest architectural decision is what wires transport. If a wire carries `byte[]` or `Bitmap`, every slider wiggle regenerates everything, the solver grinds, and the user experience is a slideshow. If a wire carries a file *path*, you lose the ability to compose operations without materializing intermediates.

The right answer is **content-addressed descriptors**:

```csharp
public sealed record VideoClip(
    string Id,                           // deterministic content hash
    string? MediaPath,                   // null if not yet materialized
    ClipSource Source,                   // T2V | I2V | Interp | Trim | Concat | Crossfade | ...
    IReadOnlyList<VideoClip> Upstream,   // graph structure embedded
    VideoClipMetadata Meta               // duration, resolution, aspect, poster path
);

public sealed record VideoFrame(
    string Id,
    string? ImagePath,
    int Width, int Height,
    FrameSource Source,
    IReadOnlyList<VideoFrame> Upstream,
    FrameMetadata Meta
);
```

Every component takes upstream tokens, computes a new content hash over `(operator name + parameters + upstream hashes)`, and emits a new token. That hash is the cache key on disk. **Nothing is rendered until a sink component demands it.** The solver runs in microseconds even on thirty-node graphs because it's just shuffling descriptor records.

The content-hash cache gives us three properties for free:

- **Deterministic reuse.** Identical graphs always hit cache. Render the same composition twice → zero Veo calls the second time.
- **Incremental recompute.** Change one slider → invalidates one clip's hash → only that clip re-renders. The crossfade downstream of it re-runs in ~2 seconds locally; the other branch stays cached.
- **Shareable cache.** If the on-disk cache is under `SA_Banana\Videos\`, two users working on the same Rhino file in the same folder share the cache. (Out of scope for v1 but free in v2.)

This is the feature Premiere literally cannot do. Premiere's render cache is time-based, fragile, and opaque. Ours is a content-hash over the token graph — so long as your inputs are the same, the output is the same, forever.

---

## 3. Architecture: four phases

### Phase 1 — Tokens and the solver

A new `SA_Banana.GH` project (Grasshopper assembly, `.gha`). Components manipulate tokens only. No rendering, no ffmpeg, no Veo calls. The entire phase proves that:

1. Wires carry `VideoClip` / `VideoFrame` tokens correctly across Grasshopper's type system.
2. Content hashes are deterministic and stable across solver runs.
3. A twelve-node graph re-solves in under 50 ms.
4. GH's undo/history correctly rewinds token state.

Ship this alone as an internal milestone. It proves the dataflow model is viable before we touch anything expensive.

### Phase 2 — SA_Banana as the render farm

The `SA_Banana.GH` plugin talks to the existing SA_Banana web server on `localhost:17172` over HTTP. **We do not reimplement any of the backend.** The job queue, the shutdown-token cancellation, the 2-concurrent limit, the disk layout, the cost estimator, the gallery — all of it already exists and is debugged.

A **Render** sink component ("cooks" in GH terminology):

1. Walks the upstream token graph from the sink node.
2. For each token, checks if `Videos/{hash}.mp4` exists on disk.
3. For cache misses, issues the appropriate `POST /api/video/generate` or chains a sequence of them.
4. Polls `GET /api/video/status?jobId=...` asynchronously, without blocking the Grasshopper solver thread.
5. Writes the resulting paths back into the tokens (mutating the `MediaPath` field — the only mutation in the system).
6. Displays a preview thumbnail on the component face.

**The Render sink is the only component that does network I/O.** Every upstream component is a pure descriptor transformation. That invariant is the entire reason the system is fast.

### Phase 3 — Component palette (MVP)

Twelve components that together cover a surprising amount of real editing:

**Sources (produce tokens from the world):**

| Component | Inputs | Output | Backs onto |
|---|---|---|---|
| `Prompt → Clip` | text, model, duration, resolution, aspect | `VideoClip` | `POST /api/video/generate` mode=t2v |
| `Image → Clip` | `VideoFrame`, motion prompt, model, duration | `VideoClip` | `POST /api/video/generate` mode=i2v |
| `Start+End → Clip` | Frame A, Frame B, transition prompt | `VideoClip` | `POST /api/video/generate` mode=interp |
| `Viewport → Frame` | viewport id / named view | `VideoFrame` | `/api/view/capture` |
| `Nano Banana → Frame` | prompt, optional reference `VideoFrame` | `VideoFrame` | `/api/generate` |
| `Gallery → Clip/Frame` | file picker | `VideoClip` or `VideoFrame` | `/api/gallery` |

**Transforms (cheap, local, no Veo call):**

| Component | Inputs | Output | Implementation |
|---|---|---|---|
| `Trim` | Clip, in-time, out-time | Clip | `ffmpeg -ss -to -c copy` (lossless, millisecond-speed) |
| `Concatenate` | N clips | Clip | `ffmpeg concat` demuxer, stream copy |
| `Crossfade` | Clip A, Clip B, duration | Clip | `ffmpeg xfade` |
| `Speed` | Clip, factor | Clip | `ffmpeg setpts` |
| `Loop` | Clip, count | Clip | `ffmpeg concat` of the same file N times |

**Sinks (trigger actual work):**

| Component | Inputs | Output | Triggers |
|---|---|---|---|
| `Render` | Clip, output path | file on disk | Full cook pass — cache checks + Veo calls + ffmpeg stitching |
| `Preview` | Clip | inline player on component | Same as Render but 480p and auto-plays |

Twelve components. Covers 80% of the real editing grammar. The remaining 20% (color correction, audio mixing, titling, masking) can wait for v2.

### Phase 4 — The editing experience

A real workflow, end-to-end:

```
[Viewport: Perspective] ──► [Image → Clip: "camera pushes forward slowly"] ──┐
                                                                              │
                                                                              ├──► [Crossfade: 1.0s] ──► [Render: out.mp4]
                                                                              │
[Viewport: Section A] ──► [Image → Clip: "golden hour sweeps across facade"] ┘
```

User hits the "Cook" button on the Render sink. Grasshopper then:

1. Detects two Veo I2V jobs are needed (8 s each at 720 p Lite = $0.80 total).
2. Submits both in parallel — jobs 1 and 2 hit the 2-concurrent cap, perfect utilization.
3. Shows live progress on each component face (green ring filling up).
4. Once both clips are cached to disk, performs the 1-second crossfade locally via ffmpeg (~2 s).
5. Writes the final 15-second clip to `out.mp4`, shows inline preview on the sink.

Now the user drags the prompt slider on Clip 1 from "slowly" to "quickly". GH:

1. Invalidates Clip 1's content hash (parameters changed).
2. Clip 2 stays cached (its upstream is unchanged).
3. The crossfade token downstream of Clip 1 also invalidates, but its inputs (Clip 1's new token + Clip 2's cached token) are all we need.
4. One Veo job runs, one ffmpeg call stitches, new file is written.

**Total cost of iteration on one clip: $0.40 + 2 seconds of local processing.** That is the feature.

---

## 4. Grasshopper-specific concerns

### 4.1 Sync solver vs. async Veo jobs

Grasshopper's solver wants components to return synchronously. Veo jobs take 30 s – 6 min. Two options:

- **(a) Async sink with placeholder.** The Render sink returns immediately with an "unsolved" marker. A background task polls, and when the job completes it calls GH's `ExpireSolution()` to re-cook the sink with the now-cached result. Simpler. The user sees a spinning indicator on the sink for minutes, which is honest.
- **(b) Custom cook queue.** We implement our own "cook when ready" queue that lives alongside GH's solver. More complex, more invasive, but no "unsolved" states.

Strong recommendation: **option (a)**. GH already handles async components gracefully (the Hops plugin, LunchBox's async components, the Rhino.Inside plugin all use this pattern). Copy the pattern.

### 4.2 Preview performance

A live-updating inline video on every component during a cook would hammer the Rhino main thread. Rules:

- Previews are **480 p maximum**.
- Only the `Preview` sink and the `Render` sink render previews. Intermediate tokens show static poster frames from their metadata, not live playback.
- Poster frames are the I2V start image or the first frame of the generated clip (already written to `Videos/frames/` by `MediaStorage`).

### 4.3 Cost exposure

A graph with five `Image → Clip` components on Veo 3.1 standard 1080 p is $16 per full cook. Users will fat-finger a wire-wiggle into that. Mitigations:

- **The Render sink must show a pre-cook cost estimate.** Walk the graph, compute total cost assuming all tokens are cache misses, display it on the component face before the user hits Cook.
- **A "Dry Run" toggle on the sink** that walks the graph and reports what would be submitted without actually submitting.
- **The existing $2 confirmation gate from the SA_Banana WebUI** should be honored. If the total pre-cook estimate exceeds $2, the sink pops a modal before the first network call.
- **Cache-hit highlighting.** During the dry run, color-code each component: green = cached hit, orange = will cost money, red = unsupported combination. Visual cost map at a glance.

### 4.4 ffmpeg dependency

ffmpeg is load-bearing for everything beyond "one Veo clip → one file". Options:

- **Bundle a static Windows build.** Full ffmpeg is ~80 MB; a stripped build with just H.264 + AAC + concat/xfade filters is ~20 MB. Acceptable if the plugin is already Rhino-sized.
- **Detect user-installed ffmpeg.** Check `PATH`, fall back to a download prompt on first use.
- **Ship both.** Bundle the stripped build; if the user has a fuller ffmpeg on PATH, prefer that.

Lean toward **option 3**. Power users get their own codec set; casual users get zero-install.

### 4.5 Component packaging

`SA_Banana.GH.gha` is a separate .NET assembly that references `SA_Banana.dll` or (better) talks to the web server over HTTP. Three reasons to keep it separate from `SA_Banana.rhp`:

1. **Optional install.** Users who don't touch Grasshopper aren't forced to load GH components into Rhino.
2. **Independent release cadence.** The core SA_Banana plugin is now stable; GH components can iterate without re-releasing the whole plugin.
3. **Clean dependency direction.** `SA_Banana.GH` depends on `SA_Banana`'s HTTP surface, not its internals. If tomorrow we swap the HTTP server for something else, the GH plugin doesn't care as long as the endpoints stay stable.

The .gha deploys to `%APPDATA%\Grasshopper\Libraries\SA_Banana.GH.gha`. Grasshopper auto-loads it on startup.

---

## 5. Component API design (sketch)

Here is the signature of a representative component, to show the shape:

```csharp
public class PromptToClipComponent : GH_Component
{
    public PromptToClipComponent()
        : base("Prompt → Clip", "T2V",
               "Generate a video clip from a text prompt using Veo.",
               "SA_Banana", "Sources") { }

    protected override void RegisterInputParams(GH_InputParamManager p)
    {
        p.AddTextParameter("Prompt", "P", "Text description of the shot", GH_ParamAccess.item);
        p.AddTextParameter("Model", "M", "Veo model ID", GH_ParamAccess.item, "veo-3.1-lite-generate-preview");
        p.AddIntegerParameter("Duration", "D", "Clip duration in seconds", GH_ParamAccess.item, 8);
        p.AddTextParameter("Resolution", "R", "720p / 1080p / 4k", GH_ParamAccess.item, "720p");
        p.AddTextParameter("Aspect", "A", "16:9 or 9:16", GH_ParamAccess.item, "16:9");
    }

    protected override void RegisterOutputParams(GH_OutputParamManager p)
    {
        p.AddGenericParameter("Clip", "C", "VideoClip token", GH_ParamAccess.item);
    }

    protected override void SolveInstance(IGH_DataAccess da)
    {
        string prompt = ""; string model = ""; int dur = 8;
        string res = ""; string aspect = "";
        if (!da.GetData(0, ref prompt)) return;
        if (!da.GetData(1, ref model))  return;
        if (!da.GetData(2, ref dur))    return;
        if (!da.GetData(3, ref res))    return;
        if (!da.GetData(4, ref aspect)) return;

        // Deterministic content hash — identical inputs → identical id
        var id = ContentHash.Compute("t2v", prompt, model, dur, res, aspect);

        var clip = new VideoClip(
            Id: id,
            MediaPath: null,  // not yet rendered
            Source: new T2VSource(prompt, model, dur, res, aspect),
            Upstream: Array.Empty<VideoClip>(),
            Meta: new VideoClipMetadata(dur, res, aspect, poster: null)
        );

        da.SetData(0, clip);
    }

    public override Guid ComponentGuid => new("...stable guid...");
}
```

Key properties of this shape:
- `SolveInstance` does **zero I/O**. It just builds a descriptor.
- Any wire upstream of this component re-solves in microseconds because the whole thing is pure record construction.
- The content hash is computed once per solve; GH caches the output parameter until inputs change.

The `Render` sink is the only component that looks meaningfully different — it spawns a background task, calls `ExpireSolution()` when the task completes, and displays progress on its face via a custom `GH_ComponentAttributes` subclass.

---

## 6. Risks and honest problems

**(a) GH's async component support is informal.** There's no first-class async-component API. Everyone who does this rolls their own pattern (Hops, LunchBox, Rhino.Inside). Known-good but not blessed by McNeel. Mitigation: copy the Hops pattern exactly, which has years of production use.

**(b) Cost exposure is real.** A careless wire-wiggle on a five-clip graph at 3.1 standard 4 K is $100. The cost gate must be unmissable and must fire *before* any HTTP call. Mitigation: the dry-run / pre-cook estimate is non-optional on v1.

**(c) Determinism caveat.** Content-hash caching assumes identical inputs → identical outputs. Veo is a diffusion model with implicit randomness unless a seed is specified. If the user wants deterministic output across cooks, they must set a seed (which is already a field on `VideoGenerationRequest` — just not exposed in the WebUI yet). If they don't, cache hits are only guaranteed for the *exact same submitted request*, not for re-submissions of semantically identical prompts. Document this loudly.

**(d) ffmpeg footprint.** 20 MB is real weight. Acceptable for a video plugin but not trivial. Mitigation: detect-first, bundle-as-fallback (section 4.4).

**(e) Rhino main thread.** Any preview that touches a `Bitmap` via System.Drawing must marshal through `RhinoApp.InvokeOnUiThread`. The existing SA_Banana code already handles this correctly for viewport capture; the GH layer must follow the same discipline. Mitigation: all thumbnail rendering goes through a single helper that enforces UI-thread marshaling.

**(f) Graph complexity.** A 50-node video graph is easy to imagine and hard to debug. GH's built-in bubble profiler helps. Mitigation: a custom profiler panel that shows per-component cache status, estimated cost, and most-recent job state.

---

## 7. Prior art check

I don't want to build something someone else has nailed. Adjacent-but-not-overlapping systems:

- **TouchDesigner** has node-based video compositing and recently added image generation. It does not have a native Rhino model bridge. The operator graph is real-time-oriented (optimized for 60 fps), not offline-rendering oriented.
- **Houdini COPs** (Compositing Operators) is a node-based image/video processor. Houdini has a Rhino importer but no live Grasshopper bridge.
- **Nuke** has `.nk` node graphs but is film-VFX-oriented and has no 3D model bridge at all.
- **Grasshopper's existing video nodes** — I'm aware of Lunchbox, Pufferfish, and Heteroptera, none of which include video generation or editing primitives. The GH video-adjacent work that exists is playback-only (Firefly had a webcam node circa 2015).
- **Rhino.Inside.Revit** uses Grasshopper as a live bridge to another host — the pattern of "GH as interop layer" has McNeel-sanctioned prior art.

**Verdict: no direct prior art.** TouchDesigner comes closest on the "node-based video with gen-AI" axis; nothing is close on "GH as video NLE" or "3D model as video input."

---

## 8. Proof of concept — the one-session build

The scope that's actually achievable in a single focused session:

**Three components:**
1. `Prompt → Clip` — T2V submission wrapper. No caching. No ffmpeg. Just builds a token.
2. `Trim` — pure descriptor transform. Emits a new token whose MediaPath is still null. The Render sink will apply the trim via ffmpeg when it materializes.
3. `Render` — async sink. Walks upstream, calls `POST /api/video/generate`, polls `/api/video/status`, downloads via `/api/video/file`, displays the result path and a preview thumbnail.

**Skipped for the PoC:**
- ffmpeg integration — the Trim component builds a trim descriptor but Render ignores it and downloads the raw clip. (The Trim component's only job in the PoC is to prove wire types carry across component boundaries.)
- Content-hash caching — every cook re-submits. Fine for a PoC; catastrophic for production.
- Cost estimation — no pre-cook estimate. The user gets billed whatever happens.
- Previews on intermediate components.
- The other nine components from the palette.

**Deliverable:** a `.gha` file that, when dropped into `%APPDATA%\Grasshopper\Libraries\`, adds three components under a new "SA_Banana" tab. Wire `Prompt → Trim → Render`, hit Cook, and watch a Veo clip land on disk.

**Estimated code:** ~400 lines across five files:
- `SA_Banana.GH.csproj` — GH assembly targeting `net48` (Grasshopper is still net48 on Rhino 8)
- `Tokens.cs` — `VideoClip`, `VideoFrame`, `ContentHash` helper
- `HttpBridge.cs` — thin wrapper around the existing SA_Banana endpoints
- `Components/PromptToClip.cs`
- `Components/Trim.cs`
- `Components/Render.cs`
- `SA_BananaGHInfo.cs` — assembly descriptor for GH's loader

**What the PoC proves:**
- Wire types work across GH's type system.
- Async rendering with `ExpireSolution()` integrates cleanly with the solver.
- The existing SA_Banana HTTP surface is sufficient — no server-side changes needed.
- The pattern is usable enough for a human to want more components.

---

## 9. Open decisions

1. **Is this v1.1 of SA_Banana, or a separate product?** Separate plugin, same author, same repo — probably best.
2. **Does aryan already use Grasshopper regularly?** The pattern is beautiful either way, but the payoff is enormous if the answer is yes. If no, this is still worth building as a proof that *the pattern* is right, even if the tool isn't for him personally.
3. **ffmpeg bundling — acceptable?** Leaning yes, with detect-first fallback, but confirm before committing the 20 MB.
4. **Seed surfacing.** Determinism requires seeds. The WebUI doesn't expose seed yet. The GH layer should probably force it (auto-generate a stable seed per component guid if the user doesn't specify) to make content-hash caching meaningful.
5. **v2 wishlist items to explicitly defer:** color grading, audio mixing, titles, masking, motion tracking, multi-track timeline view, export to EDL/AAF, collaborative cache sharing. Each is a real feature; none is PoC-critical.

---

## 10. Why this is worth writing down

Most "crazy ideas" are forgettable. This one has a specific property that makes it worth committing to disk even if we don't build it tomorrow:

**It validates the entire SA_Banana architectural effort.** The fact that we can bolt a node-based video editor on top of SA_Banana with zero backend changes is a direct consequence of every choice we made across 14 rounds of review:

- The HTTP surface is clean enough to be driven by a second client.
- The job manager is a genuine job queue, not a request-scoped task.
- The disk layout has primary-media / sidecar / helper-frame separation that caching can hook into trivially.
- The capability matrix is data, not code, so the GH plugin can consume it over the wire.
- The `StreamResult` router path means a GH component can stream video bytes without re-serializing through base64.
- The shutdown CTS propagation means a running cook can be cancelled cleanly by unloading the plugin.
- The content-hash caching becomes possible because every request shape is deterministic.

**None of that was an accident.** Every one of those decisions was load-bearing for a feature I didn't know we'd want when I made the decision. Writing this design doc is the evidence that the earlier work was not over-engineered — it was correctly-scoped for extensibility.

If we never build this, the design exercise still matters: it's the test that validates SA_Banana as a platform rather than as a one-off WebUI tab.

---

## 11. Recommended next action

One of:

- **(a) Close this doc as "someday / maybe"** and pick up WebUI polish work (reference images, video extension, seed, negative prompt) on the main SA_Banana plugin.
- **(b) Ship the three-component PoC** in a new session, using this doc as the contract. Acceptance criterion: a .gha file that can take a prompt and produce an MP4 via `Prompt → Render`.
- **(c) Ship the full twelve-component palette** across several sessions, with ffmpeg integration and content-hash caching.

My recommendation: **(b)**. The PoC is cheap enough to be worth the information it returns — we'll learn more from a working three-component .gha in production than from another round of design iteration on paper. If the PoC is a hit, we commit to (c) with confidence. If it falls flat because the GH async pattern fights us harder than expected, we've learned that too, and the four hours weren't wasted.

---

*Last edited 2026-04-09 — drafted in-session immediately after the SA_Banana Video tab was verified working end-to-end across all three Veo 3.1 variants.*
