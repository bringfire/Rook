using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading;
using Rhino;
using Rhino.Display;

namespace Rook.Handlers
{
    /// <summary>
    /// Tier 3 viewport capture — SDK-backed (<c>view.CaptureToBitmap</c>) with
    /// display-mode resolution and optional raytraced convergence. Invoked via
    /// the native bridge callback <c>viewport_capture_tier3</c> (ABI v13).
    ///
    /// The legacy Tier 2 path (<c>_-ViewCaptureToFile</c>) stays in native
    /// <c>/viewport</c>; this handler runs only when the caller sends
    /// <c>captureBackend: "tier3"</c>.
    ///
    /// Parity with legacy: full viewport state (camera + projection +
    /// display mode) is snapshotted before mutation and restored in
    /// <c>finally</c> — matches the native
    /// <c>ON_Viewport savedVP = vp.VP()</c> /
    /// <c>vp.SetVP(savedVP, true)</c> contract.
    ///
    /// Document pinning: the bridge trampoline wraps this call in
    /// <see cref="DocumentContext.WithDocument(uint?, Action)"/>, so
    /// <see cref="DocumentContext.GetDocument"/> returns the caller's
    /// target doc (multi-doc safe).
    ///
    /// Timeout contract: <c>raytracedTimeoutMs</c> is clamped to
    /// <see cref="MaxRaytracedTimeoutMs"/> (20 s) to leave headroom under
    /// the bridge callback's 30 s ceiling in
    /// <c>NativeGhBridgeRegistrar.ExecuteApiResponseCallback</c>.
    ///
    /// Scope: Tier 3 intentionally supports a narrower option set than the
    /// legacy <c>_-ViewCaptureToFile</c> path. The following legacy fields
    /// are rejected with HTTP 400 when present (rather than silently
    /// ignored): <c>scale</c>, <c>transparentBackground</c>,
    /// <c>drawGrid</c>, <c>drawWorldAxes</c>, <c>drawCPlaneAxes</c>.
    /// Silent degradation would produce false-success responses where the
    /// caller's flags do not affect the captured image. A future PR can
    /// map these onto <c>Rhino.Display.ViewCaptureSettings</c> after live
    /// verification of property-name semantics.
    /// </summary>
    public class ViewportHandler
    {
        internal const int DefaultRaytracedTimeoutMs = 10000;

        // Public cap stays comfortably under the bridge's 30 s waitHandle in
        // NativeGhBridgeRegistrar.ExecuteApiResponseCallback. Capture + PNG
        // write + JSON serialization needs the remaining ~10 s margin.
        internal const int MaxRaytracedTimeoutMs = 20000;

        internal const int RaytracedCheckIntervalMs = 250;
        internal const int RaytracedMinSamples = 10;
        internal const int RaytracedStableThreshold = 4;

        internal const int DefaultWidth = 800;
        internal const int DefaultHeight = 600;
        internal const int MinDimension = 100;
        internal const int MaxDimension = 4000;
        private static readonly string[] RaytracedModeNames =
            { "raytraced", "Raytraced", "cycles", "Cycles" };

        public ApiResponse CaptureTier3(string? body)
        {
            Tier3Request request;
            try
            {
                request = ParseRequest(body);
            }
            catch (ArgumentException ex)
            {
                return new ApiResponse { Success = false, Data = ex.Message };
            }

            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return new ApiResponse { Success = false, Data = "No active document." };
            }

            var view = doc.Views.ActiveView;
            if (view == null)
            {
                return new ApiResponse { Success = false, Data = "No active view available." };
            }

            // Snapshot the full viewport projection (camera + target + lens +
            // projection type) before any mutation, plus the display mode.
            // Matches the native handler's ON_Viewport savedVP = vp.VP()
            // save/restore contract at ViewportHandler.cpp:119 / :208.
            var savedProjection = new Rhino.DocObjects.ViewportInfo(view.ActiveViewport);
            var savedDisplayMode = view.ActiveViewport.DisplayMode;

            string resolvedViewName = view.ActiveViewport.Name;
            string resolvedDisplayMode =
                view.ActiveViewport.DisplayMode?.EnglishName ?? "current";
            int? raytracedSamples = null;

            try
            {
                // 1. View-token precedence MUST match legacy
                //    ViewportHandler.cpp (ViewNameToCommand first, then
                //    named-view fallback). Otherwise a document with a
                //    named view called "Top" captures different cameras
                //    depending on captureBackend — a silent regression.
                if (!string.IsNullOrEmpty(request.ViewName))
                {
                    if (TrySetStandardView(view, request.ViewName))
                    {
                        resolvedViewName = request.ViewName!;
                    }
                    else if (TryRestoreNamedView(doc, view, request.ViewName))
                    {
                        resolvedViewName = request.ViewName!;
                    }
                    // Unknown view name: silently keep the current view
                    // (matches legacy behavior).
                }

                // 2. Display mode: resolve via robust fallback chain and
                //    record what actually ran (not the caller token).
                bool runningRaytraced = false;
                if (!string.IsNullOrEmpty(request.DisplayMode)
                    && !string.Equals(request.DisplayMode, "current",
                                      StringComparison.OrdinalIgnoreCase))
                {
                    var targetMode = FindDisplayMode(request.DisplayMode!);
                    if (targetMode != null && targetMode.Id != savedDisplayMode?.Id)
                    {
                        view.ActiveViewport.DisplayMode = targetMode;
                        view.Redraw();
                        resolvedDisplayMode = targetMode.EnglishName;
                        runningRaytraced = IsRaytracedMode(targetMode);
                    }
                    else if (targetMode != null)
                    {
                        resolvedDisplayMode = targetMode.EnglishName;
                        runningRaytraced = IsRaytracedMode(targetMode);
                    }
                    // If targetMode == null, fall through to current mode
                    // silently — resolvedDisplayMode already reflects that.
                }
                else
                {
                    runningRaytraced = IsRaytracedMode(savedDisplayMode);
                }

                // 3. Zoom extents if requested.
                if (request.ZoomExtents)
                {
                    view.ActiveViewport.ZoomExtents();
                    view.Redraw();
                }

                // 4. Wait for raytraced convergence when both flag and mode
                //    agree. Silently ignored when either condition fails.
                if (request.RaytracedConverge && runningRaytraced)
                {
                    raytracedSamples = WaitForRaytracedRender(
                        view, request.RaytracedTimeoutMs);
                }

                // 5. Capture. Size = (width, height) clamped. SA_Banana's
                //    maxEdge helper is kept as internal scaling logic only
                //    and is NOT exposed on the public request contract.
                var captureSize = new Size(request.Width, request.Height);
                using var bitmap = view.CaptureToBitmap(captureSize);
                if (bitmap == null)
                {
                    return new ApiResponse
                    {
                        Success = false,
                        Data = "view.CaptureToBitmap returned null.",
                    };
                }

                // 6. Write to temp file, matching GrasshopperHandler.CaptureCanvasImage
                //    precedent (file-path transport, not base64).
                var tempDir = Path.Combine(
                    Path.GetTempPath(), "rook", "viewports");
                Directory.CreateDirectory(tempDir);
                var filename = "viewport_" +
                    DateTime.Now.ToString("yyyyMMdd_HHmmss_fff") + ".png";
                var filePath = Path.Combine(tempDir, filename);
                bitmap.Save(filePath, ImageFormat.Png);

                var data = new Dictionary<string, object?>
                {
                    ["format"] = "png",
                    ["width"] = bitmap.Width,
                    ["height"] = bitmap.Height,
                    ["viewName"] = resolvedViewName,
                    ["displayMode"] = resolvedDisplayMode,
                    ["savedToFile"] = true,
                    ["filePath"] = filePath,
                    ["message"] =
                        "Image saved to file. Use the Read tool to view the image.",
                    ["captureBackend"] = "tier3",
                };
                if (raytracedSamples.HasValue)
                {
                    data["raytracedSamples"] = raytracedSamples.Value;
                }

                return new ApiResponse { Success = true, Data = data };
            }
            catch (Exception ex)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = $"Tier 3 capture failed: {ex.Message}",
                };
            }
            finally
            {
                // Full viewport state restore — projection first (covers
                // camera, target, lens, view type), then display mode.
                try
                {
                    view.ActiveViewport.SetViewProjection(savedProjection, true);
                }
                catch (Exception ex)
                {
                    RhinoApp.WriteLine(
                        $"Rook: Tier 3 viewport projection restore failed: {ex.Message}");
                }
                try
                {
                    if (savedDisplayMode != null
                        && view.ActiveViewport.DisplayMode?.Id != savedDisplayMode.Id)
                    {
                        view.ActiveViewport.DisplayMode = savedDisplayMode;
                    }
                }
                catch (Exception ex)
                {
                    RhinoApp.WriteLine(
                        $"Rook: Tier 3 display mode restore failed: {ex.Message}");
                }
                try { view.Redraw(); } catch { /* swallow */ }
            }
        }

        // ─── Pure helpers (unit-testable without RhinoCommon) ──────────

        internal readonly struct Tier3Request
        {
            public int Width { get; init; }
            public int Height { get; init; }
            public string? ViewName { get; init; }
            public string? DisplayMode { get; init; }
            public bool ZoomExtents { get; init; }
            public bool RaytracedConverge { get; init; }
            public int RaytracedTimeoutMs { get; init; }
        }

        // Legacy /viewport accepts these. Tier 3 does not map them onto
        // view.CaptureToBitmap yet; accepting-and-ignoring would produce
        // false-success responses where the caller's flags do not affect
        // the captured image, so we hard-reject on presence.
        internal static readonly string[] UnsupportedLegacyFields =
        {
            "scale",
            "transparentBackground",
            "drawGrid",
            "drawWorldAxes",
            "drawCPlaneAxes",
        };

        internal static Tier3Request ParseRequest(string? body)
        {
            Dictionary<string, JsonElement>? args = null;
            if (!string.IsNullOrEmpty(body))
            {
                try
                {
                    args = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
                }
                catch (JsonException ex)
                {
                    throw new ArgumentException($"Invalid JSON body: {ex.Message}");
                }
            }

            var backend = GetStringArg(args, "captureBackend");
            if (!string.IsNullOrEmpty(backend) && backend != "tier3")
            {
                // Legacy-path requests never reach this handler — native
                // branches on captureBackend before invoking the bridge.
                // A non-tier3 value here means caller bypassed /viewport,
                // which is still a protocol error.
                throw new ArgumentException(
                    $"ViewportHandler.CaptureTier3 requires captureBackend='tier3'. Got '{backend}'.");
            }

            if (args != null)
            {
                var rejected = new List<string>();
                foreach (var field in UnsupportedLegacyFields)
                {
                    if (args.ContainsKey(field))
                    {
                        rejected.Add(field);
                    }
                }
                if (rejected.Count > 0)
                {
                    throw new ArgumentException(
                        "Tier 3 capture does not support the following /viewport " +
                        "fields (the legacy backend honors them; future PR will " +
                        "add parity via ViewCaptureSettings): " +
                        string.Join(", ", rejected) +
                        ". Remove these fields or use captureBackend='legacy'.");
                }
            }

            return new Tier3Request
            {
                Width = ClampDimension(GetIntArg(args, "width"), DefaultWidth),
                Height = ClampDimension(GetIntArg(args, "height"), DefaultHeight),
                ViewName = GetStringArg(args, "view"),
                DisplayMode = GetStringArg(args, "displayMode"),
                ZoomExtents = GetBoolArg(args, "zoomExtents"),
                RaytracedConverge = GetBoolArg(args, "raytracedConverge"),
                RaytracedTimeoutMs = ClampRaytracedTimeoutMs(
                    GetIntArg(args, "raytracedTimeoutMs")),
            };
        }

        internal static int ClampRaytracedTimeoutMs(int? raw)
        {
            if (!raw.HasValue || raw.Value <= 0)
            {
                return DefaultRaytracedTimeoutMs;
            }
            if (raw.Value > MaxRaytracedTimeoutMs)
            {
                return MaxRaytracedTimeoutMs;
            }
            return raw.Value;
        }

        internal static int ClampDimension(int? raw, int defaultValue)
        {
            if (!raw.HasValue) return defaultValue;
            if (raw.Value < MinDimension) return MinDimension;
            if (raw.Value > MaxDimension) return MaxDimension;
            return raw.Value;
        }

        internal static bool IsRaytracedModeName(string? modeName)
        {
            if (string.IsNullOrEmpty(modeName)) return false;
            foreach (var r in RaytracedModeNames)
            {
                if (string.Equals(modeName, r, StringComparison.OrdinalIgnoreCase))
                    return true;
            }
            return false;
        }

        // ─── Rhino-dependent helpers (live-Rhino only) ──────────────────

        internal static bool IsRaytracedMode(DisplayModeDescription? mode)
        {
            if (mode == null) return false;
            return IsRaytracedModeName(mode.EnglishName)
                || IsRaytracedModeName(mode.LocalName);
        }

        internal static DisplayModeDescription? FindDisplayMode(string modeName)
        {
            if (string.IsNullOrEmpty(modeName)) return null;
            if (string.Equals(modeName, "current", StringComparison.OrdinalIgnoreCase))
                return null;

            // Standard resolver first.
            var mode = DisplayModeDescription.FindByName(modeName);
            if (mode != null) return mode;

            var allModes = DisplayModeDescription.GetDisplayModes();

            mode = allModes.FirstOrDefault(m =>
                m.EnglishName.Equals(modeName, StringComparison.OrdinalIgnoreCase));
            if (mode != null) return mode;

            mode = allModes.FirstOrDefault(m =>
                m.LocalName.Equals(modeName, StringComparison.OrdinalIgnoreCase));
            if (mode != null) return mode;

            mode = allModes.FirstOrDefault(m =>
                m.EnglishName.StartsWith(modeName, StringComparison.OrdinalIgnoreCase) ||
                m.LocalName.StartsWith(modeName, StringComparison.OrdinalIgnoreCase));
            if (mode != null) return mode;

            if (Guid.TryParse(modeName, out var guid))
            {
                mode = allModes.FirstOrDefault(m => m.Id == guid);
                if (mode != null) return mode;
            }

            return null;
        }

        private static bool TryRestoreNamedView(
            RhinoDoc doc, Rhino.Display.RhinoView view, string viewName)
        {
            var namedViews = doc.NamedViews;
            for (int i = 0; i < namedViews.Count; i++)
            {
                if (string.Equals(
                    namedViews[i].Name, viewName, StringComparison.OrdinalIgnoreCase))
                {
                    namedViews.Restore(i, view.ActiveViewport);
                    view.Redraw();
                    return true;
                }
            }
            return false;
        }

        private static bool TrySetStandardView(
            Rhino.Display.RhinoView view, string viewName)
        {
            // Map the same set as the native handler's ViewNameToCommand in
            // ViewportHandler.cpp. Use the SDK (not RunScript) to avoid
            // mutating the active view via scripted commands.
            switch (viewName.ToLowerInvariant())
            {
                case "top":
                    view.ActiveViewport.SetProjection(
                        DefinedViewportProjection.Top, null, true);
                    break;
                case "bottom":
                    view.ActiveViewport.SetProjection(
                        DefinedViewportProjection.Bottom, null, true);
                    break;
                case "front":
                    view.ActiveViewport.SetProjection(
                        DefinedViewportProjection.Front, null, true);
                    break;
                case "back":
                    view.ActiveViewport.SetProjection(
                        DefinedViewportProjection.Back, null, true);
                    break;
                case "left":
                    view.ActiveViewport.SetProjection(
                        DefinedViewportProjection.Left, null, true);
                    break;
                case "right":
                    view.ActiveViewport.SetProjection(
                        DefinedViewportProjection.Right, null, true);
                    break;
                case "perspective":
                    view.ActiveViewport.SetProjection(
                        DefinedViewportProjection.Perspective, null, true);
                    break;
                default:
                    return false;
            }
            view.Redraw();
            return true;
        }

        // Returns the final sample count observed (or 0 if the realtime
        // display mode never reported any). Port of
        // SA_Banana.Services.ViewportCapture.WaitForRaytracedRender.
        private static int WaitForRaytracedRender(
            Rhino.Display.RhinoView view, int timeoutMs)
        {
            var start = DateTime.Now;
            int lastPass = -1;
            int stableCount = 0;

            while ((DateTime.Now - start).TotalMilliseconds < timeoutMs)
            {
                var rtm = view.RealtimeDisplayMode;
                if (rtm != null)
                {
                    var passFunc = rtm.LastRenderedPass;
                    int pass = passFunc != null ? passFunc() : 0;

                    if (pass >= RaytracedMinSamples)
                    {
                        return pass;
                    }
                    if (pass == lastPass && pass > 0)
                    {
                        stableCount++;
                        if (stableCount >= RaytracedStableThreshold)
                        {
                            return pass;
                        }
                    }
                    else
                    {
                        stableCount = 0;
                    }
                    lastPass = pass;
                }
                Thread.Sleep(RaytracedCheckIntervalMs);
            }

            // Timeout: final redraw + brief settle so buffer is ready.
            view.Redraw();
            Thread.Sleep(100);
            return Math.Max(0, lastPass);
        }

        // ─── Arg helpers (mirror NativeGhBridgeRegistrar conventions) ──

        private static string? GetStringArg(
            Dictionary<string, JsonElement>? args, string name)
        {
            if (args == null) return null;
            if (!args.TryGetValue(name, out var el)) return null;
            if (el.ValueKind == JsonValueKind.String) return el.GetString();
            return null;
        }

        private static int? GetIntArg(
            Dictionary<string, JsonElement>? args, string name)
        {
            if (args == null) return null;
            if (!args.TryGetValue(name, out var el)) return null;
            if (el.ValueKind == JsonValueKind.Number
                && el.TryGetInt32(out var v))
            {
                return v;
            }
            return null;
        }

        private static bool GetBoolArg(
            Dictionary<string, JsonElement>? args, string name)
        {
            if (args == null) return false;
            if (!args.TryGetValue(name, out var el)) return false;
            if (el.ValueKind == JsonValueKind.True) return true;
            if (el.ValueKind == JsonValueKind.False) return false;
            return false;
        }
    }
}
