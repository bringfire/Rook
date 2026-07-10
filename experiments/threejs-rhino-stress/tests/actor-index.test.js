import * as THREE from "three";
import { describe, expect, it } from "vitest";
import { buildActorIndex } from "../src/actor-index.js";

describe("actor index", () => {
  it("reports duplicate and malformed durable IDs", () => {
    const root = new THREE.Group();
    for (let index = 0; index < 2; index += 1) {
      const actor = new THREE.Group();
      actor.userData.actorId = "duplicate";
      root.add(actor);
    }
    const malformed = new THREE.Group();
    malformed.userData.actorId = " bad id ";
    root.add(malformed);

    const result = buildActorIndex(root);

    expect(result.duplicates).toEqual([{
      actorId: "duplicate",
      firstObject: "Group",
      duplicateObject: "Group",
    }]);
    expect(result.malformedIds).toEqual([{
      objectName: "Group",
      value: " bad id ",
      reason: "invalid_format",
    }]);
  });

  it("indexes valid IDs and counts actor nodes or orphan meshes without IDs", () => {
    const root = new THREE.Group();
    const actor = new THREE.Group();
    actor.name = "NamedActor";
    actor.userData.actorId = "actor:valid-1";
    actor.add(new THREE.Mesh());
    root.add(actor);

    const missingActor = new THREE.Group();
    missingActor.userData.actorNode = true;
    root.add(missingActor);
    root.add(new THREE.Mesh());

    const result = buildActorIndex(root);

    expect([...result.actors]).toEqual([["actor:valid-1", actor]]);
    expect(result.actorIds).toEqual(["actor:valid-1"]);
    expect(result.missingActorId).toBe(2);
    expect(result.duplicates).toEqual([]);
    expect(result.malformedIds).toEqual([]);
  });

  it("serializes stable sorted actor IDs while retaining the runtime Map", () => {
    const root = new THREE.Group();
    ["actor_z", "actor_a"].forEach((actorId) => {
      const actor = new THREE.Group();
      actor.userData.actorId = actorId;
      root.add(actor);
    });

    const result = buildActorIndex(root);
    const copied = JSON.parse(JSON.stringify(result));

    expect(result.actors).toBeInstanceOf(Map);
    expect(copied.actors).toEqual({});
    expect(copied.actorIds).toEqual(["actor_a", "actor_z"]);
  });
});
