import { Quaternion, Vector3 } from "three";

const baseTransforms = new WeakMap();
const Y_AXIS = new Vector3(0, 1, 0);
const yawQuaternion = new Quaternion();

export function evaluateAt({ actorIndex, actorRoot, motionGranularity }, time) {
  if (!Number.isFinite(time)) throw new Error("time must be finite");

  const entries = [...actorIndex.entries()]
    .sort(([left], [right]) => left.localeCompare(right));

  if (motionGranularity === "group") {
    entries.forEach(([, actor]) => restore(actor));
    restore(actorRoot);
    composeYaw(actorRoot, Math.sin(time * 0.7) * 0.2);
  } else {
    restore(actorRoot);
    entries.forEach(([actorId, actor], index) => {
      restore(actor);
      const phase = stablePhase(actorId);
      actor.position.y += Math.sin(time * 1.3 + phase)
        * (0.12 + (index % 5) * 0.01);
      composeYaw(actor, Math.sin(time * 0.5 + phase) * 0.15);
    });
  }

  validateObjectTransform(actorRoot, "actorRoot", time);
  entries.forEach(([actorId, actor]) => {
    validateObjectTransform(actor, actorId, time);
  });
}

export function transformSnapshot(index) {
  return JSON.stringify([...index.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([id, actor]) => {
      validateObjectTransform(actor, id);
      return [
        id,
        ...actor.position.toArray(),
        ...actor.quaternion.toArray(),
        ...actor.scale.toArray(),
      ].map((value) => (
        typeof value === "number" ? Number(value.toFixed(9)) : value
      ));
    }));
}

function restore(actor) {
  const base = getBaseTransform(actor);
  actor.position.copy(base.position);
  actor.quaternion.copy(base.quaternion);
  actor.scale.copy(base.scale);
}

function getBaseTransform(actor) {
  let base = baseTransforms.get(actor);
  if (base) return base;
  const declaredPosition = actor.userData?.basePosition;
  base = {
    position: Array.isArray(declaredPosition)
      ? new Vector3().fromArray(declaredPosition)
      : actor.position.clone(),
    quaternion: actor.quaternion.clone(),
    scale: actor.scale.clone(),
  };
  baseTransforms.set(actor, base);
  return base;
}

function composeYaw(actor, angle) {
  actor.quaternion.multiply(yawQuaternion.setFromAxisAngle(Y_AXIS, angle));
}

function validateObjectTransform(actor, actorId, time) {
  if (
    Number.isFinite(actor.position.x)
    && Number.isFinite(actor.position.y)
    && Number.isFinite(actor.position.z)
    && Number.isFinite(actor.quaternion.x)
    && Number.isFinite(actor.quaternion.y)
    && Number.isFinite(actor.quaternion.z)
    && Number.isFinite(actor.quaternion.w)
    && Number.isFinite(actor.scale.x)
    && Number.isFinite(actor.scale.y)
    && Number.isFinite(actor.scale.z)
  ) return;
  const suffix = time === undefined ? "" : ` at time ${time}`;
  throw new Error(`non-finite transform for actor ${actorId}${suffix}`);
}

function stablePhase(value) {
  let hash = 2166136261;
  for (const character of value) {
    hash ^= character.codePointAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return ((hash >>> 0) / 0xffffffff) * Math.PI * 2;
}
