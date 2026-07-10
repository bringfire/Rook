import { expect, it, vi } from "vitest";
import * as dashboard from "../src/main.js";

const { createRunCoordinator } = dashboard;

it("records synthetic post-trial evidence and downgrades failed precision", () => {
  expect(dashboard.addPostTrialEvidence).toBeTypeOf("function");
  const report = {
    headline: { tier: "interactive", trialIndex: 2 },
  };
  const precisionEvidence = vi.fn(() => [
    { time: 0, pass: true },
    { time: 0.5, pass: false },
    { time: 1, pass: true },
  ]);
  const contextEvidence = vi.fn(() => ({ pass: true }));

  expect(dashboard.addPostTrialEvidence(report, {
    config: { actorCount: 338 },
    source: "synthetic",
    precisionEvidence,
    contextEvidence,
  })).toBe(report);

  expect(report).toMatchObject({
    coordinatePrecisionPassed: false,
    contextVisibleEquivalence: { pass: true },
    headline: {
      tier: "impractical",
      source: "coordinate_precision",
      trialIndex: 2,
    },
  });
  expect(precisionEvidence).toHaveBeenCalledOnce();
  expect(contextEvidence).toHaveBeenCalledOnce();
});

it("reports local GLB precision as unavailable without generating pairs", () => {
  expect(dashboard.addPostTrialEvidence).toBeTypeOf("function");
  const report = { headline: { tier: "interactive", trialIndex: 0 } };
  const precisionEvidence = vi.fn();
  const contextEvidence = vi.fn();

  dashboard.addPostTrialEvidence(report, {
    config: {}, source: "glb", precisionEvidence, contextEvidence,
  });

  expect(report.coordinatePrecision).toEqual({
    status: "unavailable",
    reason: "local GLB has no generated rebased comparison pair",
  });
  expect(precisionEvidence).not.toHaveBeenCalled();
  expect(contextEvidence).not.toHaveBeenCalled();
});

it("disposes the first precision scene when the paired build fails", () => {
  expect(dashboard.runPrecisionEvidence).toBeTypeOf("function");
  const rebased = { scene: {} };
  const dispose = vi.fn();
  let builds = 0;

  expect(() => dashboard.runPrecisionEvidence({}, {
    buildSynthetic: () => {
      builds += 1;
      if (builds === 2) throw new Error("large build failed");
      return rebased;
    },
    dispose,
  })).toThrow("large build failed");

  expect(dispose).toHaveBeenCalledOnce();
  expect(dispose).toHaveBeenCalledWith(rebased.scene);
});

it("disposes both context scenes when visible comparison throws", () => {
  expect(dashboard.runContextVisibilityEvidence).toBeTypeOf("function");
  const contexts = [
    { scene: {}, camera: {} },
    { scene: {}, camera: {} },
  ];
  const dispose = vi.fn();
  const renderer = {
    getRenderTarget: () => null,
    getActiveCubeFace: () => 0,
    getActiveMipmapLevel: () => 0,
    setRenderTarget: vi.fn(),
    render: () => { throw new Error("readback failed"); },
  };

  expect(() => dashboard.runContextVisibilityEvidence({}, {
    renderer,
    buildSynthetic: () => contexts.shift(),
    evaluate: vi.fn(),
    dispose,
  })).toThrow("readback failed");

  expect(dispose.mock.calls).toEqual([
    [expect.any(Object)],
    [expect.any(Object)],
  ]);
});

it("waits for invalidated work and marks its completion stale", async () => {
  const coordinator = createRunCoordinator();
  const gate = deferred();
  let signal;
  const runPromise = coordinator.start(async (owner) => {
    signal = owner.signal;
    await gate.promise;
    return "late report";
  });
  let invalidationSettled = false;

  const invalidationPromise = coordinator.invalidate().then(() => {
    invalidationSettled = true;
  });
  expect(signal.aborted).toBe(true);
  await Promise.resolve();
  expect(invalidationSettled).toBe(false);
  expect(coordinator.running).toBe(true);

  gate.resolve();
  const [outcome] = await Promise.all([runPromise, invalidationPromise]);
  expect(outcome).toMatchObject({
    started: true,
    current: false,
    status: "fulfilled",
    value: "late report",
  });
  expect(coordinator.running).toBe(false);
});

it("refuses a second task while the first owns the run", async () => {
  const coordinator = createRunCoordinator();
  const gate = deferred();
  let starts = 0;
  const first = coordinator.start(async () => {
    starts += 1;
    await gate.promise;
  });

  const second = await coordinator.start(async () => {
    starts += 1;
  });
  expect(second).toEqual({ started: false });
  expect(starts).toBe(1);
  expect(coordinator.running).toBe(true);

  gate.resolve();
  await first;
  expect(coordinator.running).toBe(false);
});

it("stops the controller owned by the active task", async () => {
  const coordinator = createRunCoordinator();
  const gate = deferred();
  let signal;
  const runPromise = coordinator.start(async (owner) => {
    signal = owner.signal;
    await gate.promise;
  });

  coordinator.stop();
  expect(signal.aborted).toBe(true);

  gate.resolve();
  const outcome = await runPromise;
  expect(outcome).toMatchObject({
    started: true,
    current: true,
    status: "fulfilled",
  });
});

it("invalidates an async build and marks its late error stale", async () => {
  const coordinator = createRunCoordinator();
  const gate = deferred();
  const buildPromise = coordinator.startBuild(async () => {
    await gate.promise;
    throw new Error("late build failure");
  });

  await coordinator.invalidate();
  gate.resolve();
  const outcome = await buildPromise;

  expect(outcome).toMatchObject({
    current: false,
    status: "rejected",
  });
  expect(outcome.error.message).toBe("late build failure");
});

it("keeps the newer build and discards the older candidate", async () => {
  const coordinator = createRunCoordinator();
  const olderGate = deferred();
  const discarded = [];
  const older = coordinator.startBuild(async () => {
    await olderGate.promise;
    return "older candidate";
  }, (candidate) => discarded.push(candidate));

  const newer = await coordinator.startBuild(
    async () => "newer candidate",
    (candidate) => discarded.push(candidate),
  );
  expect(newer).toMatchObject({
    current: true,
    status: "fulfilled",
    value: "newer candidate",
  });
  expect(discarded).toEqual([]);

  olderGate.resolve();
  const stale = await older;
  expect(stale).toMatchObject({
    current: false,
    status: "fulfilled",
    value: "older candidate",
  });
  expect(discarded).toEqual(["older candidate"]);
});

function deferred() {
  let resolve;
  const promise = new Promise((complete) => {
    resolve = complete;
  });
  return { promise, resolve };
}
