// OcctProbe.h
//
// OCCT process initialization for in-plugin OCCT work. Installs OCCT's per-thread
// SEH->Standard_Failure translation (OSD::SetSignal) so an OCCT fault surfaces as a
// catchable Standard_Failure instead of killing the Rhino process. Plain interface (no
// OCCT types in the header) so callers don't pull OCCT headers. Called once on the
// dedicated OCCT worker thread (see OcctExecutor::WorkerLoop).
//
// [The Spike-G STEP probe (OcctProbeSharedArea) that used to live here was removed in
//  Task 8 — no STEP is read anywhere in the C++ build. The filename is retained to avoid
//  churning OcctExecutor's include during the Phase-2 integration; rename is later polish.]
#pragma once

namespace Rook {

// Install OCCT's SEH->Standard_Failure translator on the CURRENT thread.
// Call once per OCCT worker thread before any OCCT call. Idempotent in practice.
void OcctProbeInit();

} // namespace Rook
