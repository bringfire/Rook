using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rhino;
using Rook.Handlers;
using Rook.Services.Vision;
using Rook.Services.Vision.CanvasDirector;
using Rook.Services.Vision.Generation;

namespace Rook.InternalBridge
{
    /// <summary>
    /// Registers GH callbacks with the native plugin from Rhino's real managed runtime.
    /// This keeps GH execution in the same runtime/load context as Grasshopper itself.
    /// </summary>
    public static class NativeGhBridgeRegistrar
    {
        private const uint BridgeAbiVersion = 18;
        private static readonly object Sync = new();
        private static readonly IGrasshopperCore Core = new GrasshopperCore();
        private static readonly GrasshopperHandler Handler = new();
        private static readonly GumballHandler Gumball = new();
        private static readonly BlocksHandler Blocks = new();
        private static readonly CreateHandler Create = new();
        private static readonly TextureMappingHandler TextureMapping = new();
        private static readonly GameExportHandler GameExport = new();
        private static readonly ViewportHandler Viewport = new();
        private static readonly BimHandler Bim = new();
        // Image handler. Shares the same ArtifactStore + VisionSecretStore
        // as the Vision tab and the V2 video subsystem via
        // RookSubsystemRoot.Instance. Codex review of step 7 caught that
        // a fresh `new VisionHandler()` here would spawn independent
        // store instances pointing at the same disk root — they'd see
        // each other's writes through disk but hold separate in-memory
        // caches, defeating the V2 shared-singleton invariant.
        // BuildSharedVisionHandler mirrors VisionWebSurface's helper.
        private static readonly VisionHandler Vision = BuildSharedVisionHandler();
        private static readonly CanvasDirectorHandler CanvasDirector = new();

        private static VisionHandler BuildSharedVisionHandler()
        {
            return new VisionHandler(
                artifactStore: RookSubsystemRoot.Instance.SharedArtifactStore,
                generationSecrets: RookSubsystemRoot.Instance.SharedGenerationSecretStore,
                enhancer: new PromptEnhancer(),
                viewportHandler: new ViewportHandler());
        }

        // V2 video. Lazy so processes that never touch video (image-only,
        // command-only) don't pay the registry-validation + Veo-provider
        // construction cost. The Lazy is process-scoped via the registrar's
        // type-init lifetime; first video op triggers RookSubsystemRoot.Video
        // which itself lazily builds the bundle. Both lazies are
        // ExecutionAndPublication-safe.
        private static readonly Lazy<VideoOpHandler> _videoOpHandler =
            new(() =>
            {
                var bundle = RookSubsystemRoot.Instance.Video;
                return new VideoOpHandler(
                    bundle.Manager, bundle.Registry, bundle.Estimator);
            }, LazyThreadSafetyMode.ExecutionAndPublication);

        // Authoritative set of vision ops the trampoline routes. Used by
        // the unknown-op error-message builder so the rejection message
        // stays in sync with the switch. If a new op is added to the
        // switch but not to this set, the message will say "Unknown
        // vision op" without listing it — drift signal that tests catch.
        internal static readonly IReadOnlyCollection<string> ExpectedVisionOps =
            new HashSet<string>(StringComparer.Ordinal)
            {
                // Image (PR-5a/5b)
                "capture_depth",
                "generate",
                "enhance_prompt",
                "list_artifacts",
                "get_artifact",
                "approve_artifact",
                "delete_artifact",
                "consume_approved",
                // Director publish
                "publish_director_video",
                // V2 video
                VideoOpHandler.OpSubmit,
                VideoOpHandler.OpStatus,
                VideoOpHandler.OpCancel,
                VideoOpHandler.OpResult,
                VideoOpHandler.OpEstimate,
                // V4 video — list ops promoted from bridge-only (V3) to
                // native HTTP. Routed via DispatchOffUi (30 s timeout)
                // alongside the V2 status/result/estimate read ops.
                VideoOpHandler.OpListJobs,
                VideoOpHandler.OpListModels,
                // Presentation reconciler (spec 2026-06-10): typed
                // dump/repair ops behind POST /vision/presentation.
                // Native constructs these op bodies itself — no
                // user-controlled bytes pass through the route.
                "get_presentation_diagnostics",
                "repair_presentation",
            };

        /// <summary>
        /// Build the structured "Unknown vision op" message. Pulls the
        /// expected list from <see cref="ExpectedVisionOps"/> so the
        /// message and the switch share a single source of truth.
        /// </summary>
        internal static string BuildUnknownOpMessage(string? op)
        {
            if (string.IsNullOrEmpty(op))
                return "Vision request missing required 'op' discriminator.";

            var sorted = new List<string>(ExpectedVisionOps);
            sorted.Sort(StringComparer.Ordinal);
            var quoted = new List<string>(sorted.Count);
            foreach (var s in sorted) quoted.Add($"'{s}'");
            return $"Unknown vision op '{op}'. Expected one of: {string.Join(", ", quoted)}.";
        }
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
        private static readonly NativeGhBridgeCallback SolveReadinessCallback = HandleSolveReadiness;
        private static readonly NativeGhBridgeCallback WaitForSolveReadinessCallback = HandleWaitForSolveReadiness;
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
        private static readonly NativeGhBridgeCallback BlockSetLayersBatchCallback = HandleBlockSetLayersBatch;
        private static readonly NativeGhBridgeCallback BlockSetMaterialsCallback = HandleBlockSetMaterials;
        private static readonly NativeGhBridgeCallback BlockSetMaterialsBatchCallback = HandleBlockSetMaterialsBatch;
        private static readonly NativeGhBridgeCallback BlockSetObjectColorsBatchCallback = HandleBlockSetObjectColorsBatch;
        private static readonly NativeGhBridgeCallback BlockSetObjectUserStringsBatchCallback = HandleBlockSetObjectUserStringsBatch;
        private static readonly NativeGhBridgeCallback BlockSetObjectNamesBatchCallback = HandleBlockSetObjectNamesBatch;
        private static readonly NativeGhBridgeCallback BlockTransformInstanceBatchCallback = HandleBlockTransformInstanceBatch;
        private static readonly NativeGhBridgeCallback BlockReplaceObjectGeometryBatchCallback = HandleBlockReplaceObjectGeometryBatch;
        private static readonly NativeGhBridgeCallback BlockTransformObjectBatchCallback = HandleBlockTransformObjectBatch;
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
        private static readonly NativeGhBridgeCallback ViewportCaptureTier3Callback = HandleViewportCaptureTier3;
        private static readonly NativeGhBridgeCallback VisionDispatchCallback = HandleVisionDispatch;
        private static readonly NativeGhBridgeCallback CanvasDirectorDispatchCallback = HandleCanvasDirectorDispatch;
        private static readonly NativeGhBridgeCallback BimDispatchCallback = HandleBimDispatch;
        private static readonly NativeGhBridgeCallback ReconstructionDispatchCallback = HandleReconstructionDispatch;

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
            // ABI v8: batch block operations
            public IntPtr BlockSetLayersBatch;
            // ABI v9: more batch block operations
            public IntPtr BlockSetMaterialsBatch;
            public IntPtr BlockSetObjectColorsBatch;
            public IntPtr BlockSetObjectUserStringsBatch;
            public IntPtr BlockSetObjectNamesBatch;
            // ABI v10: batch block-instance transform
            public IntPtr BlockTransformInstanceBatch;
            // ABI v11: batch replace-object-geometry
            public IntPtr BlockReplaceObjectGeometryBatch;
            // ABI v12: batch transform-object
            public IntPtr BlockTransformObjectBatch;
            // ABI v13: Tier 3 viewport capture (SDK-backed, managed-side)
            public IntPtr ViewportCaptureTier3;
            // ABI v14: Vision domain — single generic dispatch; op
            // discriminator is carried in the request JSON and routed
            // inside VisionHandler.cs (the single validation boundary).
            public IntPtr VisionDispatch;
            // ABI v17: CanvasDirector domain — single generic dispatch.
            // Task 2 supplies the managed handler; Task 1 keeps ABI parity.
            public IntPtr CanvasDirectorDispatch;
            // ABI v15: BIM domain — single generic dispatch; op
            // discriminator is carried in the request JSON and routed
            // inside BimHandler.cs.
            public IntPtr BimDispatch;
            // ABI v16: Reconstruction domain — single generic dispatch.
            public IntPtr ReconstructionDispatch;
            // ABI v18: solve-readiness status and bounded off-UI wait.
            public IntPtr GhSolveReadiness;
            public IntPtr GhWaitForSolveReadiness;
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
                    BlockSetLayersBatch = Marshal.GetFunctionPointerForDelegate(BlockSetLayersBatchCallback),
                    BlockSetMaterialsBatch = Marshal.GetFunctionPointerForDelegate(BlockSetMaterialsBatchCallback),
                    BlockSetObjectColorsBatch = Marshal.GetFunctionPointerForDelegate(BlockSetObjectColorsBatchCallback),
                    BlockSetObjectUserStringsBatch = Marshal.GetFunctionPointerForDelegate(BlockSetObjectUserStringsBatchCallback),
                    BlockSetObjectNamesBatch = Marshal.GetFunctionPointerForDelegate(BlockSetObjectNamesBatchCallback),
                    BlockTransformInstanceBatch = Marshal.GetFunctionPointerForDelegate(BlockTransformInstanceBatchCallback),
                    BlockReplaceObjectGeometryBatch = Marshal.GetFunctionPointerForDelegate(BlockReplaceObjectGeometryBatchCallback),
                    BlockTransformObjectBatch = Marshal.GetFunctionPointerForDelegate(BlockTransformObjectBatchCallback),
                    ViewportCaptureTier3 = Marshal.GetFunctionPointerForDelegate(ViewportCaptureTier3Callback),
                    VisionDispatch = Marshal.GetFunctionPointerForDelegate(VisionDispatchCallback),
                    CanvasDirectorDispatch = Marshal.GetFunctionPointerForDelegate(CanvasDirectorDispatchCallback),
                    BimDispatch = Marshal.GetFunctionPointerForDelegate(BimDispatchCallback),
                    ReconstructionDispatch = Marshal.GetFunctionPointerForDelegate(ReconstructionDispatchCallback),
                    GhSolveReadiness = Marshal.GetFunctionPointerForDelegate(SolveReadinessCallback),
                    GhWaitForSolveReadiness = Marshal.GetFunctionPointerForDelegate(WaitForSolveReadinessCallback),
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
            return ExecuteApiResponseCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                _ => Handler.GetStatus());
        }

        private static int HandleDocument(
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
                DocumentForBridge);
        }

        private static int HandleQuery(
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
                QueryDocumentForBridge);
        }

        internal static ApiResponse QueryDocumentForBridge(string requestJson)
        {
            return Handler.QueryDocument();
        }

        internal static ApiResponse DocumentForBridge(string requestJson)
        {
            return Handler.GetDocumentInfo();
        }

        internal static ApiResponse ConnectForBridge(string requestJson)
        {
            return Handler.ConnectComponents(requestJson);
        }

        internal static ApiResponse CreateSliderForBridge(string requestJson)
        {
            return Handler.CreateSlider(requestJson);
        }

        internal static ApiResponse SetValueForBridge(string requestJson)
        {
            return Handler.SetValue(requestJson);
        }

        private static int HandleSelection(
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
                requestJson => Handler.GetSelection());
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
                InspectOutputForBridge);
        }

        internal static ApiResponse InspectOutputForBridge(string requestJson)
        {
            var args = ParseRequestArgs(requestJson);
            if (!GhInspectOutputSelectorResolver.TryParse(args, out var selector, out var error))
                return error!.ToApiResponse();

            return Handler.InspectOutput(
                GetStringArg(args, "guid"),
                selector,
                GetStringArg(args, "readiness_receipt_id"));
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
                ErrorsForBridge);
        }

        internal static ApiResponse ErrorsForBridge(string requestJson)
        {
            return Handler.GetCanvasErrors(GetBoolArg(ParseRequestArgs(requestJson), "debug"));
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
            string requestJson;
            try
            {
                requestJson = ReadUtf8(requestJsonUtf8, requestJsonLength);
            }
            catch
            {
                return WriteUtf8Response(
                    responseJsonUtf8,
                    responseJsonCapacity,
                    responseJsonLength,
                    httpStatusCode,
                    JsonSerializer.Serialize(new
                    {
                        success = false,
                        data = "gh_open_request_invalid",
                    }, JsonOptions),
                    400);
            }

            var preflight = GrasshopperHandler.PreflightOpenDocument(requestJson);
            if (!preflight.Success)
            {
                return WriteUtf8Response(
                    responseJsonUtf8,
                    responseJsonCapacity,
                    responseJsonLength,
                    httpStatusCode,
                    JsonSerializer.Serialize(new
                    {
                        success = false,
                        data = preflight.ErrorCode,
                    }, JsonOptions),
                    400);
            }

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
                ConnectForBridge);
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
                CreateSliderForBridge);
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
                CreatePanelForBridge);
        }

        internal static ApiResponse CreatePanelForBridge(string requestJson)
        {
            return Handler.CreatePanel(requestJson);
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
                SetValueForBridge);
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

        private static int HandleSolveReadiness(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteDirectReadinessCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => ExecuteReadinessStatusCallback(() =>
                {
                    var args = ParseRequestArgs(requestJson);
                    return Handler.GetSolveReadiness(
                        GetStringArg(args, "readiness_receipt_id"));
                }));
        }

        private static int HandleWaitForSolveReadiness(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteDirectReadinessCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode,
                requestJson => ExecuteReadinessWaitCallback(() =>
                    ExecuteReadinessWaitRequest(
                        requestJson,
                        (readinessReceiptId, timeoutMs) => Handler.WaitForSolveReadiness(
                            readinessReceiptId,
                            timeoutMs))));
        }

        private static ApiResponse ExecuteReadinessStatusCallback(Func<ApiResponse> operation)
        {
            return operation();
        }

        private static ApiResponse ExecuteReadinessWaitCallback(Func<ApiResponse> operation)
        {
            return operation();
        }

        private static int ExecuteDirectReadinessCallback(
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
                var result = ExecuteDirectGrasshopperDispatch(requestJson, operation);
                var responseJson = JsonSerializer.Serialize(new
                {
                    success = result.Success,
                    data = result.Data,
                }, JsonOptions);

                return WriteUtf8Response(
                    responseJsonUtf8,
                    responseJsonCapacity,
                    responseJsonLength,
                    httpStatusCode,
                    responseJson,
                    MapBridgeStatus(result));
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
                        data = $"Native GH readiness bridge failed: {ex.Message}",
                    }, JsonOptions),
                    500);
            }
        }

        private static ApiResponse ExecuteDirectGrasshopperDispatch(
            string requestJson,
            Func<string, ApiResponse> operation)
        {
            var args = ParseRequestArgs(requestJson);
            var rawScope = GetStringArg(args, "_rookGhDispatchScope");
            if (rawScope is null)
            {
                return operation(requestJson);
            }

            if (!string.Equals(rawScope, "observation", StringComparison.Ordinal))
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = new
                    {
                        error = "invalid_arguments",
                        message = "Readiness endpoints require an observation dispatch scope.",
                    },
                };
            }

            GrasshopperDispatchCapture? capture = null;
            Exception? captureFailure = null;
            using var waitHandle = new ManualResetEventSlim(false);
            RhinoApp.InvokeOnUiThread(new Action(() =>
            {
                try
                {
                    capture = GrasshopperDispatchContext.ProductionSource.Capture();
                }
                catch (Exception ex)
                {
                    captureFailure = ex;
                }
                finally
                {
                    waitHandle.Set();
                }
            }));

            if (!waitHandle.Wait(TimeSpan.FromSeconds(30)))
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = new { error = "gh_target_unavailable", message = "Grasshopper target capture timed out." },
                };
            }

            if (captureFailure is not null || capture is null)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = new
                    {
                        error = "gh_target_unavailable",
                        message = captureFailure?.Message ?? "Grasshopper target capture failed.",
                    },
                };
            }

            return GrasshopperDispatchContext.ExecuteCaptured(
                capture,
                () => operation(requestJson));
        }

        internal static ApiResponse ExecuteReadinessStatusForTests(Func<ApiResponse> operation)
        {
            return ExecuteReadinessStatusCallback(operation);
        }

        internal static ApiResponse ExecuteReadinessWaitForTests(Func<ApiResponse> operation)
        {
            return ExecuteReadinessWaitCallback(operation);
        }

        internal static ApiResponse ExecuteReadinessWaitForTests(
            string requestJson,
            Func<string?, int, ApiResponse> operation)
        {
            return ExecuteReadinessWaitCallback(() =>
                ExecuteReadinessWaitRequest(requestJson, operation));
        }

        private static ApiResponse ExecuteReadinessWaitRequest(
            string requestJson,
            Func<string?, int, ApiResponse> operation)
        {
            const int defaultTimeoutMs = 10_000;
            const int minimumTimeoutMs = 1;
            const int maximumTimeoutMs = 300_000;
            var args = ParseRequestArgs(requestJson);
            var timeoutMs = GetIntArg(args, "timeout_ms");
            if (args != null &&
                args.ContainsKey("timeout_ms") &&
                (!timeoutMs.HasValue ||
                 timeoutMs.Value < minimumTimeoutMs ||
                 timeoutMs.Value > maximumTimeoutMs))
            {
                return Handler.ReadinessIssueFailure("readiness_timeout_ms_out_of_range");
            }

            return operation(
                GetStringArg(args, "readiness_receipt_id"),
                timeoutMs ?? defaultTimeoutMs);
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

        private static int HandleBlockSetLayersBatch(
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
                requestJson => Blocks.SetBlockObjectLayersBatch(requestJson));
        }

        private static int HandleBlockSetMaterialsBatch(
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
                requestJson => Blocks.SetBlockObjectMaterialsBatch(requestJson));
        }

        private static int HandleBlockSetObjectColorsBatch(
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
                requestJson => Blocks.SetBlockObjectColorsBatch(requestJson));
        }

        private static int HandleBlockSetObjectUserStringsBatch(
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
                requestJson => Blocks.SetBlockObjectUserStringsBatch(requestJson));
        }

        private static int HandleBlockSetObjectNamesBatch(
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
                requestJson => Blocks.SetBlockObjectNamesBatch(requestJson));
        }

        private static int HandleBlockTransformInstanceBatch(
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
                requestJson => Blocks.TransformInstanceBatch(requestJson));
        }

        private static int HandleBlockReplaceObjectGeometryBatch(
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
                requestJson => Blocks.ReplaceObjectGeometryBatch(requestJson));
        }

        private static int HandleBlockTransformObjectBatch(
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
                requestJson => Blocks.TransformBlockObjectBatch(requestJson));
        }

        private static int HandleViewportCaptureTier3(
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
                requestJson => Viewport.CaptureTier3(requestJson));
        }

        private static int HandleVisionDispatch(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            // Peek the op discriminator to choose between the UI-thread
            // sync dispatcher (capture_depth — touches Rhino state) and
            // the off-UI async dispatcher (generate / enhance_prompt —
            // network-bound; blocking Rhino's UI thread for 30–60 s is
            // unacceptable and can deadlock HttpClient continuations that
            // capture the UI SyncContext). Unknown ops are rejected here
            // before either dispatcher is selected — prevents a bad route
            // wiring from silently hitting the off-UI boundary.
            string requestJson;
            try
            {
                requestJson = ReadUtf8(requestJsonUtf8, requestJsonLength);
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
                        data = $"Vision dispatch failed to read request: {ex.Message}"
                    }, JsonOptions),
                    500);
            }

            var op = PeekVisionOp(requestJson);

            // PR-V3 (Codex review): ExpectedVisionOps is the runtime
            // allowlist, not just a documentation set. Any op not in
            // the set is rejected before reaching the switch — so a
            // future PR that adds a case here without also updating
            // ExpectedVisionOps cannot accidentally promote a hidden
            // op to native HTTP. The containment tests pin the set;
            // this guard pins the runtime gate. (V4 added list_video_
            // jobs / list_video_models to both the set and the switch
            // intentionally.)
            if (!string.IsNullOrEmpty(op) && !ExpectedVisionOps.Contains(op))
            {
                return WriteUtf8Response(
                    responseJsonUtf8,
                    responseJsonCapacity,
                    responseJsonLength,
                    httpStatusCode,
                    JsonSerializer.Serialize(new
                    {
                        success = false,
                        data = BuildUnknownOpMessage(op),
                    }, JsonOptions),
                    400);
            }

            switch (op)
            {
                case "capture_depth":
                case "get_presentation_diagnostics":
                case "repair_presentation":
                    // UI-thread path — capture_depth needs DocumentContext
                    // + RhinoApp for viewport access (default 30 s timeout
                    // is fine; capture completes in ~1 s). The presentation
                    // ops read the surface registry / schedule repairs via
                    // the Eto UI scheduler — both return immediately
                    // (repair is accepted-and-scheduled, never blocking
                    // on the gapped toggle).
                    return ExecuteApiResponseCallback(
                        requestJsonUtf8,
                        requestJsonLength,
                        responseJsonUtf8,
                        responseJsonCapacity,
                        responseJsonLength,
                        httpStatusCode,
                        reqJson => Vision.Dispatch(reqJson));

                case "generate":
                case "enhance_prompt":
                    // Off-UI async path — Gemini network call with
                    // cooperative cancellation on the 180 s timeout.
                    return ExecuteAsyncApiResponseCallback(
                        responseJsonUtf8,
                        responseJsonCapacity,
                        responseJsonLength,
                        httpStatusCode,
                        requestJson,
                        (reqJson, ct) => Vision.DispatchAsync(reqJson, ct),
                        timeoutSeconds: 180);

                case "list_artifacts":
                case "get_artifact":
                case "approve_artifact":
                case "delete_artifact":
                case "consume_approved":
                    // Off-UI sync path — disk-only artifact-store ops.
                    // Runs on the threadpool so a large store scan or
                    // recursive delete doesn't starve the Rhino UI thread.
                    // No CancellationToken, no network-sized timeout —
                    // disk I/O is bounded and predictable; a 30 s cap is
                    // generous for the worst-case v1 store (no
                    // manifest.index.json yet).
                    return ExecuteOffUiApiResponseCallback(
                        responseJsonUtf8,
                        responseJsonCapacity,
                        responseJsonLength,
                        httpStatusCode,
                        requestJson,
                        reqJson => Vision.DispatchOffUi(reqJson),
                        timeoutSeconds: 30);

                case "publish_director_video":
                    // Off-UI sync path — disk-heavy Director publish
                    // work can hash and copy large video blobs, then
                    // re-hash the stored copy. Native still owns only
                    // dispatch; managed Vision.DispatchOffUi owns the
                    // ArtifactStore safety and publish semantics.
                    return ExecuteOffUiApiResponseCallback(
                        responseJsonUtf8,
                        responseJsonCapacity,
                        responseJsonLength,
                        httpStatusCode,
                        requestJson,
                        reqJson => Vision.DispatchOffUi(reqJson),
                        timeoutSeconds: 180);

                case VideoOpHandler.OpSubmit:
                case VideoOpHandler.OpCancel:
                    // V2 video async path. Submit kicks off a background
                    // job (returns Queued quickly); cancel makes a
                    // provider HTTP call. Same 180 s ceiling as image
                    // async ops — provider HTTP is the dominant cost and
                    // shares the same envelope.
                    return ExecuteAsyncApiResponseCallback(
                        responseJsonUtf8,
                        responseJsonCapacity,
                        responseJsonLength,
                        httpStatusCode,
                        requestJson,
                        (reqJson, ct) => _videoOpHandler.Value.DispatchAsync(reqJson, ct),
                        timeoutSeconds: 180);

                case VideoOpHandler.OpStatus:
                case VideoOpHandler.OpResult:
                case VideoOpHandler.OpEstimate:
                case VideoOpHandler.OpListJobs:
                case VideoOpHandler.OpListModels:
                    // V2 video off-UI sync path — ledger reads and pure-
                    // CPU pricing arithmetic. 30 s cap mirrors the
                    // artifact-management ops; bounded I/O.
                    //
                    // V4: list_video_jobs and list_video_models join
                    // this arm — both are pure ledger / registry reads
                    // shaped identically to status/result/estimate.
                    return ExecuteOffUiApiResponseCallback(
                        responseJsonUtf8,
                        responseJsonCapacity,
                        responseJsonLength,
                        httpStatusCode,
                        requestJson,
                        reqJson => _videoOpHandler.Value.DispatchOffUi(reqJson),
                        timeoutSeconds: 30);

                default:
                    // Reject unknown/missing op before selecting a
                    // dispatcher. Defense-in-depth against a future
                    // registration mistake where a new route forgets to
                    // extend this switch. The expected-op list comes from
                    // ExpectedVisionOps so message/switch share a single
                    // source of truth.
                    return WriteUtf8Response(
                        responseJsonUtf8,
                        responseJsonCapacity,
                        responseJsonLength,
                        httpStatusCode,
                        JsonSerializer.Serialize(new
                        {
                            success = false,
                            data = BuildUnknownOpMessage(op),
                        }, JsonOptions),
                        400);
            }
        }

        private static int HandleCanvasDirectorDispatch(
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
                requestJson => CanvasDirector.Dispatch(requestJson),
                timeoutSeconds: 120,
                timeoutErrorCode: "solve_timeout",
                timeoutHttpStatus: 504);
        }

        /// <summary>
        /// Extract the <c>op</c> field from the vision request JSON
        /// without full validation. Returns null if the body is absent,
        /// not a JSON object, or missing an op field.
        /// </summary>
        private static string? PeekVisionOp(string? requestJson)
        {
            if (string.IsNullOrEmpty(requestJson)) return null;
            try
            {
                using var doc = JsonDocument.Parse(requestJson);
                if (doc.RootElement.ValueKind != JsonValueKind.Object) return null;
                if (!doc.RootElement.TryGetProperty("op", out var opEl)) return null;
                if (opEl.ValueKind != JsonValueKind.String) return null;
                return opEl.GetString();
            }
            catch (JsonException)
            {
                return null;
            }
        }

        private static int HandleBimDispatch(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            return ExecuteBimDispatchCallback(
                requestJsonUtf8,
                requestJsonLength,
                responseJsonUtf8,
                responseJsonCapacity,
                responseJsonLength,
                httpStatusCode);
        }

        private static int HandleReconstructionDispatch(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            string requestJson;
            try
            {
                requestJson = ReadUtf8(requestJsonUtf8, requestJsonLength);
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
                        data = new
                        {
                            code = "invalid_request",
                            message = $"Reconstruction dispatch failed to read request: {ex.Message}",
                            retryable = false,
                            field = "body",
                            details = new { },
                        },
                    }, JsonOptions),
                    400);
            }

            var op = PeekVisionOp(requestJson);
            switch (op)
            {
                case ReconstructionOpHandler.OpSubmit:
                case ReconstructionOpHandler.OpRemoveBackground:
                case ReconstructionOpHandler.OpStatus:
                case ReconstructionOpHandler.OpCancel:
                case ReconstructionOpHandler.OpImportPackage:
                    return ExecuteAsyncApiResponseCallback(
                        responseJsonUtf8,
                        responseJsonCapacity,
                        responseJsonLength,
                        httpStatusCode,
                        requestJson,
                        (reqJson, ct) => RookSubsystemRoot.Instance.Reconstruction.DispatchAsync(reqJson, ct),
                        timeoutSeconds: 180);

                case ReconstructionOpHandler.OpModels:
                case ReconstructionOpHandler.OpListJobs:
                case ReconstructionOpHandler.OpResult:
                case ReconstructionOpHandler.OpPrepareImport:
                case ReconstructionOpHandler.OpRecordImport:
                case ReconstructionOpHandler.OpCleanupPreparedImport:
                case ReconstructionOpHandler.OpAssembleViewSet:
                    return ExecuteOffUiApiResponseCallback(
                        responseJsonUtf8,
                        responseJsonCapacity,
                        responseJsonLength,
                        httpStatusCode,
                        requestJson,
                        reqJson => RookSubsystemRoot.Instance.Reconstruction.DispatchOffUi(reqJson),
                        timeoutSeconds: 30);

                default:
                    return WriteUtf8Response(
                        responseJsonUtf8,
                        responseJsonCapacity,
                        responseJsonLength,
                        httpStatusCode,
                        JsonSerializer.Serialize(new
                        {
                            success = false,
                            data = new
                            {
                                code = "invalid_request",
                                message = string.IsNullOrEmpty(op)
                                    ? "Reconstruction request missing required 'op' discriminator."
                                    : $"Unknown reconstruction op '{op}'.",
                                retryable = false,
                                field = "op",
                                details = new { },
                            },
                        }, JsonOptions),
                        400);
            }
        }

        private static int ExecuteBimDispatchCallback(
            IntPtr requestJsonUtf8,
            int requestJsonLength,
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode)
        {
            try
            {
                var requestJson = ReadUtf8(requestJsonUtf8, requestJsonLength);
                var result = Bim.Dispatch(requestJson);
                var responseJson = SerializeBimDispatchEnvelope(result);

                return WriteUtf8Response(
                    responseJsonUtf8,
                    responseJsonCapacity,
                    responseJsonLength,
                    httpStatusCode,
                    responseJson,
                    MapBridgeStatus(result));
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
                        data = new
                        {
                            errorCode = "internal_error",
                            message = $"BIM dispatch failed: {ex.Message}",
                        },
                    }, JsonOptions),
                    500);
            }
        }

        private static string SerializeBimDispatchEnvelope(ApiResponse result)
        {
            var envelope = new JsonObject
            {
                ["success"] = result.Success,
                ["data"] = CloneToJsonNode(result.Data),
            };

            if (result.Diagnostic != null)
            {
                envelope["diagnostic"] = CloneToJsonNode(result.Diagnostic);
            }

            return envelope.ToJsonString(JsonOptions);
        }

        private static JsonNode? CloneToJsonNode(object? value)
        {
            if (value == null)
            {
                return null;
            }

            if (value is JsonNode node)
            {
                return node.DeepClone();
            }

            return JsonSerializer.SerializeToNode(value, JsonOptions);
        }

        /// <summary>
        /// Map an <see cref="ApiResponse"/> to the HTTP status code the
        /// native bridge should write. Honors an explicit
        /// <see cref="ApiResponse.HttpStatus"/> when set; falls back to
        /// the legacy <c>Success ? 200 : 400</c> rule otherwise. Shared
        /// by the async and off-UI executors so the fallback rule has a
        /// single point of truth.
        ///
        /// Caller contract: <paramref name="result"/> is non-null. Both
        /// production callers (the async and off-UI executors) read
        /// <c>result.Success</c> for the JSON envelope before invoking
        /// this helper, so a null value would NRE earlier. Codex step 1
        /// review noted the prior defensive null-guard was unreachable
        /// and dropped here.
        /// </summary>
        internal static int MapBridgeStatus(ApiResponse result) =>
            result.HttpStatus ?? (result.Success ? 200 : 400);

        /// <summary>
        /// Async variant of <see cref="ExecuteApiResponseCallback"/> —
        /// runs the operation on the threadpool (not the UI thread) and
        /// waits synchronously here (bridge callback signature is sync).
        /// A <see cref="CancellationTokenSource"/> fires on timeout so
        /// the outbound HttpClient request is cancelled rather than
        /// continuing to spend API time past the deadline.
        ///
        /// Does not use <c>DocumentContext.WithDocument</c> — the current
        /// async ops (generate, enhance_prompt) do not read the document.
        /// If a future async op needs document pinning, set the AsyncLocal
        /// before awaiting inside the operation delegate.
        /// </summary>
        private static int ExecuteAsyncApiResponseCallback(
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode,
            string requestJson,
            Func<string, CancellationToken, Task<ApiResponse>> operation,
            int timeoutSeconds)
        {
            try
            {
                using var cts = new CancellationTokenSource();
                var token = cts.Token;

                var task = Task.Run(async () =>
                {
                    try
                    {
                        return await operation(requestJson, token).ConfigureAwait(false);
                    }
                    catch (OperationCanceledException)
                    {
                        return new ApiResponse
                        {
                            Success = false,
                            Data = "Vision callback cancelled (bridge timeout).",
                        };
                    }
                    catch (Exception ex)
                    {
                        return new ApiResponse
                        {
                            Success = false,
                            Data = ex.Message,
                        };
                    }
                });

                string responseJson;
                int statusCode;

                if (!task.Wait(TimeSpan.FromSeconds(timeoutSeconds)))
                {
                    // Timeout: cancel the CTS so the outbound HttpClient
                    // request is aborted (cooperative cancellation —
                    // PostAsync/GetAsync respect the token). The Task
                    // itself may continue running until the token is
                    // observed, but the HTTP connection closes promptly
                    // and API quota is not spent past the deadline.
                    cts.Cancel();
                    responseJson = JsonSerializer.Serialize(new
                    {
                        success = false,
                        data = "Vision callback request timed out.",
                    }, JsonOptions);
                    statusCode = 400;
                }
                else
                {
                    var result = task.Result;
                    responseJson = JsonSerializer.Serialize(new
                    {
                        success = result.Success,
                        data = result.Data,
                    }, JsonOptions);
                    statusCode = MapBridgeStatus(result);
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
                        data = $"Native vision async bridge failed: {ex.Message}",
                    }, JsonOptions),
                    500);
            }
        }

        /// <summary>
        /// Off-UI sync variant of <see cref="ExecuteApiResponseCallback"/>.
        /// Runs the operation on the threadpool (not the UI thread) and
        /// blocks the bridge thread waiting for it. No
        /// <see cref="CancellationToken"/> — intended for disk-only ops
        /// (artifact-store list/get/approve/delete/consume) where there is
        /// no cooperative-cancellation surface to plumb a token into.
        /// A hard timeout is still enforced so a wedged operation surfaces
        /// as an envelope failure rather than hanging the HTTP client.
        ///
        /// Does not use <c>DocumentContext.WithDocument</c> — artifact-store
        /// ops do not read the Rhino document.
        /// </summary>
        private static int ExecuteOffUiApiResponseCallback(
            IntPtr responseJsonUtf8,
            int responseJsonCapacity,
            IntPtr responseJsonLength,
            IntPtr httpStatusCode,
            string requestJson,
            Func<string, ApiResponse> operation,
            int timeoutSeconds)
        {
            try
            {
                var task = Task.Run(() =>
                {
                    try
                    {
                        return operation(requestJson);
                    }
                    catch (Exception ex)
                    {
                        return new ApiResponse
                        {
                            Success = false,
                            Data = ex.Message,
                        };
                    }
                });

                string responseJson;
                int statusCode;

                if (!task.Wait(TimeSpan.FromSeconds(timeoutSeconds)))
                {
                    responseJson = JsonSerializer.Serialize(new
                    {
                        success = false,
                        data = "Vision callback request timed out.",
                    }, JsonOptions);
                    statusCode = 400;
                }
                else
                {
                    var result = task.Result;
                    responseJson = JsonSerializer.Serialize(new
                    {
                        success = result.Success,
                        data = result.Data,
                    }, JsonOptions);
                    statusCode = MapBridgeStatus(result);
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
                        data = $"Native vision off-UI bridge failed: {ex.Message}",
                    }, JsonOptions),
                    500);
            }
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
            Func<string, ApiResponse> operation,
            int timeoutSeconds = 30,
            string? timeoutErrorCode = null,
            int? timeoutHttpStatus = null)
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
                        var result = DocumentContext.WithDocument(
                            targetDoc,
                            () => ExecuteGrasshopperDispatch(
                                requestJson,
                                GrasshopperDispatchContext.ProductionSource,
                                () => operation(requestJson)));
                        responseJson = JsonSerializer.Serialize(new
                        {
                            success = result.Success,
                            data = result.Data
                        }, JsonOptions);
                        statusCode = MapBridgeStatus(result);
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

                if (!waitHandle.Wait(TimeSpan.FromSeconds(timeoutSeconds)))
                {
                    object data = timeoutErrorCode == null
                        ? "GH callback request timed out."
                        : new { code = timeoutErrorCode, message = "CanvasDirector extraction timed out while waiting for Grasshopper solve/extract." };
                    responseJson = JsonSerializer.Serialize(new
                    {
                        success = false,
                        data
                    }, JsonOptions);
                    statusCode = timeoutHttpStatus ?? 400;
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

        internal static ApiResponse ExecuteGrasshopperDispatchForTests(
            string requestJson,
            IGrasshopperDispatchSource source,
            Func<ApiResponse> operation) =>
            ExecuteGrasshopperDispatch(requestJson, source, operation);

        private static ApiResponse ExecuteGrasshopperDispatch(
            string? requestJson,
            IGrasshopperDispatchSource source,
            Func<ApiResponse> operation)
        {
            var args = ParseRequestArgs(requestJson);
            var rawScope = GetStringArg(args, "_rookGhDispatchScope");
            if (rawScope is null)
            {
                return operation();
            }

            var scope = rawScope switch
            {
                "document_independent" => GhManagedDispatchScope.DocumentIndependent,
                "observation" => GhManagedDispatchScope.Observation,
                "mutation" => GhManagedDispatchScope.Mutation,
                "transition" => GhManagedDispatchScope.Transition,
                _ => (GhManagedDispatchScope?)null,
            };
            if (!scope.HasValue)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = new
                    {
                        error = "invalid_arguments",
                        message = "The internal Grasshopper dispatch scope is invalid.",
                    },
                };
            }

            return GrasshopperDispatchContext.Execute(
                source,
                scope.Value,
                GetStringArg(args, "_rookExpectedGhDocumentId"),
                operation);
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
            var bytes = Encoding.UTF8.GetBytes(json + "\0");
            var finalStatusCode = statusCode;

            // Defense-in-depth size guard. If the intended response
            // exceeds the native buffer capacity, substitute a small
            // fitting error envelope. Without this, the native side
            // sees rc=-2 and surfaces an opaque "callback invocation
            // failed (-2)" message with no diagnostic signal — the
            // same failure class PR-5a avoided for blobs. This catches
            // any op whose serialized response unexpectedly inflates
            // (e.g. list_artifacts under worst-case metadata, even
            // after that route's compact-summary fix).
            if (responseJsonUtf8 != IntPtr.Zero && responseJsonCapacity < bytes.Length)
            {
                var fallback = JsonSerializer.Serialize(new
                {
                    success = false,
                    data = $"Response payload of {bytes.Length - 1} bytes exceeds bridge " +
                           $"buffer capacity of {responseJsonCapacity - 1} bytes. " +
                           "Reduce 'limit', apply filters, or fetch per-artifact detail " +
                           "via GET /vision/artifacts/{id}."
                }, JsonOptions);
                bytes = Encoding.UTF8.GetBytes(fallback + "\0");
                finalStatusCode = 400;
            }

            if (httpStatusCode != IntPtr.Zero)
            {
                Marshal.WriteInt32(httpStatusCode, finalStatusCode);
            }

            if (responseJsonLength != IntPtr.Zero)
            {
                Marshal.WriteInt32(responseJsonLength, bytes.Length - 1);
            }

            if (responseJsonUtf8 == IntPtr.Zero || responseJsonCapacity < bytes.Length)
            {
                // Pathological case: even the fallback envelope doesn't
                // fit (would only happen if responseJsonCapacity is
                // absurdly small or JsonOptions produces something huge).
                // Signal failure; native will surface the opaque error
                // rather than corrupt memory.
                return -2;
            }

            Marshal.Copy(bytes, 0, responseJsonUtf8, bytes.Length);
            return 0;
        }
    }
}
