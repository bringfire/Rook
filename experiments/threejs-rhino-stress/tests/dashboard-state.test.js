import { expect, it } from "vitest";
import { createRunCoordinator } from "../src/main.js";

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

function deferred() {
  let resolve;
  const promise = new Promise((complete) => {
    resolve = complete;
  });
  return { promise, resolve };
}
