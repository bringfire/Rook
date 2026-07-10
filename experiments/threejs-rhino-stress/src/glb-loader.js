import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

export function loadGlbArrayBuffer(input) {
  if (!(input instanceof ArrayBuffer)) {
    throw new TypeError("GLB input must be an ArrayBuffer");
  }
  return new GLTFLoader().parseAsync(input, "");
}
