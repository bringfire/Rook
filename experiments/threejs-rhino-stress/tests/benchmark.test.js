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
  const result = await runTrial({
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

it("performs exactly one scene world-matrix traversal per measured frame", async () => {
  const context = createContext();
  const renderer = createRenderer({
    render: (renderedScene) => {
      if (renderedScene.matrixWorldAutoUpdate) {
        renderedScene.updateMatrixWorld();
      }
    },
  });
  const result = await runTrial({
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
  const result = await runTrial({
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
  const result = await runTrial({
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
  const result = await runTrial({
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
    count: 1, samples: [5], disjointCount: 0,
  });
  expect(gl.deleteQuery).toHaveBeenCalledOnce();
});

it("aborts a cancelled trial and disposes its constructed scene", async () => {
  const dispose = vi.fn();
  const signal = { aborted: true };
  const context = createContext();
  const result = await runTrial({
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
  const result = await runTrial({
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
