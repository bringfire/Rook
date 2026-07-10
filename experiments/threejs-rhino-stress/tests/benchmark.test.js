import { expect, it, vi } from "vitest";
import { runConfiguration, runTrial } from "../src/benchmark.js";

function createRenderer({ gl, render = () => {} } = {}) {
  return {
    domElement: {
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    },
    getContext: () => gl ?? { getExtension: () => null },
    render,
    info: { render: { calls: 1, triangles: 2, points: 3, lines: 4 } },
  };
}

function createContext(scene = {}) {
  return {
    scene: {
      matrixWorldAutoUpdate: true,
      updateMatrixWorld: vi.fn(),
      ...scene,
    },
    camera: {},
  };
}

function runNodeTrial(options) {
  return runTrial({
    protocolProbe: () => {},
    checkCorrectness: () => ({ pass: true }),
    ...options,
  });
}

it("runs three trials and uses the worst completed trial", async () => {
  const tiers = ["interactive", "marginal", "preview-viable"];
  let index = 0;
  let activeCalls = 0;
  let maximumActiveCalls = 0;
  const report = await runConfiguration({
    config: { actorCount: 338 },
    trialCount: 3,
    runTrialImpl: async () => {
      activeCalls += 1;
      maximumActiveCalls = Math.max(maximumActiveCalls, activeCalls);
      await Promise.resolve();
      const tier = tiers[index++];
      activeCalls -= 1;
      return {
        status: "completed",
        classification: { tier },
        cpu: { samples: [4] },
        seek: { samples: [1] },
        matrixTraversal: { samples: [1] },
        renderSubmission: { samples: [2] },
        gpu: { samples: [3] },
      };
    },
  });

  expect(report.trials).toHaveLength(3);
  expect(maximumActiveCalls).toBe(1);
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
    config: {},
    trialCount: 3,
    runTrialImpl: async ({ trialIndex }) => trialIndex === 1
      ? { status: "aborted", reason: "context_lost" }
      : {
          status: "completed",
          classification: { tier: "interactive" },
          cpu: { samples: [] },
          gpu: { samples: [] },
        },
  });

  expect(report.headline.tier).toBe("impractical");
});

it("converts construction failure into an aborted trial", async () => {
  const dispose = vi.fn(() => {
    throw new Error("must not dispose missing context");
  });
  const result = await runNodeTrial({
    trialIndex: 0,
    renderer: {},
    buildScene: async () => { throw new Error("construction failed"); },
    evaluate: () => {},
    dispose,
    protocolProbe: () => {},
    schedule: (callback) => callback(),
    now: () => 0,
  });

  expect(result).toMatchObject({
    trialIndex: 0, status: "aborted", reason: "construction failed",
  });
  expect(dispose).not.toHaveBeenCalled();
});

it("converts initial protocol-probe failure into an aborted trial", async () => {
  const buildScene = vi.fn();
  const dispose = vi.fn();
  const result = await runNodeTrial({
    trialIndex: 0,
    renderer: {},
    buildScene,
    evaluate: () => {},
    dispose,
    protocolProbe: () => {
      throw new Error("benchmark document must remain visible");
    },
    schedule: (callback) => callback(),
    now: () => 0,
  });
  expect(result).toMatchObject({
    trialIndex: 0,
    status: "aborted",
    reason: "benchmark document must remain visible",
  });
  expect(buildScene).not.toHaveBeenCalled();
  expect(dispose).not.toHaveBeenCalled();
});

it("aborts callback protocol-probe failure and disposes the scene", async () => {
  const context = createContext();
  const evaluate = vi.fn();
  const dispose = vi.fn();
  let probes = 0;
  const result = await runNodeTrial({
    trialIndex: 0,
    renderer: createRenderer(),
    buildScene: async () => context,
    evaluate,
    dispose,
    protocolProbe: () => {
      probes += 1;
      if (probes === 2) throw new Error("drawing buffer changed");
    },
    protocol: { warmupFrames: 1, measuredFrames: 0 },
    schedule: (callback) => callback(),
    now: () => 0,
  });

  expect(result).toMatchObject({
    status: "aborted", reason: "drawing buffer changed",
  });
  expect(evaluate).not.toHaveBeenCalled();
  expect(dispose).toHaveBeenCalledWith(context.scene);
});

it("retains complete trial evidence and addressability correctness", async () => {
  const context = {
    ...createContext(),
    sourceKind: "synthetic",
    sourceProvenance: {
      sourceKind: "synthetic", actorCount: 1,
    },
    structure: { nodes: 4, actors: 1 },
    sceneTraversalMs: 7,
    sourceOrigin: [1, 2, 3],
    rebaseOrigin: [1, 2, 3],
    appliedRenderOffset: [0, 0, 0],
    addressability: { missingActorId: 0, duplicates: [] },
    addressabilityPassed: false,
  };
  const checkCorrectness = vi.fn(() => ({ pass: true }));
  const result = await runNodeTrial({
    trialIndex: 0,
    renderer: createRenderer(),
    buildScene: async () => context,
    evaluate: () => {},
    dispose: () => {},
    checkCorrectness,
    protocol: { warmupFrames: 0, measuredFrames: 0 },
    protocolProbe: () => {},
    schedule: (callback) => callback(),
    now: () => 0,
  });

  expect(checkCorrectness).toHaveBeenCalledWith(context);
  expect(result).toMatchObject({
    sourceKind: "synthetic",
    sourceProvenance: {
      sourceKind: "synthetic", actorCount: 1,
    },
    structure: context.structure,
    sceneTraversalMs: 7,
    origins: {
      sourceOrigin: [1, 2, 3],
      rebaseOrigin: [1, 2, 3],
      appliedRenderOffset: [0, 0, 0],
    },
    addressability: context.addressability,
    rendererInfo: { calls: 1, triangles: 2, points: 3, lines: 4 },
    correctness: { pass: true },
    correctnessPassed: false,
  });
});

it("retains captured environment at the report root", async () => {
  const environment = { threeRevision: "181", drawingBuffer: [1920, 1080] };
  const report = await runConfiguration({
    config: {},
    environment,
    trialCount: 0,
    runTrialImpl: vi.fn(),
  });
  expect(report.environment).toBe(environment);
});

it("retains serializable source provenance at the report root", async () => {
  const sourceProvenance = {
    sourceKind: "local_glb",
    filename: "actor-metadata.glb",
    sizeBytes: 896,
    sha256: "efc13eb1b477a8f64faa64ec83983691e8c095121a3689109b4bad26c59071e4",
  };
  const report = await runConfiguration({
    config: {},
    sourceKind: "local_glb",
    sourceProvenance,
    trialCount: 0,
    runTrialImpl: vi.fn(),
  });

  expect(report).toMatchObject({
    sourceKind: "local_glb",
    sourceProvenance,
  });
  expect(JSON.parse(JSON.stringify(report)).sourceProvenance)
    .toEqual(sourceProvenance);
});

it("performs exactly one scene world-matrix traversal per measured frame", async () => {
  const context = createContext();
  const renderer = createRenderer({
    render: (renderedScene) => {
      if (renderedScene.matrixWorldAutoUpdate) {
        renderedScene.updateMatrixWorld();
      }
    },
  });
  const result = await runNodeTrial({
    trialIndex: 0,
    renderer,
    buildScene: async () => context,
    evaluate: () => {},
    dispose: () => {},
    protocol: { warmupFrames: 0, measuredFrames: 3 },
    protocolProbe: () => {},
    schedule: (callback) => callback(),
    now: performance.now.bind(performance),
  });

  expect(result.status).toBe("completed");
  expect(context.scene.matrixWorldAutoUpdate).toBe(false);
  expect(context.scene.updateMatrixWorld).toHaveBeenCalledTimes(3);
  expect(context.scene.updateMatrixWorld).toHaveBeenNthCalledWith(1, true);
});

it("stops scheduling after the first aborted trial", async () => {
  let calls = 0;
  const report = await runConfiguration({
    config: {},
    trialCount: 3,
    runTrialImpl: async () => {
      calls += 1;
      return { status: "aborted", reason: "cancelled" };
    },
  });

  expect(calls).toBe(1);
  expect(report.trials).toHaveLength(1);
  expect(report.headline.tier).toBe("impractical");
});

it("keeps seek, matrix, render, and combined CPU samples separate", async () => {
  const timestamps = [0, 10, 20, 21, 23, 24, 27, 30, 34, 40];
  const context = createContext();
  const result = await runNodeTrial({
    trialIndex: 2,
    renderer: createRenderer(),
    buildScene: async () => context,
    evaluate: () => {},
    dispose: () => {},
    protocol: { warmupFrames: 0, measuredFrames: 1 },
    schedule: (callback) => callback(),
    now: () => timestamps.shift(),
  });

  expect(result).toMatchObject({
    trialIndex: 2,
    status: "completed",
    constructionMs: 10,
    cpu: { samples: [20] },
    seek: { samples: [2] },
    matrixTraversal: { samples: [3] },
    renderSubmission: { samples: [4] },
  });
});

it("completes a zero-frame trial without scheduling or fabricating samples", async () => {
  const schedule = vi.fn();
  const dispose = vi.fn();
  const context = createContext();
  const result = await runNodeTrial({
    trialIndex: 0,
    renderer: createRenderer(),
    buildScene: async () => context,
    evaluate: vi.fn(),
    dispose,
    protocol: { warmupFrames: 0, measuredFrames: 0 },
    schedule,
    now: () => 0,
  });

  expect(result.status).toBe("completed");
  expect(schedule).not.toHaveBeenCalled();
  expect(result.cpu).toMatchObject({ count: 0, p95: null, samples: [] });
  expect(result.seek).toMatchObject({ count: 0, p95: null, samples: [] });
  expect(result.matrixTraversal).toMatchObject({
    count: 0, p95: null, samples: [],
  });
  expect(result.renderSubmission).toMatchObject({
    count: 0, p95: null, samples: [],
  });
  expect(dispose).toHaveBeenCalledOnce();
  expect(dispose).toHaveBeenCalledWith(context.scene);
});

it("drains pending GPU queries before recording the trial", async () => {
  const extension = {
    TIME_ELAPSED_EXT: "time_elapsed",
    GPU_DISJOINT_EXT: "gpu_disjoint",
  };
  let availabilityChecks = 0;
  const gl = {
    QUERY_RESULT_AVAILABLE: "query_available",
    QUERY_RESULT: "query_result",
    getExtension: () => extension,
    createQuery: () => ({ id: 1 }),
    beginQuery: vi.fn(),
    endQuery: vi.fn(),
    getParameter: () => false,
    getQueryParameter: (_query, parameter) => {
      if (parameter === "query_available") {
        availabilityChecks += 1;
        return availabilityChecks >= 2;
      }
      return 5_000_000;
    },
    deleteQuery: vi.fn(),
  };
  const result = await runNodeTrial({
    trialIndex: 0,
    renderer: createRenderer({ gl }),
    buildScene: async () => createContext(),
    evaluate: () => {},
    dispose: () => {},
    protocol: { warmupFrames: 0, measuredFrames: 1 },
    schedule: (callback) => callback(),
    now: (() => {
      let value = 0;
      return () => value++;
    })(),
  });

  expect(result.status).toBe("completed");
  expect(availabilityChecks).toBe(2);
  expect(result.gpu).toMatchObject({
    available: true,
    status: "insufficient_samples",
    validCount: 1,
    count: 1,
    samples: [5],
    disjointCount: 0,
  });
  expect(gl.deleteQuery).toHaveBeenCalledOnce();
});

it("reports unavailable GPU timing explicitly", async () => {
  const result = await runNodeTrial({
    trialIndex: 0,
    renderer: createRenderer(),
    buildScene: async () => createContext(),
    evaluate: () => {},
    dispose: () => {},
    protocol: { warmupFrames: 0, measuredFrames: 1, gpuValidSampleFloor: 270 },
    schedule: (callback) => callback(),
    now: (() => { let value = 0; return () => value++; })(),
  });

  expect(result.gpu).toMatchObject({
    available: false,
    status: "unavailable",
    validCount: 0,
    disjointCount: 0,
    samples: [],
  });
  expect(result.classification.basis).toBe("cpu_proxy_only");
});

it.each([
  ["construction", [0, Number.NaN]],
  ["seek", [0, 1, Number.NaN]],
])("aborts before recording a non-finite %s duration", async (metric, timestamps) => {
  const result = await runNodeTrial({
    trialIndex: 0,
    renderer: createRenderer(),
    buildScene: async () => createContext(),
    evaluate: () => {},
    dispose: () => {},
    protocol: { warmupFrames: 0, measuredFrames: metric === "construction" ? 0 : 1 },
    schedule: (callback) => callback(),
    now: () => timestamps.shift(),
  });

  expect(result).toMatchObject({
    status: "aborted",
    reason: `non_finite_timing:${metric}`,
    diagnostic: { stage: "timing", metric },
  });
  expect(result.cpu?.samples ?? []).not.toContainEqual(Number.NaN);
});

it("aborts a cancelled trial and disposes its constructed scene", async () => {
  const dispose = vi.fn();
  const signal = { aborted: true };
  const context = createContext();
  const result = await runNodeTrial({
    trialIndex: 0,
    renderer: createRenderer(),
    buildScene: async () => context,
    evaluate: vi.fn(),
    dispose,
    signal,
    protocol: { warmupFrames: 0, measuredFrames: 1 },
    schedule: (callback) => callback(),
    now: () => 0,
  });

  expect(result).toMatchObject({
    status: "aborted", reason: "run stopped",
  });
  expect(dispose).toHaveBeenCalledWith(context.scene);
});

it("aborts on context loss and removes the listener before disposal", async () => {
  const events = [];
  let lost;
  const renderer = createRenderer({
    render: () => lost({
      preventDefault: () => events.push("prevented"),
    }),
  });
  renderer.domElement.addEventListener.mockImplementation((_name, listener) => {
    lost = listener;
  });
  renderer.domElement.removeEventListener.mockImplementation(() => {
    events.push("listener_removed");
  });
  const dispose = vi.fn(() => events.push("disposed"));
  const result = await runNodeTrial({
    trialIndex: 0,
    renderer,
    buildScene: async () => createContext(),
    evaluate: () => {},
    dispose,
    protocol: { warmupFrames: 0, measuredFrames: 1 },
    schedule: (callback) => callback(),
    now: () => 0,
  });

  expect(result).toMatchObject({
    status: "aborted", reason: "context_lost",
  });
  expect(renderer.domElement.removeEventListener)
    .toHaveBeenCalledWith("webglcontextlost", lost);
  expect(events).toEqual(["prevented", "listener_removed", "disposed"]);
});

it("captures context loss while scene construction is pending", async () => {
  let lost;
  const renderer = createRenderer();
  renderer.domElement.addEventListener.mockImplementation((_name, listener) => {
    lost = listener;
  });
  const context = createContext();
  const evaluate = vi.fn();
  const dispose = vi.fn();
  const result = await runNodeTrial({
    trialIndex: 0,
    renderer,
    buildScene: async () => {
      lost({ preventDefault: vi.fn() });
      await Promise.resolve();
      return context;
    },
    evaluate,
    dispose,
    protocol: { warmupFrames: 0, measuredFrames: 0 },
    schedule: (callback) => callback(),
    now: () => 0,
  });

  expect(result).toMatchObject({
    status: "aborted", reason: "context_lost",
  });
  expect(evaluate).not.toHaveBeenCalled();
  expect(dispose).toHaveBeenCalledWith(context.scene);
});

it("captures context loss during the final warm-up frame", async () => {
  let lost;
  const renderer = createRenderer({
    render: () => lost({ preventDefault: vi.fn() }),
  });
  renderer.domElement.addEventListener.mockImplementation((_name, listener) => {
    lost = listener;
  });
  const result = await runNodeTrial({
    trialIndex: 0,
    renderer,
    buildScene: async () => createContext(),
    evaluate: () => {},
    dispose: () => {},
    protocol: { warmupFrames: 1, measuredFrames: 0 },
    schedule: (callback) => callback(),
    now: () => 0,
  });

  expect(result).toMatchObject({
    status: "aborted", reason: "context_lost",
  });
});

it("captures context loss while pending GPU queries drain", async () => {
  const extension = {
    TIME_ELAPSED_EXT: "time_elapsed",
    GPU_DISJOINT_EXT: "gpu_disjoint",
  };
  let available = false;
  const gl = {
    QUERY_RESULT_AVAILABLE: "query_available",
    QUERY_RESULT: "query_result",
    getExtension: () => extension,
    createQuery: () => ({ id: 1 }),
    beginQuery: () => {},
    endQuery: () => {},
    getParameter: () => false,
    getQueryParameter: (_query, parameter) =>
      parameter === "query_available" ? available : 5_000_000,
    deleteQuery: () => {},
  };
  let lost;
  const renderer = createRenderer({ gl });
  renderer.domElement.addEventListener.mockImplementation((_name, listener) => {
    lost = listener;
  });
  let scheduled = 0;
  const result = await runNodeTrial({
    trialIndex: 0,
    renderer,
    buildScene: async () => createContext(),
    evaluate: () => {},
    dispose: () => {},
    protocol: { warmupFrames: 0, measuredFrames: 1 },
    schedule: (callback) => {
      scheduled += 1;
      if (scheduled === 2) {
        lost({ preventDefault: vi.fn() });
        available = true;
      }
      callback();
    },
    now: () => 0,
  });

  expect(result).toMatchObject({
    status: "aborted", reason: "context_lost",
  });
});

it("captures context loss during asynchronous correctness checking", async () => {
  let lost;
  const renderer = createRenderer();
  renderer.domElement.addEventListener.mockImplementation((_name, listener) => {
    lost = listener;
  });
  const result = await runNodeTrial({
    trialIndex: 0,
    renderer,
    buildScene: async () => createContext(),
    evaluate: () => {},
    dispose: () => {},
    checkCorrectness: async () => {
      lost({ preventDefault: vi.fn() });
      await Promise.resolve();
      return { pass: true };
    },
    protocol: { warmupFrames: 0, measuredFrames: 0 },
    schedule: (callback) => callback(),
    now: () => 0,
  });

  expect(result).toMatchObject({
    status: "aborted", reason: "context_lost",
  });
  expect(result.classification?.tier).not.toBe("interactive");
});

it("turns between-trial cancellation into an evidence-preserving abort", async () => {
  const controller = new AbortController();
  const cpu = { count: 1, samples: [4] };
  const report = await runConfiguration({
    config: {},
    signal: controller.signal,
    trialCount: 3,
    runTrialImpl: async () => {
      controller.abort();
      return {
        status: "completed",
        classification: { tier: "interactive" },
        cpu,
        gpu: { samples: [] },
      };
    },
  });

  expect(report.trials).toHaveLength(1);
  expect(report.trials[0]).toMatchObject({
    status: "aborted", reason: "cancelled", cpu,
  });
  expect(report.headline).toEqual({
    tier: "impractical", source: "aborted_trial", trialIndex: 0,
  });
});

it("converts scene disposal failure into a resolved aborted trial", async () => {
  const result = await runNodeTrial({
    trialIndex: 0,
    renderer: createRenderer(),
    buildScene: async () => createContext(),
    evaluate: () => {},
    dispose: () => { throw new Error("scene disposal failed"); },
    protocol: { warmupFrames: 0, measuredFrames: 0 },
    schedule: (callback) => callback(),
    now: () => 0,
  });

  expect(result).toMatchObject({
    status: "aborted",
    reason: "cleanup_failed",
    cleanupErrors: [{
      stage: "scene_disposal", message: "scene disposal failed",
    }],
  });
});

it("continues timer and scene cleanup after listener cleanup fails", async () => {
  const events = [];
  const extension = {
    TIME_ELAPSED_EXT: "time_elapsed",
    GPU_DISJOINT_EXT: "gpu_disjoint",
  };
  const gl = {
    getExtension: () => extension,
    createQuery: () => ({ id: 1 }),
    beginQuery: () => {},
    endQuery: () => {},
    deleteQuery: () => events.push("timer_disposed"),
  };
  const renderer = createRenderer({
    gl,
    render: () => { throw new Error("render failed"); },
  });
  renderer.domElement.removeEventListener.mockImplementation(() => {
    events.push("listener_cleanup_attempted");
    throw new Error("listener cleanup failed");
  });
  const result = await runNodeTrial({
    trialIndex: 0,
    renderer,
    buildScene: async () => createContext(),
    evaluate: () => {},
    dispose: () => events.push("scene_disposed"),
    protocol: { warmupFrames: 0, measuredFrames: 1 },
    schedule: (callback) => callback(),
    now: () => 0,
  });

  expect(result).toMatchObject({
    status: "aborted",
    reason: "render failed",
    cleanupErrors: [{
      stage: "listener_removal", message: "listener cleanup failed",
    }],
  });
  expect(events).toEqual([
    "listener_cleanup_attempted", "timer_disposed", "scene_disposed",
  ]);
});
