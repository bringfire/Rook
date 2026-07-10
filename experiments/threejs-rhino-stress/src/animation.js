export function evaluateAt({ actorIndex, actorRoot, motionGranularity }, time) {
  if (!Number.isFinite(time)) throw new Error("time must be finite");

  const entries = [...actorIndex.entries()]
    .sort(([left], [right]) => left.localeCompare(right));

  if (motionGranularity === "group") {
    entries.forEach(([, actor]) => restore(actor));
    actorRoot.rotation.y = Math.sin(time * 0.7) * 0.2;
  } else {
    actorRoot.rotation.set(0, 0, 0);
    entries.forEach(([actorId, actor], index) => {
      restore(actor);
      const phase = stablePhase(actorId);
      actor.position.y += Math.sin(time * 1.3 + phase)
        * (0.12 + (index % 5) * 0.01);
      actor.rotation.y = Math.sin(time * 0.5 + phase) * 0.15;
    });
  }

  actorRoot.updateMatrixWorld(true);
}

export function transformSnapshot(index) {
  return JSON.stringify([...index.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([id, actor]) => [
      id,
      ...actor.position.toArray(),
      ...actor.quaternion.toArray(),
      ...actor.scale.toArray(),
    ].map((value) => (
      typeof value === "number" ? Number(value.toFixed(9)) : value
    ))));
}

function restore(actor) {
  const base = actor.userData.basePosition ?? actor.position.toArray();
  actor.userData.basePosition = [...base];
  actor.position.fromArray(base);
  actor.rotation.set(0, 0, 0);
}

function stablePhase(value) {
  let hash = 2166136261;
  for (const character of value) {
    hash ^= character.codePointAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return ((hash >>> 0) / 0xffffffff) * Math.PI * 2;
}
