// SceneGraphWatcher.cpp
//
// CRhinoEventWatcher implementation that captures per-object events
// (add, delete, replace, modify-attributes) and feeds them to CSceneGraph.
//
// All callbacks fire on Rhino's main thread. We do minimal work here:
// read object attributes, bounding box, and layer path, then enqueue.

#include "stdafx.h"
#include "SceneGraph/SceneGraphWatcher.h"
#include "SceneGraph/SceneGraph.h"
#include "SceneGraph/SceneGraphModels.h"
#include "Models/DocumentHelpers.h"

CSceneGraphWatcher::CSceneGraphWatcher(Rook::CSceneGraph& owner)
    : m_owner(owner)
{
}

// ================================================================
// Type Filter
// ================================================================

bool CSceneGraphWatcher::IsTrackableType(ON::object_type type)
{
    // Track core geometry types that have meaningful bounding boxes.
    // Exclude annotations, text, hatches, lights, instance refs, grips, etc.
    switch (type)
    {
    case ON::point_object:
    case ON::pointset_object:
    case ON::curve_object:
    case ON::surface_object:
    case ON::brep_object:
    case ON::mesh_object:
    case ON::subd_object:
    case ON::extrusion_object:
        return true;
    default:
        return false;
    }
}

// ================================================================
// Event Capture
// ================================================================

Rook::ObjectEvent CSceneGraphWatcher::CaptureEvent(
    CRhinoDoc& doc, CRhinoObject& object, Rook::ObjectEvent::Type eventType)
{
    Rook::ObjectEvent ev;
    ev.type = eventType;

    // UUID
    ev.id = Rook::UuidToString(object.Attributes().m_uuid);

    // Name
    ON_wString wName = object.Attributes().m_name;
    if (!wName.IsEmpty())
        ev.name = Rook::WideToUtf8(wName);

    // Layer full path
    int layerIdx = object.Attributes().m_layer_index;
    if (layerIdx >= 0 && layerIdx < doc.m_layer_table.LayerCount())
    {
        ON_wString wPath;
        doc.m_layer_table.GetLayerPathName(layerIdx, wPath);
        if (!wPath.IsEmpty())
            ev.layerPath = Rook::WideToUtf8(wPath);
    }

    // Geometry type
    ev.geometryType = Rook::ObjectTypeToString(object.ObjectType());

    // Bounding box
    if (object.Geometry())
    {
        ON_BoundingBox bb = object.Geometry()->BoundingBox();
        if (bb.IsValid())
        {
            ev.bboxMin = { bb.m_min.x, bb.m_min.y, bb.m_min.z };
            ev.bboxMax = { bb.m_max.x, bb.m_max.y, bb.m_max.z };
            ev.bboxValid = true;
        }
    }

    // Unit scale (for proximity threshold conversion)
    ev.unitScale = ON::UnitScale(
        doc.Properties().ModelUnitsAndTolerances().m_unit_system,
        ON::LengthUnitSystem::Meters);

    return ev;
}

// ================================================================
// CRhinoEventWatcher Overrides
// ================================================================

void CSceneGraphWatcher::OnAddObject(CRhinoDoc& doc, CRhinoObject& object)
{
    if (!IsTrackableType(object.ObjectType())) return;
    auto ev = CaptureEvent(doc, object, Rook::ObjectEvent::Type::Created);
    m_owner.EnqueueEvent(std::move(ev));
}

void CSceneGraphWatcher::OnDeleteObject(CRhinoDoc& doc, CRhinoObject& object)
{
    if (!IsTrackableType(object.ObjectType())) return;

    // For deletes, we only need the UUID. No geometry access needed.
    Rook::ObjectEvent ev;
    ev.type = Rook::ObjectEvent::Type::Deleted;
    ev.id = Rook::UuidToString(object.Attributes().m_uuid);
    m_owner.EnqueueEvent(std::move(ev));
}

void CSceneGraphWatcher::OnReplaceObject(
    CRhinoDoc& doc, CRhinoObject& /*oldObject*/, CRhinoObject& newObject)
{
    if (!IsTrackableType(newObject.ObjectType())) return;
    auto ev = CaptureEvent(doc, newObject, Rook::ObjectEvent::Type::Modified);
    m_owner.EnqueueEvent(std::move(ev));
}

void CSceneGraphWatcher::OnModifyObjectAttributes(
    CRhinoDoc& doc, CRhinoObject& object, const CRhinoObjectAttributes& /*oldAtts*/)
{
    if (!IsTrackableType(object.ObjectType())) return;
    // Attribute changes (name, layer, color, etc.) — re-capture full data
    auto ev = CaptureEvent(doc, object, Rook::ObjectEvent::Type::Modified);
    m_owner.EnqueueEvent(std::move(ev));
}

// ================================================================
// Document Lifecycle
// ================================================================

void CSceneGraphWatcher::OnEndOpenDocument(
    CRhinoDoc& doc, const wchar_t* /*filename*/, BOOL /*bMerge*/, BOOL /*bReference*/)
{
    m_owner.ReconcileAsync(doc);
}

void CSceneGraphWatcher::OnCloseDocument(CRhinoDoc& /*doc*/)
{
    m_owner.ClearAsync();
}
