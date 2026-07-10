import { readFile } from "node:fs/promises";
import { describe, expect, it } from "vitest";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { buildActorMetadataGlb, sha256Hex } from "../scripts/fixture-builder.mjs";

const fixture = new URL("../fixtures/actor-metadata.glb", import.meta.url);
const checksum = new URL("../fixtures/actor-metadata.sha256", import.meta.url);

describe("metadata fixture", () => {
  it("is byte deterministic", async () => {
    const committed = await readFile(fixture);
    const digest = (await readFile(checksum, "utf8")).trim();
    const generated = buildActorMetadataGlb();
    expect(generated.equals(committed)).toBe(true);
    expect(sha256Hex(generated)).toBe(digest);
  });

  it("survives GLTFLoader with exact actor IDs", async () => {
    const bytes = await readFile(fixture);
    const input = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
    const gltf = await new GLTFLoader().parseAsync(input, "");
    const actors = [];
    gltf.scene.traverse((object) => {
      if (object.userData.actorId) actors.push(object);
    });
    expect(actors.map((actor) => actor.userData.actorId).sort())
      .toEqual(["fixture_actor_a", "fixture_actor_b"]);
    expect(actors.every((actor) => actor.userData.actorSetId === "fixture_set")).toBe(true);
    expect(actors.every((actor) => actor.userData.sourceKind === "fixture")).toBe(true);
    expect(actors[0]).not.toBe(actors[1]);
  });
});
