"""Create a tiny Rhino fixture for relationship fact projection live smoke.

Run inside Rhino Python via Rook `rhino_execute` or Rhino's script editor.
The script creates five objects on one layer and prints JSON with owner ids.
"""

from __future__ import annotations

import json

import Rhino
import scriptcontext as sc


SOURCE = "relationship_fact_smoke"
REVISION = "smoke001"
POSE = "smoke_pose"
LAYER_NAME = "Rook_RelationshipFactSmoke"


def _ensure_layer(name: str) -> int:
    layer_index = sc.doc.Layers.FindByFullPath(name, -1)
    if layer_index >= 0:
        return layer_index
    layer = Rhino.DocObjects.Layer()
    layer.Name = name
    return sc.doc.Layers.Add(layer)


def _clear_smoke_layer(layer_index: int) -> int:
    layer = sc.doc.Layers[layer_index]
    objects = sc.doc.Objects.FindByLayer(layer)
    cleared = 0
    if objects:
        for rhino_object in list(objects):
            if sc.doc.Objects.Delete(rhino_object, True):
                cleared += 1
    return cleared


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


def main() -> dict[str, str]:
    layer_index = _ensure_layer(LAYER_NAME)
    cleared_count = _clear_smoke_layer(layer_index)
    attrs = Rhino.DocObjects.ObjectAttributes()
    attrs.LayerIndex = layer_index

    member_curve = Rhino.Geometry.LineCurve(
        Rhino.Geometry.Point3d(0.0, 0.0, 0.0),
        Rhino.Geometry.Point3d(1.0, 0.0, 0.0),
    )
    member_id = sc.doc.Objects.AddCurve(member_curve, attrs)

    joint_id = sc.doc.Objects.AddPoint(Rhino.Geometry.Point3d(0.0, 0.0, 0.0), attrs)
    member_feature_id = sc.doc.Objects.AddPoint(Rhino.Geometry.Point3d(0.0, 0.0, 0.1), attrs)
    joint_feature_id = sc.doc.Objects.AddPoint(Rhino.Geometry.Point3d(0.0, 0.0, 0.2), attrs)
    relationship_curve = Rhino.Geometry.LineCurve(
        Rhino.Geometry.Point3d(0.0, 0.0, 0.1),
        Rhino.Geometry.Point3d(0.0, 0.0, 0.2),
    )
    relationship_id = sc.doc.Objects.AddCurve(relationship_curve, attrs)

    _stamp(
        member_id,
        {
            **_base_attrs("member"),
            "rook.graph.member_id": "smoke_member",
            "rook.graph.feature_ids": "smoke_member.start",
            "rook.graph.relationship_ids": "smoke_member.start_connects_smoke_joint",
        },
    )
    _stamp(
        joint_id,
        {
            **_base_attrs("joint"),
            "rook.graph.node_id": "smoke_joint",
            "rook.graph.feature_ids": "smoke_joint.point",
            "rook.graph.relationship_ids": "smoke_member.start_connects_smoke_joint",
        },
    )
    _stamp(
        member_feature_id,
        {
            **_base_attrs("feature"),
            "rook.graph.feature_id": "smoke_member.start",
            "rook.graph.owner": "smoke_member",
            "rook.graph.owner_kind": "member",
            "rook.graph.feature_kind": "endpoint",
            "rook.graph.role": "start",
            "rook.graph.true_position_m": "[0.0, 0.0, 0.0]",
            "rook.graph.visual_lift_m": "0.1",
        },
    )
    _stamp(
        joint_feature_id,
        {
            **_base_attrs("feature"),
            "rook.graph.feature_id": "smoke_joint.point",
            "rook.graph.owner": "smoke_joint",
            "rook.graph.owner_kind": "node",
            "rook.graph.feature_kind": "point",
            "rook.graph.role": "joint",
            "rook.graph.true_position_m": "[0.0, 0.0, 0.0]",
            "rook.graph.visual_lift_m": "0.2",
        },
    )
    _stamp(
        relationship_id,
        {
            **_base_attrs("relationship"),
            "rook.graph.relationship_id": "smoke_member.start_connects_smoke_joint",
            "rook.graph.relationship_type": "connects",
            "rook.graph.from_feature": "smoke_member.start",
            "rook.graph.to_feature": "smoke_joint.point",
            "rook.graph.contact_kind": "point_to_point",
            "rook.graph.provenance": "authored_assembly_graph",
        },
    )

    sc.doc.Views.Redraw()
    return {
        "source": SOURCE,
        "revision": REVISION,
        "pose": POSE,
        "clearedObjectCount": cleared_count,
        "memberObjectId": str(member_id),
        "jointObjectId": str(joint_id),
        "memberFeatureObjectId": str(member_feature_id),
        "jointFeatureObjectId": str(joint_feature_id),
        "relationshipObjectId": str(relationship_id),
    }


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, sort_keys=True))
