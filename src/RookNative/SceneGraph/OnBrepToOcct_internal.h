// OnBrepToOcct_internal.h
//
// OCCT-AWARE internal accessor for OcctFaceSet. Included ONLY by OCCT
// translation units (those that already pull OCCT headers + use NotUsing PCH
// with the per-file OCCT include path) — e.g. OcctAdjacencyEngine.cpp. This
// exposes the converted OCCT faces to the engine WITHOUT leaking OCCT types
// into the public, pimpl'd OnBrepToOcct.h.
//
// `OcctFaceAt` is defined in OnBrepToOcct.cpp where OcctFaceSet::Impl is a
// complete type. The slot->source-face-index map and faceCount() are already
// public on OcctFaceSet (sourceFaceIndex(slot) / faceCount()).
#pragma once
#include <TopoDS_Face.hxx>

namespace Rook {
class OcctFaceSet;
// Return the converted OCCT face at `slot` in [0, faceCount()). Slot is the
// OCCT slot index, NOT the ON_Brep face index (use sourceFaceIndex(slot) to map
// slot -> ON_Brep face index). Caller guarantees slot is in range.
const TopoDS_Face& OcctFaceAt(const OcctFaceSet& set, int slot);
}
