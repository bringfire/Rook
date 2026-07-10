# Rook Three.js Rhino Stress Harness

This is an isolated experiment. It does not connect to live Rhino or ship with Rook.

## Setup

From the Rook root, first prove the ignore boundary:

```powershell
git check-ignore -v experiments/threejs-rhino-stress/node_modules/.probe
```

Then run from this experiment directory:

```powershell
npm ci
npm run fixture
npm test
npm run build
npm run dev
```

Open the local URL printed by Vite. Keep browser zoom at 100 percent and leave the tab visible for the entire run. Use **Build / Load** after changing a configuration, then use **Run 3 Trials**. The checked-in local-file case is `fixtures/actor-metadata.glb`.

## Protocol

The harness fixes 1920 x 1080 at DPR 1, uses 120 warm-up frames and 300 measured frames for each of three trials, and reports nearest-rank p50/p95/p99/max. GPU timing uses `EXT_disjoint_timer_query_webgl2` when at least 270 samples are valid.

Camera position, target, projection, and actor size stay fixed across tiers. Synthetic actor centers are distributed over the same 8.1-by-8.1 world-space extent at every actor count, so all declared actors remain in the fixed-camera frustum while increasing node, draw-call, vertex, and material pressure.

Each trial is classified independently. The headline is the worst completed trial; any aborted trial makes the configuration impractical. Pooled values are descriptive only. The 10,000-actor case is opt-in and requires explicit confirmation. Pixel readback runs after timed trials.

For synthetic sources, the report contains three coordinate-precision samples at animation times 0, 0.5, and 1, plus a visible-equivalence comparison between unbatched and merged context. Any failed comparison makes the headline impractical. Local GLB reports coordinate precision unavailable because it has no generated rebased comparison pair.
