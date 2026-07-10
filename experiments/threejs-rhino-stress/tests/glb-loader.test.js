import { readFile } from "node:fs/promises";
import { expect, it, vi } from "vitest";
import { loadGlbArrayBuffer } from "../src/glb-loader.js";

it("parses a local ArrayBuffer without URL fetch", async () => {
  const bytes = await readFile(
    new URL("../fixtures/actor-metadata.glb", import.meta.url));
  const input = bytes.buffer.slice(
    bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
  const gltf = await loadGlbArrayBuffer(input);
  expect(gltf.scene.children).toHaveLength(2);
});

it("rejects external resources before fetch", async () => {
  const input = new TextEncoder().encode(JSON.stringify({
    asset: { version: "2.0" },
    buffers: [{ uri: "external.bin", byteLength: 12 }],
    bufferViews: [{ buffer: 0, byteLength: 12 }],
    accessors: [{
      bufferView: 0,
      componentType: 5126,
      count: 1,
      type: "VEC3",
      min: [0, 0, 0],
      max: [0, 0, 0],
    }],
    meshes: [{ primitives: [{ attributes: { POSITION: 0 } }] }],
    nodes: [{ mesh: 0 }],
    scenes: [{ nodes: [0] }],
    scene: 0,
  })).buffer;
  const fetchSpy = vi.spyOn(globalThis, "fetch")
    .mockRejectedValue(new Error("network access blocked by test"));

  try {
    await expect(loadGlbArrayBuffer(input)).rejects.toThrow(
      "External GLB resource URL is not allowed: external.bin");
    expect(fetchSpy).not.toHaveBeenCalled();
  } finally {
    fetchSpy.mockRestore();
  }
});
