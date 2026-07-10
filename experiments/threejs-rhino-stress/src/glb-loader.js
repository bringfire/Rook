import { LoadingManager } from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

export function loadGlbArrayBuffer(input) {
  if (!(input instanceof ArrayBuffer)) {
    throw new TypeError("GLB input must be an ArrayBuffer");
  }
  const manager = new LoadingManager();
  manager.setURLModifier((url) => {
    if (/^(data|blob):/i.test(url)) return url;
    throw new Error("External GLB resource URL is not allowed: " + url);
  });
  return new GLTFLoader(manager).parseAsync(input, "");
}
