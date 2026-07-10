import { describe, expect, it } from "vitest";
import * as THREE from "three";
import { vi } from "vitest";
import {
  ACTOR_PRESETS, BENCHMARK_PROTOCOL, DEFAULT_CONFIG,
} from "../src/config.js";
import { evaluateAt } from "../src/animation.js";
import { buildActorIndex } from "../src/actor-index.js";
import { disposeScene } from "../src/disposal.js";
import { addFixedLights, createCamera } from "../src/renderer.js";
import { createSyntheticScene } from "../src/scene-generator.js";

describe("scene generator", () => {
  it("uses the fixed benchmark protocol and verified default actor count", () => {
    expect(BENCHMARK_PROTOCOL).toEqual({
      width: 1920,
      height: 1080,
      pixelRatio: 1,
      warmupFrames: 120,
      measuredFrames: 300,
      trials: 3,
      gpuValidSampleFloor: 270,
    });
    expect(DEFAULT_CONFIG.actorCount).toBe(338);
    expect(createSyntheticScene().actors).toHaveLength(338);
  });

  it("creates stable distinct actors with shared geometry and material", () => {
    const result = createSyntheticScene({ actorCount: 3, geometryOwnership: "shared" });
    expect(result.actors.map((actor) => actor.userData.actorId)).toEqual([
      "synthetic_actor_000000", "synthetic_actor_000001", "synthetic_actor_000002",
    ]);
    expect(new Set(result.actors).size).toBe(3);
    expect(result.actors[0].children[0].geometry)
      .toBe(result.actors[1].children[0].geometry);
    expect(result.actors[0].children[0].material)
      .toBe(result.actors[1].children[0].material);
  });

  it("duplicates geometry only when selected", () => {
    const result = createSyntheticScene({ actorCount: 2, geometryOwnership: "duplicated" });
    expect(result.actors[0].children[0].geometry)
      .not.toBe(result.actors[1].children[0].geometry);
  });

  it("duplicates materials only when selected", () => {
    const result = createSyntheticScene({ actorCount: 2, materialOwnership: "per-actor" });
    const left = result.actors[0].children[0].material;
    const right = result.actors[1].children[0].material;
    expect(left).not.toBe(right);
    expect(left.color.getHex()).toBe(right.color.getHex());
    expect(left.roughness).toBe(right.roughness);
    expect(left.metalness).toBe(right.metalness);
  });

  it("keeps directional-light direction invariant under world rebasing", () => {
    const rebased = new THREE.Scene();
    const large = new THREE.Scene();
    addFixedLights(rebased, [0, 0, 0]);
    addFixedLights(large, [300000, -200000, 20000]);
    const nearLight = rebased.children.find((object) => object.isDirectionalLight);
    const farLight = large.children.find((object) => object.isDirectionalLight);
    const nearDirection = nearLight.position.clone().sub(nearLight.target.position);
    const farDirection = farLight.position.clone().sub(farLight.target.position);

    expect(farDirection.toArray()).toEqual(nearDirection.toArray());
    expect(nearLight.target.parent).toBe(rebased);
    expect(farLight.target.parent).toBe(large);
  });

  it.each(ACTOR_PRESETS)("keeps all %i actors in the fixed-camera frustum", (actorCount) => {
    for (const coordinateMode of ["rebased", "large"]) {
      const generated = createSyntheticScene({ actorCount, coordinateMode });
      generated.actorIndex = buildActorIndex(generated.actorRoot).actors;
      generated.motionGranularity = "group";
      const camera = createCamera(generated.appliedRenderOffset);

      for (const time of [0, 0.5, 1]) {
        evaluateAt(generated, time);
        generated.scene.updateMatrixWorld(true);
        camera.updateMatrixWorld(true);
        const projectionView = new THREE.Matrix4().multiplyMatrices(
          camera.projectionMatrix,
          camera.matrixWorldInverse,
        );
        const frustum = new THREE.Frustum()
          .setFromProjectionMatrix(projectionView);
        const visibleActors = generated.actors.filter((actor) =>
          frustum.intersectsObject(actor.children[0])).length;

        expect(visibleActors).toBe(actorCount);
      }
      disposeScene(generated.scene);
    }
  });

  it.each(ACTOR_PRESETS)(
    "keeps the %i-actor layout inside the fixed benchmark extent",
    (actorCount) => {
      const generated = createSyntheticScene({ actorCount });
      generated.actorRoot.updateMatrixWorld(true);
      const size = new THREE.Box3()
        .setFromObject(generated.actorRoot, true)
        .getSize(new THREE.Vector3());

      expect(size.x).toBeCloseTo(8.7, 6);
      expect(size.z).toBeCloseTo(8.7, 6);
      disposeScene(generated.scene);
    },
  );

  it("keeps camera values fixed across actor tiers", () => {
    const small = createSyntheticScene({ actorCount: 100 });
    const large = createSyntheticScene({ actorCount: 10000 });
    const smallCamera = createCamera(small.appliedRenderOffset);
    const largeCamera = createCamera(large.appliedRenderOffset);

    expect(smallCamera.position.toArray()).toEqual([12, 10, 18]);
    expect(largeCamera.position.toArray()).toEqual([12, 10, 18]);
    expect(largeCamera.projectionMatrix.toArray())
      .toEqual(smallCamera.projectionMatrix.toArray());
    disposeScene(small.scene);
    disposeScene(large.scene);
  });

  it.each([
    ["duplicated geometry", { geometryOwnership: "duplicated" }, THREE.BufferGeometry.prototype],
    ["per-actor material", { materialOwnership: "per-actor" }, THREE.Material.prototype],
  ])("disposes the unused shared template for %s", (_label, overrides, prototype) => {
    const dispose = vi.spyOn(prototype, "dispose");
    try {
      const result = createSyntheticScene({ actorCount: 2, ...overrides });
      const live = new Set();
      result.scene.traverse((object) => {
        if (object.geometry) live.add(object.geometry);
        if (object.material) live.add(object.material);
      });
      const disposedObjects = dispose.mock.contexts;
      expect(disposedObjects.some((object) => !live.has(object))).toBe(true);
    } finally {
      dispose.mockRestore();
    }
  });

  it("separates source, rebase, and applied render origins", () => {
    const rebased = createSyntheticScene({
      actorCount: 1, coordinateMode: "rebased",
    });
    const large = createSyntheticScene({
      actorCount: 1, coordinateMode: "large",
    });
    expect(rebased.sourceOrigin).toEqual([300000, -200000, 20000]);
    expect(rebased.rebaseOrigin).toEqual([300000, -200000, 20000]);
    expect(rebased.appliedRenderOffset).toEqual([0, 0, 0]);
    expect(rebased.actorRoot.position.toArray()).toEqual([0, 0, 0]);
    expect(rebased.contextRoot.position.toArray()).toEqual([0, 0, 0]);
    expect(large.sourceOrigin).toEqual([300000, -200000, 20000]);
    expect(large.rebaseOrigin).toEqual([0, 0, 0]);
    expect(large.appliedRenderOffset).toEqual([300000, -200000, 20000]);
    expect(large.actorRoot.position.toArray()).toEqual([300000, -200000, 20000]);
    expect(large.contextRoot.position.toArray()).toEqual([300000, -200000, 20000]);
  });
});
