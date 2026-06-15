// OcctProbe.h
//
// Spike G tracer: minimal OCCT-in-plugin probe. Proves OCCT links, initializes,
// and runs BRepAlgoAPI_Common inside RookNative. Plain interface (no OCCT types in
// the header) so the Rhino-facing handler can call it WITHOUT pulling OCCT headers
// (avoids any OpenNURBS<->OCCT header clash). Mirrors the eventual pure-engine seam.
#pragma once
#include <string>

namespace Rook {

// Call once before any probe (OSD::SetSignal + allocator setup). Idempotent.
void OcctProbeInit();

// Reads two STEP files, sums face-pair Common() areas (the Spike-A primitive),
// returns shared area in the STEP's units (mm^2) or -1 on read failure.
// `diag` receives a short status string.
double OcctProbeSharedArea(const std::string& stepA, const std::string& stepB, std::string& diag);

} // namespace Rook
