// OcctProbe.cpp
//
// OCCT process initialization. OCCT-ONLY translation unit: includes no Rhino SDK, no
// stdafx.h (NotUsing PCH in the vcxproj). Installs OCCT's SEH->Standard_Failure
// translation so in-plugin OCCT faults surface as catchable Standard_Failure instead of
// killing the process.
//
// [The Spike-G STEP probe (OcctProbeSharedArea + ReadStep) was removed in Task 8: it was
//  dev-only and read STEP, which the production build must never do. No STEPControl /
//  DataExchange header is included by any C++ TU.]
#include "SceneGraph/OcctProbe.h"

#include <OSD.hxx>

namespace Rook {

void OcctProbeInit()
{
    // Signal/exception handling setup for OCCT on the current thread. Idempotent in
    // practice; safe to call once per OCCT worker thread before any OCCT call.
    OSD::SetSignal(false);
}

} // namespace Rook
