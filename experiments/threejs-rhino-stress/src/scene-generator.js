import * as THREE from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import { DEFAULT_CONFIG, LARGE_WORLD_OFFSET } from "./config.js";

export function createSyntheticScene(overrides = {}) {
  const config = { ...DEFAULT_CONFIG, ...overrides };
  const scene = new THREE.Scene();
  const actorRoot = new THREE.Group();
  const contextRoot = new THREE.Group();
  actorRoot.name = "ActorSet";
  contextRoot.name = "StaticContext";
  scene.add(contextRoot, actorRoot);

  const sourceOrigin = new THREE.Vector3(...LARGE_WORLD_OFFSET);
  const appliedRenderOffset = config.coordinateMode === "large"
    ? sourceOrigin.clone()
    : new THREE.Vector3();
  const rebaseOrigin = config.coordinateMode === "rebased"
    ? sourceOrigin.clone()
    : new THREE.Vector3();
  actorRoot.position.copy(appliedRenderOffset);
  contextRoot.position.copy(appliedRenderOffset);

  const segments = Math.max(1, Number(config.geometryDensity));
  const sharedGeometry = new THREE.BoxGeometry(
    0.6, 0.6, 0.6, segments, segments, segments,
  );
  const sharedMaterial = new THREE.MeshStandardMaterial({
    color: 0x4aa3ff,
    roughness: 0.65,
    metalness: 0.05,
  });
  const actors = [];
  const columns = Math.ceil(Math.sqrt(config.actorCount));

  for (let index = 0; index < config.actorCount; index += 1) {
    const actor = new THREE.Group();
    actor.userData = {
      actorId: "synthetic_actor_" + String(index).padStart(6, "0"),
      actorSetId: "synthetic_set",
      sourceKind: "synthetic",
      actorNode: true,
    };
    actor.position.set(
      (index % columns) * 0.9,
      0,
      Math.floor(index / columns) * 0.9,
    );
    actor.userData.basePosition = actor.position.toArray();

    const geometry = config.geometryOwnership === "shared"
      ? sharedGeometry
      : sharedGeometry.clone();
    const material = config.materialOwnership === "shared"
      ? sharedMaterial
      : new THREE.MeshStandardMaterial({ color: 0x4aa3ff + (index % 32) });
    actor.add(new THREE.Mesh(geometry, material));
    actorRoot.add(actor);
    actors.push(actor);
  }

  if (config.geometryOwnership !== "shared") sharedGeometry.dispose();
  if (config.materialOwnership !== "shared") sharedMaterial.dispose();

  buildContext(contextRoot, config.contextMode);
  return {
    scene,
    actorRoot,
    contextRoot,
    actors,
    config,
    sourceKind: "synthetic",
    sourceOrigin: sourceOrigin.toArray(),
    rebaseOrigin: rebaseOrigin.toArray(),
    appliedRenderOffset: appliedRenderOffset.toArray(),
  };
}

function buildContext(root, mode) {
  const base = new THREE.BoxGeometry(2, 0.15, 2);
  const materials = [
    new THREE.MeshStandardMaterial({ color: 0x7a8291 }),
    new THREE.MeshStandardMaterial({ color: 0x555d6b }),
  ];
  const entries = Array.from({ length: 24 }, (_, index) => ({
    material: index % 2,
    matrix: new THREE.Matrix4().makeTranslation(
      (index % 6) * 2.2,
      -0.5,
      Math.floor(index / 6) * 2.2,
    ),
  }));

  if (mode === "merged") {
    for (let material = 0; material < materials.length; material += 1) {
      const parts = entries
        .filter((entry) => entry.material === material)
        .map((entry) => base.clone().applyMatrix4(entry.matrix));
      root.add(new THREE.Mesh(mergeGeometries(parts, false), materials[material]));
      parts.forEach((part) => part.dispose());
    }
    base.dispose();
  } else {
    entries.forEach((entry) => {
      const mesh = new THREE.Mesh(base, materials[entry.material]);
      mesh.applyMatrix4(entry.matrix);
      root.add(mesh);
    });
  }
}

export function countScene(root) {
  const geometries = new Set();
  const materials = new Set();
  let nodes = 0;
  let actors = 0;
  let meshes = 0;
  let triangles = 0;

  root.traverse((object) => {
    nodes += 1;
    if (object.userData?.actorId) actors += 1;
    if (!object.isMesh) return;
    meshes += 1;
    geometries.add(object.geometry);
    (Array.isArray(object.material) ? object.material : [object.material])
      .forEach((material) => materials.add(material));
    triangles += (
      object.geometry.index?.count
      ?? object.geometry.attributes.position.count
    ) / 3;
  });

  return {
    nodes,
    actors,
    geometries: geometries.size,
    meshes,
    materials: materials.size,
    triangles,
  };
}
