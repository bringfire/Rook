// UndoScope.h
//
// RAII wrapper for Rhino undo records.
// Ensures EndUndoRecord is always called, even on exception.

#pragma once

namespace Rook {

class UndoScope
{
public:
    explicit UndoScope(CRhinoDoc* pDoc, const wchar_t* description)
        : m_pDoc(pDoc)
    {
        // BeginUndoRecord(const wchar_t*) is OBSOLETE — use BeginUndoRecordEx.
        m_sn = pDoc->BeginUndoRecordEx(description);
    }

    ~UndoScope()
    {
        if (m_sn > 0 && m_pDoc)
            m_pDoc->EndUndoRecord(m_sn);
    }

    UndoScope(const UndoScope&) = delete;
    UndoScope& operator=(const UndoScope&) = delete;

private:
    CRhinoDoc* m_pDoc;
    unsigned int m_sn = 0;
};

} // namespace Rook
