// SceneGraphWatcher.h
//
// CRhinoEventWatcher subclass that captures per-object events
// and enqueues lightweight ObjectEvent data to the scene graph.
//
// Callbacks fire on Rhino's main thread. We NEVER modify the document
// inside these callbacks — just capture data and enqueue.

#pragma once

#include "SceneGraph/SceneGraphModels.h"

namespace Rook { class CSceneGraph; }

class CSceneGraphWatcher : public CRhinoEventWatcher
{
public:
    explicit CSceneGraphWatcher(Rook::CSceneGraph& owner);

    // CRhinoEventWatcher overrides — per-object events
    void OnAddObject(CRhinoDoc& doc, CRhinoObject& object) override;
    void OnDeleteObject(CRhinoDoc& doc, CRhinoObject& object) override;
    void OnReplaceObject(CRhinoDoc& doc, CRhinoObject& oldObject, CRhinoObject& newObject) override;
    void OnModifyObjectAttributes(CRhinoDoc& doc, CRhinoObject& object, const CRhinoObjectAttributes& oldAtts) override;

    // CRhinoEventWatcher overrides — document lifecycle
    void OnEndOpenDocument(CRhinoDoc& doc, const wchar_t* filename,
                           BOOL bMerge, BOOL bReference) override;
    void OnCloseDocument(CRhinoDoc& doc) override;

    // Returns true if this object type should be tracked by the scene graph.
    // Filters out annotations, hatches, text dots, instance references, etc.
    // Public so CaptureReconcileData can share the same allow-list.
    static bool IsTrackableType(ON::object_type type);

private:

    // Capture lightweight data from a CRhinoObject into an ObjectEvent.
    static Rook::ObjectEvent CaptureEvent(CRhinoDoc& doc, CRhinoObject& object,
                                           Rook::ObjectEvent::Type eventType);

    Rook::CSceneGraph& m_owner;
};
