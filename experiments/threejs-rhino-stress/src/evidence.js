import { REVISION, Vector3 } from "three";
import { evaluateAt, transformSnapshot } from "./animation.js";
import { BENCHMARK_PROTOCOL } from "./config.js";

const DETERMINISTIC_SEEK_SAMPLE_TIMES = Object.freeze([
  0, 0.25, 0.5, 0.75, 1,
]);
const DETERMINISTIC_SEEK_ORDERS = Object.freeze({
  forward: DETERMINISTIC_SEEK_SAMPLE_TIMES,
  reverse: [...DETERMINISTIC_SEEK_SAMPLE_TIMES].reverse(),
  shuffled: [0.5, 0, 1, 0.25, 0.75],
});

export function validateProtocolEnvironment({
  visibilityState, width, height,
}) {
  if (visibilityState !== "visible") {
    throw new Error("benchmark document must remain visible");
  }
  if (
    width !== BENCHMARK_PROTOCOL.width
    || height !== BENCHMARK_PROTOCOL.height
  ) {
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
    gpuVendor: debug
      ? gl.getParameter(debug.UNMASKED_VENDOR_WEBGL)
      : null,
    gpuRenderer: debug
      ? gl.getParameter(debug.UNMASKED_RENDERER_WEBGL)
      : null,
    heap: memory
      ? {
          usedJSHeapSize: memory.usedJSHeapSize,
          totalJSHeapSize: memory.totalJSHeapSize,
          jsHeapSizeLimit: memory.jsHeapSizeLimit,
        }
      : null,
  };
}

export function runCorrectnessChecks(context) {
  const actors = [...context.actorIndex.values()];
  if (!actors.length) {
    return {
      pass: false,
      deterministicSeek: false,
      deterministicSeekScope: "actor_root_and_actors",
      independentTransform: false,
      pivotSanity: { status: "failed", reason: "no addressable actors" },
    };
  }

  const seekEvidence = checkDeterministicSeek(context);
  const deterministicSeek = Object.values(seekEvidence.orders)
    .every(Boolean);
  updateWorldMatrices(context);

  const firstActor = actors[0];
  const secondActor = actors[1] ?? actors[0];
  const secondBefore = secondActor.matrixWorld.clone();
  firstActor.position.x += 1;
  firstActor.updateMatrixWorld(true);
  const independentTransform = secondActor.matrixWorld.equals(secondBefore);

  let pivotSanity;
  const syntheticIdentity = checkSyntheticIdentity(context);
  const sharedGeometry = checkSharedGeometry(context, actors);
  if (context.sourceKind !== "synthetic") {
    pivotSanity = {
      status: "unavailable",
      reason: "arbitrary local GLB pivot semantics are outside this experiment",
    };
  } else {
    evaluateAt(context, 0);
    updateWorldMatrices(context);
    const savedQuaternion = firstActor.quaternion.clone();
    const pivotExpected = firstActor.parent.localToWorld(
      firstActor.position.clone(),
    );
    firstActor.rotation.set(0, Math.PI / 2, 0);
    firstActor.updateWorldMatrix(true, true);
    const pivotActual = firstActor.localToWorld(new Vector3(0, 0, 0));
    const localProbe = new Vector3(1, 0, 0);
    const offAxisActual = firstActor.localToWorld(localProbe.clone());
    const expectedOffset = localProbe.multiply(firstActor.scale)
      .applyAxisAngle(new Vector3(0, 1, 0), Math.PI / 2);
    const offAxisExpected = firstActor.parent.localToWorld(
      firstActor.position.clone().add(expectedOffset),
    );
    const pivotError = pivotActual.distanceTo(pivotExpected);
    const offAxisError = offAxisActual.distanceTo(offAxisExpected);
    const passed = pivotError <= 1e-9 && offAxisError <= 1e-9;
    pivotSanity = passed
      ? { status: "passed" }
      : { status: "failed", pivotError, offAxisError };
    firstActor.quaternion.copy(savedQuaternion);
    firstActor.updateWorldMatrix(true, true);
  }

  evaluateAt(context, 0);
  updateWorldMatrices(context);
  return {
    pass: deterministicSeek
      && independentTransform
      && syntheticIdentity.status !== "failed"
      && sharedGeometry.status !== "failed"
      && pivotSanity.status !== "failed",
    deterministicSeek,
    deterministicSeekScope: "actor_root_and_actors",
    deterministicSeekOrders: seekEvidence.orders,
    deterministicSeekSampleTimes: [...DETERMINISTIC_SEEK_SAMPLE_TIMES],
    independentTransform,
    syntheticIdentity,
    sharedGeometry,
    pivotSanity,
  };
}

function checkDeterministicSeek(context) {
  const hashes = new Map();
  const orders = {};
  Object.entries(DETERMINISTIC_SEEK_ORDERS).forEach(([name, times]) => {
    let passed = true;
    times.forEach((time) => {
      evaluateAt(context, time);
      const snapshot = transformSnapshot(
        context.actorIndex, context.actorRoot,
      );
      if (hashes.has(time)) passed &&= hashes.get(time) === snapshot;
      else hashes.set(time, snapshot);
    });
    orders[name] = passed;
  });
  return { orders };
}

function checkSyntheticIdentity(context) {
  if (context.sourceKind !== "synthetic") return { status: "unavailable" };
  const expectedCount = Number(context.config?.actorCount ?? 0);
  const expectedIds = Array.from({ length: expectedCount }, (_, index) =>
    `synthetic_actor_${String(index).padStart(6, "0")}`);
  const actualIds = [...context.actorIndex.keys()].sort();
  const passed = actualIds.length === expectedIds.length
    && actualIds.every((actorId, index) => actorId === expectedIds[index]);
  return {
    status: passed ? "passed" : "failed",
    expectedCount,
    actualCount: actualIds.length,
  };
}

function checkSharedGeometry(context, actors) {
  if (context.sourceKind !== "synthetic") return { status: "unavailable" };
  if (context.config?.geometryOwnership !== "shared") {
    return { status: "not_applicable" };
  }
  const firstGeometry = actors[0]?.children?.find(
    (child) => child.isMesh,
  )?.geometry;
  const passed = Boolean(firstGeometry) && actors.every((actor) =>
    actor.children.find((child) => child.isMesh)?.geometry === firstGeometry);
  return { status: passed ? "passed" : "failed" };
}

function updateWorldMatrices(context) {
  if (context.scene) context.scene.updateMatrixWorld(true);
  else context.actorRoot.updateMatrixWorld(true);
}
