using System;
using System.IO;
using System.Linq;
using System.Xml.Linq;
using Xunit;

namespace RookBim.Tests
{
    public class RookBimModuleSourceTests
    {
        private static readonly string RepoRoot = FindRepoRoot();

        [Fact]
        public void RookBimProject_TargetsNet48AndReferencesRevitApisPrivately()
        {
            var project = LoadProject("src/RookBim/RookBim.csproj");
            var rookProject = LoadProject("src/Rook/Rook.csproj");
            var text = Read("src/RookBim/RookBim.csproj");

            Assert.Equal("net48", ValueOf(project, "TargetFramework"));
            Assert.Equal("enable", ValueOf(project, "Nullable"));
            Assert.Equal("latest", ValueOf(project, "LangVersion"));
            Assert.Equal(ValueOf(rookProject, "Version"), ValueOf(project, "Version"));
            Assert.Equal("RookBIM", ValueOf(project, "Title"));
            Assert.DoesNotContain("RhinoInside.Revit", text, StringComparison.OrdinalIgnoreCase);

            var projectReference = project.Descendants("ProjectReference").Single();
            Assert.Equal("../Rook/Rook.csproj", NormalizeProjectPath(AttributeValue(projectReference, "Include")));

            AssertRevitReference(project, "RevitAPI");
            AssertRevitReference(project, "RevitAPIUI");
        }

        [Fact]
        public void RookProject_DoesNotReferenceRookBimProjectOrRevitApi()
        {
            var text = Read("src/Rook/Rook.csproj");
            var project = XDocument.Parse(text);

            Assert.DoesNotContain("RookBim.csproj", text, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("Autodesk.Revit", text, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("<Reference Include=\"RevitAPI", text, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain(
                project.Descendants("ProjectReference"),
                reference => AttributeValue(reference, "Include").IndexOf("RookBim", StringComparison.OrdinalIgnoreCase) >= 0);
        }

        [Fact]
        public void RookSolution_DoesNotIncludeOptionalRookBimProjects()
        {
            var text = Read("Rook.sln");

            Assert.DoesNotContain("RookBim.csproj", text, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("RookBim.Tests.csproj", text, StringComparison.OrdinalIgnoreCase);
        }

        [Fact]
        public void RookBimModuleActivate_InstallsRevitRuntimeFromOptionalAssembly()
        {
            var text = Read("src/RookBim/RookBimModule.cs");

            Assert.Contains("public static class RookBimModule", text);
            Assert.Contains("public static void Activate()", text);
            Assert.Contains("IsLoaded(\"RevitAPIUI\")", text);
            Assert.Contains("IsLoaded(\"RhinoInside.Revit\")", text);
            Assert.Contains("new RookBimUnavailableRuntime", text);
            Assert.Contains("\"not_rhino_inside\"", text);
            Assert.Contains("RookBimRuntimeRegistry.Install", text);
            Assert.Contains("new RevitRookBimRuntime()", text);
            Assert.Contains("\"RookBim.dll\"", text);
        }

        [Fact]
        public void RevitTask7_UsesRhinoInsideHostContextDispatcherWithoutTransactions()
        {
            var dispatcher = Read("src/RookBim/Revit/RevitApiDispatcher.cs");
            var revitFiles = Directory
                .GetFiles(Path.Combine(RepoRoot, "src", "RookBim", "Revit"), "*.cs")
                .Select(File.ReadAllText);
            var combined = string.Join(Environment.NewLine, revitFiles);

            Assert.Contains("RhinoInside.Revit.Revit", dispatcher);
            Assert.Contains("EnqueueIdlingAction", dispatcher);
            Assert.Contains("ActiveUIApplication", dispatcher);
            Assert.Contains("Type.GetType", dispatcher);
            Assert.Contains("AppDomain.CurrentDomain", dispatcher);
            Assert.Contains("TargetInvocationException", dispatcher);
            Assert.Contains("TaskCompletionSource", dispatcher);
            Assert.Contains("new Action(item.Execute)", dispatcher);
            Assert.DoesNotContain("Task.Run", dispatcher);
            Assert.DoesNotContain("ExternalEvent.Create", dispatcher);
            Assert.DoesNotContain("IExternalEventHandler", dispatcher);
            Assert.DoesNotContain("Transaction", combined);
        }

        [Fact]
        public void RevitTask7_RuntimeUsesDispatcherForStatusAndActiveDocument()
        {
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");
            var context = Read("src/RookBim/Revit/RevitContext.cs");
            var serializer = Read("src/RookBim/Revit/RevitIdentitySerializer.cs");

            Assert.Contains("RevitApiDispatcher", runtime);
            Assert.Contains("dispatcher.InvokeAbandonable", runtime);
            Assert.Contains("ActiveDocument(UIApplication", context);
            Assert.Contains("ActiveUiDocument(UIApplication", context);
            Assert.Contains("ActiveUIDocument", context);
            Assert.Contains("GetWorksharingCentralGUID", serializer);
            Assert.Contains("GuidSource", serializer);
            Assert.Contains("BimDocumentGuidSource.Unavailable", serializer);
            Assert.DoesNotContain("PathFallback", serializer);

            Assert.Contains("Available = true", runtime);
            Assert.Contains("Runtime = \"rookbim\"", runtime);
            Assert.Contains("Host = \"revit\"", runtime);
            Assert.Contains("Module = ModuleName", runtime);
            Assert.Contains("ErrorCode = \"no_active_document\"", runtime);
            Assert.Contains("BimErrorCode.NoActiveDocument", runtime);
            Assert.Contains("409", runtime);
        }

        [Fact]
        public void RevitTask7_ActiveDocumentResultUsesViewPropertyForCamelCaseContract()
        {
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");

            Assert.Contains("View = SerializeActiveView(uidoc, document)", runtime);
            Assert.Contains("public BimViewIdentity? View { get; set; }", runtime);
            Assert.DoesNotContain("ActiveView = SerializeActiveView(uidoc, document)", runtime);
            Assert.DoesNotContain("public BimViewIdentity? ActiveView { get; set; }", runtime);
        }

        [Fact]
        public void RevitTask7_ElementIdSerializationUsesBoundedNullableConversion()
        {
            var serializer = Read("src/RookBim/Revit/RevitIdentitySerializer.cs");

            Assert.Contains("private const int InvalidElementIdValue = -1;", serializer);
            Assert.Contains("Id = ToInt32OrNull(view.Id) ?? InvalidElementIdValue", serializer);
            Assert.Contains("ElementId = ToInt32OrNull(element.Id)", serializer);
            Assert.Contains("private static int? ToInt32OrNull(ElementId? id)", serializer);
            Assert.Contains("if (value < int.MinValue || value > int.MaxValue)", serializer);
            Assert.Contains("return null;", serializer);
            Assert.DoesNotContain("Convert.ToInt32", serializer);
        }

        [Fact]
        public void RevitTask7_DispatchTimeoutAbandonsPendingWork()
        {
            var dispatcher = Read("src/RookBim/Revit/RevitApiDispatcher.cs");
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");

            Assert.Contains("InvokeAbandonable", dispatcher);
            Assert.Contains("public bool Abandon()", dispatcher);
            Assert.Contains("TryAbandon()", dispatcher);
            Assert.Contains("CompareExchange(ref state, Running, Pending)", dispatcher);
            Assert.Contains("CompareExchange(ref state, Abandoned, Pending)", dispatcher);
            Assert.Contains("TrySetCanceled", dispatcher);
            Assert.Contains("var dispatch = dispatcher.InvokeAbandonable(work);", runtime);
            Assert.Contains("dispatch.Abandon();", runtime);
            Assert.Contains("throw new TimeoutException", runtime);
            Assert.Contains("Timed out waiting for RhinoInside Revit idling-queue execution.", runtime);
            Assert.DoesNotContain("Timed out waiting for Revit ExternalEvent execution.", runtime);
        }

        [Fact]
        public void RevitTask7_DispatchDoesNotMaskFaultedTasksWithAggregateException()
        {
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");
            var dispatch = ExtractMethod(runtime, "private T Dispatch<T>(");

            Assert.DoesNotContain(".Wait(DispatchTimeout)", dispatch);
            Assert.Contains("Task.WaitAny", dispatch);
            Assert.Contains("dispatch.Task.GetAwaiter().GetResult();", dispatch);
            Assert.Contains("DescribeDispatchException", runtime);
            Assert.Contains("AggregateException", runtime);
        }

        [Fact]
        public void RevitTask7_StatusDispatchFailureKeepsRookBimRuntime()
        {
            var runtime = NormalizeLineEndings(Read("src/RookBim/Revit/RevitRookBimRuntime.cs"));

            Assert.Contains(
                "catch (Exception ex)\n" +
                "            {\n" +
                "                return new BimStatusResponse\n" +
                "                {\n" +
                "                    Available = false,\n" +
                "                    Runtime = \"rookbim\",\n" +
                "                    ErrorCode = \"not_rhino_inside\",\n" +
                    "                    Message = $\"RookBIM could not enter the Revit API context: {DescribeDispatchException(ex)}\",\n" +
                "                    Host = \"unknown\",\n" +
                "                    Module = ModuleName\n" +
                "                };\n" +
                "            }",
                runtime);
            Assert.DoesNotContain("Runtime = \"unavailable\"", runtime);
        }

        [Fact]
        public void RevitTask10_SelectionServiceUsesResolvedIdentitiesAndUiSelectionOnly()
        {
            var service = Read("src/RookBim/Revit/RevitSelectionService.cs");
            var select = ExtractMethod(service, "public BimApiResponse Select(");
            var clear = ExtractMethod(service, "public BimApiResponse Clear(");

            Assert.Contains("internal sealed class RevitSelectionService", service);
            Assert.Contains("if (request == null || request.Identities == null || request.Identities.Count == 0)", select);
            Assert.Contains("BimErrorCode.InvalidScope", select);
            Assert.True(
                select.IndexOf("BimErrorCode.InvalidScope", StringComparison.Ordinal) <
                select.IndexOf("uiDocument.Selection.SetElementIds(ids)", StringComparison.Ordinal));
            Assert.Contains("RevitIdentitySerializer.Resolve(uiDocument.Document, identity)", select);
            Assert.Contains("if (!resolved.Success)", select);
            Assert.Contains("return BimApiResponse.Fail(", select);
            Assert.Contains("resolved.ErrorCode", select);
            Assert.Contains("uiDocument.Selection.SetElementIds(ids)", select);
            Assert.Contains("selectedCount = ids.Count", select);
            Assert.Contains("identities = selectedIdentities", select);
            Assert.Contains("document = RevitIdentitySerializer.DocumentIdentity(uiDocument.Document)", select);
            Assert.Contains("uiDocument.Selection.SetElementIds(new List<ElementId>())", clear);
            Assert.Contains("selectedCount = 0", clear);
            Assert.DoesNotContain("Transaction", service);
            Assert.DoesNotContain("OverrideGraphicSettings", service);
            Assert.DoesNotContain("TemporaryView", service);
        }

        [Fact]
        public void RevitTask10_RuntimeWiresSelectionThroughDispatcher()
        {
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");
            var select = ExtractMethod(runtime, "public BimApiResponse SelectElements(");
            var clear = ExtractMethod(runtime, "public BimApiResponse ClearSelection(");

            Assert.Contains("private readonly RevitSelectionService selection;", runtime);
            Assert.Contains("this.selection = new RevitSelectionService();", runtime);
            Assert.Contains("return Dispatch(uiapp =>", select);
            Assert.Contains("return Dispatch(uiapp =>", clear);
            Assert.Contains("RevitContext.ActiveUiDocument(uiapp)", select);
            Assert.Contains("RevitContext.ActiveUiDocument(uiapp)", clear);
            Assert.Contains("BimErrorCode.NoActiveDocument", select);
            Assert.Contains("BimErrorCode.NoActiveDocument", clear);
            Assert.Contains("selection.Select(uidoc, request)", select);
            Assert.Contains("selection.Clear(uidoc)", clear);
            Assert.DoesNotContain("LaterToolUnavailable", select);
            Assert.DoesNotContain("LaterToolUnavailable", clear);
        }

        [Fact]
        public void RevitCategoryResolver_UsesLiveDocumentCategoryTableAsAuthority()
        {
            var resolver = Read("src/RookBim/Revit/RevitCategoryResolver.cs");

            Assert.Contains("internal sealed class RevitCategoryResolver", resolver);
            Assert.Contains("document.Settings.Categories", resolver);
            Assert.Contains("BimCategoryResolution", resolver);
            Assert.Contains("BimCategoryResolutionStrategy.BuiltInExact", resolver);
            Assert.Contains("BimCategoryResolutionStrategy.CategoryIdExact", resolver);
            Assert.Contains("BimCategoryResolutionStrategy.DocumentDisplayNameExact", resolver);
            Assert.Contains("BimCategoryResolutionStrategy.DocumentDisplayNameNormalized", resolver);
            Assert.Contains("BimCategoryResolutionStrategy.BuiltInTolerant", resolver);
            Assert.Contains("BimCategoryResolutionStrategy.CuratedAlias", resolver);
            Assert.Contains("MaxSuggestions = 5", resolver);
            Assert.Contains("BimCategoryResolutionStatus.Ambiguous", resolver);
            Assert.Contains("Queryable = entry.Summary.Id.HasValue", resolver);
            Assert.Contains("TrimTrailingPluralS(entry.NormalizedName), singularInput", resolver);
            Assert.Contains("private static int SuggestionRank(", resolver);
            Assert.Contains("private static int EditDistance(", resolver);
            Assert.Contains("OrderBy(candidate => candidate.Rank)", resolver);
            Assert.Contains("TryGetBuiltInCategory", resolver);
            Assert.Contains("TryBuildCategoryEntry", resolver);
            Assert.Contains("SafeCategoryId", resolver);
            Assert.Contains("SafeCategoryName", resolver);
            Assert.Contains("SafeCategoryType", resolver);
            Assert.Contains("catch (Autodesk.Revit.Exceptions.InternalException)", resolver);
            Assert.Contains("catch (Autodesk.Revit.Exceptions.InvalidOperationException)", resolver);
            Assert.Contains("SkippedCount", resolver);
            Assert.Contains("DegradedCount", resolver);
            Assert.Contains("Diagnostics", resolver);
            Assert.Contains("RecordSkip", resolver);
            Assert.Contains("RecordDegradation", resolver);
            Assert.Contains("SafeBuiltInCategory", resolver);
            Assert.Contains("ResolveBuiltIn(document, builtIn)", resolver);
            Assert.DoesNotContain("BuiltInsByCategoryId", resolver);
            Assert.DoesNotContain("SafeCategoryParent", resolver);
            Assert.DoesNotContain(".Where(entry => string.IsNullOrEmpty(normalizedInput)", resolver);
            Assert.DoesNotContain("knowledge", resolver, StringComparison.OrdinalIgnoreCase);
        }

        [Fact]
        public void RevitCategoryResolver_TreatsInvalidBuiltInAsUnavailable()
        {
            var resolver = Read("src/RookBim/Revit/RevitCategoryResolver.cs");
            var safeBuiltIn = ExtractMethod(resolver, "private static string? SafeBuiltInCategory(");

            Assert.Contains("builtIn == BuiltInCategory.INVALID", safeBuiltIn);
            Assert.Contains("return null;", safeBuiltIn);
        }

        [Fact]
        public void RevitCategoryResolver_CatchesRevitInvalidOperationDuringExplicitBuiltInLookup()
        {
            var resolver = Read("src/RookBim/Revit/RevitCategoryResolver.cs");
            var tryGetBuiltIn = ExtractMethod(resolver, "private static bool TryGetBuiltInCategory(");

            Assert.Contains("catch (Autodesk.Revit.Exceptions.InvalidOperationException)", tryGetBuiltIn);
        }

        [Fact]
        public void RevitRuntime_WiresListCategoriesThroughDispatcher()
        {
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");
            var listCategories = ExtractMethod(runtime, "public BimApiResponse ListCategories(");

            Assert.Contains("private readonly RevitCategoryResolver categories;", runtime);
            Assert.Contains("this.categories = new RevitCategoryResolver();", runtime);
            Assert.Contains("return ExecuteInDocumentContext", listCategories);
            Assert.Contains("RevitContext.ActiveUiDocument(uiapp)", runtime);
            Assert.Contains("BimErrorCode.NoActiveDocument", runtime);
            Assert.Contains("categories.List(document)", runtime);
            Assert.DoesNotContain("BimErrorCode.NotRhinoInside", listCategories);
            Assert.Contains("BimErrorCode.InternalError", runtime);
        }

        [Fact]
        public void RevitQueryService_UsesCategoryResolverAndReturnsResolutionEvidence()
        {
            var service = Read("src/RookBim/Revit/RevitQueryService.cs");
            var query = ExtractMethod(service, "public BimApiResponse Query(");

            Assert.Contains("private readonly RevitCategoryResolver categories", service);
            Assert.Contains("categories.Resolve(document, categoryName)", query);
            Assert.Contains("BimErrorCode.AmbiguousCategory", query);
            Assert.Contains("BimErrorCode.CategoryNotQueryable", query);
            Assert.Contains("Data = new { resolution = resolution }", service);
            Assert.Contains("CategoryResolution = categoryResolution", service);
            Assert.Contains("TryResolvedCategoryFilter", service);
            Assert.Contains("new ElementCategoryFilter(new ElementId((long)id.Value))", service);
            Assert.Contains("collector.WherePasses(categoryFilter);", query);
            Assert.DoesNotContain("ResolveBuiltInCategory", service);
        }

        [Fact]
        public void RevitTask9_RuntimeWiresElementInfoAndParametersThroughDispatcher()
        {
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");
            var elementInfo = ExtractMethod(runtime, "public BimApiResponse ElementInfo(");
            var elementParameters = ExtractMethod(runtime, "public BimApiResponse ElementParameters(");

            Assert.Contains("return Dispatch(uiapp =>", elementInfo);
            Assert.Contains("return Dispatch(uiapp =>", elementParameters);
            Assert.Contains("RevitContext.ActiveUiDocument(uiapp)", elementInfo);
            Assert.Contains("RevitContext.ActiveUiDocument(uiapp)", elementParameters);
            Assert.Contains("ResolveElementOrFailure(document, request?.Identity)", elementInfo);
            Assert.Contains("ResolveElementOrFailure(document, request?.Identity)", elementParameters);
            Assert.Contains("BuildElementInfo(document, resolved.Element!)", elementInfo);
            Assert.Contains("RevitParameterSerializer.Serialize(resolved.Element!)", elementParameters);
            Assert.DoesNotContain("LaterToolUnavailable", elementInfo);
            Assert.DoesNotContain("LaterToolUnavailable", elementParameters);
        }

        [Fact]
        public void RevitTask9_ElementResolverPreservesIdentityEnvelopeBoundaries()
        {
            var serializer = Read("src/RookBim/Revit/RevitIdentitySerializer.cs");

            Assert.Contains("public static BimElementResolveResult Resolve(Document document, BimElementIdentity? identity)", serializer);
            Assert.Contains("HasLinkedEvidence(identity)", serializer);
            Assert.Contains("identity.LinkInstanceId.HasValue", serializer);
            Assert.Contains("identity.LinkedElementUniqueId", serializer);
            Assert.Contains("BimErrorCode.LinkedElementUnsupported", serializer);
            Assert.Contains("DocumentMatches(DocumentIdentity(document), identity)", serializer);
            Assert.Contains("BimErrorCode.DocumentMismatch", serializer);
            Assert.Contains("document.GetElement(identity.UniqueId)", serializer);
            Assert.Contains("if (identity.ElementId.HasValue && !ElementIdMatches(byUniqueId.Id, identity.ElementId.Value))", serializer);
            Assert.Contains("Only use elementId fallback when uniqueId is absent.", serializer);
            Assert.Contains("document.GetElement(new ElementId((long)identity.ElementId.Value))", serializer);
            Assert.Contains("BimErrorCode.ElementNotFound", serializer);
        }

        [Fact]
        public void RevitTask9_ParameterSerializerReturnsStorageAndValueEvidence()
        {
            var serializer = Read("src/RookBim/Revit/RevitParameterSerializer.cs");

            Assert.Contains("internal static class RevitParameterSerializer", serializer);
            Assert.Contains("public static IReadOnlyList<object> Serialize(Element element)", serializer);
            Assert.Contains("SerializeParameters(result, element, \"instance\")", serializer);
            Assert.Contains("SerializeParameters(result, type, \"type\")", serializer);
            Assert.Contains("source = source", serializer);
            Assert.Contains("ownerElementId = ToInt32OrNull(owner.Id)", serializer);
            Assert.Contains("ownerUniqueId = NullIfWhiteSpace(owner.UniqueId)", serializer);
            Assert.Contains("name = definition?.Name ?? string.Empty", serializer);
            Assert.Contains("storageType = parameter.StorageType.ToString()", serializer);
            Assert.Contains("displayValue = DisplayValue(parameter)", serializer);
            Assert.Contains("rawValue = RawValue(parameter)", serializer);
            Assert.Contains("isReadOnly = parameter.IsReadOnly", serializer);
            Assert.Contains("builtIn = TryBuiltInName(parameter)", serializer);
            Assert.Contains("guid = TryGuid(parameter)", serializer);
            Assert.Contains("canCompareNumeric = false", serializer);
            Assert.Contains("StorageType.String", serializer);
            Assert.Contains("StorageType.Integer", serializer);
            Assert.Contains("StorageType.Double", serializer);
            Assert.Contains("StorageType.ElementId", serializer);
            Assert.Contains("parameter.Definition as InternalDefinition", serializer);
        }

        [Fact]
        public void RevitTask8_RuntimeWiresOnlyQueryElementsThroughDispatcher()
        {
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");
            var queryElements = ExtractMethod(runtime, "public BimApiResponse QueryElements(");

            Assert.Contains("private readonly RevitQueryService query;", runtime);
            Assert.Contains("this.query = new RevitQueryService();", runtime);
            Assert.Contains("return ExecuteInDocumentContext", queryElements);
            Assert.Contains("RevitContext.ActiveUiDocument(uiapp)", runtime);
            Assert.Contains("BimErrorCode.NoActiveDocument", runtime);
            Assert.Contains("query.Query(document, view, request)", runtime);
            Assert.DoesNotContain("LaterToolUnavailable", queryElements);
        }

        [Fact]
        public void RevitTask8_QueryServiceUsesBoundedCollectorsAndEffectiveFilters()
        {
            var service = Read("src/RookBim/Revit/RevitQueryService.cs");
            var query = ExtractMethod(service, "public BimApiResponse Query(");
            var validationIndex = query.IndexOf("var validation = request.Validate();", StringComparison.Ordinal);
            var collectorIndex = query.IndexOf("new FilteredElementCollector", StringComparison.Ordinal);

            Assert.True(validationIndex >= 0);
            Assert.True(collectorIndex > validationIndex);
            Assert.Contains("request.EffectiveScope == BimQueryScope.ActiveView && activeView == null", query);
            Assert.Contains("BimErrorCode.NoActiveView", query);
            Assert.Contains("new FilteredElementCollector(document, activeView!.Id)", query);
            Assert.Contains("catch (Autodesk.Revit.Exceptions.ArgumentException)", query);
            Assert.Contains("catch (ArgumentException)", query);
            Assert.Contains("new FilteredElementCollector(document)", query);
            Assert.Contains("collector.WhereElementIsNotElementType();", query);
            Assert.Contains("collector.WherePasses(categoryFilter);", query);
            Assert.Contains("var filters = request.EffectiveFilters;", query);
            Assert.DoesNotContain("request.Filters", service);
        }

        [Fact]
        public void RevitTask8_QueryServicePreflightsAmbiguousParametersAcrossCandidateSet()
        {
            var service = Read("src/RookBim/Revit/RevitQueryService.cs");
            var query = ExtractMethod(service, "public BimApiResponse Query(");
            var preflightIndex = query.IndexOf("PreflightFilterParameterAmbiguity(document, candidates, filters)", StringComparison.Ordinal);
            var filterIndex = query.IndexOf("MatchesAllFilters(element, document, filters, missingCounts)", StringComparison.Ordinal);

            Assert.True(preflightIndex >= 0);
            Assert.True(filterIndex > preflightIndex);
            Assert.Contains("private static BimApiResponse? PreflightFilterParameterAmbiguity(", service);
            Assert.Contains("ICollection<Element> candidates", service);
            Assert.Contains("foreach (var element in candidates)", service);
            Assert.Contains("GetElementAndTypeParameters(document, element)", service);
            Assert.Contains("parameter.Definition as InternalDefinition", service);
            Assert.Contains("BimErrorCode.AmbiguousParameter", service);
            Assert.Contains("error = \"ambiguous_parameter\"", service);
            Assert.Contains("candidates = identities.Values.ToList()", service);
        }

        [Fact]
        public void RevitTask8_QueryServiceCapsUnfilteredCollectionBeforeFullMaterialization()
        {
            var service = Read("src/RookBim/Revit/RevitQueryService.cs");
            var query = ExtractMethod(service, "public BimApiResponse Query(");

            Assert.Contains("if (filters.Count == 0)", query);
            Assert.Contains("CollectUnfilteredResults(collector, request.EffectiveLimit)", query);
            Assert.Contains("return BimApiResponse.Ok(BuildResult(", query);
            Assert.Contains("limit + 1", service);
            Assert.Contains("break;", ExtractMethod(service, "private static CappedElementCollection CollectUnfilteredResults("));
        }

        [Fact]
        public void RevitTask8_QueryServiceReturnsApprovedSummaryShape()
        {
            var service = Read("src/RookBim/Revit/RevitQueryService.cs");

            Assert.Contains("new BimQueryElementsResult", service);
            Assert.Contains("Document = RevitIdentitySerializer.DocumentIdentity(document)", service);
            Assert.Contains("Scope = request.EffectiveScope", service);
            Assert.Contains("View = request.EffectiveScope == BimQueryScope.ActiveView", service);
            Assert.Contains("Query = new BimQuerySummary", service);
            Assert.Contains("MissingParameterCounts = missingCounts", service);
            Assert.Contains("new BimElementSummary", service);
            Assert.Contains("Identity = RevitIdentitySerializer.ElementIdentity(element)", service);
            Assert.Contains("new BimCategorySummary", service);
            Assert.Contains("new BimElementTypeSummary", service);
        }

        [Fact]
        public void RevitTask8_QueryServiceAcceptsDisplayNamePluralCategories()
        {
            var service = Read("src/RookBim/Revit/RevitQueryService.cs");

            Assert.Contains("categories.Resolve(document, categoryName)", service);
            Assert.DoesNotContain("NormalizeCategoryCandidate", service);
            Assert.DoesNotContain("TrimTrailingPluralS", service);
            Assert.DoesNotContain("ResolveBuiltInCategory", service);
        }

        [Fact]
        public void RevitTask10_DoesNotStartWritesGraphicsOrTemporaryViewIsolation()
        {
            var revitDirectory = Path.Combine(RepoRoot, "src", "RookBim", "Revit");
            var revitFiles = Directory.GetFiles(revitDirectory, "*.cs");
            var combined = string.Join(Environment.NewLine, revitFiles.Select(File.ReadAllText));

            Assert.DoesNotContain("ParameterFilterElement", combined);
            Assert.DoesNotContain("OverrideGraphicSettings", combined);
            Assert.DoesNotContain("TemporaryView", combined);
            Assert.DoesNotContain("Transaction", combined);
        }

        [Fact]
        public void RookBimProject_CopiesBuiltModuleToExistingRookRuntimeDirectoryOnly()
        {
            var text = Read("src/RookBim/RookBim.csproj");

            Assert.Contains("CopyRookBimToRookRuntime", text);
            Assert.Contains("AfterTargets=\"Build\"", text);
            Assert.Contains("../Rook/bin/$(Configuration)/$(TargetFramework)", NormalizeProjectPath(text));
            Assert.Contains("Exists('$(RookRuntimeDir)')", text);
            Assert.Contains("$(TargetPath)", text);
            Assert.Contains("$(TargetDir)$(TargetName).pdb", text);
        }

        [Fact]
        public void RookProject_OptionallyIncludesAlreadyBuiltRookBimArtifacts()
        {
            var text = Read("src/Rook/Rook.csproj");

            Assert.Contains("../RookBim/bin/$(Configuration)/$(TargetFramework)/RookBim.dll", NormalizeProjectPath(text));
            Assert.Contains("../RookBim/bin/$(Configuration)/$(TargetFramework)/RookBim.pdb", NormalizeProjectPath(text));
            Assert.Contains("Exists('../RookBim/bin/$(Configuration)/$(TargetFramework)/RookBim.dll')", NormalizeProjectPath(text));
            Assert.Contains("Exists('../RookBim/bin/$(Configuration)/$(TargetFramework)/RookBim.pdb')", NormalizeProjectPath(text));
            Assert.Contains("<Link>RookBim.dll</Link>", text);
            Assert.Contains("<Link>RookBim.pdb</Link>", text);
            Assert.Contains("<CopyToOutputDirectory>PreserveNewest</CopyToOutputDirectory>", text);
        }

        private static void AssertRevitReference(XDocument project, string include)
        {
            var reference = project
                .Descendants("Reference")
                .Single(element => string.Equals(AttributeValue(element, "Include"), include, StringComparison.OrdinalIgnoreCase));

            Assert.Contains("$(RevitInstallDir)", ValueOf(reference, "HintPath"));
            Assert.Equal("false", ValueOf(reference, "Private"));
        }

        private static XDocument LoadProject(string relativePath)
        {
            return XDocument.Load(Path.Combine(RepoRoot, relativePath.Replace('/', Path.DirectorySeparatorChar)));
        }

        private static string Read(string relativePath)
        {
            return File.ReadAllText(Path.Combine(RepoRoot, relativePath.Replace('/', Path.DirectorySeparatorChar)));
        }

        private static string ValueOf(XContainer container, string elementName)
        {
            return container.Descendants(elementName).Select(element => element.Value).FirstOrDefault() ?? string.Empty;
        }

        private static string AttributeValue(XElement element, string attributeName)
        {
            return element.Attribute(attributeName)?.Value ?? string.Empty;
        }

        private static string NormalizeProjectPath(string value)
        {
            return value.Replace('\\', '/');
        }

        private static string NormalizeLineEndings(string value)
        {
            return value.Replace("\r\n", "\n");
        }

        private static string ExtractMethod(string source, string signatureStartText)
        {
            var signatureStart = source.IndexOf(
                signatureStartText,
                StringComparison.Ordinal);
            if (signatureStart < 0)
                throw new InvalidOperationException(
                    "Method not found: " + signatureStartText);

            var bodyStart = source.IndexOf('{', signatureStart);
            if (bodyStart < 0)
                throw new InvalidOperationException(
                    "Method body not found: " + signatureStartText);

            var depth = 0;
            for (var i = bodyStart; i < source.Length; i++)
            {
                if (source[i] == '{')
                    depth++;
                else if (source[i] == '}')
                {
                    depth--;
                    if (depth == 0)
                        return source.Substring(signatureStart, i - signatureStart + 1);
                }
            }

            throw new InvalidOperationException(
                "Brace did not close at index " + bodyStart);
        }

        private static string FindRepoRoot()
        {
            var directory = new DirectoryInfo(AppContext.BaseDirectory);
            while (directory != null)
            {
                if (File.Exists(Path.Combine(directory.FullName, "Rook.sln")))
                {
                    return directory.FullName;
                }

                directory = directory.Parent;
            }

            throw new InvalidOperationException("Could not find repository root.");
        }
    }
}
