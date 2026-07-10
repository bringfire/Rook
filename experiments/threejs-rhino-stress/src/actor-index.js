export function buildActorIndex(root) {
  const actors = new Map();
  let missingActorId = 0;
  const duplicates = [];
  const malformedIds = [];
  const pattern = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/;

  root.traverse((object) => {
    const hasActorId = Object.prototype.hasOwnProperty.call(
      object.userData ?? {},
      "actorId",
    );
    const actorId = object.userData?.actorId;

    if (hasActorId) {
      if (typeof actorId !== "string" || !pattern.test(actorId)) {
        malformedIds.push({
          objectName: object.name || object.type,
          value: actorId,
          reason: "invalid_format",
        });
      } else if (actors.has(actorId)) {
        const first = actors.get(actorId);
        duplicates.push({
          actorId,
          firstObject: first.name || first.type,
          duplicateObject: object.name || object.type,
        });
      } else {
        actors.set(actorId, object);
      }
    } else if (
      object.userData?.actorNode === true
      || (object.isMesh && !hasActorAncestor(object))
    ) {
      missingActorId += 1;
    }
  });

  return {
    actors,
    actorIds: [...actors.keys()].sort((left, right) => left.localeCompare(right)),
    missingActorId,
    duplicates,
    malformedIds,
  };
}

function hasActorAncestor(object) {
  let cursor = object.parent;
  while (cursor) {
    if (cursor.userData?.actorId) return true;
    cursor = cursor.parent;
  }
  return false;
}
