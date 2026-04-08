// ObjectDiffTracker.h
//
// Snapshots object GUIDs before/after a command to detect newly created objects.
// Must be used entirely on the main thread (CRhinoObjectIterator is not thread-safe).

#pragma once

#include <vector>
#include <set>
#include <cstring>

namespace Rook {

// ON_UUID is a plain C struct without operator<. Provide a comparator for std::set.
struct UuidLess
{
    bool operator()(const ON_UUID& a, const ON_UUID& b) const
    {
        return std::memcmp(&a, &b, sizeof(ON_UUID)) < 0;
    }
};

class ObjectDiffTracker
{
public:
    // Capture current object IDs as the "before" snapshot.
    explicit ObjectDiffTracker(CRhinoDoc* pDoc)
        : m_pDoc(pDoc)
    {
        CaptureIds(m_before);
    }

    // Returns GUIDs of objects that exist now but didn't exist at construction time.
    std::vector<ON_UUID> GetNewObjects()
    {
        std::set<ON_UUID, UuidLess> after;
        CaptureIds(after);

        std::vector<ON_UUID> result;
        for (const auto& id : after)
        {
            if (m_before.find(id) == m_before.end())
                result.push_back(id);
        }
        return result;
    }

private:
    void CaptureIds(std::set<ON_UUID, UuidLess>& out)
    {
        CRhinoObjectIterator it(*m_pDoc,
            CRhinoObjectIterator::normal_or_locked_objects,
            CRhinoObjectIterator::active_objects);
        for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
            out.insert(obj->Attributes().m_uuid);
    }

    CRhinoDoc* m_pDoc;
    std::set<ON_UUID, UuidLess> m_before;
};

} // namespace Rook
