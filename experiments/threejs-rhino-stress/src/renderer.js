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

export function createCamera(offset = [0, 0, 0], root = null) {
  const camera = new THREE.PerspectiveCamera(
    35,
    BENCHMARK_PROTOCOL.width / BENCHMARK_PROTOCOL.height,
    0.1,
    10000,
  );
  const target = new THREE.Vector3(
    offset[0] + 6, offset[1], offset[2] + 6,
  );
  let distance = Math.sqrt(12 ** 2 + 10 ** 2 + 18 ** 2);
  if (root) {
    root.updateMatrixWorld(true);
    const bounds = new THREE.Box3().setFromObject(root, true);
    if (!bounds.isEmpty()) {
      const sphere = bounds.getBoundingSphere(new THREE.Sphere());
      target.copy(sphere.center);
      const verticalFov = THREE.MathUtils.degToRad(camera.fov);
      const horizontalFov = 2 * Math.atan(
        Math.tan(verticalFov / 2) * camera.aspect,
      );
      const limitingFov = Math.min(verticalFov, horizontalFov);
      distance = (sphere.radius / Math.sin(limitingFov / 2)) * 1.12;
      camera.far = Math.max(10000, distance + sphere.radius * 4);
      camera.updateProjectionMatrix();
    }
  }
  const direction = new THREE.Vector3(6, 10, 12).normalize();
  camera.position.copy(target).addScaledVector(direction, distance);
  camera.lookAt(target);
  camera.updateMatrixWorld(true);
  camera.userData.frameTarget = target.toArray();
  camera.userData.frameDistance = distance;
  return camera;
}

export function addFixedLights(scene, offset = [0, 0, 0]) {
  scene.add(new THREE.AmbientLight(0xffffff, 1.1));
  const light = new THREE.DirectionalLight(0xffffff, 2.2);
  light.position.set(offset[0] + 10, offset[1] + 18, offset[2] + 8);
  light.target.position.set(offset[0], offset[1], offset[2]);
  scene.add(light.target, light);
}
