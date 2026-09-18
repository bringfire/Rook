// RookServer.h
//
// HTTP server for RookNative using cpp-httplib.
// Runs on a background thread, serves JSON responses on 127.0.0.1.
// Port is OS-assigned (port 0) — the actual port is published via a
// discovery file in the shared discovery root. The default root is
// %LOCALAPPDATA%/Rook/discovery; when LOCALAPPDATA is unavailable,
// publication falls back to %TEMP%/rook.

#pragma once

class CRookServer
{
public:
    CRookServer();
    ~CRookServer();

    // Start the HTTP server on an OS-assigned port.
    // Must be called from the main thread, AFTER CMainThreadDispatcher::Instance().Start().
    // Returns true if the server started successfully.
    bool Start();

    // Stop the server, join the background thread, remove discovery file.
    void Stop();

    bool IsRunning() const { return m_running.load(); }
    int Port() const { return m_port; }
    void RefreshDiscoveryFile();

    static CRookServer& Instance();

    // Response helpers — usable from any thread.
    static void SendSuccess(httplib::Response& res, const nlohmann::json& data);
    static void SendError(httplib::Response& res, const std::string& message);
    // SendErrorData: like SendError but preserves structured JSON data in the envelope.
    // Use this when the error response contains structured data (not just a message string).
    static void SendErrorData(httplib::Response& res, const nlohmann::json& data);
    // SendErrorWithDiagnostic: preserves legacy string data while adding the
    // additive Phase 2 route diagnostic sibling. Callers may override
    // res.status after this helper to preserve established route status.
    static void SendErrorWithDiagnostic(
        httplib::Response& res,
        const std::string& message,
        const nlohmann::json& diagnostic);
    // SendErrorDataWithDiagnostic: preserves structured JSON data while adding
    // the additive Phase 2 route diagnostic sibling.
    static void SendErrorDataWithDiagnostic(
        httplib::Response& res,
        const nlohmann::json& data,
        const nlohmann::json& diagnostic);

private:
    void RegisterRoutes();
    void WriteDiscoveryFile();
    void RemoveDiscoveryFile();
    std::string GetDiscoveryFolder();
    std::string GetDiscoveryFilePath();

    // Route handlers — Phase 1
    void HandlePing(const httplib::Request& req, httplib::Response& res);
    void HandleCapabilities(const httplib::Request& req, httplib::Response& res);

    // Route handlers — Grasshopper and companion-backed boundary
    void HandleMake2d(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperStatus(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperDocument(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperQuery(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperSelection(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperCategories(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperLibrary(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperGetValue(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperSetValue(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperSetScript(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperScriptParams(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperConnections(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperDelete(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperPreview(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperClear(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperOpenDocument(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperNewDocument(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperMove(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperGroup(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperGroups(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperGroupResize(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperCluster(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperExploreSelection(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperExploreCluster(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperBatchComponentInfo(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperCreateComponent(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperCreateSlider(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperCreatePanel(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperComponent(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperInspectOutput(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperErrors(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperConnect(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperDisconnect(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperSetReference(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperGetReference(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperClearReference(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperSolve(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperSolveReadiness(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperWaitForSolveReadiness(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperBakeOutput(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperSnapshot(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperEdit(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperUndo(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperCanvasFocus(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperCanvasZoom(const httplib::Request& req, httplib::Response& res);
    void HandleGrasshopperCanvasImage(const httplib::Request& req, httplib::Response& res);
    void HandleManagedBlockSetLayers(const httplib::Request& req, httplib::Response& res);
    void HandleManagedBlockSetLayersBatch(const httplib::Request& req, httplib::Response& res);
    void HandleManagedBlockSetMaterials(const httplib::Request& req, httplib::Response& res);
    void HandleManagedBlockSetMaterialsBatch(const httplib::Request& req, httplib::Response& res);
    void HandleManagedBlockSetObjectColorsBatch(const httplib::Request& req, httplib::Response& res);
    void HandleManagedBlockSetObjectUserStringsBatch(const httplib::Request& req, httplib::Response& res);
    void HandleManagedBlockSetObjectNamesBatch(const httplib::Request& req, httplib::Response& res);
    void HandleManagedBlockTransformInstanceBatch(const httplib::Request& req, httplib::Response& res);
    void HandleBlockSetInstancePropertiesRoute(const httplib::Request& req, httplib::Response& res);
    void HandleBlockSetInstanceVisibilityRoute(const httplib::Request& req, httplib::Response& res);
    void HandleBlockTransformInstanceRoute(const httplib::Request& req, httplib::Response& res);
    void HandleBlockArrayInstancesRoute(const httplib::Request& req, httplib::Response& res);
    void HandleManagedBlockSetObjectColors(const httplib::Request& req, httplib::Response& res);
    void HandleManagedBlockSetObjectNames(const httplib::Request& req, httplib::Response& res);
    void HandleManagedBlockSetObjectUserStrings(const httplib::Request& req, httplib::Response& res);
    void HandleManagedBlockReplaceObjectGeometry(const httplib::Request& req, httplib::Response& res);
    void HandleManagedBlockReplaceObjectGeometryBatch(const httplib::Request& req, httplib::Response& res);
    void HandleManagedBlockTransformObject(const httplib::Request& req, httplib::Response& res);
    void HandleManagedBlockTransformObjectBatch(const httplib::Request& req, httplib::Response& res);
    void HandleBlockFindInstancesRoute(const httplib::Request& req, httplib::Response& res);
    void HandleBlockUserStringsRoute(const httplib::Request& req, httplib::Response& res);
    void HandleBlockObjectsDetailedRoute(const httplib::Request& req, httplib::Response& res);

    // Route handlers — Phase 2 (delegate to Rook::Handlers::*)
    void HandleDocument(const httplib::Request& req, httplib::Response& res);
    void HandleLayers(const httplib::Request& req, httplib::Response& res);
    void HandleObjects(const httplib::Request& req, httplib::Response& res);
    void HandleObjectHistory(const httplib::Request& req, httplib::Response& res);
    void HandleObjectsWithHistory(const httplib::Request& req, httplib::Response& res);
    void HandleGeometry(const httplib::Request& req, httplib::Response& res);

    // Route handlers — Phase 4A (delegate to Rook::Handlers::*)
    void HandleCommand(const httplib::Request& req, httplib::Response& res);
    void HandleExecute(const httplib::Request& req, httplib::Response& res);
    void HandleCreate(const httplib::Request& req, httplib::Response& res);
    void HandleDelete(const httplib::Request& req, httplib::Response& res);
    void HandleTransform(const httplib::Request& req, httplib::Response& res);
    void HandleCopy(const httplib::Request& req, httplib::Response& res);
    void HandleUndo(const httplib::Request& req, httplib::Response& res);
    void HandleRedo(const httplib::Request& req, httplib::Response& res);

    // Route handlers — Phase 4B (delegate to Rook::Handlers::*)
    void HandleCreateLayer(const httplib::Request& req, httplib::Response& res);
    void HandleCreateLayersBatch(const httplib::Request& req, httplib::Response& res);
    void HandleDeleteLayer(const httplib::Request& req, httplib::Response& res);
    void HandleLayerVisibility(const httplib::Request& req, httplib::Response& res);
    void HandleLayerLock(const httplib::Request& req, httplib::Response& res);
    void HandleLayerCurrent(const httplib::Request& req, httplib::Response& res);
    void HandleLayerSetProperties(const httplib::Request& req, httplib::Response& res);
    void HandleLayerSetPropertiesBatch(const httplib::Request& req, httplib::Response& res);
    void HandleLayerRename(const httplib::Request& req, httplib::Response& res);
    void HandleLayerMoveObjects(const httplib::Request& req, httplib::Response& res);
    void HandleLayerMerge(const httplib::Request& req, httplib::Response& res);
    void HandleLayerDependencies(const httplib::Request& req, httplib::Response& res);
    void HandleGetSelection(const httplib::Request& req, httplib::Response& res);
    void HandleSelect(const httplib::Request& req, httplib::Response& res);
    void HandleViewport(const httplib::Request& req, httplib::Response& res);
    void HandleDirectorObjectStates(const httplib::Request& req, httplib::Response& res);
    void HandleDirectorViewState(const httplib::Request& req, httplib::Response& res);
    void HandleDirectorCurveSamples(const httplib::Request& req, httplib::Response& res);
    void HandleDirectorVideoAssemble(const httplib::Request& req, httplib::Response& res);
    void HandleDirectorFrameCapture(const httplib::Request& req, httplib::Response& res);
    void HandleDirectorCaptureDepthPass(const httplib::Request& req, httplib::Response& res);
    void HandleGetDisplayModes(const httplib::Request& req, httplib::Response& res);
    void HandleSetDisplayMode(const httplib::Request& req, httplib::Response& res);
    void HandleMeasureDistance(const httplib::Request& req, httplib::Response& res);
    void HandleMeasureArea(const httplib::Request& req, httplib::Response& res);
    void HandleMeasureVolume(const httplib::Request& req, httplib::Response& res);
    void HandleMeasureLength(const httplib::Request& req, httplib::Response& res);
    void HandleMeasureBbox(const httplib::Request& req, httplib::Response& res);
    void HandleMeasureCentroid(const httplib::Request& req, httplib::Response& res);

    // Route handlers — Phase 4C (delegate to Rook::Handlers::*)
    void HandleGetGroups(const httplib::Request& req, httplib::Response& res);
    void HandleGroup(const httplib::Request& req, httplib::Response& res);
    void HandleUngroup(const httplib::Request& req, httplib::Response& res);
    void HandleGroupMembers(const httplib::Request& req, httplib::Response& res);
    void HandleDocumentOpen(const httplib::Request& req, httplib::Response& res);
    void HandleDocumentSave(const httplib::Request& req, httplib::Response& res);
    void HandleDocumentSaveCopy(const httplib::Request& req, httplib::Response& res);
    void HandleDocumentNew(const httplib::Request& req, httplib::Response& res);
    void HandleDocumentUnits(const httplib::Request& req, httplib::Response& res);
    void HandleGetViews(const httplib::Request& req, httplib::Response& res);
    void HandleViewsSave(const httplib::Request& req, httplib::Response& res);
    void HandleViewsRestore(const httplib::Request& req, httplib::Response& res);
    void HandleGetMaterials(const httplib::Request& req, httplib::Response& res);
    void HandleCreateMaterial(const httplib::Request& req, httplib::Response& res);
    void HandleDeleteMaterial(const httplib::Request& req, httplib::Response& res);
    void HandleAssignMaterial(const httplib::Request& req, httplib::Response& res);
    void HandlePurgeMaterials(const httplib::Request& req, httplib::Response& res);
    void HandleGetLinetypes(const httplib::Request& req, httplib::Response& res);
    void HandlePurgeLinetypes(const httplib::Request& req, httplib::Response& res);
    void HandleImport(const httplib::Request& req, httplib::Response& res);
    void HandleExport(const httplib::Request& req, httplib::Response& res);
    void HandleBoolean(const httplib::Request& req, httplib::Response& res);
    void HandleFillet(const httplib::Request& req, httplib::Response& res);
    void HandleChamfer(const httplib::Request& req, httplib::Response& res);
    void HandleOffset(const httplib::Request& req, httplib::Response& res);

    // Route handlers — Phase 4D: Analysis (delegate to Rook::Handlers::*)
    void HandleCurvatureCurve(const httplib::Request& req, httplib::Response& res);
    void HandleCurvatureSurface(const httplib::Request& req, httplib::Response& res);
    void HandleDraftAngle(const httplib::Request& req, httplib::Response& res);
    void HandleClosestPoint(const httplib::Request& req, httplib::Response& res);
    void HandleCurvePointAt(const httplib::Request& req, httplib::Response& res);
    void HandleCurveTangent(const httplib::Request& req, httplib::Response& res);
    void HandleCurveFrame(const httplib::Request& req, httplib::Response& res);
    void HandleSurfaceNormal(const httplib::Request& req, httplib::Response& res);
    void HandleBrepEdges(const httplib::Request& req, httplib::Response& res);
    void HandleBrepFaces(const httplib::Request& req, httplib::Response& res);
    void HandleBrepVertices(const httplib::Request& req, httplib::Response& res);
    void HandleIsClosed(const httplib::Request& req, httplib::Response& res);
    void HandleIsValid(const httplib::Request& req, httplib::Response& res);

    // Route handlers — Phase 4D: Curves (delegate to Rook::Handlers::*)
    void HandleCurveJoin(const httplib::Request& req, httplib::Response& res);
    void HandleCurveExplode(const httplib::Request& req, httplib::Response& res);
    void HandleCurveDivide(const httplib::Request& req, httplib::Response& res);
    void HandleCurveExtend(const httplib::Request& req, httplib::Response& res);
    void HandleCurveTrim(const httplib::Request& req, httplib::Response& res);
    void HandleCurveSplit(const httplib::Request& req, httplib::Response& res);
    void HandleCurveRebuild(const httplib::Request& req, httplib::Response& res);
    void HandleCurveFillet(const httplib::Request& req, httplib::Response& res);
    void HandleCurveProject(const httplib::Request& req, httplib::Response& res);
    void HandleCurvePull(const httplib::Request& req, httplib::Response& res);
    void HandleCurveOffset(const httplib::Request& req, httplib::Response& res);
    void HandleCurveOffsetOnSurface(const httplib::Request& req, httplib::Response& res);

    // Route handlers — Phase 4E: Intersection (delegate to Rook::Handlers::*)
    void HandleIntersectCurves(const httplib::Request& req, httplib::Response& res);
    void HandleIntersectCurveSurface(const httplib::Request& req, httplib::Response& res);
    void HandleIntersectCurveBrep(const httplib::Request& req, httplib::Response& res);
    void HandleIntersectBreps(const httplib::Request& req, httplib::Response& res);
    void HandleIntersectPlane(const httplib::Request& req, httplib::Response& res);
    void HandleRoadIntersectionCandidates(const httplib::Request& req, httplib::Response& res);
    void HandleRoadIntersectionAnalyze(const httplib::Request& req, httplib::Response& res);
    void HandleRoadIntersectionCommit(const httplib::Request& req, httplib::Response& res);
    void HandleRoadIntersectionResolve(const httplib::Request& req, httplib::Response& res);

    // Route handlers — Phase 4E: Split/Trim (delegate to Rook::Handlers::*)
    void HandleSplitBrep(const httplib::Request& req, httplib::Response& res);
    void HandleTrimBrep(const httplib::Request& req, httplib::Response& res);
    void HandleSplitFace(const httplib::Request& req, httplib::Response& res);

    // Route handlers — Phase 4E: Offset Brep (delegate to Rook::Handlers::*)
    void HandleOffsetBrep(const httplib::Request& req, httplib::Response& res);

    // Route handlers — Phase 4E: Mesh (delegate to Rook::Handlers::*)
    void HandleMeshFromBrep(const httplib::Request& req, httplib::Response& res);
    void HandleMeshBox(const httplib::Request& req, httplib::Response& res);
    void HandleMeshSphere(const httplib::Request& req, httplib::Response& res);
    void HandleMeshCylinder(const httplib::Request& req, httplib::Response& res);
    void HandleMeshCone(const httplib::Request& req, httplib::Response& res);
    void HandleMeshBoolean(const httplib::Request& req, httplib::Response& res);
    void HandleMeshReduce(const httplib::Request& req, httplib::Response& res);
    void HandleMeshQuadRemesh(const httplib::Request& req, httplib::Response& res);
    void HandleMeshRepair(const httplib::Request& req, httplib::Response& res);
    void HandleMeshSmooth(const httplib::Request& req, httplib::Response& res);
    void HandleMeshWeld(const httplib::Request& req, httplib::Response& res);
    void HandleMeshUnweld(const httplib::Request& req, httplib::Response& res);

    // Route handlers — Phase 4E: SubD (delegate to Rook::Handlers::*)
    void HandleSubDBox(const httplib::Request& req, httplib::Response& res);
    void HandleSubDSphere(const httplib::Request& req, httplib::Response& res);
    void HandleSubDCylinder(const httplib::Request& req, httplib::Response& res);
    void HandleSubDFromMesh(const httplib::Request& req, httplib::Response& res);
    void HandleSubDFromSurface(const httplib::Request& req, httplib::Response& res);
    void HandleSubDSubdivide(const httplib::Request& req, httplib::Response& res);
    void HandleSubDCrease(const httplib::Request& req, httplib::Response& res);
    void HandleSubDToBrep(const httplib::Request& req, httplib::Response& res);
    void HandleSubDToMesh(const httplib::Request& req, httplib::Response& res);

    // Route handlers — Phase 4F: Blocks (delegate to Rook::Handlers::*)
    void HandleGetBlocks(const httplib::Request& req, httplib::Response& res);
    void HandleBlockCreate(const httplib::Request& req, httplib::Response& res);
    void HandleBlockInsert(const httplib::Request& req, httplib::Response& res);
    void HandleBlockExplode(const httplib::Request& req, httplib::Response& res);
    void HandleBlockDelete(const httplib::Request& req, httplib::Response& res);
    void HandleBlockRename(const httplib::Request& req, httplib::Response& res);
    void HandleBlockDescription(const httplib::Request& req, httplib::Response& res);
    void HandleBlockInfo(const httplib::Request& req, httplib::Response& res);
    void HandleBlockAddObjects(const httplib::Request& req, httplib::Response& res);
    void HandleBlockRemoveObjects(const httplib::Request& req, httplib::Response& res);
    void HandleBlockReplaceGeometry(const httplib::Request& req, httplib::Response& res);
    void HandleBlockInstances(const httplib::Request& req, httplib::Response& res);
    void HandleBlockReplaceInstance(const httplib::Request& req, httplib::Response& res);
    void HandleBlockReplaceInstanceBatch(const httplib::Request& req, httplib::Response& res);
    void HandleBlockResetScale(const httplib::Request& req, httplib::Response& res);
    void HandleBlockResetScaleBatch(const httplib::Request& req, httplib::Response& res);
    void HandleBlockLink(const httplib::Request& req, httplib::Response& res);
    void HandleBlockRefresh(const httplib::Request& req, httplib::Response& res);
    void HandleBlockUnlink(const httplib::Request& req, httplib::Response& res);
    void HandleBlockPurge(const httplib::Request& req, httplib::Response& res);
    void HandleBlockDuplicate(const httplib::Request& req, httplib::Response& res);
    void HandleBlockRebase(const httplib::Request& req, httplib::Response& res);
    void HandleBlockRebaseRecursive(const httplib::Request& req, httplib::Response& res);
    void HandleBlockNested(const httplib::Request& req, httplib::Response& res);
    void HandleBlockCompare(const httplib::Request& req, httplib::Response& res);
    void HandleBlockMerge(const httplib::Request& req, httplib::Response& res);
    void HandleBlockLayerCensus(const httplib::Request& req, httplib::Response& res);

    // Route handlers — Phase 4F: Texture Mapping (delegate to Rook::Handlers::*)
    void HandleUvBox(const httplib::Request& req, httplib::Response& res);
    void HandleUvPlanar(const httplib::Request& req, httplib::Response& res);
    void HandleUvCylinder(const httplib::Request& req, httplib::Response& res);
    void HandleUvSphere(const httplib::Request& req, httplib::Response& res);

    // Route handlers — Phase 4F: Game Export (delegate to Rook::Handlers::*)
    void HandleGameExportTag(const httplib::Request& req, httplib::Response& res);
    void HandleGameExportTagFromLayers(const httplib::Request& req, httplib::Response& res);
    void HandleGameExportValidate(const httplib::Request& req, httplib::Response& res);
    void HandleGameExportExport(const httplib::Request& req, httplib::Response& res);
    void HandleGameExportPrepare(const httplib::Request& req, httplib::Response& res);

    // Route handlers — Phase 3: Scene Graph (delegate to Rook::Handlers::*)
    void HandleSceneGraph(const httplib::Request& req, httplib::Response& res);
    void HandleSceneGraphNode(const httplib::Request& req, httplib::Response& res);
    void HandleSceneGraphQuery(const httplib::Request& req, httplib::Response& res);
    void HandleSceneGraphStats(const httplib::Request& req, httplib::Response& res);
    void HandleSceneGraphDiff(const httplib::Request& req, httplib::Response& res);
    void HandleSceneGraphReconcile(const httplib::Request& req, httplib::Response& res);
    void HandleSceneGraphClassify(const httplib::Request& req, httplib::Response& res);
    void HandleSceneGraphOverlay(const httplib::Request& req, httplib::Response& res);

    // Route handlers — Phase 5: Command Interactive (delegate to Rook::Handlers::*)
    void HandleCommandPrompt(const httplib::Request& req, httplib::Response& res);
    void HandleCommandStart(const httplib::Request& req, httplib::Response& res);
    void HandleCommandInput(const httplib::Request& req, httplib::Response& res);
    void HandleCommandCancel(const httplib::Request& req, httplib::Response& res);

    // Route handlers — Phase 5: User Prompts (delegate to Rook::Handlers::*)
    void HandlePromptPoint(const httplib::Request& req, httplib::Response& res);
    void HandlePromptObject(const httplib::Request& req, httplib::Response& res);
    void HandlePromptObjects(const httplib::Request& req, httplib::Response& res);
    void HandlePromptSubObject(const httplib::Request& req, httplib::Response& res);
    void HandlePromptDistance(const httplib::Request& req, httplib::Response& res);

    // Route handlers — Phase 5: AI Gumball (delegate to Rook::Handlers::*)
    void HandleGumballActivate(const httplib::Request& req, httplib::Response& res);
    void HandleGumballDeactivate(const httplib::Request& req, httplib::Response& res);
    void HandleGumballStatus(const httplib::Request& req, httplib::Response& res);
    void HandleGumballHistory(const httplib::Request& req, httplib::Response& res);
    void HandleGumballSettings(const httplib::Request& req, httplib::Response& res);
    void HandleGumballExtrude(const httplib::Request& req, httplib::Response& res);
    void HandleGumballCut(const httplib::Request& req, httplib::Response& res);

    // Route handlers — Phase 6A: AI Gumball v2 (delegate to Rook::Handlers::*)
    void HandleGumballContext(const httplib::Request& req, httplib::Response& res);
    void HandleGumballAlign(const httplib::Request& req, httplib::Response& res);
    void HandleGumballAppearance(const httplib::Request& req, httplib::Response& res);

    // Route handlers — Phase 5: Session Recording (delegate to Rook::Handlers::*)
    void HandleSessionCurrent(const httplib::Request& req, httplib::Response& res);
    void HandleSessionHistory(const httplib::Request& req, httplib::Response& res);
    void HandleSessionList(const httplib::Request& req, httplib::Response& res);
    void HandleSessionExport(const httplib::Request& req, httplib::Response& res);

    // unique_ptr because httplib::Server is non-movable/non-copyable.
    std::unique_ptr<httplib::Server> m_server;
    std::thread m_server_thread;
    std::string m_host_generation_id;
    int m_port = 0;
    std::atomic<bool> m_running{false};
    std::filesystem::path m_discovery_path;
};
