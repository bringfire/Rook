import { describe, expect, it } from "vitest";
import { BENCHMARK_PROTOCOL, DEFAULT_CONFIG } from "../src/config.js";
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
    const result = createSyntheticScene({ actorCount: 2, materialOwnership: "duplicated" });
    expect(result.actors[0].children[0].material)
      .not.toBe(result.actors[1].children[0].material);
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
