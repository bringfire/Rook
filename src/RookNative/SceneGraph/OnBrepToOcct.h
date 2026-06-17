#pragma once
#include <vector>
#include <memory>
class ON_Brep;
namespace Rook {
// RAII owning result of a Brep->OCCT conversion (pimpl; OCCT types only in the .cpp).
// Move-only; frees the OCCT shape on destruction.
class OcctFaceSet {
public:
    OcctFaceSet();
    ~OcctFaceSet();
    OcctFaceSet(OcctFaceSet&&) noexcept;
    OcctFaceSet& operator=(OcctFaceSet&&) noexcept;
    OcctFaceSet(const OcctFaceSet&) = delete;
    OcctFaceSet& operator=(const OcctFaceSet&) = delete;
    int faceCount() const;
    int sourceFaceIndex(int occtSlot) const;
    const std::vector<int>& failedFaceIndices() const;
    struct Impl;
    Impl* impl();
    const Impl* impl() const;
private:
    std::unique_ptr<Impl> m_impl;
};
// Convert every analytic face of `brep` to an OCCT face, preserving the SOURCE
// ON_Brep face index. Failed faces recorded in failedFaceIndices(). Pure: no Rhino
// SDK, no STEP, no threads. Empty set (faceCount()==0) if nothing converts.
OcctFaceSet ConvertBrepFaces(const ON_Brep& brep);
// Sum of the OCCT SurfaceProperties().Mass() over every converted face, in the
// SAME units as the source ON_Brep (model units; squared for area). 0.0 if empty.
double OcctFaceSetTotalArea(const OcctFaceSet& set);
}
