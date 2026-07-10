import { REVISION, Vector3 } from "three";
import { evaluateAt, transformSnapshot } from "./animation.js";
import { BENCHMARK_PROTOCOL } from "./config.js";

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

  evaluateAt(context, 0.75);
  const first = transformSnapshot(context.actorIndex, context.actorRoot);
  evaluateAt(context, 0.1);
  evaluateAt(context, 0.75);
  const deterministicSeek = transformSnapshot(
    context.actorIndex, context.actorRoot,
  ) === first;
  updateWorldMatrices(context);

  const firstActor = actors[0];
  const secondActor = actors[1] ?? actors[0];
  const secondBefore = secondActor.matrixWorld.clone();
  firstActor.position.x += 1;
  firstActor.updateMatrixWorld(true);
  const independentTransform = secondActor.matrixWorld.equals(secondBefore);

  let pivotSanity;
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
      && pivotSanity.status !== "failed",
    deterministicSeek,
    deterministicSeekScope: "actor_root_and_actors",
    independentTransform,
    pivotSanity,
  };
}

function updateWorldMatrices(context) {
  if (context.scene) context.scene.updateMatrixWorld(true);
  else context.actorRoot.updateMatrixWorld(true);
}
