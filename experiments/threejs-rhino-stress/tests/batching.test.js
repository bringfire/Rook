import { expect, it } from "vitest";
import { countScene, createSyntheticScene } from "../src/scene-generator.js";

it("merges static context without changing triangle or material counts", () => {
  const plain = countScene(createSyntheticScene({
    actorCount: 2, contextMode: "unbatched",
  }).contextRoot);
  const merged = countScene(createSyntheticScene({
    actorCount: 2, contextMode: "merged",
  }).contextRoot);
  expect(merged.triangles).toBe(plain.triangles);
  expect(merged.materials).toBe(plain.materials);
  expect(merged.meshes).toBeLessThan(plain.meshes);
});
