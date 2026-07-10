import * as THREE from "three";
import { expect, it, vi } from "vitest";
import { disposeScene } from "../src/disposal.js";
import { createSyntheticScene } from "../src/scene-generator.js";

it("disposes shared resources once", () => {
  const generated = createSyntheticScene({ actorCount: 3 });
  const geometry = generated.actors[0].children[0].geometry;
  const material = generated.actors[0].children[0].material;
  const texture = new THREE.Texture();
  material.map = texture;
  const geometrySpy = vi.spyOn(geometry, "dispose");
  const materialSpy = vi.spyOn(material, "dispose");
  const textureSpy = vi.spyOn(texture, "dispose");

  const counts = disposeScene(generated.scene);

  expect(geometrySpy).toHaveBeenCalledTimes(1);
  expect(materialSpy).toHaveBeenCalledTimes(1);
  expect(textureSpy).toHaveBeenCalledTimes(1);
  expect(counts).toEqual({ geometries: 2, materials: 3, textures: 1 });
  expect(generated.scene.children).toEqual([]);
});
