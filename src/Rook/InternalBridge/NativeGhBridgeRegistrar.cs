using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Threading;
using Rhino;
using Rook.Handlers;

namespace Rook.InternalBridge
{
    /// <summary>
    /// Registers GH callbacks with the native plugin from Rhino's real managed runtime.
    /// This keeps GH execution in the same runtime/load context as Grasshopper itself.
    /// </summary>
    public static class NativeGhBridgeRegistrar
    {
        private const uint BridgeAbiVersion = 7;
        private static readonly object Sync = new();
        private static readonly IGrasshopperCore Core = new GrasshopperCore();
        private static readonly GrasshopperHandler Handler = new();
        private static readonly GumballHandler Gumball = new();
        private static readonly BlocksHandler Blocks = new();
        private static readonly CreateHandler Create = new();
        private static readonly TextureMappingHandler TextureMapping = new();
        private static readonly GameExportHandler GameExport = new();
        private static readonly JsonSerializerOptions JsonOptions = new()
        {
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase
        };

        private static readonly NativeGhBridgeCallback StatusCallback = HandleStatus;
        private static readonly NativeGhBridgeCallback DocumentCallback = HandleDocument;
        private static readonly NativeGhBridgeCallback QueryCallback = HandleQuery;
        private static readonly NativeGhBridgeCallback SelectionCallback = HandleSelection;
        private static readonly NativeGhBridgeCallback CategoriesCallback = HandleCategories;
        private static readonly NativeGhBridgeCallback LibraryCallback = HandleLibrary;
        private static readonly NativeGhBridgeCallback GetValueCallback = HandleGetValue;
        private static readonly NativeGhBridgeCallback ConnectionsCallback = HandleConnections;
        private static readonly NativeGhBridgeCallback GroupsCallback = HandleGroups;
        private static readonly NativeGhBridgeCallback ComponentCallback = HandleComponent;
        private static readonly NativeGhBridgeCallback InspectOutputCallback = HandleInspectOutput;
        private static readonly NativeGhBridgeCallback ErrorsCallback = HandleErrors;
        private static readonly NativeGhBridgeCallback GetReferenceCallback = HandleGetReference;
        private static readonly NativeGhBridgeCallback SetScriptCallback = HandleSetScript;
        private static readonly NativeGhBridgeCallback PreviewCallback = HandlePreview;
        private static readonly NativeGhBridgeCallback ClearCallback = HandleClear;
        private static readonly NativeGhBridgeCallback OpenDocumentCallback = HandleOpenDocument;
        private static readonly NativeGhBridgeCallback NewDocumentCallback = HandleNewDocument;
        private static readonly NativeGhBridgeCallback SetReferenceCallback = HandleSetReference;
        private static readonly NativeGhBridgeCallback ClearReferenceCallback = HandleClearReference;
        private static readonly NativeGhBridgeCallback MoveCallback = HandleMove;
        private static readonly NativeGhBridgeCallback GroupCallback = HandleGroup;
        private static readonly NativeGhBridgeCallback GroupResizeCallback = HandleGroupResize;
        private static readonly NativeGhBridgeCallback ClusterCallback = HandleCluster;
        private static readonly NativeGhBridgeCallback ExploreSelectionCallback = HandleExploreSelection;
        private static readonly NativeGhBridgeCallback ExploreClusterCallback = HandleExploreCluster;
        private static readonly NativeGhBridgeCallback BatchComponentInfoCallback = HandleBatchComponentInfo;
        private static readonly NativeGhBridgeCallback CreateComponentCallback = HandleCreateComponent;
        private static readonly NativeGhBridgeCallback CreateSliderCallback = HandleCreateSlider;
        private static readonly NativeGhBridgeCallback CreatePanelCallback = HandleCreatePanel;
        private static readonly NativeGhBridgeCallback ConnectCallback = HandleConnect;
        private static readonly NativeGhBridgeCallback DisconnectCallback = HandleDisconnect;
        private static readonly NativeGhBridgeCallback SetValueCallback = HandleSetValue;
        private static readonly NativeGhBridgeCallback DeleteCallback = HandleDelete;
        private static readonly NativeGhBridgeCallback SolveCallback = HandleSolve;
        // Canvas Graph Protocol
        private static readonly NativeGhBridgeCallback SnapshotCallback = HandleSnapshot;
        private static readonly NativeGhBridgeCallback EditCallback = HandleEdit;
        private static readonly NativeGhBridgeCallback UndoCallback = HandleUndo;
        private static readonly NativeGhBridgeCallback CanvasFocusCallback = HandleCanvasFocus;
        private static readonly NativeGhBridgeCallback CanvasZoomCallback = HandleCanvasZoom;
        private static readonly NativeGhBridgeCallback CanvasImageCallback = HandleCanvasImage;
        // Non-GH callbacks below are not all live route dependencies anymore.
        // See docs/plans/2026-03-08-companion-boundary-audit.md for the current
        // boundary: GH is companion-backed by design, while only a narrow non-GH
        // exception list still intentionally depends on the companion.
        private static readonly Make2dHandler Make2dHandler = new();
        private static readonly NativeGhBridgeCallback Make2dCallback = HandleMake2d;
        private static readonly NativeGhBridgeCallback GumballExtrudeCallback = HandleGumballExtrude;
        private static readonly NativeGhBridgeCallback GumballCutCallback = HandleGumballCut;
        private static readonly NativeGhBridgeCallback GumballSettingsCallback = HandleGumballSettings;
        private static readonly NativeGhBridgeCallback BlockSetLayersCallback = HandleBlockSetLayers;
        private static readonly NativeGhBridgeCallback BlockSetMaterialsCallback = HandleBlockSetMaterials;
        private static readonly NativeGhBridgeCallback BlockSetInstancePropertiesCallback = HandleBlockSetInstanceProperties;
        private static readonly NativeGhBridgeCallback BlockSetInstanceVisibilityCallback = HandleBlockSetInstanceVisibility;
        private static readonly NativeGhBridgeCallback BlockTransformInstanceCallback = HandleBlockTransformInstance;
        private static readonly NativeGhBridgeCallback BlockArrayInstancesCallback = HandleBlockArrayInstances;
        private static readonly NativeGhBridgeCallback BlockSetObjectColorsCallback = HandleBlockSetObjectColors;
        private static readonly NativeGhBridgeCallback BlockSetObjectNamesCallback = HandleBlockSetObjectNames;
        private static readonly NativeGhBridgeCallback BlockSetObjectUserStringsCallback = HandleBlockSetObjectUserStrings;
        private static readonly NativeGhBridgeCallback BlockFindInstancesCallback = HandleBlockFindInstances;
        private static readonly NativeGhBridgeCallback BlockUserStringsCallback = HandleBlockUserStrings;
        private static readonly NativeGhBridgeCallback BlockObjectsDetailedCallback = HandleBlockObjectsDetailed;
        private static readonly NativeGhBridgeCallback BlockReplaceObjectGeometryCallback = HandleBlockReplaceObjectGeometry;
        private static readonly NativeGhBridgeCallback BlockTransformObjectCallback = HandleBlockTransformObject;
        private static readonly NativeGhBridgeCallback CreateGeometryCallback = HandleCreateGeometry;
        private static readonly NativeGhBridgeCallback UvPlanarCallback = HandleUvPlanar;
        private static readonly NativeGhBridgeCallback GameExportPrepareCallback = HandleGameExportPrepare;
        private static readonly NativeGhBridgeCallback ScriptParamsCallback = HandleScriptParams;
        private static readonly NativeGhBridgeCallback BakeOutputCallback = HandleBakeOutput;

        private static bool _isRegistered;
        private static bool _registrationErrorLogged;
        private static RegisterGhBridgeDelegate? _registerBridge;
        private static ClearGhBridgeDelegate? _clearBridge;

        [UnmanagedFunctionPointer(CallingConvention.StdCall)]
        private delegate int NativeGhBridgeCallback(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode);

        [UnmanagedFunctionPointer(CallingConvention.StdCall)]
        private delegate int RegisterGhBridgeDelegate(ref NativeGhBridgeRegistration registration);

        [UnmanagedFunctionPointer(CallingConvention.StdCall)]
        private delegate void ClearGhBridgeDelegate();

        [StructLayout(LayoutKind.Sequential)]
        private struct NativeGhBridgeRegistration
        {
            public uint StructSize;
            public uint Version;
            public IntPtr GhStatus;
            public IntPtr GhDocument;
            public IntPtr GhQuery;
            public IntPtr GhSelection;
            public IntPtr GhCategories;
            public IntPtr GhLibrary;
            public IntPtr GhGetValue;
            public IntPtr GhConnections;
            public IntPtr GhGroups;
            public IntPtr GhComponent;
            public IntPtr GhInspectOutput;
            public IntPtr GhErrors;
            public IntPtr GhGetReference;
            public IntPtr GhSetScript;
            public IntPtr GhPreview;
            public IntPtr GhClear;
            public IntPtr GhOpenDocument;
            public IntPtr GhNewDocument;
            public IntPtr GhSetReference;
            public IntPtr GhClearReference;
            public IntPtr GhMove;
            public IntPtr GhGroup;
            public IntPtr GhGroupResize;
            public IntPtr GhCluster;
            public IntPtr GhExploreSelection;
            public IntPtr GhExploreCluster;
            public IntPtr GhBatchComponentInfo;
            public IntPtr GhCreateComponent;
            public IntPtr GhCreateSlider;
            public IntPtr GhCreatePanel;
            public IntPtr GhConnect;
            public IntPtr GhDisconnect;
            public IntPtr GhSetValue;
            public IntPtr GhDelete;
            public IntPtr GhSolve;
            // Canvas Graph Protocol
            public IntPtr GhSnapshot;
            public IntPtr GhEdit;
            public IntPtr GhUndo;
            public IntPtr GhCanvasFocus;
            public IntPtr GhCanvasZoom;
            public IntPtr GhCanvasImage;
            public IntPtr GhMake2d;
            public IntPtr GumballExtrude;
            public IntPtr GumballCut;
            public IntPtr GumballSettings;
            public IntPtr BlockSetLayers;
            public IntPtr BlockSetMaterials;
            public IntPtr BlockSetInstanceProperties;
            public IntPtr BlockSetInstanceVisibility;
            public IntPtr BlockTransformInstance;
            public IntPtr BlockArrayInstances;
            public IntPtr BlockSetObjectColors;
            public IntPtr BlockSetObjectNames;
            public IntPtr BlockSetObjectUserStrings;
            public IntPtr BlockFindInstances;
            public IntPtr BlockUserStrings;
            public IntPtr BlockObjectsDetailed;
            public IntPtr BlockReplaceObjectGeometry;
            public IntPtr BlockTransformObject;
            public IntPtr CreateGeometry;
            public IntPtr UvPlanar;
            public IntPtr GameExportPrepare;
            public IntPtr GhScriptParams;
            public IntPtr GhBakeOutput;
        }

        [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Ansi)]
        private static extern IntPtr GetProcAddress(IntPtr hModule, string procName);

        public static bool TryRegister()
        {
            lock (Sync)
            {
                if (_isRegistered)
                {
                    return true;
                }

                if (!TryResolveNativeExports(out var registerBridge, out var clearBridge))
                {
                    return false;
                }

                var registration = new NativeGhBridgeRegistration
                {
                    StructSize = (uint)Marshal.SizeOf<NativeGhBridgeRegistration>(),
                    Version = BridgeAbiVersion,
                    GhStatus = Marshal.GetFunctionPointerForDelegate(StatusCallback),
                    GhDocument = Marshal.GetFunctionPointerForDelegate(DocumentCallback),
                    GhQuery = Marshal.GetFunctionPointerForDelegate(QueryCallback),
                    GhSelection = Marshal.GetFunctionPointerForDelegate(SelectionCallback),
                    GhCategories = Marshal.GetFunctionPointerForDelegate(CategoriesCallback),
                    GhLibrary = Marshal.GetFunctionPointerForDelegate(LibraryCallback),
                    GhGetValue = Marshal.GetFunctionPointerForDelegate(GetValueCallback),
                    GhConnections = Marshal.GetFunctionPointerForDelegate(ConnectionsCallback),
                    GhGroups = Marshal.GetFunctionPointerForDelegate(GroupsCallback),
                    GhComponent = Marshal.GetFunctionPointerForDelegate(ComponentCallback),
                    GhInspectOutput = Marshal.GetFunctionPointerForDelegate(InspectOutputCallback),
                    GhErrors = Marshal.GetFunctionPointerForDelegate(ErrorsCallback),
                    GhGetReference = Marshal.GetFunctionPointerForDelegate(GetReferenceCallback),
                    GhSetScript = Marshal.GetFunctionPointerForDelegate(SetScriptCallback),
                    GhPreview = Marshal.GetFunctionPointerForDelegate(PreviewCallback),
                    GhClear = Marshal.GetFunctionPointerForDelegate(ClearCallback),
                    GhOpenDocument = Marshal.GetFunctionPointerForDelegate(OpenDocumentCallback),
                    GhNewDocument = Marshal.GetFunctionPointerForDelegate(NewDocumentCallback),
                    GhSetReference = Marshal.GetFunctionPointerForDelegate(SetReferenceCallback),
                    GhClearReference = Marshal.GetFunctionPointerForDelegate(ClearReferenceCallback),
                    GhMove = Marshal.GetFunctionPointerForDelegate(MoveCallback),
                    GhGroup = Marshal.GetFunctionPointerForDelegate(GroupCallback),
                    GhGroupResize = Marshal.GetFunctionPointerForDelegate(GroupResizeCallback),
                    GhCluster = Marshal.GetFunctionPointerForDelegate(ClusterCallback),
                    GhExploreSelection = Marshal.GetFunctionPointerForDelegate(ExploreSelectionCallback),
                    GhExploreCluster = Marshal.GetFunctionPointerForDelegate(ExploreClusterCallback),
                    GhBatchComponentInfo = Marshal.GetFunctionPointerForDelegate(BatchComponentInfoCallback),
                    GhCreateComponent = Marshal.GetFunctionPointerForDelegate(CreateComponentCallback),
                    GhCreateSlider = Marshal.GetFunctionPointerForDelegate(CreateSliderCallback),
                    GhCreatePanel = Marshal.GetFunctionPointerForDelegate(CreatePanelCallback),
                    GhConnect = Marshal.GetFunctionPointerForDelegate(ConnectCallback),
                    GhDisconnect = Marshal.GetFunctionPointerForDelegate(DisconnectCallback),
                    GhSetValue = Marshal.GetFunctionPointerForDelegate(SetValueCallback),
                    GhDelete = Marshal.GetFunctionPointerForDelegate(DeleteCallback),
                    GhSolve = Marshal.GetFunctionPointerForDelegate(SolveCallback),
                    // Canvas Graph Protocol
                    GhSnapshot = Marshal.GetFunctionPointerForDelegate(SnapshotCallback),
                    GhEdit = Marshal.GetFunctionPointerForDelegate(EditCallback),
                    GhUndo = Marshal.GetFunctionPointerForDelegate(UndoCallback),
                    GhCanvasFocus = Marshal.GetFunctionPointerForDelegate(CanvasFocusCallback),
                    GhCanvasZoom = Marshal.GetFunctionPointerForDelegate(CanvasZoomCallback),
                    GhCanvasImage = Marshal.GetFunctionPointerForDelegate(CanvasImageCallback),
                    GhMake2d = Marshal.GetFunctionPointerForDelegate(Make2dCallback),
                    GumballExtrude = Marshal.GetFunctionPointerForDelegate(GumballExtrudeCallback),
                    GumballCut = Marshal.GetFunctionPointerForDelegate(GumballCutCallback),
                    GumballSettings = Marshal.GetFunctionPointerForDelegate(GumballSettingsCallback),
                    BlockSetLayers = Marshal.GetFunctionPointerForDelegate(BlockSetLayersCallback),
                    BlockSetMaterials = Marshal.GetFunctionPointerForDelegate(BlockSetMaterialsCallback),
                    BlockSetInstanceProperties = Marshal.GetFunctionPointerForDelegate(BlockSetInstancePropertiesCallback),
                    BlockSetInstanceVisibility = Marshal.GetFunctionPointerForDelegate(BlockSetInstanceVisibilityCallback),
                    BlockTransformInstance = Marshal.GetFunctionPointerForDelegate(BlockTransformInstanceCallback),
                    BlockArrayInstances = Marshal.GetFunctionPointerForDelegate(BlockArrayInstancesCallback),
                    BlockSetObjectColors = Marshal.GetFunctionPointerForDelegate(BlockSetObjectColorsCallback),
                    BlockSetObjectNames = Marshal.GetFunctionPointerForDelegate(BlockSetObjectNamesCallback),
                    BlockSetObjectUserStrings = Marshal.GetFunctionPointerForDelegate(BlockSetObjectUserStringsCallback),
                    BlockFindInstances = Marshal.GetFunctionPointerForDelegate(BlockFindInstancesCallback),
                    BlockUserStrings = Marshal.GetFunctionPointerForDelegate(BlockUserStringsCallback),
                    BlockObjectsDetailed = Marshal.GetFunctionPointerForDelegate(BlockObjectsDetailedCallback),
                    BlockReplaceObjectGeometry = Marshal.GetFunctionPointerForDelegate(BlockReplaceObjectGeometryCallback),
                    BlockTransformObject = Marshal.GetFunctionPointerForDelegate(BlockTransformObjectCallback),
                    CreateGeometry = Marshal.GetFunctionPointerForDelegate(CreateGeometryCallback),
                    UvPlanar = Marshal.GetFunctionPointerForDelegate(UvPlanarCallback),
                    GameExportPrepare = Marshal.GetFunctionPointerForDelegate(GameExportPrepareCallback),
                    GhScriptParams = Marshal.GetFunctionPointerForDelegate(ScriptParamsCallback),
                    GhBakeOutput = Marshal.GetFunctionPointerForDelegate(BakeOutputCallback),
                };

                var rc = registerBridge(ref registration);
                if (rc != 0)
                {
                    if (!_registrationErrorLogged)
                    {
                        RhinoApp.WriteLine($"Rook: native GH bridge registration failed ({rc}).");
                        _registrationErrorLogged = true;
                    }
                    return false;
                }

                _registerBridge = registerBridge;
                _clearBridge = clearBridge;
                _isRegistered = true;
                _registrationErrorLogged = false;
                RhinoApp.WriteLine("Rook: native GH callback bridge registered.");
                return true;
            }
        }

        public static void ClearRegistration()
        {
            lock (Sync)
            {
                if (!_isRegistered || _clearBridge == null)
                {
                    return;
                }

                _clearBridge();
                _isRegistered = false;
                _registerBridge = null;
                _clearBridge = null;
            }
        }

        private static bool TryResolveNativeExports(
            out RegisterGhBridgeDelegate registerBridge,
            out ClearGhBridgeDelegate clearBridge)
        {
            registerBridge = null!;
            clearBridge = null!;

            var module = Process.GetCurrentProcess()
                .Modules
                .Cast<ProcessModule>()
                .FirstOrDefault(m => string.Equals(m.ModuleName, "RookNative.rhp", StringComparison.OrdinalIgnoreCase));
            if (module == null || module.BaseAddress == IntPtr.Zero)
            {
                return false;
            }

            var registerPtr = GetProcAddress(module.BaseAddress, "RookRegisterGhBridge");
            var clearPtr = GetProcAddress(module.BaseAddress, "RookClearGhBridge");
            if (registerPtr == IntPtr.Zero || clearPtr == IntPtr.Zero)
            {
                if (!_registrationErrorLogged)
                {
                    RhinoApp.WriteLine("Rook: native GH bridge exports not found in RookNative.rhp.");
                    _registrationErrorLogged = true;
                }
                return false;
            }

            registerBridge = Marshal.GetDelegateForFunctionPointer<RegisterGhBridgeDelegate>(registerPtr);
            clearBridge = Marshal.GetDelegateForFunctionPointer<ClearGhBridgeDelegate>(clearPtr);
            return true;
        }

        private static int HandleStatus(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteReadOnlyCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                () => Core.GetStatus());
        }

        private static int HandleDocument(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteReadOnlyCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                () => Core.GetDocumentInfo());
        }

        private static int HandleQuery(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteReadOnlyCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                () => Core.QueryDocument());
        }

        private static int HandleSelection(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteReadOnlyCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                () => Core.GetSelection());
        }

        private static int HandleCategories(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                _ => Handler.GetCategories());
        }

        private static int HandleLibrary(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson =>
                {
                    var args = ParseRequestArgs(requestJson);
                    return Handler.SearchLibrary(
                        GetStringArg(args, "search"),
                        GetStringArg(args, "category"),
                        GetIntArg(args, "limit") ?? 50,
                        GetBoolArg(args, "audit"),
                        GetBoolArg(args, "exact"));
                });
        }

        private static int HandleGetValue(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Handler.GetValue(GetStringArg(ParseRequestArgs(requestJson), "guid")));
        }

        private static int HandleConnections(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Handler.GetConnections(GetStringArg(ParseRequestArgs(requestJson), "guid")));
        }

        private static int HandleGroups(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                _ => Handler.GetGroups());
        }

        private static int HandleComponent(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Handler.GetComponentInfo(GetStringArg(ParseRequestArgs(requestJson), "guid")));
        }

        private static int HandleInspectOutput(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson =>
                {
                    var args = ParseRequestArgs(requestJson);
                    return Handler.InspectOutput(
                        GetStringArg(args, "guid"),
                        GetStringArg(args, "param"));
                });
        }

        private static int HandleErrors(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Handler.GetCanvasErrors(GetBoolArg(ParseRequestArgs(requestJson), "debug")));
        }

        private static int HandleGetReference(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Handler.GetReference(GetStringArg(ParseRequestArgs(requestJson), "guid")));
        }

        private static int HandleSetScript(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Handler.SetScript(requestJson));
        }

        private static int HandleScriptParams(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Handler.ScriptParams(requestJson));
        }

        private static int HandleBakeOutput(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Handler.BakeOutput(requestJson));
        }

        private static int HandlePreview(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Handler.SetPreview(requestJson));
        }

        private static int HandleClear(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                _ => Handler.ClearCanvas());
        }

        private static int HandleOpenDocument(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Handler.OpenDocument(requestJson));
        }

        private static int HandleNewDocument(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                _ => Handler.NewDocument());
        }

        private static int HandleSetReference(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Handler.SetReference(requestJson));
        }

        private static int HandleClearReference(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Handler.ClearReference(requestJson));
        }

        private static int HandleMove(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Handler.MoveObjects(requestJson));
        }

        private static int HandleGroup(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Handler.CreateGroup(requestJson));
        }

        private static int HandleGroupResize(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Handler.ResizeGroupToFit(requestJson));
        }

        private static int HandleCluster(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Handler.CreateCluster(requestJson));
        }

        private static int HandleExploreSelection(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Handler.ExploreSelection(requestJson));
        }

        private static int HandleExploreCluster(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Handler.ExploreCluster(requestJson));
        }

        private static int HandleBatchComponentInfo(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Handler.HandleBatchComponentInfo(requestJson));
        }

        private static int HandleCreateComponent(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Handler.CreateComponent(requestJson));
        }

        private static int HandleConnect(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Handler.ConnectComponents(requestJson));
        }

        private static int HandleCreateSlider(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Handler.CreateSlider(requestJson));
        }

        private static int HandleCreatePanel(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Handler.CreatePanel(requestJson));
        }

        private static int HandleDisconnect(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Handler.DisconnectComponents(requestJson));
        }

        private static int HandleSetValue(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Handler.SetValue(requestJson));
        }

        private static int HandleDelete(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Handler.DeleteObjects(requestJson));
        }

        private static int HandleSolve(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Handler.TriggerSolve(requestJson));
        }

        // Canvas Graph Protocol handlers
        private static int HandleSnapshot(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Handler.TakeSnapshot(requestJson));
        }

        private static int HandleEdit(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Handler.ApplyEdit(requestJson));
        }

        private static int HandleUndo(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                _ => Handler.UndoCanvas());
        }

        private static int HandleCanvasFocus(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Handler.FocusCanvas(requestJson));
        }

        private static int HandleCanvasZoom(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Handler.ZoomCanvas(requestJson));
        }

        private static int HandleCanvasImage(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Handler.CaptureCanvasImage(requestJson));
        }

        private static int HandleMake2d(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Make2dHandler.Make2d(requestJson));
        }

        private static int HandleGumballExtrude(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Gumball.Extrude(requestJson));
        }

        private static int HandleGumballCut(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Gumball.Cut(requestJson));
        }

        private static int HandleGumballSettings(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Gumball.Settings(requestJson));
        }

        private static int HandleBlockSetLayers(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Blocks.SetBlockObjectLayers(requestJson));
        }

        private static int HandleBlockSetMaterials(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Blocks.SetBlockObjectMaterials(requestJson));
        }

        private static int HandleBlockSetInstanceProperties(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Blocks.SetInstanceProperties(requestJson));
        }

        private static int HandleBlockSetInstanceVisibility(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Blocks.SetInstanceVisibility(requestJson));
        }

        private static int HandleBlockTransformInstance(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Blocks.TransformInstance(requestJson));
        }

        private static int HandleBlockArrayInstances(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Blocks.ArrayInstances(requestJson));
        }

        private static int HandleBlockSetObjectColors(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Blocks.SetBlockObjectColors(requestJson));
        }

        private static int HandleBlockSetObjectNames(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Blocks.SetBlockObjectNames(requestJson));
        }

        private static int HandleBlockSetObjectUserStrings(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Blocks.SetBlockObjectUserStrings(requestJson));
        }

        private static int HandleBlockFindInstances(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Blocks.FindInstances(requestJson));
        }

        private static int HandleBlockUserStrings(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Blocks.BlockUserStrings(requestJson));
        }

        private static int HandleBlockObjectsDetailed(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson =>
                {
                    string? blockName = null;
                    if (!string.IsNullOrEmpty(requestJson))
                    {
                        try
                        {
                            var request = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(requestJson);
                            if (request != null &&
                                request.TryGetValue("name", out var nameEl) &&
                                nameEl.ValueKind == JsonValueKind.String)
                            {
                                blockName = nameEl.GetString();
                            }
                        }
                        catch
                        {
                        }
                    }
                    return Blocks.GetBlockObjectsDetailed(blockName);
                });
        }

        private static int HandleBlockReplaceObjectGeometry(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Blocks.ReplaceObjectGeometry(requestJson));
        }

        private static int HandleBlockTransformObject(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Blocks.TransformBlockObject(requestJson));
        }

        private static int HandleCreateGeometry(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => Create.CreateGeometry(requestJson));
        }

        private static int HandleUvPlanar(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => TextureMapping.ApplyPlanarMapping(requestJson));
        }

        private static int HandleGameExportPrepare(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => GameExport.PrepareForGameExport(requestJson));
        }

        private static int ExecuteReadOnlyCallback<T>(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode,
            Func<BridgeResult<T>> operation)
        {
            try
            {
                var requestJson = ReadUtf8(requestJsonUtf8, requestJsonLength);
                string responseJson = string.Empty;
                int statusCode = 500;

                var waitHandle = new ManualResetEventSlim(false);
                RhinoApp.InvokeOnUiThread(new Action(() =>
                {
                    try
                    {
                        var targetDoc = ParseDocumentSerialNumber(requestJson);
                        var result = DocumentContext.WithDocument(targetDoc, operation);
                        object? data = result.Success ? result.Data : result.Error;
                        responseJson = JsonSerializer.Serialize(new
                        {
                            success = result.Success,
                            data
                        }, JsonOptions);
                        statusCode = result.Success ? 200 : 400;
                    }
                    catch (Exception ex)
                    {
                        responseJson = JsonSerializer.Serialize(new
                        {
                            success = false,
                            data = ex.Message
                        }, JsonOptions);
                        statusCode = 400;
                    }
                    finally
                    {
                        waitHandle.Set();
                    }
                }));

                if (!waitHandle.Wait(TimeSpan.FromSeconds(30)))
                {
                    responseJson = JsonSerializer.Serialize(new
                    {
                        success = false,
                        data = "GH callback request timed out."
                    }, JsonOptions);
                    statusCode = 400;
                }

                return WriteUtf8Response(
                    responseJsonUtf8,
                    responseJsonCapacity,
                    responseJsonLength,
                    httpStatusCode,
                    responseJson,
                    statusCode);
            }
            catch (Exception ex)
            {
                return WriteUtf8Response(
                    responseJsonUtf8,
                    responseJsonCapacity,
                    responseJsonLength,
                    httpStatusCode,
                    JsonSerializer.Serialize(new
                    {
                        success = false,
                        data = $"Native GH bridge failed: {ex.Message}"
                    }, JsonOptions),
                    500);
            }
        }

        private static int ExecuteApiResponseCallback(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode,
            Func<string, ApiResponse> operation)
        {
            try
            {
                var requestJson = ReadUtf8(requestJsonUtf8, requestJsonLength);
                string responseJson = string.Empty;
                int statusCode = 500;

                var waitHandle = new ManualResetEventSlim(false);
                RhinoApp.InvokeOnUiThread(new Action(() =>
                {
                    try
                    {
                        var targetDoc = ParseDocumentSerialNumber(requestJson);
                        var result = DocumentContext.WithDocument(targetDoc, () => operation(requestJson));
                        responseJson = JsonSerializer.Serialize(new
                        {
                            success = result.Success,
                            data = result.Data
                        }, JsonOptions);
                        statusCode = result.Success ? 200 : 400;
                    }
                    catch (Exception ex)
                    {
                        responseJson = JsonSerializer.Serialize(new
                        {
                            success = false,
                            data = ex.Message
                        }, JsonOptions);
                        statusCode = 400;
                    }
                    finally
                    {
                        waitHandle.Set();
                    }
                }));

                if (!waitHandle.Wait(TimeSpan.FromSeconds(30)))
                {
                    responseJson = JsonSerializer.Serialize(new
                    {
                        success = false,
                        data = "GH callback request timed out."
                    }, JsonOptions);
                    statusCode = 400;
                }

                return WriteUtf8Response(
                    responseJsonUtf8,
                    responseJsonCapacity,
                    responseJsonLength,
                    httpStatusCode,
                    responseJson,
                    statusCode);
            }
            catch (Exception ex)
            {
                return WriteUtf8Response(
                    responseJsonUtf8,
                    responseJsonCapacity,
                    responseJsonLength,
                    httpStatusCode,
                    JsonSerializer.Serialize(new
                    {
                        success = false,
                        data = $"Native GH bridge failed: {ex.Message}"
                    }, JsonOptions),
                    500);
            }
        }

        private static uint? ParseDocumentSerialNumber(string? requestJson)
        {
            var args = ParseRequestArgs(requestJson);
            if (args != null &&
                args.TryGetValue("documentSerialNumber", out var serialElement) &&
                serialElement.ValueKind == JsonValueKind.Number)
            {
                return serialElement.GetUInt32();
            }

            return null;
        }

        private static Dictionary<string, JsonElement>? ParseRequestArgs(string? requestJson)
        {
            if (string.IsNullOrWhiteSpace(requestJson))
            {
                return null;
            }

            try
            {
                return JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(requestJson);
            }
            catch
            {
                // Treat request parsing as non-fatal for bridge routing.
                return null;
            }
        }

        private static string? GetStringArg(Dictionary<string, JsonElement>? args, string name)
        {
            if (args == null || !args.TryGetValue(name, out var value))
            {
                return null;
            }

            return value.ValueKind switch
            {
                JsonValueKind.String => value.GetString(),
                JsonValueKind.Number => value.ToString(),
                JsonValueKind.True => bool.TrueString,
                JsonValueKind.False => bool.FalseString,
                _ => null,
            };
        }

        private static int? GetIntArg(Dictionary<string, JsonElement>? args, string name)
        {
            if (args == null || !args.TryGetValue(name, out var value))
            {
                return null;
            }

            if (value.ValueKind == JsonValueKind.Number && value.TryGetInt32(out var intValue))
            {
                return intValue;
            }

            if (value.ValueKind == JsonValueKind.String &&
                int.TryParse(value.GetString(), out intValue))
            {
                return intValue;
            }

            return null;
        }

        private static bool GetBoolArg(Dictionary<string, JsonElement>? args, string name)
        {
            if (args == null || !args.TryGetValue(name, out var value))
            {
                return false;
            }

            if (value.ValueKind == JsonValueKind.True)
            {
                return true;
            }

            if (value.ValueKind == JsonValueKind.False)
            {
                return false;
            }

            if (value.ValueKind == JsonValueKind.String &&
                bool.TryParse(value.GetString(), out var boolValue))
            {
                return boolValue;
            }

            return false;
        }

        private static string ReadUtf8(IntPtr pointer, int length)
        {
            if (pointer == IntPtr.Zero || length <= 0)
            {
                return string.Empty;
            }

            var buffer = new byte[length];
            Marshal.Copy(pointer, buffer, 0, length);
            return Encoding.UTF8.GetString(buffer);
        }

        private static int WriteUtf8Response(
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode,
            string json,
            int statusCode)
        {
            if (httpStatusCode != IntPtr.Zero)
            {
                Marshal.WriteInt32(httpStatusCode, statusCode);
            }

            var bytes = Encoding.UTF8.GetBytes(json + "\0");
            if (responseJsonLength != IntPtr.Zero)
            {
                Marshal.WriteInt32(responseJsonLength, bytes.Length - 1);
            }

            if (responseJsonUtf8 == IntPtr.Zero || responseJsonCapacity < bytes.Length)
            {
                return -2;
            }

            Marshal.Copy(bytes, 0, responseJsonUtf8, bytes.Length);
            return 0;
        }
    }
}
