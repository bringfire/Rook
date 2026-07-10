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
    // The benchmark owns the single world-matrix traversal. Three.js r181
    // otherwise performs another traversal inside WebGLRenderer.render().
    context.scene.matrixWorldAutoUpdate = false;
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
      correctness,
      correctnessPassed,
      classification,
    };
  } catch (error) {
    return {
      trialIndex,
      status: "aborted",
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
  config,
  trialCount = BENCHMARK_PROTOCOL.trials,
  runTrialImpl = runTrial,
  ...options
}) {
  const trials = [];
  for (let trialIndex = 0; trialIndex < trialCount; trialIndex += 1) {
    const trial = await runTrialImpl({ ...options, config, trialIndex });
    trials.push(trial);
    if (trial.status !== "completed" || options.signal?.aborted) break;
  }
  return {
    schemaVersion: 1,
    config,
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

async function drain(timer, schedule, signal) {
  for (let attempt = 0;
    attempt < 120 && timer.snapshot().pendingCount > 0;
    attempt += 1) {
    await new Promise((resolve, reject) => schedule(() => {
      if (signal?.aborted) {
        reject(new DOMException("run stopped", "AbortError"));
      } else {
        timer.poll();
        resolve();
      }
    }));
  }
}
