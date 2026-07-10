import { describe, expect, it } from "vitest";
import * as THREE from "three";
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

  it("is transform-only and leaves world traversal to its caller", () => {
    const context = createContext();
    let traversals = 0;
    context.actorRoot.traverse((object) => {
      const original = object.updateMatrixWorld.bind(object);
      object.updateMatrixWorld = (...args) => {
        traversals += 1;
        return original(...args);
      };
    });

    evaluateAt(context, 0.5);

    expect(traversals).toBe(0);
  });

  it("preserves imported root and actor base transforms across seek history", () => {
    const root = new THREE.Group();
    root.position.set(10, 20, 30);
    root.quaternion.setFromEuler(new THREE.Euler(0.2, 0.3, 0.4));
    root.scale.set(2, 3, 4);
    const actor = new THREE.Group();
    actor.userData.actorId = "imported_actor";
    actor.position.set(1, 2, 3);
    actor.quaternion.setFromEuler(new THREE.Euler(-0.3, 0.1, 0.2));
    actor.scale.set(0.5, 1.5, 2.5);
    root.add(actor);
    const context = {
      actorRoot: root,
      actorIndex: new Map([["imported_actor", actor]]),
      motionGranularity: "individual",
    };
    const rootBase = snapshotObject(root);
    const actorBase = snapshotObject(actor);

    evaluateAt(context, 0.8);
    const expected = transformSnapshot(context.actorIndex);
    evaluateAt(context, 0.1);
    evaluateAt(context, 0.8);

    expect(transformSnapshot(context.actorIndex)).toBe(expected);
    expect(root.position.toArray()).toEqual(rootBase.position);
    expect(root.quaternion.toArray()).toEqual(rootBase.quaternion);
    expect(root.scale.toArray()).toEqual(rootBase.scale);
    expect(actor.scale.toArray()).toEqual(actorBase.scale);
    expect(actor.position.x).toBe(actorBase.position[0]);
    expect(actor.position.z).toBe(actorBase.position[2]);

    context.motionGranularity = "group";
    evaluateAt(context, 0.6);
    expect(actor.position.toArray()).toEqual(actorBase.position);
    expect(actor.quaternion.toArray()).toEqual(actorBase.quaternion);
    expect(actor.scale.toArray()).toEqual(actorBase.scale);
    expect(root.position.toArray()).toEqual(rootBase.position);
    expect(root.scale.toArray()).toEqual(rootBase.scale);
    expect(root.quaternion.toArray()).not.toEqual([0, 0, 0, 1]);
  });

  it("rejects non-finite sampled transforms instead of serializing null", () => {
    const context = createContext();
    const actor = context.actors[0];
    actor.userData.basePosition[1] = Number.NaN;

    expect(() => evaluateAt(context, 0.5)).toThrow(
      /non-finite transform.*synthetic_actor_000000.*0.5/,
    );
    actor.position.y = Number.NaN;
    expect(() => transformSnapshot(context.actorIndex)).toThrow(
      /non-finite transform.*synthetic_actor_000000/,
    );
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

function snapshotObject(object) {
  return {
    position: object.position.toArray(),
    quaternion: object.quaternion.toArray(),
    scale: object.scale.toArray(),
  };
}
