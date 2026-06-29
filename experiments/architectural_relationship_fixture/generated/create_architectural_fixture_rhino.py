from __future__ import annotations

import json

import Rhino
import scriptcontext as sc


SOURCE = "architectural_relationship_fixture"
REVISION = "a001"
POSE = "architectural_reference"
LAYER_NAME = "Rook_ArchitecturalRelationshipFixture"

OBJECTS = [
    {"object_id": "column_01", "object_kind": "column", "name": "Column 01"},
    {"object_id": "slab_01", "object_kind": "slab", "name": "Slab 01"},
    {"object_id": "wall_01", "object_kind": "wall", "name": "Wall 01"},
    {"object_id": "door_01", "object_kind": "door", "name": "Door 01"},
    {"object_id": "opening_01", "object_kind": "opening", "name": "Opening 01"},
    {"object_id": "duct_01", "object_kind": "duct", "name": "Duct 01"},
    {"object_id": "space_01", "object_kind": "space", "name": "Space 01"},
]

FEATURES = [
    {
        "feature_id": "column_01.top_point",
        "owner_id": "column_01",
        "owner_kind": "column",
        "feature_kind": "point",
        "role": "top_point",
        "point": [0.0, 0.0, 3.0],
    },
    {
        "feature_id": "slab_01.underside_region",
        "owner_id": "slab_01",
        "owner_kind": "slab",
        "feature_kind": "region",
        "role": "underside_region",
        "point": [0.0, 0.0, 3.0],
    },
    {
        "feature_id": "door_01.body",
        "owner_id": "door_01",
        "owner_kind": "door",
        "feature_kind": "body",
        "role": "body",
        "point": [2.0, -0.1, 1.0],
    },
    {
        "feature_id": "wall_01.host_region",
        "owner_id": "wall_01",
        "owner_kind": "wall",
        "feature_kind": "region",
        "role": "host_region",
        "point": [2.0, 0.0, 1.0],
    },
    {
        "feature_id": "opening_01.profile",
        "owner_id": "opening_01",
        "owner_kind": "opening",
        "feature_kind": "profile",
        "role": "profile",
        "point": [2.0, 0.02, 1.0],
    },
    {
        "feature_id": "wall_01.opening_region",
        "owner_id": "wall_01",
        "owner_kind": "wall",
        "feature_kind": "region",
        "role": "opening_region",
        "point": [2.0, 0.0, 1.0],
    },
    {
        "feature_id": "duct_01.centerline",
        "owner_id": "duct_01",
        "owner_kind": "duct",
        "feature_kind": "line",
        "role": "centerline",
        "point": [4.0, 0.0, 2.2],
    },
    {
        "feature_id": "wall_01.penetration_region",
        "owner_id": "wall_01",
        "owner_kind": "wall",
        "feature_kind": "region",
        "role": "penetration_region",
        "point": [4.0, 0.0, 2.2],
    },
    {
        "feature_id": "space_01.boundary",
        "owner_id": "space_01",
        "owner_kind": "space",
        "feature_kind": "boundary",
        "role": "boundary",
        "point": [5.5, 0.0, 1.2],
    },
    {
        "feature_id": "wall_01.inner_face",
        "owner_id": "wall_01",
        "owner_kind": "wall",
        "feature_kind": "face",
        "role": "inner_face",
        "point": [5.5, 0.0, 1.2],
    },
]

RELATIONSHIPS = [
    {
        "relationship_id": "column_01.top_point_supports_slab_01.underside_region",
        "relationship_type": "supports",
        "from_feature": "column_01.top_point",
        "to_feature": "slab_01.underside_region",
        "contact_kind": "point_to_region",
        "provenance": "authored_architectural_fixture",
        "status": "accepted",
    },
    {
        "relationship_id": "door_01.body_hosted_by_wall_01.host_region",
        "relationship_type": "hosted_by",
        "from_feature": "door_01.body",
        "to_feature": "wall_01.host_region",
        "contact_kind": "body_to_region",
        "provenance": "authored_architectural_fixture",
        "status": "accepted",
    },
    {
        "relationship_id": "opening_01.profile_voids_wall_01.opening_region",
        "relationship_type": "voids",
        "from_feature": "opening_01.profile",
        "to_feature": "wall_01.opening_region",
        "contact_kind": "profile_to_region",
        "provenance": "authored_architectural_fixture",
        "status": "accepted",
    },
    {
        "relationship_id": "duct_01.centerline_penetrates_wall_01.penetration_region",
        "relationship_type": "penetrates",
        "from_feature": "duct_01.centerline",
        "to_feature": "wall_01.penetration_region",
        "contact_kind": "line_to_region",
        "provenance": "authored_architectural_fixture",
        "status": "accepted",
    },
    {
        "relationship_id": "space_01.boundary_bounded_by_wall_01.inner_face",
        "relationship_type": "bounded_by",
        "from_feature": "space_01.boundary",
        "to_feature": "wall_01.inner_face",
        "contact_kind": "boundary_to_face",
        "provenance": "authored_architectural_fixture",
        "status": "accepted",
    },
]


def _ensure_layer(name: str) -> int:
    layer_index = sc.doc.Layers.FindByFullPath(name, -1)
    if layer_index >= 0:
        return layer_index
    layer = Rhino.DocObjects.Layer()
    layer.Name = name
    return sc.doc.Layers.Add(layer)


def _clear_layer(layer_index: int) -> int:
    layer = sc.doc.Layers[layer_index]
    objects = sc.doc.Objects.FindByLayer(layer)
    cleared = 0
    if objects:
        for rhino_object in list(objects):
            if sc.doc.Objects.Delete(rhino_object, True):
                cleared += 1
    return cleared


def _attrs(layer_index: int, name: str) -> Rhino.DocObjects.ObjectAttributes:
    attrs = Rhino.DocObjects.ObjectAttributes()
    attrs.LayerIndex = layer_index
    attrs.Name = name
    return attrs


def _stamp(object_id, values: dict[str, str]) -> None:
    rhino_object = sc.doc.Objects.FindId(object_id)
    if rhino_object is None:
        raise RuntimeError("object not found: {}".format(object_id))
    for key, value in values.items():
        rhino_object.Attributes.SetUserString(key, value)
    rhino_object.CommitChanges()


def _base_attrs(visual_type: str) -> dict[str, str]:
    return {
        "rook.graph.source": SOURCE,
        "rook.graph.revision": REVISION,
        "rook.graph.pose": POSE,
        "rook.graph.visual_type": visual_type,
    }


def _box(corner1, corner2) -> Rhino.Geometry.Brep:
    bbox = Rhino.Geometry.BoundingBox(
        Rhino.Geometry.Point3d(*corner1),
        Rhino.Geometry.Point3d(*corner2),
    )
    return Rhino.Geometry.Brep.CreateFromBox(bbox)


def _feature_by_id(feature_id: str) -> dict:
    for feature in FEATURES:
        if feature["feature_id"] == feature_id:
            return feature
    raise RuntimeError("feature not found: {}".format(feature_id))


def _object_geometry(object_id: str):
    if object_id == "column_01":
        return _box([-0.15, -0.15, 0.0], [0.15, 0.15, 3.0])
    if object_id == "slab_01":
        return _box([-1.0, -1.0, 3.0], [6.5, 1.0, 3.25])
    if object_id == "wall_01":
        return _box([1.0, -0.05, 0.0], [6.0, 0.05, 3.0])
    if object_id == "door_01":
        return _box([1.7, -0.08, 0.0], [2.3, -0.02, 2.1])
    if object_id == "opening_01":
        return Rhino.Geometry.Rectangle3d(
            Rhino.Geometry.Plane.WorldZX,
            Rhino.Geometry.Interval(0.0, 2.1),
            Rhino.Geometry.Interval(1.7, 2.3),
        ).ToNurbsCurve()
    if object_id == "duct_01":
        return Rhino.Geometry.LineCurve(
            Rhino.Geometry.Point3d(3.5, -0.8, 2.2),
            Rhino.Geometry.Point3d(4.5, 0.8, 2.2),
        )
    if object_id == "space_01":
        polyline = Rhino.Geometry.Polyline(
            [
                Rhino.Geometry.Point3d(1.0, -1.0, 0.02),
                Rhino.Geometry.Point3d(6.0, -1.0, 0.02),
                Rhino.Geometry.Point3d(6.0, 0.0, 0.02),
                Rhino.Geometry.Point3d(1.0, 0.0, 0.02),
                Rhino.Geometry.Point3d(1.0, -1.0, 0.02),
            ]
        )
        return polyline.ToNurbsCurve()
    raise RuntimeError("object geometry not found: {}".format(object_id))


def _add_geometry(geometry, attrs):
    if isinstance(geometry, Rhino.Geometry.Brep):
        return sc.doc.Objects.AddBrep(geometry, attrs)
    if isinstance(geometry, Rhino.Geometry.Curve):
        return sc.doc.Objects.AddCurve(geometry, attrs)
    raise RuntimeError("unsupported geometry type: {}".format(type(geometry)))


def main() -> dict:
    layer_index = _ensure_layer(LAYER_NAME)
    cleared_count = _clear_layer(layer_index)

    feature_ids_by_owner: dict[str, list[str]] = {}
    relationship_ids_by_owner: dict[str, list[str]] = {}
    for feature in FEATURES:
        feature_ids_by_owner.setdefault(feature["owner_id"], []).append(feature["feature_id"])
    for relationship in RELATIONSHIPS:
        for feature_key in ("from_feature", "to_feature"):
            owner = _feature_by_id(relationship[feature_key])["owner_id"]
            relationship_ids_by_owner.setdefault(owner, []).append(relationship["relationship_id"])

    owner_object_ids: dict[str, str] = {}
    for obj in OBJECTS:
        object_id = _add_geometry(_object_geometry(obj["object_id"]), _attrs(layer_index, obj["name"]))
        owner_object_ids[obj["object_id"]] = str(object_id)
        _stamp(
            object_id,
            {
                **_base_attrs("object"),
                "rook.graph.object_id": obj["object_id"],
                "rook.graph.object_kind": obj["object_kind"],
                "rook.graph.feature_ids": ",".join(sorted(feature_ids_by_owner.get(obj["object_id"], []))),
                "rook.graph.relationship_ids": ",".join(
                    sorted(set(relationship_ids_by_owner.get(obj["object_id"], [])))
                ),
                "rook.graph.display_name": obj["name"],
            },
        )

    feature_object_ids: dict[str, str] = {}
    for feature in FEATURES:
        point = Rhino.Geometry.Point3d(*feature["point"])
        object_id = sc.doc.Objects.AddPoint(point, _attrs(layer_index, feature["feature_id"]))
        feature_object_ids[feature["feature_id"]] = str(object_id)
        _stamp(
            object_id,
            {
                **_base_attrs("feature"),
                "rook.graph.feature_id": feature["feature_id"],
                "rook.graph.owner_id": feature["owner_id"],
                "rook.graph.owner_kind": feature["owner_kind"],
                "rook.graph.feature_kind": feature["feature_kind"],
                "rook.graph.role": feature["role"],
                "rook.graph.true_position_m": json.dumps(feature["point"]),
            },
        )

    relationship_object_ids: dict[str, str] = {}
    for relationship in RELATIONSHIPS:
        from_point = Rhino.Geometry.Point3d(*_feature_by_id(relationship["from_feature"])["point"])
        to_point = Rhino.Geometry.Point3d(*_feature_by_id(relationship["to_feature"])["point"])
        object_id = sc.doc.Objects.AddCurve(
            Rhino.Geometry.LineCurve(from_point, to_point),
            _attrs(layer_index, relationship["relationship_id"]),
        )
        relationship_object_ids[relationship["relationship_id"]] = str(object_id)
        _stamp(
            object_id,
            {
                **_base_attrs("relationship"),
                "rook.graph.relationship_id": relationship["relationship_id"],
                "rook.graph.relationship_type": relationship["relationship_type"],
                "rook.graph.from_feature": relationship["from_feature"],
                "rook.graph.to_feature": relationship["to_feature"],
                "rook.graph.contact_kind": relationship["contact_kind"],
                "rook.graph.provenance": relationship["provenance"],
                "rook.graph.status": relationship["status"],
            },
        )

    sc.doc.Views.Redraw()
    return {
        "success": True,
        "source": SOURCE,
        "revision": REVISION,
        "pose": POSE,
        "clearedObjectCount": cleared_count,
        "ownerObjectCount": len(owner_object_ids),
        "featureObjectCount": len(feature_object_ids),
        "relationshipObjectCount": len(relationship_object_ids),
        "createdObjectCount": len(owner_object_ids) + len(feature_object_ids) + len(relationship_object_ids),
        "ownerObjectIds": owner_object_ids,
        "featureObjectIds": feature_object_ids,
        "relationshipObjectIds": relationship_object_ids,
    }


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, sort_keys=True))
