import { readFile } from "node:fs/promises";
import { expect, it } from "vitest";
import { loadGlbArrayBuffer } from "../src/glb-loader.js";

it("parses a local ArrayBuffer without URL fetch", async () => {
  const bytes = await readFile(
    new URL("../fixtures/actor-metadata.glb", import.meta.url));
  const input = bytes.buffer.slice(
    bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
  const gltf = await loadGlbArrayBuffer(input);
  expect(gltf.scene.children).toHaveLength(2);
});
