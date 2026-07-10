import * as THREE from "three";
import { BENCHMARK_PROTOCOL } from "./config.js";

export const PRECISION_SAMPLE_TIMES = Object.freeze([0, 0.5, 1]);

export function comparePixelBuffers(left, right) {
  if (!left.length || left.length !== right.length) {
    throw new Error("pixel buffers must have equal nonzero length");
  }
  let sum = 0;
  let maxChannelError = 0;
  let differing = 0;
  for (let index = 0; index < left.length; index += 1) {
    const difference = Math.abs(left[index] - right[index]);
    sum += difference;
    maxChannelError = Math.max(maxChannelError, difference);
    if (difference > 2) differing += 1;
  }
  const meanAbsoluteChannelError = sum / left.length;
  const differingChannelRatio = differing / left.length;
  return {
    pass: meanAbsoluteChannelError <= 0.25 && differingChannelRatio <= 0.001,
    meanAbsoluteChannelError,
    maxChannelError,
    differingChannelRatio,
  };
}

export function readScenePixels(renderer, scene, camera) {
  const target = new THREE.WebGLRenderTarget(
    BENCHMARK_PROTOCOL.width,
    BENCHMARK_PROTOCOL.height,
  );
  const previous = renderer.getRenderTarget();
  const previousCubeFace = renderer.getActiveCubeFace();
  const previousMipmapLevel = renderer.getActiveMipmapLevel();
  const pixels = new Uint8Array(
    BENCHMARK_PROTOCOL.width * BENCHMARK_PROTOCOL.height * 4,
  );

  try {
    renderer.setRenderTarget(target);
    renderer.render(scene, camera);
    renderer.readRenderTargetPixels(
      target,
      0,
      0,
      BENCHMARK_PROTOCOL.width,
      BENCHMARK_PROTOCOL.height,
      pixels,
    );
    return pixels;
  } finally {
    renderer.setRenderTarget(previous, previousCubeFace, previousMipmapLevel);
    target.dispose();
  }
}
