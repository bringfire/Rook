import * as THREE from "three";
import { BENCHMARK_PROTOCOL } from "./config.js";

export function createFixedRenderer(canvas) {
  const renderer = new THREE.WebGLRenderer({
    canvas,
    antialias: true,
    powerPreference: "high-performance",
  });
  renderer.setPixelRatio(1);
  renderer.setSize(BENCHMARK_PROTOCOL.width, BENCHMARK_PROTOCOL.height, false);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.NoToneMapping;
  renderer.setClearColor(0x101722, 1);
  if (!renderer.capabilities.isWebGL2) {
    throw new Error("WebGL2 is required for benchmark runs");
  }
  return renderer;
}

export function createCamera(offset = [0, 0, 0]) {
  const camera = new THREE.PerspectiveCamera(
    35,
    BENCHMARK_PROTOCOL.width / BENCHMARK_PROTOCOL.height,
    0.1,
    10000,
  );
  camera.position.set(offset[0] + 12, offset[1] + 10, offset[2] + 18);
  camera.lookAt(offset[0] + 6, offset[1], offset[2] + 6);
  camera.updateMatrixWorld(true);
  return camera;
}

export function addFixedLights(scene, offset = [0, 0, 0]) {
  scene.add(new THREE.AmbientLight(0xffffff, 1.1));
  const light = new THREE.DirectionalLight(0xffffff, 2.2);
  light.position.set(offset[0] + 10, offset[1] + 18, offset[2] + 8);
  scene.add(light);
}
