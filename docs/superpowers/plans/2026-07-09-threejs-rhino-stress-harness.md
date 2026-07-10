# Three.js Rhino Stress Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Build an isolated, reproducible Three.js browser experiment that measures distinct animatable scene nodes, proves GLB actor metadata survival, compares scene-organization strategies, and evaluates deterministic absolute-time animation without changing production Rook code.

**Architecture:** A Vite application under experiments/threejs-rhino-stress owns deterministic scene generation, GLB loading, actor indexing, absolute-time evaluation, WebGL rendering, benchmark orchestration, and report presentation. Pure modules hold identity, metrics, fixture, and lifecycle logic so Vitest can verify them without WebGL; browser-only adapters own GPU queries, pixel readback, and the fixed render profile.

**Tech Stack:** Node 22.20.0, npm 10.9.3, Three.js 0.181.2, Vite 8.1.4, Vitest 4.1.10, JavaScript ES modules, WebGL2.

## Global Constraints

- Work only under experiments/threejs-rhino-stress plus this plan document; do not modify RookNative, Rook Companion, MCP registration, installer, or release packaging.
- Create the experiment-local .gitignore and prove node_modules is ignored before running any dependency installation command.
- Pin direct dependencies exactly: three@0.181.2, vite@8.1.4, and vitest@4.1.10; commit package-lock.json.
- Require Node >=22.12.0 <23 and declare packageManager npm@10.9.3.
- Make no runtime network requests; GLB inputs come from generated fixtures or the local file picker.
- Fix the drawing buffer at 1920 x 1080 with renderer pixel ratio 1.
- Use 120 warm-up frames, 300 measured frames, and three trials per configuration.
- Classify each completed trial independently. The configuration headline is the worst completed trial; any aborted trial, context loss, or absence of a completed trial makes the headline impractical. Pooled samples are descriptive only.
- Use the greater of CPU-submission p95 and valid GPU-duration p95 when at least 270 GPU samples exist; otherwise qualify the tier as cpu_proxy_only.
- Keep the 10,000-actor case opt-in; never run it on page load.
- Evaluate animation from explicit absolute time only.
- Execute through superpowers:subagent-driven-development sequentially: one fresh implementer per task, a requirements review and code-quality review gate after each task, no parallel task dispatch, and one final whole-branch review.

## Execution Preflight: Isolated Feature Worktree

Before Task 1, invoke superpowers:using-git-worktrees and create an isolated worktree from the verified main branch. The intended branch and location are:

~~~text
branch: codex/threejs-rhino-stress-harness
worktree: C:/Users/aryan/source/repos/Rook/.worktrees/threejs-rhino-stress-harness
~~~

The preflight must verify that `.worktrees/` is ignored, create the worktree without changing main, and confirm the new worktree starts clean:

~~~powershell
git check-ignore -v .worktrees/probe
git worktree add .worktrees/threejs-rhino-stress-harness -b codex/threejs-rhino-stress-harness
git -C .worktrees/threejs-rhino-stress-harness status --short
~~~

Expected: the ignore probe exits 0, worktree creation succeeds, and status output is empty. All Task 1-10 commands run inside the feature worktree. Dependency installation remains forbidden until Task 1 creates the experiment-local `.gitignore` and its separate `node_modules/.probe` check passes.

## Planned File Structure

~~~text
experiments/threejs-rhino-stress/
  .gitignore
  package.json
  package-lock.json
  index.html
  README.md
  src/
    actor-index.js
    animation.js
    benchmark.js
    config.js
    disposal.js
    evidence.js
    glb-loader.js
    gpu-timer.js
    main.js
    metrics.js
    precision.js
    renderer.js
    scene-generator.js
    styles.css
  scripts/
    fixture-builder.mjs
    generate-actor-metadata-fixture.mjs
  fixtures/
    actor-metadata.glb
    actor-metadata.sha256
  tests/
    actor-index.test.js
    animation.test.js
    benchmark.test.js
    batching.test.js
    disposal.test.js
    evidence.test.js
    fixture.test.js
    glb-loader.test.js
    metrics.test.js
    precision.test.js
    scaffold.test.js
    scene-generator.test.js
~~~

---

### Task 1: Safe Scaffold and Pinned Toolchain

**Files:**
- Create: experiments/threejs-rhino-stress/.gitignore
- Create: experiments/threejs-rhino-stress/package.json
- Create: experiments/threejs-rhino-stress/index.html
- Create: experiments/threejs-rhino-stress/src/main.js
- Create: experiments/threejs-rhino-stress/src/styles.css
- Create: experiments/threejs-rhino-stress/tests/scaffold.test.js
- Generate: experiments/threejs-rhino-stress/package-lock.json

**Interfaces:**
- Consumes: repository ignore behavior and installed Node/npm.
- Produces: isolated npm project with test, build, dev, and fixture scripts.

- [ ] **Step 1: Create .gitignore before any npm command**

~~~gitignore
node_modules/
dist/
reports/
tmp/
~~~

- [ ] **Step 2: Prove node_modules is ignored**

Run from the Rook root:

~~~powershell
git check-ignore -v experiments/threejs-rhino-stress/node_modules/.probe
~~~

Expected: exit 0 and output naming the experiment-local .gitignore. Stop if it fails.

- [ ] **Step 3: Create the exact package manifest**

~~~json
{
  "name": "rook-threejs-rhino-stress",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "engines": { "node": ">=22.12.0 <23" },
  "packageManager": "npm@10.9.3",
  "scripts": {
    "dev": "vite --host 127.0.0.1",
    "test": "vitest run",
    "test:watch": "vitest",
    "build": "vite build",
    "fixture": "node scripts/generate-actor-metadata-fixture.mjs"
  },
  "dependencies": { "three": "0.181.2" },
  "devDependencies": { "vite": "8.1.4", "vitest": "4.1.10" }
}
~~~

- [ ] **Step 4: Write the failing scaffold test**

~~~js
// tests/scaffold.test.js
import { describe, expect, it } from "vitest";
import { APP_TITLE } from "../src/main.js";

describe("scaffold", () => {
  it("uses the fixed title", () => {
    expect(APP_TITLE).toBe("Rook Three.js Rhino Stress Harness");
  });
});
~~~

- [ ] **Step 5: Install only after Step 2, then confirm the red test**

~~~powershell
npm install
npm test -- --run tests/scaffold.test.js
~~~

Expected: npm creates package-lock.json and ignored node_modules; the test fails because src/main.js is absent.

- [ ] **Step 6: Add the minimal page shell**

~~~js
// src/main.js
export const APP_TITLE = "Rook Three.js Rhino Stress Harness";
if (typeof document !== "undefined") {
  document.title = APP_TITLE;
  document.querySelector("#app").innerHTML =
    '<main class="shell"><h1>' + APP_TITLE + '</h1><p>Scaffold ready.</p></main>';
}
~~~

~~~html
<!-- index.html -->
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <link rel="stylesheet" href="/src/styles.css">
  <title>Rook Three.js Rhino Stress Harness</title>
</head>
<body><div id="app"></div><script type="module" src="/src/main.js"></script></body>
</html>
~~~

~~~css
/* src/styles.css */
:root { color-scheme: dark; font-family: Inter, system-ui, sans-serif; }
* { box-sizing: border-box; }
body { margin: 0; background: #0b1020; color: #e8edf7; }
.shell { min-height: 100vh; padding: 24px; }
~~~

- [ ] **Step 7: Verify and commit**

~~~powershell
npm test -- --run tests/scaffold.test.js
npm run build
git add experiments/threejs-rhino-stress
git commit -m "chore: scaffold Three.js Rhino stress experiment"
~~~

Expected: one passing test, build exit 0, and no node_modules or dist content staged.

---

### Task 2: Per-Trial Metrics and Worst-Trial Headline

**Files:**
- Create: experiments/threejs-rhino-stress/src/metrics.js
- Create: experiments/threejs-rhino-stress/tests/metrics.test.js

**Interfaces:**
- Produces: nearestRank(values, quantile), summarizeSamples(values), classifyTrial(input), classifyConfiguration(trials).

- [ ] **Step 1: Write failing classification tests**

~~~js
// tests/metrics.test.js
import { describe, expect, it } from "vitest";
import {
  classifyConfiguration, classifyTrial, nearestRank, summarizeSamples,
} from "../src/metrics.js";

describe("metrics", () => {
  it("uses nearest-rank percentiles", () => {
    const values = Array.from({ length: 100 }, (_, index) => index + 1);
    expect(nearestRank(values, 0.5)).toBe(50);
    expect(nearestRank(values, 0.95)).toBe(95);
    expect(nearestRank(values, 0.99)).toBe(99);
  });

  it("does not invent empty statistics", () => {
    expect(summarizeSamples([])).toEqual({
      count: 0, average: null, p50: null, p95: null, p99: null, max: null,
    });
  });

  it("uses the slower valid CPU or GPU p95", () => {
    expect(classifyTrial({
      status: "completed", correctnessPassed: true, constructionMs: 200,
      cpu: { p95: 8, p99: 12 },
      gpu: { validCount: 300, p95: 20, p99: 22 },
    })).toMatchObject({ tier: "preview-viable", basis: "cpu_and_gpu", frameP95: 20 });
  });

  it("uses CPU proxy below 270 GPU samples", () => {
    expect(classifyTrial({
      status: "completed", correctnessPassed: true, constructionMs: 200,
      cpu: { p95: 12, p99: 20 },
      gpu: { validCount: 269, p95: 6, p99: 8 },
    })).toMatchObject({ tier: "interactive", basis: "cpu_proxy_only" });
  });

  it("uses the worst completed trial, not pooled samples", () => {
    expect(classifyConfiguration([
      { status: "completed", classification: { tier: "interactive" } },
      { status: "completed", classification: { tier: "marginal" } },
      { status: "completed", classification: { tier: "preview-viable" } },
    ])).toEqual({ tier: "marginal", source: "worst_completed_trial", trialIndex: 1 });
  });

  it("makes an aborted trial impractical", () => {
    expect(classifyConfiguration([
      { status: "completed", classification: { tier: "interactive" } },
      { status: "aborted", reason: "context_lost" },
    ])).toEqual({ tier: "impractical", source: "aborted_trial", trialIndex: 1 });
  });
});
~~~

- [ ] **Step 2: Run the red test**

~~~powershell
npm test -- --run tests/metrics.test.js
~~~

Expected: FAIL because src/metrics.js is absent.

- [ ] **Step 3: Implement statistics and classification**

~~~js
// src/metrics.js
const TIER_RANK = {
  interactive: 0, "preview-viable": 1, marginal: 2, impractical: 3,
};

export function nearestRank(values, quantile) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.max(1, Math.ceil(quantile * sorted.length)) - 1];
}

export function summarizeSamples(values) {
  if (!values.length) {
    return { count: 0, average: null, p50: null, p95: null, p99: null, max: null };
  }
  return {
    count: values.length,
    average: values.reduce((sum, value) => sum + value, 0) / values.length,
    p50: nearestRank(values, 0.5),
    p95: nearestRank(values, 0.95),
    p99: nearestRank(values, 0.99),
    max: Math.max(...values),
  };
}

export function classifyTrial({ status, correctnessPassed, constructionMs, cpu, gpu }) {
  if (status !== "completed" || !correctnessPassed || constructionMs > 30000) {
    return { tier: "impractical", basis: "trial_failure", frameP95: null, frameP99: null };
  }
  const gpuValid = gpu?.validCount >= 270 && Number.isFinite(gpu?.p95);
  const basis = gpuValid ? "cpu_and_gpu" : "cpu_proxy_only";
  const frameP95 = gpuValid ? Math.max(cpu.p95, gpu.p95) : cpu.p95;
  const frameP99 = gpuValid ? Math.max(cpu.p99, gpu.p99) : cpu.p99;
  let tier = "interactive";
  if (frameP95 > 100) tier = "impractical";
  else if (constructionMs > 10000 || frameP95 > 33.33) tier = "marginal";
  else if (frameP95 > 16.67 || frameP99 > 33.33) tier = "preview-viable";
  return { tier, basis, frameP95, frameP99 };
}

export function classifyConfiguration(trials) {
  const aborted = trials.findIndex((trial) => trial.status !== "completed");
  if (aborted >= 0) return { tier: "impractical", source: "aborted_trial", trialIndex: aborted };
  if (!trials.length) return { tier: "impractical", source: "no_completed_trial", trialIndex: null };
  let worst = 0;
  for (let index = 1; index < trials.length; index += 1) {
    if (TIER_RANK[trials[index].classification.tier] >
        TIER_RANK[trials[worst].classification.tier]) worst = index;
  }
  return {
    tier: trials[worst].classification.tier,
    source: "worst_completed_trial",
    trialIndex: worst,
  };
}
~~~

- [ ] **Step 4: Verify and commit**

~~~powershell
npm test -- --run tests/metrics.test.js
npm test
git add experiments/threejs-rhino-stress/src/metrics.js experiments/threejs-rhino-stress/tests/metrics.test.js
git commit -m "test: define Three.js benchmark tiers"
~~~

Expected: focused and full suites pass.

---

### Task 3: Independent Metadata-Bearing GLB Fixture

**Files:**
- Create: experiments/threejs-rhino-stress/scripts/fixture-builder.mjs
- Create: experiments/threejs-rhino-stress/scripts/generate-actor-metadata-fixture.mjs
- Generate: experiments/threejs-rhino-stress/fixtures/actor-metadata.glb
- Generate: experiments/threejs-rhino-stress/fixtures/actor-metadata.sha256
- Create: experiments/threejs-rhino-stress/tests/fixture.test.js

**Interfaces:**
- Produces: buildActorMetadataGlb(): Buffer and sha256Hex(bytes): string.

- [ ] **Step 1: Write failing fixture and loader proof**

~~~js
// tests/fixture.test.js
import { readFile } from "node:fs/promises";
import { describe, expect, it } from "vitest";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { buildActorMetadataGlb, sha256Hex } from "../scripts/fixture-builder.mjs";

const fixture = new URL("../fixtures/actor-metadata.glb", import.meta.url);
const checksum = new URL("../fixtures/actor-metadata.sha256", import.meta.url);

describe("metadata fixture", () => {
  it("is byte deterministic", async () => {
    const committed = await readFile(fixture);
    const digest = (await readFile(checksum, "utf8")).trim();
    const generated = buildActorMetadataGlb();
    expect(generated.equals(committed)).toBe(true);
    expect(sha256Hex(generated)).toBe(digest);
  });

  it("survives GLTFLoader with exact actor IDs", async () => {
    const bytes = await readFile(fixture);
    const input = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
    const gltf = await new GLTFLoader().parseAsync(input, "");
    const actors = [];
    gltf.scene.traverse((object) => {
      if (object.userData.actorId) actors.push(object);
    });
    expect(actors.map((actor) => actor.userData.actorId).sort())
      .toEqual(["fixture_actor_a", "fixture_actor_b"]);
    expect(actors.every((actor) => actor.userData.actorSetId === "fixture_set")).toBe(true);
    expect(actors.every((actor) => actor.userData.sourceKind === "fixture")).toBe(true);
    expect(actors[0]).not.toBe(actors[1]);
  });
});
~~~

- [ ] **Step 2: Run the red test**

~~~powershell
npm test -- --run tests/fixture.test.js
~~~

Expected: FAIL because generator and fixture are absent.

- [ ] **Step 3: Implement an independent minimal GLB writer**

~~~js
// scripts/fixture-builder.mjs
import { createHash } from "node:crypto";

const pad4 = (length) => (4 - (length % 4)) % 4;
const u32 = (value) => {
  const result = Buffer.alloc(4);
  result.writeUInt32LE(value);
  return result;
};

export const sha256Hex = (bytes) =>
  createHash("sha256").update(bytes).digest("hex");

export function buildActorMetadataGlb() {
  const positions = Buffer.alloc(36);
  [[-0.5, 0, 0], [0.5, 0, 0], [0, 1, 0]].forEach((point, pointIndex) => {
    point.forEach((value, axis) =>
      positions.writeFloatLE(value, pointIndex * 12 + axis * 4));
  });
  const indices = Buffer.alloc(8);
  [0, 1, 2].forEach((value, index) => indices.writeUInt16LE(value, index * 2));
  const binary = Buffer.concat([positions, indices]);
  const gltf = {
    asset: { version: "2.0", generator: "Rook actor fixture" },
    scene: 0,
    scenes: [{ nodes: [0, 1] }],
    nodes: [
      { name: "Actor A", mesh: 0, translation: [-1, 0, 0],
        extras: { actorId: "fixture_actor_a", actorSetId: "fixture_set", sourceKind: "fixture" } },
      { name: "Actor B", mesh: 0, translation: [1, 0, 0],
        extras: { actorId: "fixture_actor_b", actorSetId: "fixture_set", sourceKind: "fixture" } },
    ],
    meshes: [{ primitives: [{ attributes: { POSITION: 0 }, indices: 1, mode: 4 }] }],
    buffers: [{ byteLength: binary.length }],
    bufferViews: [
      { buffer: 0, byteOffset: 0, byteLength: 36, target: 34962 },
      { buffer: 0, byteOffset: 36, byteLength: 6, target: 34963 },
    ],
    accessors: [
      { bufferView: 0, componentType: 5126, count: 3, type: "VEC3",
        min: [-0.5, 0, 0], max: [0.5, 1, 0] },
      { bufferView: 1, componentType: 5123, count: 3, type: "SCALAR",
        min: [0], max: [2] },
    ],
  };
  const source = Buffer.from(JSON.stringify(gltf));
  const json = Buffer.concat([source, Buffer.alloc(pad4(source.length), 0x20)]);
  const bin = Buffer.concat([binary, Buffer.alloc(pad4(binary.length))]);
  const length = 12 + 8 + json.length + 8 + bin.length;
  return Buffer.concat([
    Buffer.from("glTF"), u32(2), u32(length),
    u32(json.length), Buffer.from("JSON"), json,
    u32(bin.length), Buffer.from([0x42, 0x49, 0x4e, 0]), bin,
  ]);
}
~~~

- [ ] **Step 4: Add the deterministic writer command**

~~~js
// scripts/generate-actor-metadata-fixture.mjs
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { buildActorMetadataGlb, sha256Hex } from "./fixture-builder.mjs";

const output = resolve(dirname(fileURLToPath(import.meta.url)), "../fixtures");
const bytes = buildActorMetadataGlb();
await mkdir(output, { recursive: true });
await writeFile(resolve(output, "actor-metadata.glb"), bytes);
await writeFile(resolve(output, "actor-metadata.sha256"),
  sha256Hex(bytes) + "\n", "utf8");
~~~

- [ ] **Step 5: Generate, verify, and commit**

~~~powershell
npm run fixture
npm test -- --run tests/fixture.test.js
git add experiments/threejs-rhino-stress/scripts experiments/threejs-rhino-stress/fixtures experiments/threejs-rhino-stress/tests/fixture.test.js
git commit -m "test: prove GLB actor metadata survival"
~~~

Expected: both fixture tests pass and regeneration is byte-identical.

---

### Task 4: Deterministic Actors and Static Context Batching

**Files:**
- Create: experiments/threejs-rhino-stress/src/config.js
- Create: experiments/threejs-rhino-stress/src/scene-generator.js
- Create: experiments/threejs-rhino-stress/tests/scene-generator.test.js
- Create: experiments/threejs-rhino-stress/tests/batching.test.js

**Interfaces:**
- Produces: DEFAULT_CONFIG, BENCHMARK_PROTOCOL, createSyntheticScene(config), countScene(root).

- [ ] **Step 1: Write failing scene and batching tests**

~~~js
// tests/scene-generator.test.js
import { describe, expect, it } from "vitest";
import { createSyntheticScene } from "../src/scene-generator.js";

describe("scene generator", () => {
  it("creates stable distinct actors with shared geometry", () => {
    const result = createSyntheticScene({ actorCount: 3, geometryOwnership: "shared" });
    expect(result.actors.map((actor) => actor.userData.actorId)).toEqual([
      "synthetic_actor_000000", "synthetic_actor_000001", "synthetic_actor_000002",
    ]);
    expect(new Set(result.actors).size).toBe(3);
    expect(result.actors[0].children[0].geometry)
      .toBe(result.actors[1].children[0].geometry);
  });

  it("duplicates geometry only when selected", () => {
    const result = createSyntheticScene({ actorCount: 2, geometryOwnership: "duplicated" });
    expect(result.actors[0].children[0].geometry)
      .not.toBe(result.actors[1].children[0].geometry);
  });

  it("separates source, rebase, and applied render origins", () => {
    const rebased = createSyntheticScene({
      actorCount: 1, coordinateMode: "rebased",
    });
    const large = createSyntheticScene({
      actorCount: 1, coordinateMode: "large",
    });
    expect(rebased.sourceOrigin).toEqual([300000, -200000, 20000]);
    expect(rebased.rebaseOrigin).toEqual([300000, -200000, 20000]);
    expect(rebased.appliedRenderOffset).toEqual([0, 0, 0]);
    expect(large.sourceOrigin).toEqual([300000, -200000, 20000]);
    expect(large.rebaseOrigin).toEqual([0, 0, 0]);
    expect(large.appliedRenderOffset).toEqual([300000, -200000, 20000]);
  });
});
~~~

~~~js
// tests/batching.test.js
import { describe, expect, it } from "vitest";
import { countScene, createSyntheticScene } from "../src/scene-generator.js";

it("merges static context without changing triangle or material counts", () => {
  const plain = countScene(createSyntheticScene({ actorCount: 2, contextMode: "unbatched" }).contextRoot);
  const merged = countScene(createSyntheticScene({ actorCount: 2, contextMode: "merged" }).contextRoot);
  expect(merged.triangles).toBe(plain.triangles);
  expect(merged.materials).toBe(plain.materials);
  expect(merged.meshes).toBeLessThan(plain.meshes);
});
~~~

- [ ] **Step 2: Run the red tests**

~~~powershell
npm test -- --run tests/scene-generator.test.js tests/batching.test.js
~~~

Expected: FAIL because scene-generator.js is absent.

- [ ] **Step 3: Add fixed configuration**

~~~js
// src/config.js
export const ACTOR_PRESETS = Object.freeze([100, 338, 1000, 10000]);
export const LARGE_WORLD_OFFSET = Object.freeze([300000, -200000, 20000]);
export const BENCHMARK_PROTOCOL = Object.freeze({
  width: 1920, height: 1080, pixelRatio: 1,
  warmupFrames: 120, measuredFrames: 300, trials: 3,
  gpuValidSampleFloor: 270,
});
export const DEFAULT_CONFIG = Object.freeze({
  actorCount: 338,
  geometryDensity: 1,
  geometryOwnership: "shared",
  motionGranularity: "individual",
  coordinateMode: "rebased",
  materialOwnership: "shared",
  contextMode: "unbatched",
});
~~~

- [ ] **Step 4: Implement deterministic geometry and real context merging**

~~~js
// src/scene-generator.js
import * as THREE from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import { DEFAULT_CONFIG, LARGE_WORLD_OFFSET } from "./config.js";

export function createSyntheticScene(overrides = {}) {
  const config = { ...DEFAULT_CONFIG, ...overrides };
  const scene = new THREE.Scene();
  const actorRoot = new THREE.Group();
  const contextRoot = new THREE.Group();
  actorRoot.name = "ActorSet";
  contextRoot.name = "StaticContext";
  scene.add(contextRoot, actorRoot);

  const sourceOrigin = new THREE.Vector3(...LARGE_WORLD_OFFSET);
  const appliedRenderOffset = config.coordinateMode === "large"
    ? sourceOrigin.clone() : new THREE.Vector3();
  const rebaseOrigin = config.coordinateMode === "rebased"
    ? sourceOrigin.clone() : new THREE.Vector3();
  actorRoot.position.copy(appliedRenderOffset);
  contextRoot.position.copy(appliedRenderOffset);

  const segments = Math.max(1, Number(config.geometryDensity));
  const sharedGeometry = new THREE.BoxGeometry(0.6, 0.6, 0.6, segments, segments, segments);
  const sharedMaterial = new THREE.MeshStandardMaterial({
    color: 0x4aa3ff, roughness: 0.65, metalness: 0.05,
  });
  const actors = [];
  const columns = Math.ceil(Math.sqrt(config.actorCount));

  for (let index = 0; index < config.actorCount; index += 1) {
    const actor = new THREE.Group();
    actor.userData = {
      actorId: "synthetic_actor_" + String(index).padStart(6, "0"),
      actorSetId: "synthetic_set", sourceKind: "synthetic", actorNode: true,
    };
    actor.position.set((index % columns) * 0.9, 0,
      Math.floor(index / columns) * 0.9);
    actor.userData.basePosition = actor.position.toArray();
    const geometry = config.geometryOwnership === "shared"
      ? sharedGeometry : sharedGeometry.clone();
    const material = config.materialOwnership === "shared"
      ? sharedMaterial
      : new THREE.MeshStandardMaterial({ color: 0x4aa3ff + (index % 32) });
    actor.add(new THREE.Mesh(geometry, material));
    actorRoot.add(actor);
    actors.push(actor);
  }

  buildContext(contextRoot, config.contextMode);
  return {
    scene, actorRoot, contextRoot, actors, config,
    sourceOrigin: sourceOrigin.toArray(),
    rebaseOrigin: rebaseOrigin.toArray(),
    appliedRenderOffset: appliedRenderOffset.toArray(),
  };
}

function buildContext(root, mode) {
  const base = new THREE.BoxGeometry(2, 0.15, 2);
  const materials = [
    new THREE.MeshStandardMaterial({ color: 0x7a8291 }),
    new THREE.MeshStandardMaterial({ color: 0x555d6b }),
  ];
  const entries = Array.from({ length: 24 }, (_, index) => ({
    material: index % 2,
    matrix: new THREE.Matrix4().makeTranslation(
      (index % 6) * 2.2, -0.5, Math.floor(index / 6) * 2.2),
  }));

  if (mode === "merged") {
    for (let material = 0; material < 2; material += 1) {
      const parts = entries.filter((entry) => entry.material === material)
        .map((entry) => base.clone().applyMatrix4(entry.matrix));
      root.add(new THREE.Mesh(mergeGeometries(parts, false), materials[material]));
      parts.forEach((part) => part.dispose());
    }
    base.dispose();
  } else {
    entries.forEach((entry) => {
      const mesh = new THREE.Mesh(base, materials[entry.material]);
      mesh.applyMatrix4(entry.matrix);
      root.add(mesh);
    });
  }
}

export function countScene(root) {
  const materials = new Set();
  let meshes = 0;
  let triangles = 0;
  root.traverse((object) => {
    if (!object.isMesh) return;
    meshes += 1;
    (Array.isArray(object.material) ? object.material : [object.material])
      .forEach((material) => materials.add(material));
    triangles += (object.geometry.index?.count ??
      object.geometry.attributes.position.count) / 3;
  });
  return { meshes, materials: materials.size, triangles };
}
~~~

- [ ] **Step 5: Verify and commit**

~~~powershell
npm test -- --run tests/scene-generator.test.js tests/batching.test.js
npm test
git add experiments/threejs-rhino-stress/src/config.js experiments/threejs-rhino-stress/src/scene-generator.js experiments/threejs-rhino-stress/tests/scene-generator.test.js experiments/threejs-rhino-stress/tests/batching.test.js
git commit -m "feat: add deterministic Three.js stress scenes"
~~~

Expected: focused and full suites pass.

---

### Task 5: Actor Index, Absolute-Time Animation, and Disposal

**Files:**
- Create: experiments/threejs-rhino-stress/src/actor-index.js
- Create: experiments/threejs-rhino-stress/src/animation.js
- Create: experiments/threejs-rhino-stress/src/disposal.js
- Create: experiments/threejs-rhino-stress/tests/actor-index.test.js
- Create: experiments/threejs-rhino-stress/tests/animation.test.js
- Create: experiments/threejs-rhino-stress/tests/disposal.test.js

**Interfaces:**
- Produces: buildActorIndex(root), evaluateAt(context, time), transformSnapshot(index), disposeScene(root).

- [ ] **Step 1: Write failing identity and seek tests**

~~~js
// tests/actor-index.test.js
import * as THREE from "three";
import { expect, it } from "vitest";
import { buildActorIndex } from "../src/actor-index.js";

it("reports duplicate and malformed durable IDs", () => {
  const root = new THREE.Group();
  for (let index = 0; index < 2; index += 1) {
    const actor = new THREE.Group();
    actor.userData.actorId = "duplicate";
    root.add(actor);
  }
  const malformed = new THREE.Group();
  malformed.userData.actorId = " bad id ";
  root.add(malformed);
  const result = buildActorIndex(root);
  expect(result.duplicates).toEqual([{
    actorId: "duplicate",
    firstObject: "Group",
    duplicateObject: "Group",
  }]);
  expect(result.malformedIds).toEqual([{
    objectName: "Group", value: " bad id ", reason: "invalid_format",
  }]);
});
~~~

~~~js
// tests/animation.test.js
import { expect, it } from "vitest";
import { buildActorIndex } from "../src/actor-index.js";
import { evaluateAt, transformSnapshot } from "../src/animation.js";
import { createSyntheticScene } from "../src/scene-generator.js";

it("is independent of seek history", () => {
  const generated = createSyntheticScene({ actorCount: 4 });
  const actorIndex = buildActorIndex(generated.scene).actors;
  const context = { ...generated, actorIndex, motionGranularity: "individual" };
  evaluateAt(context, 0.75);
  const expected = transformSnapshot(actorIndex);
  evaluateAt(context, 0.1);
  evaluateAt(context, 0.75);
  expect(transformSnapshot(actorIndex)).toBe(expected);
});
~~~

~~~js
// tests/disposal.test.js
import { expect, it, vi } from "vitest";
import { disposeScene } from "../src/disposal.js";
import { createSyntheticScene } from "../src/scene-generator.js";

it("disposes shared resources once", () => {
  const generated = createSyntheticScene({ actorCount: 3 });
  const geometry = generated.actors[0].children[0].geometry;
  const spy = vi.spyOn(geometry, "dispose");
  disposeScene(generated.scene);
  expect(spy).toHaveBeenCalledTimes(1);
});
~~~

- [ ] **Step 2: Run the red tests**

~~~powershell
npm test -- --run tests/actor-index.test.js tests/animation.test.js tests/disposal.test.js
~~~

Expected: FAIL because the source modules are absent.

- [ ] **Step 3: Implement actor indexing**

~~~js
// src/actor-index.js
export function buildActorIndex(root) {
  const actors = new Map();
  let missingActorId = 0;
  const duplicates = [];
  const malformedIds = [];
  const pattern = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/;
  root.traverse((object) => {
    const hasActorId = Object.prototype.hasOwnProperty.call(
      object.userData ?? {}, "actorId");
    const actorId = object.userData?.actorId;
    if (hasActorId) {
      if (typeof actorId !== "string" || !pattern.test(actorId)) {
        malformedIds.push({
          objectName: object.name || object.type,
          value: actorId,
          reason: "invalid_format",
        });
      } else if (actors.has(actorId)) {
        duplicates.push({
          actorId,
          firstObject: actors.get(actorId).name || actors.get(actorId).type,
          duplicateObject: object.name || object.type,
        });
      } else {
        actors.set(actorId, object);
      }
    } else if (object.userData?.actorNode === true ||
      (object.isMesh && !hasActorAncestor(object))) {
      missingActorId += 1;
    }
  });
  return { actors, missingActorId, duplicates, malformedIds };
}

function hasActorAncestor(object) {
  let cursor = object.parent;
  while (cursor) {
    if (cursor.userData?.actorId) return true;
    cursor = cursor.parent;
  }
  return false;
}
~~~

- [ ] **Step 4: Implement absolute-time transforms**

~~~js
// src/animation.js
export function evaluateAt({ actorIndex, actorRoot, motionGranularity }, time) {
  if (!Number.isFinite(time)) throw new Error("time must be finite");
  const entries = [...actorIndex.entries()]
    .sort(([left], [right]) => left.localeCompare(right));
  if (motionGranularity === "group") {
    entries.forEach(([, actor]) => restore(actor));
    actorRoot.rotation.y = Math.sin(time * 0.7) * 0.2;
  } else {
    actorRoot.rotation.set(0, 0, 0);
    entries.forEach(([actorId, actor], index) => {
      restore(actor);
      const phase = stablePhase(actorId);
      actor.position.y += Math.sin(time * 1.3 + phase) *
        (0.12 + (index % 5) * 0.01);
      actor.rotation.y = Math.sin(time * 0.5 + phase) * 0.15;
    });
  }
  actorRoot.updateMatrixWorld(true);
}

export function transformSnapshot(index) {
  return JSON.stringify([...index.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([id, actor]) => [id, ...actor.position.toArray(),
      ...actor.quaternion.toArray(), ...actor.scale.toArray()]
      .map((value) => typeof value === "number"
        ? Number(value.toFixed(9)) : value)));
}

function restore(actor) {
  const base = actor.userData.basePosition ?? actor.position.toArray();
  actor.userData.basePosition = [...base];
  actor.position.fromArray(base);
  actor.rotation.set(0, 0, 0);
}

function stablePhase(value) {
  let hash = 2166136261;
  for (const character of value) {
    hash ^= character.codePointAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return ((hash >>> 0) / 0xffffffff) * Math.PI * 2;
}
~~~

- [ ] **Step 5: Implement unique resource disposal**

~~~js
// src/disposal.js
export function disposeScene(root) {
  const geometries = new Set();
  const materials = new Set();
  const textures = new Set();
  root.traverse((object) => {
    if (object.geometry) geometries.add(object.geometry);
    const list = Array.isArray(object.material)
      ? object.material : object.material ? [object.material] : [];
    list.forEach((material) => {
      materials.add(material);
      Object.values(material).forEach((value) => {
        if (value?.isTexture) textures.add(value);
      });
    });
  });
  textures.forEach((texture) => texture.dispose());
  materials.forEach((material) => material.dispose());
  geometries.forEach((geometry) => geometry.dispose());
  root.clear();
  return {
    geometries: geometries.size,
    materials: materials.size,
    textures: textures.size,
  };
}
~~~

- [ ] **Step 6: Verify and commit**

~~~powershell
npm test -- --run tests/actor-index.test.js tests/animation.test.js tests/disposal.test.js
npm test
git add experiments/threejs-rhino-stress/src/actor-index.js experiments/threejs-rhino-stress/src/animation.js experiments/threejs-rhino-stress/src/disposal.js experiments/threejs-rhino-stress/tests/actor-index.test.js experiments/threejs-rhino-stress/tests/animation.test.js experiments/threejs-rhino-stress/tests/disposal.test.js
git commit -m "feat: add deterministic actor lifecycle"
~~~

Expected: focused and full suites pass.

---

### Task 6: Fixed Renderer, GPU Timing, and Pixel Evidence

**Files:**
- Create: experiments/threejs-rhino-stress/src/renderer.js
- Create: experiments/threejs-rhino-stress/src/gpu-timer.js
- Create: experiments/threejs-rhino-stress/src/precision.js
- Create: experiments/threejs-rhino-stress/tests/precision.test.js

**Interfaces:**
- Produces: createFixedRenderer(canvas), createCamera(offset), addFixedLights(scene, offset), createGpuTimer(gl), comparePixelBuffers(left, right), readScenePixels(renderer, scene, camera).

- [ ] **Step 1: Write failing pixel-metric tests**

~~~js
// tests/precision.test.js
import { expect, it } from "vitest";
import { comparePixelBuffers, PRECISION_SAMPLE_TIMES } from "../src/precision.js";

it("uses required sample times", () => {
  expect(PRECISION_SAMPLE_TIMES).toEqual([0, 0.5, 1]);
});

it("passes within tolerance and fails above it", () => {
  expect(comparePixelBuffers(
    new Uint8Array([10, 20, 30, 255]),
    new Uint8Array([10, 20, 31, 255]),
  ).pass).toBe(true);
  const left = new Uint8Array(400);
  const right = new Uint8Array(400);
  right.fill(10, 0, 8);
  expect(comparePixelBuffers(left, right).pass).toBe(false);
});
~~~

- [ ] **Step 2: Run the red test**

~~~powershell
npm test -- --run tests/precision.test.js
~~~

Expected: FAIL because precision.js is absent.

- [ ] **Step 3: Implement the fixed renderer**

~~~js
// src/renderer.js
import * as THREE from "three";
import { BENCHMARK_PROTOCOL } from "./config.js";

export function createFixedRenderer(canvas) {
  const renderer = new THREE.WebGLRenderer({
    canvas, antialias: true, powerPreference: "high-performance",
  });
  renderer.setPixelRatio(1);
  renderer.setSize(BENCHMARK_PROTOCOL.width, BENCHMARK_PROTOCOL.height, false);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.NoToneMapping;
  renderer.setClearColor(0x101722, 1);
  if (!renderer.capabilities.isWebGL2) {
    throw new Error("WebGL2 is required for benchmark runs");
  }
  return renderer;
}

export function createCamera(offset = [0, 0, 0]) {
  const camera = new THREE.PerspectiveCamera(
    35, BENCHMARK_PROTOCOL.width / BENCHMARK_PROTOCOL.height, 0.1, 10000);
  camera.position.set(offset[0] + 12, offset[1] + 10, offset[2] + 18);
  camera.lookAt(offset[0] + 6, offset[1], offset[2] + 6);
  camera.updateMatrixWorld(true);
  return camera;
}

export function addFixedLights(scene, offset = [0, 0, 0]) {
  scene.add(new THREE.AmbientLight(0xffffff, 1.1));
  const light = new THREE.DirectionalLight(0xffffff, 2.2);
  light.position.set(offset[0] + 10, offset[1] + 18, offset[2] + 8);
  scene.add(light);
}
~~~

- [ ] **Step 4: Implement disjoint GPU query collection**

~~~js
// src/gpu-timer.js
export function createGpuTimer(gl) {
  const extension = gl.getExtension("EXT_disjoint_timer_query_webgl2");
  const pending = [];
  const samplesMs = [];
  let disjointCount = 0;
  let active = null;
  return {
    available: Boolean(extension),
    begin() {
      if (!extension || active) return;
      active = gl.createQuery();
      gl.beginQuery(extension.TIME_ELAPSED_EXT, active);
    },
    end() {
      if (!extension || !active) return;
      gl.endQuery(extension.TIME_ELAPSED_EXT);
      pending.push(active);
      active = null;
    },
    poll() {
      if (!extension) return;
      const disjoint = gl.getParameter(extension.GPU_DISJOINT_EXT);
      for (let index = pending.length - 1; index >= 0; index -= 1) {
        const query = pending[index];
        if (!gl.getQueryParameter(query, gl.QUERY_RESULT_AVAILABLE)) continue;
        const nanoseconds = gl.getQueryParameter(query, gl.QUERY_RESULT);
        if (disjoint) disjointCount += 1;
        else samplesMs.push(nanoseconds / 1000000);
        gl.deleteQuery(query);
        pending.splice(index, 1);
      }
    },
    snapshot: () => ({
      available: Boolean(extension), samplesMs: [...samplesMs],
      disjointCount, pendingCount: pending.length,
    }),
    dispose() {
      if (active) gl.deleteQuery(active);
      pending.forEach((query) => gl.deleteQuery(query));
      pending.length = 0;
      active = null;
    },
  };
}
~~~

- [ ] **Step 5: Implement precision calculations and offscreen readback**

~~~js
// src/precision.js
import * as THREE from "three";
import { BENCHMARK_PROTOCOL } from "./config.js";

export const PRECISION_SAMPLE_TIMES = Object.freeze([0, 0.5, 1]);

export function comparePixelBuffers(left, right) {
  if (!left.length || left.length !== right.length) {
    throw new Error("pixel buffers must have equal nonzero length");
  }
  let sum = 0;
  let maxChannelError = 0;
  let differing = 0;
  for (let index = 0; index < left.length; index += 1) {
    const difference = Math.abs(left[index] - right[index]);
    sum += difference;
    maxChannelError = Math.max(maxChannelError, difference);
    if (difference > 2) differing += 1;
  }
  const meanAbsoluteChannelError = sum / left.length;
  const differingChannelRatio = differing / left.length;
  return {
    pass: meanAbsoluteChannelError <= 0.25 &&
      differingChannelRatio <= 0.001,
    meanAbsoluteChannelError, maxChannelError, differingChannelRatio,
  };
}

export function readScenePixels(renderer, scene, camera) {
  const target = new THREE.WebGLRenderTarget(
    BENCHMARK_PROTOCOL.width, BENCHMARK_PROTOCOL.height);
  const previous = renderer.getRenderTarget();
  const pixels = new Uint8Array(
    BENCHMARK_PROTOCOL.width * BENCHMARK_PROTOCOL.height * 4);
  renderer.setRenderTarget(target);
  renderer.render(scene, camera);
  renderer.readRenderTargetPixels(target, 0, 0,
    BENCHMARK_PROTOCOL.width, BENCHMARK_PROTOCOL.height, pixels);
  renderer.setRenderTarget(previous);
  target.dispose();
  return pixels;
}
~~~

- [ ] **Step 6: Verify and commit**

~~~powershell
npm test -- --run tests/precision.test.js
npm test
npm run build
git add experiments/threejs-rhino-stress/src/renderer.js experiments/threejs-rhino-stress/src/gpu-timer.js experiments/threejs-rhino-stress/src/precision.js experiments/threejs-rhino-stress/tests/precision.test.js
git commit -m "feat: add fixed WebGL benchmark adapters"
~~~

Expected: all tests and the Vite build pass.

---

### Task 7: Three-Trial Benchmark Orchestration

**Files:**
- Create: experiments/threejs-rhino-stress/src/benchmark.js
- Create: experiments/threejs-rhino-stress/tests/benchmark.test.js

**Interfaces:**
- Consumes: renderer, scene factory, evaluator, disposer, protocol, GPU timer, and metrics.
- Produces: runTrial(options) and runConfiguration(options).

- [ ] **Step 1: Write failing headline-tier orchestration tests**

~~~js
// tests/benchmark.test.js
import { expect, it } from "vitest";
import { runConfiguration, runTrial } from "../src/benchmark.js";

it("runs three trials and uses the worst completed trial", async () => {
  const tiers = ["interactive", "marginal", "preview-viable"];
  let index = 0;
  const report = await runConfiguration({
    config: { actorCount: 338 },
    trialCount: 3,
    runTrialImpl: async () => ({
      status: "completed",
      classification: { tier: tiers[index++] },
      cpu: { samples: [4] },
      seek: { samples: [1] },
      matrixTraversal: { samples: [1] },
      renderSubmission: { samples: [2] },
      gpu: { samples: [3] },
    }),
  });
  expect(report.trials).toHaveLength(3);
  expect(report.headline).toEqual({
    tier: "marginal", source: "worst_completed_trial", trialIndex: 1,
  });
  expect(report.pooled.classificationRole).toBe("descriptive_only");
  expect(report.pooled.seek.count).toBe(3);
  expect(report.pooled.matrixTraversal.count).toBe(3);
  expect(report.pooled.renderSubmission.count).toBe(3);
});

it("lets an aborted trial override completed trials", async () => {
  const report = await runConfiguration({
    config: {}, trialCount: 3,
    runTrialImpl: async ({ trialIndex }) => trialIndex === 1
      ? { status: "aborted", reason: "context_lost" }
      : { status: "completed", classification: { tier: "interactive" },
          cpu: { samples: [] }, gpu: { samples: [] } },
  });
  expect(report.headline.tier).toBe("impractical");
});

it("converts construction failure into an aborted trial", async () => {
  const result = await runTrial({
    trialIndex: 0,
    renderer: {},
    buildScene: async () => { throw new Error("construction failed"); },
    evaluate: () => {},
    dispose: () => { throw new Error("must not dispose missing context"); },
    schedule: (callback) => callback(),
    now: () => 0,
  });
  expect(result).toMatchObject({
    trialIndex: 0, status: "aborted", reason: "construction failed",
  });
});

it("stops scheduling after the first aborted trial", async () => {
  let calls = 0;
  const report = await runConfiguration({
    config: {}, trialCount: 3,
    runTrialImpl: async () => {
      calls += 1;
      return { status: "aborted", reason: "cancelled" };
    },
  });
  expect(calls).toBe(1);
  expect(report.trials).toHaveLength(1);
  expect(report.headline.tier).toBe("impractical");
});
~~~

- [ ] **Step 2: Run the red test**

~~~powershell
npm test -- --run tests/benchmark.test.js
~~~

Expected: FAIL because benchmark.js is absent.

- [ ] **Step 3: Implement warm-up, measured frames, and trial records**

~~~js
// src/benchmark.js
import { BENCHMARK_PROTOCOL } from "./config.js";
import { createGpuTimer } from "./gpu-timer.js";
import {
  classifyConfiguration, classifyTrial, summarizeSamples,
} from "./metrics.js";

export async function runTrial({
  trialIndex, renderer, buildScene, evaluate, dispose, signal,
  protocol = BENCHMARK_PROTOCOL,
  checkCorrectness = async () => ({ pass: true }),
  schedule = requestAnimationFrame,
  now = performance.now.bind(performance),
}) {
  let context = null;
  let timer = null;
  let constructionMs = null;
  let contextLost = false;
  let listenerAttached = false;
  const frameCpuSamples = [];
  const seekSamples = [];
  const matrixTraversalSamples = [];
  const renderSubmissionSamples = [];
  const lost = (event) => {
    event.preventDefault();
    contextLost = true;
  };
  try {
    const started = now();
    context = await buildScene();
    constructionMs = now() - started;
    timer = createGpuTimer(renderer.getContext());
    renderer.domElement.addEventListener("webglcontextlost", lost, { once: true });
    listenerAttached = true;

    await frames(protocol.warmupFrames, (frame) => {
      evaluate(context, frame / 60);
      context.scene.updateMatrixWorld(true);
      renderer.render(context.scene, context.camera);
    }, schedule, signal);

    await frames(protocol.measuredFrames, (frame) => {
      const frameStart = now();

      const seekStart = now();
      evaluate(context, frame / 60);
      seekSamples.push(now() - seekStart);

      const traversalStart = now();
      context.scene.updateMatrixWorld(true);
      matrixTraversalSamples.push(now() - traversalStart);

      timer.begin();
      const renderStart = now();
      renderer.render(context.scene, context.camera);
      renderSubmissionSamples.push(now() - renderStart);
      timer.end();
      frameCpuSamples.push(now() - frameStart);
      timer.poll();
      if (contextLost) throw new DOMException("context lost", "AbortError");
    }, schedule, signal);

    await drain(timer, schedule, signal);
    const gpuRaw = timer.snapshot();
    const cpu = summarizeSamples(frameCpuSamples);
    const seek = summarizeSamples(seekSamples);
    const matrixTraversal = summarizeSamples(matrixTraversalSamples);
    const renderSubmission = summarizeSamples(renderSubmissionSamples);
    const gpu = summarizeSamples(gpuRaw.samplesMs);
    const correctness = await checkCorrectness(context);
    const correctnessPassed = correctness.pass;
    const classification = classifyTrial({
      status: "completed", correctnessPassed, constructionMs, cpu,
      gpu: { ...gpu, validCount: gpuRaw.samplesMs.length },
    });
    return {
      trialIndex, status: "completed", constructionMs,
      cpu: { ...cpu, samples: frameCpuSamples },
      seek: { ...seek, samples: seekSamples },
      matrixTraversal: {
        ...matrixTraversal, samples: matrixTraversalSamples,
      },
      renderSubmission: {
        ...renderSubmission, samples: renderSubmissionSamples,
      },
      gpu: { ...gpu, samples: gpuRaw.samplesMs,
        disjointCount: gpuRaw.disjointCount },
      correctness, correctnessPassed, classification,
    };
  } catch (error) {
    return {
      trialIndex, status: "aborted",
      reason: contextLost ? "context_lost" : error.message,
    };
  } finally {
    if (listenerAttached) {
      renderer.domElement.removeEventListener("webglcontextlost", lost);
    }
    timer?.dispose();
    if (context?.scene) dispose(context.scene);
  }
}

export async function runConfiguration({
  config, trialCount = BENCHMARK_PROTOCOL.trials,
  runTrialImpl = runTrial, ...options
}) {
  const trials = [];
  for (let trialIndex = 0; trialIndex < trialCount; trialIndex += 1) {
    const trial = await runTrialImpl({ ...options, config, trialIndex });
    trials.push(trial);
    if (trial.status !== "completed" || options.signal?.aborted) break;
  }
  return {
    schemaVersion: 1, config, trials,
    headline: classifyConfiguration(trials),
    pooled: {
      cpu: summarizeSamples(trials.flatMap(
        (trial) => trial.cpu?.samples ?? [])),
      gpu: summarizeSamples(trials.flatMap(
        (trial) => trial.gpu?.samples ?? [])),
      seek: summarizeSamples(trials.flatMap(
        (trial) => trial.seek?.samples ?? [])),
      matrixTraversal: summarizeSamples(trials.flatMap(
        (trial) => trial.matrixTraversal?.samples ?? [])),
      renderSubmission: summarizeSamples(trials.flatMap(
        (trial) => trial.renderSubmission?.samples ?? [])),
      classificationRole: "descriptive_only",
    },
  };
}

function frames(count, callback, schedule, signal) {
  return new Promise((resolve, reject) => {
    let frame = 0;
    const step = () => {
      if (signal?.aborted) {
        reject(new DOMException("run stopped", "AbortError"));
        return;
      }
      try {
        callback(frame);
        frame += 1;
        if (frame >= count) resolve();
        else schedule(step);
      } catch (error) {
        reject(error);
      }
    };
    schedule(step);
  });
}

async function drain(timer, schedule, signal) {
  for (let attempt = 0;
    attempt < 120 && timer.snapshot().pendingCount > 0;
    attempt += 1) {
    await new Promise((resolve, reject) => schedule(() => {
      if (signal?.aborted) reject(
        new DOMException("run stopped", "AbortError"));
      else {
        timer.poll();
        resolve();
      }
    }));
  }
}
~~~

- [ ] **Step 4: Verify and commit**

~~~powershell
npm test -- --run tests/benchmark.test.js
npm test
git add experiments/threejs-rhino-stress/src/benchmark.js experiments/threejs-rhino-stress/tests/benchmark.test.js
git commit -m "feat: orchestrate reproducible Three.js trials"
~~~

Expected: tests prove the headline uses the worst completed trial and pooled data is descriptive only.

---

### Task 8: Protocol, Correctness, and Report Evidence Contract

**Files:**
- Create: experiments/threejs-rhino-stress/src/evidence.js
- Create: experiments/threejs-rhino-stress/tests/evidence.test.js
- Modify: experiments/threejs-rhino-stress/src/scene-generator.js
- Modify: experiments/threejs-rhino-stress/src/benchmark.js
- Modify: experiments/threejs-rhino-stress/tests/fixture.test.js

**Interfaces:**
- Consumes: actor index, absolute-time evaluator, renderer, browser document, and scene counts.
- Produces: validateProtocolEnvironment(options), captureEnvironment(renderer), runCorrectnessChecks(context), and complete per-trial evidence.

- [ ] **Step 1: Write failing protocol and correctness tests**

~~~js
// tests/evidence.test.js
import { expect, it } from "vitest";
import { buildActorIndex } from "../src/actor-index.js";
import {
  runCorrectnessChecks, validateProtocolEnvironment,
} from "../src/evidence.js";
import { createSyntheticScene } from "../src/scene-generator.js";

it("invalidates hidden or resized trials", () => {
  expect(() => validateProtocolEnvironment({
    visibilityState: "hidden", width: 1920, height: 1080,
  })).toThrow(/visible/);
  expect(() => validateProtocolEnvironment({
    visibilityState: "visible", width: 960, height: 540,
  })).toThrow(/1920 x 1080/);
});

it("checks deterministic seek, independent transforms, and pivots", () => {
  const context = createSyntheticScene({ actorCount: 3 });
  context.actorIndex = buildActorIndex(context.scene).actors;
  context.motionGranularity = "individual";
  expect(runCorrectnessChecks(context)).toEqual({
    pass: true,
    deterministicSeek: true,
    independentTransform: true,
    pivotSanity: true,
  });
});
~~~

Extend tests/fixture.test.js after actor-index.js exists:

~~~js
import { buildActorIndex } from "../src/actor-index.js";

// after GLTFLoader parse:
const indexed = buildActorIndex(gltf.scene);
expect(indexed.actors.size).toBe(2);
expect(indexed.missingActorId).toBe(0);
expect(indexed.duplicates).toEqual([]);
expect(indexed.malformedIds).toEqual([]);
~~~

- [ ] **Step 2: Run the red evidence tests**

~~~powershell
npm test -- --run tests/evidence.test.js tests/fixture.test.js
~~~

Expected: FAIL because evidence.js is absent and fixture lookup assertions are not yet supported by the test imports.

- [ ] **Step 3: Implement evidence capture**

~~~js
// src/evidence.js
import { REVISION, Vector3 } from "three";
import { evaluateAt, transformSnapshot } from "./animation.js";
import { BENCHMARK_PROTOCOL } from "./config.js";

export function validateProtocolEnvironment({
  visibilityState, width, height,
}) {
  if (visibilityState !== "visible") {
    throw new Error("benchmark document must remain visible");
  }
  if (width !== BENCHMARK_PROTOCOL.width ||
      height !== BENCHMARK_PROTOCOL.height) {
    throw new Error("drawing buffer must remain 1920 x 1080");
  }
}

export function captureEnvironment(renderer) {
  const gl = renderer.getContext();
  const debug = gl.getExtension("WEBGL_debug_renderer_info");
  const memory = performance.memory;
  return {
    threeRevision: REVISION,
    userAgent: navigator.userAgent,
    platform: navigator.platform,
    devicePixelRatio: window.devicePixelRatio,
    visualViewportScale: window.visualViewport?.scale ?? null,
    drawingBuffer: [renderer.domElement.width, renderer.domElement.height],
    gpuVendor: debug ? gl.getParameter(debug.UNMASKED_VENDOR_WEBGL) : null,
    gpuRenderer: debug ? gl.getParameter(debug.UNMASKED_RENDERER_WEBGL) : null,
    heap: memory ? {
      usedJSHeapSize: memory.usedJSHeapSize,
      totalJSHeapSize: memory.totalJSHeapSize,
      jsHeapSizeLimit: memory.jsHeapSizeLimit,
    } : null,
  };
}

export function runCorrectnessChecks(context) {
  const actors = [...context.actorIndex.values()];
  if (!actors.length) {
    return {
      pass: false, deterministicSeek: false,
      independentTransform: false, pivotSanity: false,
    };
  }

  evaluateAt(context, 0.75);
  const first = transformSnapshot(context.actorIndex);
  evaluateAt(context, 0.1);
  evaluateAt(context, 0.75);
  const deterministicSeek =
    transformSnapshot(context.actorIndex) === first;

  const firstActor = actors[0];
  const secondActor = actors[1] ?? actors[0];
  const secondBefore = secondActor.matrixWorld.clone();
  firstActor.position.x += 1;
  firstActor.updateMatrixWorld(true);
  const independentTransform = secondActor.matrixWorld.equals(secondBefore);

  evaluateAt(context, 0);
  const savedQuaternion = firstActor.quaternion.clone();
  const pivotExpected = firstActor.parent.localToWorld(
    firstActor.position.clone());
  firstActor.rotation.set(0, Math.PI / 2, 0);
  firstActor.updateWorldMatrix(true, true);
  const pivotActual = firstActor.localToWorld(new Vector3(0, 0, 0));
  const offAxisActual = firstActor.localToWorld(new Vector3(1, 0, 0));
  const offAxisExpected = firstActor.parent.localToWorld(
    firstActor.position.clone().add(new Vector3(0, 0, -1)));
  const pivotSanity =
    pivotActual.distanceTo(pivotExpected) <= 1e-9 &&
    offAxisActual.distanceTo(offAxisExpected) <= 1e-9;
  firstActor.quaternion.copy(savedQuaternion);
  firstActor.updateWorldMatrix(true, true);

  evaluateAt(context, 0);
  return {
    pass: deterministicSeek && independentTransform && pivotSanity,
    deterministicSeek, independentTransform, pivotSanity,
  };
}
~~~

- [ ] **Step 4: Expand structural counts**

Change countScene in scene-generator.js so its return value includes nodes, actors, unique geometries, meshes, materials, and triangles:

~~~js
export function countScene(root) {
  const geometries = new Set();
  const materials = new Set();
  let nodes = 0;
  let actors = 0;
  let meshes = 0;
  let triangles = 0;
  root.traverse((object) => {
    nodes += 1;
    if (object.userData?.actorId) actors += 1;
    if (!object.isMesh) return;
    meshes += 1;
    geometries.add(object.geometry);
    (Array.isArray(object.material) ? object.material : [object.material])
      .forEach((material) => materials.add(material));
    triangles += (object.geometry.index?.count ??
      object.geometry.attributes.position.count) / 3;
  });
  return {
    nodes, actors, geometries: geometries.size,
    meshes, materials: materials.size, triangles,
  };
}
~~~

- [ ] **Step 5: Enforce protocol and retain complete trial evidence**

In benchmark.js, import validateProtocolEnvironment and runCorrectnessChecks. At trial start and inside every warm-up/measured callback, call:

~~~js
validateProtocolEnvironment({
  visibilityState: document.visibilityState,
  width: renderer.domElement.width,
  height: renderer.domElement.height,
});
~~~

After the final measured render, capture:

~~~js
const rendererInfo = {
  calls: renderer.info.render.calls,
  triangles: renderer.info.render.triangles,
  points: renderer.info.render.points,
  lines: renderer.info.render.lines,
};
const correctness = runCorrectnessChecks(context);
const correctnessPassed =
  context.addressabilityPassed !== false && correctness.pass;
~~~

Return these fields in the completed trial:

~~~js
structure: context.structure,
sceneTraversalMs: context.sceneTraversalMs,
origins: {
  sourceOrigin: context.sourceOrigin,
  rebaseOrigin: context.rebaseOrigin,
  appliedRenderOffset: context.appliedRenderOffset,
},
addressability: context.addressability,
rendererInfo,
correctness,
~~~

Make buildSynthetic and the local GLB builder attach countScene(scene) as structure and the buildActorIndex result as addressability. Make runConfiguration accept an environment argument and retain it at the report root. The pooled object remains descriptive_only.

- [ ] **Step 6: Verify evidence coverage and commit**

~~~powershell
npm test -- --run tests/evidence.test.js tests/fixture.test.js tests/benchmark.test.js
npm test
npm run build
git add experiments/threejs-rhino-stress/src/evidence.js experiments/threejs-rhino-stress/src/scene-generator.js experiments/threejs-rhino-stress/src/benchmark.js experiments/threejs-rhino-stress/tests/evidence.test.js experiments/threejs-rhino-stress/tests/fixture.test.js
git commit -m "feat: capture benchmark correctness evidence"
~~~

Expected: protocol invalidation, metadata lookup, pivot, independent-transform, deterministic-seek, structure, and report evidence tests pass.


---

### Task 9: Local GLB Loading and Browser Dashboard

**Files:**
- Create: experiments/threejs-rhino-stress/src/glb-loader.js
- Create: experiments/threejs-rhino-stress/tests/glb-loader.test.js
- Modify: experiments/threejs-rhino-stress/index.html
- Modify: experiments/threejs-rhino-stress/src/main.js
- Modify: experiments/threejs-rhino-stress/src/styles.css

**Interfaces:**
- Consumes: all modules from Tasks 2-7.
- Produces: ArrayBuffer-only GLB parsing, explicit controls, seek/run/stop/reset, and copyable JSON report.

- [ ] **Step 1: Write the failing local-loader test**

~~~js
// tests/glb-loader.test.js
import { readFile } from "node:fs/promises";
import { expect, it } from "vitest";
import { loadGlbArrayBuffer } from "../src/glb-loader.js";

it("parses a local ArrayBuffer without URL fetch", async () => {
  const bytes = await readFile(
    new URL("../fixtures/actor-metadata.glb", import.meta.url));
  const input = bytes.buffer.slice(
    bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
  const gltf = await loadGlbArrayBuffer(input);
  expect(gltf.scene.children).toHaveLength(2);
});
~~~

- [ ] **Step 2: Run the red test, then add the loader**

~~~powershell
npm test -- --run tests/glb-loader.test.js
~~~

Expected: FAIL because glb-loader.js is absent.

~~~js
// src/glb-loader.js
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

export function loadGlbArrayBuffer(input) {
  if (!(input instanceof ArrayBuffer)) {
    throw new TypeError("GLB input must be an ArrayBuffer");
  }
  return new GLTFLoader().parseAsync(input, "");
}
~~~

- [ ] **Step 3: Replace index.html with explicit controls**

~~~html
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <link rel="stylesheet" href="/src/styles.css">
  <title>Rook Three.js Rhino Stress Harness</title>
</head>
<body>
<main class="layout">
  <aside class="panel controls">
    <h1>Rook Three.js Rhino Stress Harness</h1>
    <label>Source <select id="source"><option value="synthetic">Synthetic</option><option value="glb">Local GLB</option></select></label>
    <label>GLB <input id="glb-file" type="file" accept=".glb" disabled></label>
    <label>Actors <select id="actor-count"><option>100</option><option selected>338</option><option>1000</option><option>10000</option></select></label>
    <label>Density <select id="density"><option>1</option><option>2</option><option>4</option></select></label>
    <label>Geometry <select id="geometry"><option value="shared">Shared</option><option value="duplicated">Duplicated</option></select></label>
    <label>Motion <select id="motion"><option value="individual">Individual</option><option value="group">Group</option></select></label>
    <label>Coordinates <select id="coordinates"><option value="rebased">Rebased</option><option value="large">Large world</option></select></label>
    <label>Materials <select id="materials"><option value="shared">Shared</option><option value="per-actor">Per actor</option></select></label>
    <label>Context <select id="context"><option value="unbatched">Unbatched</option><option value="merged">Merged</option></select></label>
    <label>Time <input id="time" type="range" min="0" max="5" step="0.01" value="0"></label>
    <div class="actions"><button id="build">Build / Load</button><button id="run">Run 3 Trials</button><button id="stop">Stop</button><button id="reset">Reset</button></div>
    <p id="status" role="status">Ready.</p>
  </aside>
  <section class="viewport"><canvas id="canvas" width="1920" height="1080"></canvas></section>
  <section class="panel report"><button id="copy-report">Copy JSON</button><pre id="report">No report.</pre></section>
</main>
<script type="module" src="/src/main.js"></script>
</body>
</html>
~~~

- [ ] **Step 4: Wire the dashboard with these exact boundaries**

Implement src/main.js using this state model; keep helper functions as named so they remain testable during review:

~~~js
import { buildActorIndex } from "./actor-index.js";
import { evaluateAt } from "./animation.js";
import { runConfiguration } from "./benchmark.js";
import { DEFAULT_CONFIG } from "./config.js";
import { disposeScene } from "./disposal.js";
import { loadGlbArrayBuffer } from "./glb-loader.js";
import { addFixedLights, createCamera, createFixedRenderer } from "./renderer.js";
import { createSyntheticScene } from "./scene-generator.js";

export const APP_TITLE = "Rook Three.js Rhino Stress Harness";
const el = Object.fromEntries([...document.querySelectorAll("[id]")]
  .map((node) => [node.id, node]));
const renderer = createFixedRenderer(el.canvas);
let active = null;
let report = null;
let controller = null;

el.source.addEventListener("change", () => {
  el["glb-file"].disabled = el.source.value !== "glb";
});
el.build.addEventListener("click", () => buildOrLoad().catch(showError));
el.run.addEventListener("click", () => run().catch(showError));
el.stop.addEventListener("click", () => controller?.abort());
el.reset.addEventListener("click", reset);
el.time.addEventListener("input", () => renderAt(Number(el.time.value)));
el["copy-report"].addEventListener("click", () =>
  navigator.clipboard.writeText(JSON.stringify(report, null, 2)));

async function buildOrLoad() {
  reset();
  const config = readConfig();
  active = el.source.value === "glb"
    ? await loadLocal(config) : buildSynthetic(config);
  renderAt(0);
  el.status.textContent = "Loaded " + active.actorIndex.size + " actors.";
}

function buildSynthetic(config) {
  const generated = createSyntheticScene(config);
  addFixedLights(generated.scene, generated.appliedRenderOffset);
  return finalize(generated, createCamera(generated.appliedRenderOffset));
}

async function loadLocal(config) {
  const file = el["glb-file"].files[0];
  if (!file) throw new Error("Choose a local GLB file first");
  const gltf = await loadGlbArrayBuffer(await file.arrayBuffer());
  addFixedLights(gltf.scene);
  return finalize({
    scene: gltf.scene, actorRoot: gltf.scene, contextRoot: gltf.scene,
    config, sourceOrigin: [0, 0, 0], rebaseOrigin: [0, 0, 0],
    appliedRenderOffset: [0, 0, 0],
  }, createCamera());
}

function finalize(context, camera) {
  const result = buildActorIndex(context.scene);
  return {
    ...context, camera, actorIndex: result.actors,
    motionGranularity: context.config.motionGranularity,
  };
}

function renderAt(time) {
  if (!active) return;
  evaluateAt(active, time);
  renderer.render(active.scene, active.camera);
}

async function run() {
  if (Number(el["actor-count"].value) === 10000 &&
      !confirm("Run the opt-in 10,000 actor benchmark?")) return;
  if (el.source.value === "glb" && !localGlbBytes) {
    throw new Error("Build / Load the local GLB before benchmarking");
  }
  disposePreview();
  controller = new AbortController();
  const config = readConfig();
  report = await runConfiguration({
    config, renderer, signal: controller.signal,
    buildScene: async () => buildSynthetic(config),
    evaluate: evaluateAt, dispose: disposeScene,
  });
  el.report.textContent = JSON.stringify(report, null, 2);
  el.status.textContent = "Headline tier: " + report.headline.tier;
}

function readConfig() {
  return {
    ...DEFAULT_CONFIG,
    actorCount: Number(el["actor-count"].value),
    geometryDensity: Number(el.density.value),
    geometryOwnership: el.geometry.value,
    motionGranularity: el.motion.value,
    coordinateMode: el.coordinates.value,
    materialOwnership: el.materials.value,
    contextMode: el.context.value,
  };
}

function reset() {
  controller?.abort();
  disposePreview();
  localGlbBytes = null;
  report = null;
  el.report.textContent = "No report.";
  el.status.textContent = "Ready.";
}

function disposePreview() {
  if (active?.scene) disposeScene(active.scene);
  active = null;
  renderer.clear();
}

function showError(error) {
  el.status.textContent = error.message;
  el.report.textContent = JSON.stringify({ error: error.message }, null, 2);
}
~~~

- [ ] **Step 5: Make local GLB a repeatable three-trial source and attach environment evidence**

Import captureEnvironment and countScene. Replace the provisional finalize/run source selection with these exact boundaries:

~~~js
import { captureEnvironment } from "./evidence.js";
import { countScene } from "./scene-generator.js";

let localGlbBytes = null;

async function loadLocal(config) {
  const file = el["glb-file"].files[0];
  if (!file) throw new Error("Choose a local GLB file first");
  localGlbBytes = await file.arrayBuffer();
  return buildLocalFromBytes(config);
}

async function buildLocalFromBytes(config) {
  if (!localGlbBytes) throw new Error("Choose and load a local GLB first");
  const gltf = await loadGlbArrayBuffer(localGlbBytes.slice(0));
  addFixedLights(gltf.scene);
  return finalize({
    scene: gltf.scene, actorRoot: gltf.scene, contextRoot: gltf.scene,
    config, sourceOrigin: [0, 0, 0], rebaseOrigin: [0, 0, 0],
    appliedRenderOffset: [0, 0, 0], sourceKind: "local_glb",
  }, createCamera());
}

function finalize(context, camera) {
  const traversalStarted = performance.now();
  const addressability = buildActorIndex(context.scene);
  const structure = countScene(context.scene);
  const sceneTraversalMs = performance.now() - traversalStarted;
  return {
    ...context, camera, actorIndex: addressability.actors,
    addressability,
    addressabilityPassed:
      addressability.missingActorId === 0 &&
      addressability.duplicates.length === 0 &&
      addressability.malformedIds.length === 0 &&
      addressability.actors.size > 0,
    structure,
    sceneTraversalMs,
    motionGranularity: context.config.motionGranularity,
  };
}

function buildTrialSource(config) {
  return el.source.value === "glb"
    ? buildLocalFromBytes(config)
    : Promise.resolve(buildSynthetic(config));
}

// In run(), pass these values to runConfiguration:
environment: captureEnvironment(renderer),
buildScene: async () => buildTrialSource(config),
~~~

Expected: local GLB trials reparse the same retained ArrayBuffer without fetch; every trial reports source structure and addressability; the report root records Three revision, browser, drawing buffer, GPU identity when exposed, and optional heap values.

- [ ] **Step 6: Add functional styling**

~~~css
:root { color-scheme: dark; font-family: Inter, system-ui, sans-serif; }
* { box-sizing: border-box; }
body { margin: 0; background: #0b1020; color: #e8edf7; }
.layout { min-height: 100vh; display: grid; grid-template-columns: 320px minmax(0,1fr); grid-template-rows: minmax(0,1fr) 280px; gap: 12px; padding: 12px; }
.panel { background: #141b2d; border: 1px solid #263149; border-radius: 10px; padding: 16px; overflow: auto; }
.controls { grid-row: 1 / 3; display: flex; flex-direction: column; gap: 10px; }
.controls label { display: grid; grid-template-columns: 110px 1fr; gap: 8px; align-items: center; }
.viewport { display: grid; place-items: center; background: #050811; border-radius: 10px; overflow: hidden; }
canvas { width: 100%; height: auto; max-height: 100%; object-fit: contain; }
.actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
button, select, input { min-height: 34px; }
.report { grid-column: 2; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; }
~~~

- [ ] **Step 7: Verify tests, build, and browser behavior**

~~~powershell
npm test -- --run tests/glb-loader.test.js
npm test
npm run build
npm run dev
~~~

Expected: loader and full suites pass, build exits 0, 338 actors load, scrubber seeks, the known fixture loads with two actors, and 10,000 requires confirmation. Use the in-app browser and inspect the console.

- [ ] **Step 8: Commit the dashboard**

~~~powershell
git add experiments/threejs-rhino-stress/index.html experiments/threejs-rhino-stress/src/main.js experiments/threejs-rhino-stress/src/styles.css experiments/threejs-rhino-stress/src/glb-loader.js experiments/threejs-rhino-stress/tests/glb-loader.test.js
git commit -m "feat: add Three.js stress harness dashboard"
~~~

---

### Task 10: Coordinate Comparison, Documentation, and Final Verification

**Files:**
- Modify: experiments/threejs-rhino-stress/src/precision.js
- Modify: experiments/threejs-rhino-stress/src/main.js
- Create: experiments/threejs-rhino-stress/README.md

**Interfaces:**
- Produces: compareCoordinateScenes(options) and final benchmark reports containing three precision samples outside performance windows.

- [ ] **Step 1: Implement paired-scene comparison**

Add to src/precision.js:

~~~js
export function compareCoordinateScenes({
  renderer, rebased, large, evaluate,
}) {
  return PRECISION_SAMPLE_TIMES.map((time) => {
    evaluate(rebased, time);
    evaluate(large, time);
    const near = readScenePixels(
      renderer, rebased.scene, rebased.camera);
    const far = readScenePixels(
      renderer, large.scene, large.camera);
    return { time, ...comparePixelBuffers(near, far) };
  });
}
~~~

- [ ] **Step 2: Run precision evidence after timed trials**

Add to src/main.js imports:

~~~js
import {
  compareCoordinateScenes, comparePixelBuffers, readScenePixels,
} from "./precision.js";
~~~

Add the helper and invoke it immediately after runConfiguration resolves:

~~~js
function runPrecisionEvidence(config) {
  const rebased = buildSynthetic({ ...config, coordinateMode: "rebased" });
  const large = buildSynthetic({ ...config, coordinateMode: "large" });
  try {
    return compareCoordinateScenes({
      renderer, rebased, large, evaluate: evaluateAt,
    });
  } finally {
    disposeScene(rebased.scene);
    disposeScene(large.scene);
  }
}

function runContextVisibilityEvidence(config) {
  const unbatched = buildSynthetic({ ...config, contextMode: "unbatched" });
  const merged = buildSynthetic({ ...config, contextMode: "merged" });
  try {
    evaluateAt(unbatched, 0);
    evaluateAt(merged, 0);
    return comparePixelBuffers(
      readScenePixels(renderer, unbatched.scene, unbatched.camera),
      readScenePixels(renderer, merged.scene, merged.camera),
    );
  } finally {
    disposeScene(unbatched.scene);
    disposeScene(merged.scene);
  }
}

// after runConfiguration:
if (el.source.value === "synthetic") {
  report.coordinatePrecision = runPrecisionEvidence(config);
  report.coordinatePrecisionPassed =
    report.coordinatePrecision.every((sample) => sample.pass);
  if (!report.coordinatePrecisionPassed) {
    report.headline = {
      tier: "impractical",
      source: "coordinate_precision",
      trialIndex: report.headline.trialIndex,
    };
  }
  report.contextVisibleEquivalence =
    runContextVisibilityEvidence(config);
  if (!report.contextVisibleEquivalence.pass) {
    report.headline = {
      tier: "impractical",
      source: "context_visible_equivalence",
      trialIndex: report.headline.trialIndex,
    };
  }
} else {
  report.coordinatePrecision = {
    status: "unavailable",
    reason: "local GLB has no generated rebased comparison pair",
  };
}
~~~

- [ ] **Step 3: Document exact operation and interpretation**

~~~~markdown
# Rook Three.js Rhino Stress Harness

This is an isolated experiment. It does not connect to live Rhino or ship with Rook.

## Setup

From the Rook root, first prove the ignore boundary:

~~~powershell
git check-ignore -v experiments/threejs-rhino-stress/node_modules/.probe
~~~

Then run from this experiment directory:

~~~powershell
npm ci
npm run fixture
npm test
npm run build
npm run dev
~~~

## Protocol

Keep browser zoom at 100 percent and the tab visible. The harness fixes 1920 x 1080 at DPR 1, uses 120 warm-up frames and 300 measured frames for each of three trials, and reports nearest-rank p50/p95/p99/max. GPU timing uses EXT_disjoint_timer_query_webgl2 when at least 270 samples are valid.

Each trial is classified independently. The headline is the worst completed trial; any aborted trial makes the configuration impractical. Pooled values are descriptive only. The 10,000-actor case is opt-in. Pixel readback runs after timed trials.
~~~~

- [ ] **Step 4: Run complete automated verification**

~~~powershell
npm run fixture
npm test
npm run build
git diff --check
git status --short
~~~

Expected: fixture regeneration leaves no diff, all tests pass, build exits 0, diff check exits 0, and only Task 10 files are modified before commit.

- [ ] **Step 5: Run the manual acceptance matrix**

Run these configurations in the in-app browser:

~~~text
100 actors / defaults
338 actors / defaults
338 / duplicated geometry
338 / group motion
338 / merged context
338 / large coordinates
1,000 actors / defaults
10,000 actors / defaults after explicit confirmation
local actor-metadata.glb fixture
~~~

Expected for each completed synthetic run: three independently classified trials, worst-trial headline, descriptive pooled metrics, correctness outcome, and three coordinate-precision samples. GPU results have at least 270 valid samples or classification says cpu_proxy_only.

- [ ] **Step 6: Commit final integration**

~~~powershell
git add experiments/threejs-rhino-stress/src/main.js experiments/threejs-rhino-stress/src/precision.js experiments/threejs-rhino-stress/README.md
git commit -m "docs: complete Three.js stress harness protocol"
~~~

- [ ] **Step 7: Verify committed state**

~~~powershell
git status --short
git log -10 --oneline -- experiments/threejs-rhino-stress
~~~

Expected: clean worktree and focused experiment commits for scaffold, metrics, fixture, scene generation, actor lifecycle, renderer adapters, orchestration, dashboard, and final integration.

- [ ] **Step 8: Run the final whole-branch review gate**

Dispatch a fresh review agent after all task-level requirements and code-quality gates have passed. The reviewer reads the approved design, this plan, and the complete feature-branch diff against main; it must specifically recheck benchmark isolation, construction/cancellation failure paths, separate seek/traversal/render metrics, actor-ID diagnostics, origin semantics, pivot geometry, and visible equivalence.

After resolving any findings, rerun:

~~~powershell
npm test
npm run build
git diff main...HEAD --check
git status --short
~~~

Expected: all tests pass, build exits 0, branch diff check exits 0, status is clean, and the final reviewer reports no blocking findings.
