import { buildActorIndex } from "./actor-index.js";
import { evaluateAt } from "./animation.js";
import { runConfiguration } from "./benchmark.js";
import { DEFAULT_CONFIG } from "./config.js";
import { disposeScene } from "./disposal.js";
import { captureEnvironment } from "./evidence.js";
import { loadGlbArrayBuffer } from "./glb-loader.js";
import {
  addFixedLights, createCamera, createFixedRenderer,
} from "./renderer.js";
import { countScene, createSyntheticScene } from "./scene-generator.js";

export const APP_TITLE = "Rook Three.js Rhino Stress Harness";

export function createRunCoordinator() {
  let epoch = 0;
  let activeRun = null;

  return {
    get running() {
      return activeRun !== null;
    },

    async start(task) {
      if (activeRun) return { started: false };

      let settle;
      const owner = {
        controller: new AbortController(),
        epoch: ++epoch,
        settled: new Promise((resolve) => {
          settle = resolve;
        }),
      };
      activeRun = owner;

      try {
        Promise.resolve(task({ signal: owner.controller.signal })).then(
          (value) => settle({ status: "fulfilled", value }),
          (error) => settle({ status: "rejected", error }),
        );
      } catch (error) {
        settle({ status: "rejected", error });
      }

      const outcome = await owner.settled;
      const current = activeRun === owner && epoch === owner.epoch;
      if (activeRun === owner) activeRun = null;
      return { started: true, current, ...outcome };
    },

    async startBuild(task, discard) {
      const buildEpoch = ++epoch;
      let outcome;
      try {
        outcome = { status: "fulfilled", value: await task() };
      } catch (error) {
        outcome = { status: "rejected", error };
      }

      const current = epoch === buildEpoch;
      let discardError = null;
      if (!current && outcome.status === "fulfilled" && discard) {
        try {
          discard(outcome.value);
        } catch (error) {
          discardError = error;
        }
      }
      return { current, ...outcome, discardError };
    },

    async invalidate() {
      epoch += 1;
      const owner = activeRun;
      if (!owner) return;
      owner.controller.abort();
      await owner.settled;
    },

    stop() {
      activeRun?.controller.abort();
    },
  };
}

let el = null;
let renderer = null;
let active = null;
let report = null;
let localGlbBytes = null;
const runCoordinator = createRunCoordinator();

if (typeof document !== "undefined") initializeDashboard();

function initializeDashboard() {
  document.title = APP_TITLE;
  el = Object.fromEntries([...document.querySelectorAll("[id]")]
    .map((node) => [node.id, node]));
  renderer = createFixedRenderer(el.canvas);

  el.source.addEventListener("change", () => {
    el["glb-file"].disabled = el.source.value !== "glb";
  });
  el.build.addEventListener("click", () => buildOrLoad().catch(showError));
  el.run.addEventListener("click", () => run().catch(showError));
  el.stop.addEventListener("click", () => runCoordinator.stop());
  el.reset.addEventListener("click", () => reset().catch(showError));
  el.time.addEventListener("input", () => renderAt(Number(el.time.value)));
  el["copy-report"].addEventListener("click", () =>
    navigator.clipboard.writeText(JSON.stringify(report, null, 2)));
}

async function buildOrLoad() {
  await reset();
  const config = readConfig();
  const source = el.source.value;
  const outcome = await runCoordinator.startBuild(
    async () => source === "glb"
      ? loadLocal(config)
      : { context: buildSynthetic(config), bytes: null },
    (candidate) => disposeScene(candidate.context.scene),
  );
  if (!outcome.current) return;
  if (outcome.status === "rejected") throw outcome.error;

  active = outcome.value.context;
  localGlbBytes = outcome.value.bytes;
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
  const bytes = await file.arrayBuffer();
  return {
    context: await buildLocalFromBytes(config, bytes),
    bytes,
  };
}

async function buildLocalFromBytes(config, bytes = localGlbBytes) {
  if (!bytes) throw new Error("Choose and load a local GLB first");
  const gltf = await loadGlbArrayBuffer(bytes.slice(0));
  addFixedLights(gltf.scene);
  return finalize({
    scene: gltf.scene,
    actorRoot: gltf.scene,
    contextRoot: gltf.scene,
    config,
    sourceOrigin: [0, 0, 0],
    rebaseOrigin: [0, 0, 0],
    appliedRenderOffset: [0, 0, 0],
    sourceKind: "local_glb",
  }, createCamera());
}

function finalize(context, camera) {
  const traversalStarted = performance.now();
  const addressability = buildActorIndex(context.scene);
  const structure = countScene(context.scene);
  const sceneTraversalMs = performance.now() - traversalStarted;
  return {
    ...context,
    camera,
    actorIndex: addressability.actors,
    addressability,
    addressabilityPassed:
      addressability.missingActorId === 0
      && addressability.duplicates.length === 0
      && addressability.malformedIds.length === 0
      && addressability.actors.size > 0,
    structure,
    sceneTraversalMs,
    motionGranularity: context.config.motionGranularity,
  };
}

function renderAt(time) {
  if (!active) return;
  evaluateAt(active, time);
  renderer.render(active.scene, active.camera);
}

async function run() {
  if (runCoordinator.running) return;
  if (
    Number(el["actor-count"].value) === 10000
    && !confirm("Run the opt-in 10,000 actor benchmark?")
  ) return;
  const selectedSource = el.source.value;
  if (selectedSource === "glb" && !localGlbBytes) {
    throw new Error("Build / Load the local GLB before benchmarking");
  }
  const config = readConfig();
  const outcome = await runCoordinator.start(async ({ signal }) => {
    disposePreview();
    el.run.disabled = true;
    el.status.textContent = "Running 3 trials...";
    return runConfiguration({
      config,
      renderer,
      signal,
      environment: captureEnvironment(renderer),
      buildScene: async () => buildTrialSource(config, selectedSource),
      evaluate: evaluateAt,
      dispose: disposeScene,
    });
  });

  if (!outcome.started || !outcome.current) return;
  el.run.disabled = false;
  if (outcome.status === "rejected") {
    showError(outcome.error);
    return;
  }
  report = outcome.value;
  el.report.textContent = JSON.stringify(report, null, 2);
  el.status.textContent = "Headline tier: " + report.headline.tier;
}

function buildTrialSource(config, source = el.source.value) {
  return source === "glb"
    ? buildLocalFromBytes(config)
    : Promise.resolve(buildSynthetic(config));
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

async function reset() {
  await runCoordinator.invalidate();
  disposePreview();
  localGlbBytes = null;
  report = null;
  el.run.disabled = false;
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
