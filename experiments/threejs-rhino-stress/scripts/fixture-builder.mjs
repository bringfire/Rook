import { createHash } from "node:crypto";

const pad4 = (length) => (4 - (length % 4)) % 4;
const u32 = (value) => {
  const result = Buffer.alloc(4);
  result.writeUInt32LE(value);
  return result;
};

export const sha256Hex = (bytes) =>
  createHash("sha256").update(bytes).digest("hex");

export function buildActorMetadataGlb() {
  const positions = Buffer.alloc(36);
  [[-0.5, 0, 0], [0.5, 0, 0], [0, 1, 0]].forEach((point, pointIndex) => {
    point.forEach((value, axis) =>
      positions.writeFloatLE(value, pointIndex * 12 + axis * 4));
  });
  const indices = Buffer.alloc(8);
  [0, 1, 2].forEach((value, index) => indices.writeUInt16LE(value, index * 2));
  const binary = Buffer.concat([positions, indices]);
  const gltf = {
    asset: { version: "2.0", generator: "Rook actor fixture" },
    scene: 0,
    scenes: [{ nodes: [0, 1] }],
    nodes: [
      { name: "Actor A", mesh: 0, translation: [-1, 0, 0],
        extras: { actorId: "fixture_actor_a", actorSetId: "fixture_set", sourceKind: "fixture" } },
      { name: "Actor B", mesh: 0, translation: [1, 0, 0],
        extras: { actorId: "fixture_actor_b", actorSetId: "fixture_set", sourceKind: "fixture" } },
    ],
    meshes: [{ primitives: [{ attributes: { POSITION: 0 }, indices: 1, mode: 4 }] }],
    buffers: [{ byteLength: binary.length }],
    bufferViews: [
      { buffer: 0, byteOffset: 0, byteLength: 36, target: 34962 },
      { buffer: 0, byteOffset: 36, byteLength: 6, target: 34963 },
    ],
    accessors: [
      { bufferView: 0, componentType: 5126, count: 3, type: "VEC3",
        min: [-0.5, 0, 0], max: [0.5, 1, 0] },
      { bufferView: 1, componentType: 5123, count: 3, type: "SCALAR",
        min: [0], max: [2] },
    ],
  };
  const source = Buffer.from(JSON.stringify(gltf));
  const json = Buffer.concat([source, Buffer.alloc(pad4(source.length), 0x20)]);
  const bin = Buffer.concat([binary, Buffer.alloc(pad4(binary.length))]);
  const length = 12 + 8 + json.length + 8 + bin.length;
  return Buffer.concat([
    Buffer.from("glTF"), u32(2), u32(length),
    u32(json.length), Buffer.from("JSON"), json,
    u32(bin.length), Buffer.from([0x42, 0x49, 0x4e, 0]), bin,
  ]);
}
