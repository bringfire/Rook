// RookNativePlugin.h
//
// CRookNativePlugin - Rhino C++ utility plugin.
// This is the entry point for the RookNative plugin, which provides
// a high-performance HTTP server for Claude Code ↔ Rhino communication.

#pragma once

#include "Resource.h"

class CRookNativePlugin : public CRhinoUtilityPlugIn
{
public:
    CRookNativePlugin();
    ~CRookNativePlugin() = default;

    // Required overrides
    const wchar_t* PlugInName() const override;
    const wchar_t* PlugInVersion() const override;
    GUID PlugInID() const override;
    CRhinoPlugIn::plugin_load_time PlugInLoadTime() override;

    // Lifecycle
    BOOL OnLoadPlugIn() override;
    void OnUnloadPlugIn() override;

    // Singleton access
    static CRookNativePlugin& Instance();

    // Returns true when Rhino is hosted inside another application (Revit, etc.)
    static bool IsRhinoInside();

private:
    ON_wString m_plugin_version;

    // Prevent copying
    CRookNativePlugin(const CRookNativePlugin&) = delete;
    CRookNativePlugin& operator=(const CRookNativePlugin&) = delete;
};

// Global function required by the Rhino SDK to access the plugin instance
CRookNativePlugin& RookNativePlugIn();
