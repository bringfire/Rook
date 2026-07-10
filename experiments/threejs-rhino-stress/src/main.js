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
import {
  compareCoordinateScenes, comparePixelBuffers, readScenePixels,
} from "./precision.js";
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

export function runPrecisionEvidence(config, {
  renderer: evidenceRenderer = renderer,
  buildSynthetic: build = buildSynthetic,
  evaluate = evaluateAt,
  dispose = disposeScene,
} = {}) {
  const contexts = [];
  try {
    const rebased = build({ ...config, coordinateMode: "rebased" });
    contexts.push(rebased);
    const large = build({ ...config, coordinateMode: "large" });
    contexts.push(large);
    return compareCoordinateScenes({
      renderer: evidenceRenderer,
      rebased,
      large,
      evaluate,
    });
  } finally {
    disposeEvidenceScenes(contexts, dispose);
  }
}

export function runContextVisibilityEvidence(config, {
  renderer: evidenceRenderer = renderer,
  buildSynthetic: build = buildSynthetic,
  evaluate = evaluateAt,
  dispose = disposeScene,
} = {}) {
  const contexts = [];
  try {
    const unbatched = build({ ...config, contextMode: "unbatched" });
    contexts.push(unbatched);
    const merged = build({ ...config, contextMode: "merged" });
    contexts.push(merged);
    evaluate(unbatched, 0);
    evaluate(merged, 0);
    return comparePixelBuffers(
      readScenePixels(
        evidenceRenderer, unbatched.scene, unbatched.camera,
      ),
      readScenePixels(evidenceRenderer, merged.scene, merged.camera),
    );
  } finally {
    disposeEvidenceScenes(contexts, dispose);
  }
}

export function addPostTrialEvidence(report, {
  config,
  source,
  precisionEvidence = () => runPrecisionEvidence(config),
  contextEvidence = () => runContextVisibilityEvidence(config),
  contextEventTarget = renderer?.domElement,
}) {
  if (report.trials?.some((trial) => trial.status !== "completed")) {
    report.postTrialEvidence = {
      status: "skipped", reason: "timed_trial_aborted",
    };
    return report;
  }

  if (source !== "synthetic") {
    report.coordinatePrecision = {
      status: "unavailable",
      reason: "local GLB has no generated rebased comparison pair",
    };
    report.postTrialEvidence = { status: "completed", failures: [] };
    return report;
  }

  const failures = [];
  let contextLost = false;
  const lost = (event) => {
    contextLost = true;
    event.preventDefault();
  };
  if (contextEventTarget?.addEventListener) {
    contextEventTarget.addEventListener("webglcontextlost", lost, { once: true });
  }
  try {
    try {
      report.coordinatePrecision = precisionEvidence();
      report.coordinatePrecisionPassed = report.coordinatePrecision
        .every((sample) => sample.pass);
      if (!report.coordinatePrecisionPassed) {
        report.headline = impracticalHeadline(report, "coordinate_precision");
      }
    } catch (error) {
      const failure = evidenceFailure("coordinate_precision", error);
      failures.push(failure);
      report.coordinatePrecision = { status: "failed", ...failure };
    }

    try {
      report.contextVisibleEquivalence = contextEvidence();
      if (!report.contextVisibleEquivalence.pass) {
        report.headline = impracticalHeadline(
          report, "context_visible_equivalence",
        );
      }
    } catch (error) {
      const failure = evidenceFailure("context_visible_equivalence", error);
      failures.push(failure);
      report.contextVisibleEquivalence = { status: "failed", ...failure };
    }

    if (contextLost) {
      failures.push({
        stage: "webgl_context",
        message: "WebGL context lost during post-trial evidence",
      });
    }
  } finally {
    contextEventTarget?.removeEventListener?.("webglcontextlost", lost);
  }

  report.postTrialEvidence = {
    status: failures.length ? "failed" : "completed",
    failures,
  };
  if (failures.length) {
    report.headline = impracticalHeadline(report, "post_trial_evidence");
  }
  return report;
}

function evidenceFailure(stage, error) {
  return {
    stage,
    message: error instanceof Error ? error.message : String(error),
  };
}

function impracticalHeadline(report, source) {
  return {
    tier: "impractical",
    source,
    trialIndex: report.headline?.trialIndex ?? null,
  };
}

function disposeEvidenceScenes(contexts, dispose) {
  let firstError = null;
  contexts.forEach((context) => {
    try {
      dispose(context.scene);
    } catch (error) {
      firstError ??= error;
    }
  });
  if (firstError) throw firstError;
}

let el = null;
let renderer = null;
let active = null;
let report = null;
let localGlbBytes = null;
let localGlbProvenance = null;
const runCoordinator = createRunCoordinator();

if (typeof document !== "undefined") initializeDashboard();

export function initializeDashboard({
  documentRef = document,
  navigatorRef = globalThis.navigator,
  createRenderer = createFixedRenderer,
} = {}) {
  documentRef.title = APP_TITLE;
  el = Object.fromEntries([...documentRef.querySelectorAll("[id]")]
    .map((node) => [node.id, node]));
  renderer = null;

  el["copy-report"].addEventListener("click", () =>
    navigatorRef?.clipboard?.writeText(JSON.stringify(report, null, 2)));

  try {
    renderer = createRenderer(el.canvas);
  } catch (error) {
    publishFailure(error, {
      stage: "renderer_initialization",
      source: el.source?.value ?? null,
      file: selectedFilename(),
      config: safeReadConfig(),
    });
    setRendererControlsDisabled(true);
    return dashboardApi();
  }

  el.source.addEventListener("change", () => {
    el["glb-file"].disabled = el.source.value !== "glb";
  });
  el.build.addEventListener("click", () => buildOrLoad().catch((error) =>
    showError(error, { stage: "build_or_load" })));
  el.run.addEventListener("click", () => run().catch((error) =>
    showError(error, { stage: "benchmark_run" })));
  el.stop.addEventListener("click", () => runCoordinator.stop());
  el.reset.addEventListener("click", () => reset().catch((error) =>
    showError(error, { stage: "reset" })));
  el.time.addEventListener("input", () => renderAt(Number(el.time.value)));
  return dashboardApi();
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
  localGlbProvenance = outcome.value.provenance;
  renderAt(0);
  el.status.textContent = "Loaded " + active.actorIndex.size + " actors.";
}

function buildSynthetic(config) {
  const generated = createSyntheticScene(config);
  const camera = createCamera(generated.appliedRenderOffset);
  addFixedLights(generated.scene, generated.appliedRenderOffset);
  return finalizeContext(generated, camera);
}

async function loadLocal(config) {
  const file = el["glb-file"].files[0];
  if (!file) throw new Error("Choose a local GLB file first");
  const bytes = await file.arrayBuffer();
  const provenance = await createLocalGlbProvenance(file, bytes);
  return {
    context: await buildLocalFromBytes(config, bytes, provenance),
    bytes,
    provenance,
  };
}

async function buildLocalFromBytes(
  config,
  bytes = localGlbBytes,
  provenance = localGlbProvenance,
) {
  if (!bytes) throw new Error("Choose and load a local GLB first");
  const gltf = await loadGlbArrayBuffer(bytes.slice(0));
  const camera = createCamera();
  addFixedLights(gltf.scene);
  return finalizeContext({
    scene: gltf.scene,
    actorRoot: gltf.scene,
    contextRoot: gltf.scene,
    config,
    sourceOrigin: [0, 0, 0],
    rebaseOrigin: [0, 0, 0],
    appliedRenderOffset: [0, 0, 0],
    sourceKind: "local_glb",
    sourceProvenance: provenance,
  }, camera);
}

export async function createLocalGlbProvenance(
  file,
  bytes,
  subtle = globalThis.crypto?.subtle,
) {
  if (!subtle) throw new Error("Web Crypto is required for GLB provenance");
  const digest = await subtle.digest("SHA-256", bytes);
  const sha256 = [...new Uint8Array(digest)]
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("");
  return {
    sourceKind: "local_glb",
    filename: file.name,
    sizeBytes: bytes.byteLength,
    sha256,
  };
}

export function finalizeContext(context, camera, now = performance.now.bind(performance)) {
  const traversalStarted = now();
  const addressability = buildActorIndex(context.actorRoot);
  const structure = countScene(context.scene);
  const sceneTraversalMs = now() - traversalStarted;
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
  active.scene.updateMatrixWorld(true);
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
  const configSnapshot = Object.freeze(readConfig());
  const sourceKind = selectedSource === "glb" ? "local_glb" : "synthetic";
  const sourceProvenance = selectedSource === "glb"
    ? { ...localGlbProvenance }
    : { sourceKind: "synthetic", actorCount: configSnapshot.actorCount };
  const outcome = await runCoordinator.start(async ({ signal }) => {
    disposePreview();
    el.run.disabled = true;
    el.status.textContent = "Running 3 trials...";
    const timedReport = await runConfiguration({
      config: configSnapshot,
      renderer,
      signal,
      environment: captureEnvironment(renderer),
      sourceKind,
      sourceProvenance,
      buildScene: async () => buildTrialSource(
        configSnapshot, selectedSource, sourceProvenance,
      ),
      evaluate: evaluateAt,
      dispose: disposeScene,
    });
    return addPostTrialEvidence(timedReport, {
      config: configSnapshot,
      source: selectedSource,
      contextEventTarget: renderer.domElement,
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

function buildTrialSource(config, source, provenance) {
  return source === "glb"
    ? buildLocalFromBytes(config, localGlbBytes, provenance)
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
  localGlbProvenance = null;
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

export function createFailureReport(error, {
  stage, source = null, file = null, config = null,
}) {
  const message = error instanceof Error ? error.message : String(error);
  return {
    schemaVersion: 1,
    status: "failed",
    failure: { stage, message, source, file, config },
    headline: { tier: "impractical", source: stage, trialIndex: null },
  };
}

function showError(error, { stage = "dashboard_action" } = {}) {
  publishFailure(error, {
    stage,
    source: el?.source?.value ?? null,
    file: selectedFilename(),
    config: safeReadConfig(),
  });
}

function publishFailure(error, context) {
  report = createFailureReport(error, context);
  el.status.textContent = report.failure.message;
  el.report.textContent = JSON.stringify(report, null, 2);
  return report;
}

function selectedFilename() {
  return el?.["glb-file"]?.files?.[0]?.name ?? null;
}

function safeReadConfig() {
  try {
    return readConfig();
  } catch {
    return null;
  }
}

function setRendererControlsDisabled(disabled) {
  ["build", "run", "stop", "reset", "time"].forEach((id) => {
    if (el[id]) el[id].disabled = disabled;
  });
}

function dashboardApi() {
  return {
    getReport: () => report,
    getRenderer: () => renderer,
  };
}
