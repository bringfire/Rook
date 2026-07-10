import { describe, expect, it } from "vitest";
import { buildActorIndex } from "../src/actor-index.js";
import { evaluateAt, transformSnapshot } from "../src/animation.js";
import { createSyntheticScene } from "../src/scene-generator.js";

function createContext(motionGranularity = "individual") {
  const generated = createSyntheticScene({ actorCount: 4 });
  const actorIndex = buildActorIndex(generated.scene).actors;
  return { ...generated, actorIndex, motionGranularity };
}

describe("absolute-time animation", () => {
  it("is independent of seek history", () => {
    const context = createContext();

    evaluateAt(context, 0.75);
    const expected = transformSnapshot(context.actorIndex);
    evaluateAt(context, 0.1);
    evaluateAt(context, 0.75);

    expect(transformSnapshot(context.actorIndex)).toBe(expected);
  });

  it("restores actor transforms when switching to group motion", () => {
    const context = createContext();
    evaluateAt(context, 0.75);

    context.motionGranularity = "group";
    evaluateAt(context, 0.2);

    expect(context.actors.map((actor) => actor.position.toArray()))
      .toEqual(context.actors.map((actor) => actor.userData.basePosition));
    expect(context.actors.every((actor) => actor.rotation.y === 0)).toBe(true);
    expect(context.actorRoot.rotation.y).toBeCloseTo(Math.sin(0.2 * 0.7) * 0.2);
  });

  it("rejects non-finite seek times", () => {
    const context = createContext();
    expect(() => evaluateAt(context, Number.NaN)).toThrow("time must be finite");
    expect(() => evaluateAt(context, Number.POSITIVE_INFINITY))
      .toThrow("time must be finite");
  });
});
