import { BENCHMARK_PROTOCOL } from "./config.js";
import {
  runCorrectnessChecks, validateProtocolEnvironment,
} from "./evidence.js";
import { createGpuTimer } from "./gpu-timer.js";
import {
  classifyConfiguration, classifyTrial, summarizeSamples,
} from "./metrics.js";

export async function runTrial({
  trialIndex, renderer, buildScene, evaluate, dispose, signal,
  protocol = BENCHMARK_PROTOCOL,
  checkCorrectness = runCorrectnessChecks,
  protocolProbe = () => validateProtocolEnvironment({
    visibilityState: document.visibilityState,
    width: renderer.domElement.width,
    height: renderer.domElement.height,
  }),
  schedule = requestAnimationFrame,
  now = performance.now.bind(performance),
}) {
  let context = null;
  let timer = null;
  let constructionMs = null;
  let contextLost = false;
  let listenerAttached = false;
  let result;
  const frameCpuSamples = [];
  const seekSamples = [];
  const matrixTraversalSamples = [];
  const renderSubmissionSamples = [];
  const lost = (event) => {
    contextLost = true;
    event.preventDefault();
  };
  const assertContextActive = () => {
    if (contextLost) throw new DOMException("context lost", "AbortError");
  };

  try {
    protocolProbe();
    if (typeof renderer.domElement?.addEventListener === "function" &&
        typeof renderer.domElement?.removeEventListener === "function") {
      renderer.domElement.addEventListener(
        "webglcontextlost", lost, { once: true });
      listenerAttached = true;
    }
    const started = now();
    context = await buildScene();
    constructionMs = now() - started;
    assertContextActive();
    // The benchmark owns the single world-matrix traversal. Three.js r181
    // otherwise performs another traversal inside WebGLRenderer.render().
    context.scene.matrixWorldAutoUpdate = false;
    timer = createGpuTimer(renderer.getContext());

    await frames(protocol.warmupFrames, (frame) => {
      protocolProbe();
      assertContextActive();
      evaluate(context, frame / 60);
      context.scene.updateMatrixWorld(true);
      renderer.render(context.scene, context.camera);
      assertContextActive();
    }, schedule, signal);

    await frames(protocol.measuredFrames, (frame) => {
      protocolProbe();
      assertContextActive();
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
      assertContextActive();
    }, schedule, signal);

    await drain(timer, schedule, signal, assertContextActive);
    const gpuRaw = timer.snapshot();
    const cpu = summarizeSamples(frameCpuSamples);
    const seek = summarizeSamples(seekSamples);
    const matrixTraversal = summarizeSamples(matrixTraversalSamples);
    const renderSubmission = summarizeSamples(renderSubmissionSamples);
    const gpu = summarizeSamples(gpuRaw.samplesMs);
    assertContextActive();
    const correctness = await checkCorrectness(context);
    assertContextActive();
    const correctnessPassed = context.addressabilityPassed !== false
      && correctness.pass;
    const rendererInfo = {
      calls: renderer.info.render.calls,
      triangles: renderer.info.render.triangles,
      points: renderer.info.render.points,
      lines: renderer.info.render.lines,
    };
    const classification = classifyTrial({
      status: "completed", correctnessPassed, constructionMs, cpu,
      gpu: { ...gpu, validCount: gpuRaw.samplesMs.length },
    });
    result = {
      trialIndex,
      status: "completed",
      constructionMs,
      cpu: { ...cpu, samples: frameCpuSamples },
      seek: { ...seek, samples: seekSamples },
      matrixTraversal: {
        ...matrixTraversal, samples: matrixTraversalSamples,
      },
      renderSubmission: {
        ...renderSubmission, samples: renderSubmissionSamples,
      },
      gpu: {
        ...gpu,
        samples: gpuRaw.samplesMs,
        disjointCount: gpuRaw.disjointCount,
      },
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
      correctnessPassed,
      classification,
    };
  } catch (error) {
    result = {
      trialIndex,
      status: "aborted",
      reason: contextLost ? "context_lost" : error.message,
    };
  }

  const cleanupErrors = [];
  if (listenerAttached) {
    try {
      renderer.domElement.removeEventListener("webglcontextlost", lost);
    } catch (error) {
      cleanupErrors.push(cleanupError("listener_removal", error));
    }
  }
  if (timer) {
    try {
      timer.dispose();
    } catch (error) {
      cleanupErrors.push(cleanupError("gpu_timer_disposal", error));
    }
  }
  if (context?.scene) {
    try {
      dispose(context.scene);
    } catch (error) {
      cleanupErrors.push(cleanupError("scene_disposal", error));
    }
  }

  if (cleanupErrors.length) {
    result = {
      ...result,
      status: "aborted",
      reason: result.status === "completed" ? "cleanup_failed" : result.reason,
      cleanupErrors,
    };
  }

  return result;
}

export async function runConfiguration({
  config,
  environment,
  trialCount = BENCHMARK_PROTOCOL.trials,
  runTrialImpl = runTrial,
  ...options
}) {
  const trials = [];
  for (let trialIndex = 0; trialIndex < trialCount; trialIndex += 1) {
    let trial = await runTrialImpl({ ...options, config, trialIndex });
    if (trial.status === "completed" && options.signal?.aborted) {
      trial = { ...trial, status: "aborted", reason: "cancelled" };
    }
    trials.push(trial);
    if (trial.status !== "completed") break;
  }
  return {
    schemaVersion: 1,
    config,
    environment,
    trials,
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
  if (count <= 0) return Promise.resolve();
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

async function drain(timer, schedule, signal, assertContextActive) {
  assertContextActive();
  for (let attempt = 0;
    attempt < 120 && timer.snapshot().pendingCount > 0;
    attempt += 1) {
    await new Promise((resolve, reject) => schedule(() => {
      if (signal?.aborted) {
        reject(new DOMException("run stopped", "AbortError"));
      } else {
        try {
          assertContextActive();
          timer.poll();
          assertContextActive();
          resolve();
        } catch (error) {
          reject(error);
        }
      }
    }));
  }
  assertContextActive();
}

function cleanupError(stage, error) {
  return {
    stage,
    message: error instanceof Error ? error.message : String(error),
  };
}
