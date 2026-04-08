// stdafx.h : Precompiled header for RookNative
//
// The Rhino SDK requires a specific include order.
// Do not rearrange these includes.

#pragma once

// ============================================================================
// Step 0: Define WIN64 for the Rhino SDK.
// MSVC auto-defines _WIN64 (underscore) for x64 targets, but rhinoSdkChecks.h
// checks for WIN64 (no underscore) before any Windows headers are included.
// Without this, the preamble errors: "WIN64 should be defined".
// ============================================================================
#if defined(_WIN64) && !defined(WIN64)
#define WIN64
#endif

// ============================================================================
// Step 1: Rhino SDK preamble - MUST be the very first include.
// Sets up _WIN32_WINNT, WINVER, and validates the build environment.
// rhinoSdkChecks.h (included by preamble) requires WIN64 and NOT WIN32.
// ============================================================================
#include "RhinoSdkStdafxPreamble.h"

// ============================================================================
// Step 1.5: Winsock2 — required by both MFC (v14.44+ demands it) and httplib.
// Must come AFTER preamble (which checks !WIN32) but BEFORE MFC headers.
// winsock2.h → windows.h → defines WIN32, which we fix in Step 3.
// ============================================================================
#include <winsock2.h>
#include <ws2tcpip.h>

// ============================================================================
// Step 2: MFC headers - required by the Rhino C++ SDK.
// The SDK's UI headers reference CListCtrl, CSliderCtrl, CRichEditCtrl, etc.
// All of these MFC control classes must be available before RhinoSdk.h.
// ============================================================================
#include <afxwin.h>          // MFC core and standard components
#include <afxext.h>          // MFC extensions
#include <afxcmn.h>          // MFC common controls (CListCtrl, CSliderCtrl, etc.)
#include <afxrich.h>         // MFC rich edit (CRichEditCtrl)
#include <afxdisp.h>         // MFC Automation
#include <shlobj.h>          // Shell API (BROWSEINFO used by RhinoSdkUiDirDialog)

// ============================================================================
// Step 3: Fix WIN32/WIN64 conflict.
// MFC's <afxwin.h> includes <windows.h> which defines WIN32 even on x64.
// The Rhino SDK's rhinoSdkChecks.h (re-included by RhinoSdk.h with no
// include guard) errors if both WIN32 and WIN64 are defined.
// ============================================================================
#if defined(WIN64) && defined(WIN32)
#undef WIN32
#endif

// ============================================================================
// Step 4: Rhino SDK compatibility and main umbrella header.
// RHINO_V6_READY: acknowledges awareness of V6+ API changes.
// RHINO_SDK_MFC: tells the SDK that MFC headers are available.
// ============================================================================
#define RHINO_V6_READY
#define RHINO_SDK_MFC
#include "RhinoSdk.h"

// Render Development Kit — deferred until Phase 4 (material operations).
// Uncomment when MaterialHandler is implemented.
// #include "RhRdkHeaders.h"

// Auto-link Rhino SDK libraries via #pragma comment(lib, ...)
#include "rhinoSdkPlugInLinkingPragmas.h"

// ============================================================================
// Step 5: C++ standard library
// ============================================================================
#include <string>
#include <vector>
#include <memory>
#include <functional>
#include <mutex>
#include <queue>
#include <thread>
#include <future>
#include <atomic>
#include <unordered_map>
#include <condition_variable>

// ============================================================================
// Step 6: Third-party header-only libraries (in PCH for single compilation)
// ============================================================================
#include "vendor/nlohmann/json.hpp"

// httplib includes winsock2.h internally (Step 0.5 suppressed winsock1 to avoid conflict).
// Requires ws2_32.lib (linked in vcxproj).
#include "vendor/httplib/httplib.h"
