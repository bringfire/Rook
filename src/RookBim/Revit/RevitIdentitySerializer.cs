using System;
using Autodesk.Revit.DB;
using Rook.Bim;

namespace RookBim.Revit
{
    public static class RevitIdentitySerializer
    {
        private const int InvalidElementIdValue = -1;

        public static BimDocumentIdentity DocumentIdentity(Document document)
        {
            if (document == null)
            {
                throw new ArgumentNullException(nameof(document));
            }

            var centralGuid = GetWorksharingCentralGUID(document);
            return new BimDocumentIdentity
            {
                Guid = centralGuid.HasValue ? centralGuid.Value.ToString("D") : null,
                GuidSource = centralGuid.HasValue
                    ? BimDocumentGuidSource.RevitPersistentGuid
                    : BimDocumentGuidSource.Unavailable,
                Title = NullIfWhiteSpace(document.Title),
                Path = NullIfWhiteSpace(document.PathName),
                IsFamilyDocument = document.IsFamilyDocument,
                IsWorkshared = document.IsWorkshared
            };
        }

        public static BimDocumentIdentity DocumentIdentity(
            Document document,
            BimDiagnosticContext diagnostics,
            bool includeAuxiliaryState)
        {
            if (document == null)
            {
                throw new ArgumentNullException(nameof(document));
            }

            if (diagnostics == null)
            {
                throw new ArgumentNullException(nameof(diagnostics));
            }

            var centralGuid = GetWorksharingCentralGUID(document, diagnostics);
            var title = diagnostics.Enabled
                ? BimDiagnosticProbe.Production(
                    diagnostics,
                    BimDiagnosticStage.RevitDocumentTitle,
                    () => document.Title,
                    BimDiagnosticFields.None)
                : document.Title;
            var path = diagnostics.Enabled
                ? BimDiagnosticProbe.Production(
                    diagnostics,
                    BimDiagnosticStage.RevitDocumentPath,
                    () => document.PathName,
                    BimDiagnosticFields.None)
                : document.PathName;
            var isFamilyDocument = diagnostics.Enabled
                ? BimDiagnosticProbe.Production(
                    diagnostics,
                    BimDiagnosticStage.RevitDocumentIsFamily,
                    () => document.IsFamilyDocument,
                    BimDiagnosticFields.None,
                    value => value
                        ? BimDiagnosticDetailCode.True
                        : BimDiagnosticDetailCode.False)
                : document.IsFamilyDocument;
            var outputIsWorkshared = diagnostics.Enabled
                ? BimDiagnosticProbe.Production(
                    diagnostics,
                    BimDiagnosticStage.RevitDocumentOutputIsWorkshared,
                    () => document.IsWorkshared,
                    BimDiagnosticFields.None,
                    value => value
                        ? BimDiagnosticDetailCode.True
                        : BimDiagnosticDetailCode.False)
                : document.IsWorkshared;

            var result = new BimDocumentIdentity
            {
                Guid = centralGuid.HasValue ? centralGuid.Value.ToString("D") : null,
                GuidSource = centralGuid.HasValue
                    ? BimDocumentGuidSource.RevitPersistentGuid
                    : BimDocumentGuidSource.Unavailable,
                Title = NullIfWhiteSpace(title),
                Path = NullIfWhiteSpace(path),
                IsFamilyDocument = isFamilyDocument,
                IsWorkshared = outputIsWorkshared
            };

            if (includeAuxiliaryState)
            {
                ProbeDocumentState(document, diagnostics);
            }

            return result;
        }

        public static BimViewIdentity ViewIdentity(View view)
        {
            if (view == null)
            {
                throw new ArgumentNullException(nameof(view));
            }

            return new BimViewIdentity
            {
                Id = ToInt32OrNull(view.Id) ?? InvalidElementIdValue,
                UniqueId = NullIfWhiteSpace(TryGetUniqueId(view)),
                Name = NullIfWhiteSpace(view.Name),
                Type = view.ViewType.ToString()
            };
        }

        public static BimElementIdentity ElementIdentity(Element element)
        {
            if (element == null)
            {
                throw new ArgumentNullException(nameof(element));
            }

            var document = element.Document;
            var documentIdentity = DocumentIdentity(document);
            var uniqueId = NullIfWhiteSpace(element.UniqueId);

            return new BimElementIdentity
            {
                Source = "revit",
                DocumentGuid = documentIdentity.Guid,
                DocumentGuidSource = documentIdentity.GuidSource,
                DocumentTitle = documentIdentity.Title,
                DocumentPath = documentIdentity.Path,
                ElementId = ToInt32OrNull(element.Id),
                UniqueId = uniqueId,
                FullUniqueId = uniqueId,
                Linked = false,
                Resolved = true,
                Confidence = BimIdentityConfidence.Exact
            };
        }

        public static BimElementResolveResult Resolve(Document document, BimElementIdentity? identity)
        {
            if (document == null)
            {
                throw new ArgumentNullException(nameof(document));
            }

            if (identity == null)
            {
                return BimElementResolveResult.Fail(
                    BimErrorCode.ElementNotFound,
                    "Element identity is required.");
            }

            if (HasLinkedEvidence(identity))
            {
                return BimElementResolveResult.Fail(
                    BimErrorCode.LinkedElementUnsupported,
                    "Linked Revit element identities are not supported in Phase 1.");
            }

            if (!DocumentMatches(DocumentIdentity(document), identity))
            {
                return BimElementResolveResult.Fail(
                    BimErrorCode.DocumentMismatch,
                    "Element identity belongs to a different Revit document.");
            }

            if (!string.IsNullOrWhiteSpace(identity.UniqueId))
            {
                var byUniqueId = document.GetElement(identity.UniqueId);
                if (byUniqueId != null)
                {
                    if (identity.ElementId.HasValue && !ElementIdMatches(byUniqueId.Id, identity.ElementId.Value))
                    {
                        return BimElementResolveResult.Fail(
                            BimErrorCode.ElementNotFound,
                            "Element identity uniqueId resolved, but elementId does not match.");
                    }

                    return BimElementResolveResult.Ok(byUniqueId);
                }

                return BimElementResolveResult.Fail(
                    BimErrorCode.ElementNotFound,
                    "Element identity uniqueId did not resolve in the active Revit document.");
            }

            // Only use elementId fallback when uniqueId is absent.
            if (identity.ElementId.HasValue)
            {
                var byElementId = document.GetElement(new ElementId((long)identity.ElementId.Value));
                if (byElementId != null)
                {
                    return BimElementResolveResult.Ok(byElementId);
                }
            }

            return BimElementResolveResult.Fail(
                BimErrorCode.ElementNotFound,
                "Element identity did not resolve in the active Revit document.");
        }

        private static bool DocumentMatches(
            BimDocumentIdentity documentIdentity,
            BimElementIdentity identity)
        {
            if (identity.DocumentGuidSource != BimDocumentGuidSource.RevitPersistentGuid ||
                string.IsNullOrWhiteSpace(identity.DocumentGuid))
            {
                return true;
            }

            if (documentIdentity.GuidSource != BimDocumentGuidSource.RevitPersistentGuid ||
                string.IsNullOrWhiteSpace(documentIdentity.Guid))
            {
                return false;
            }

            return string.Equals(
                documentIdentity.Guid,
                identity.DocumentGuid,
                StringComparison.OrdinalIgnoreCase);
        }

        private static bool HasLinkedEvidence(BimElementIdentity identity)
        {
            return identity.Linked ||
                identity.LinkInstanceId.HasValue ||
                !string.IsNullOrWhiteSpace(identity.LinkInstanceUniqueId) ||
                !string.IsNullOrWhiteSpace(identity.LinkedDocumentGuid) ||
                identity.LinkedElementId.HasValue ||
                !string.IsNullOrWhiteSpace(identity.LinkedElementUniqueId);
        }

        private static Guid? GetWorksharingCentralGUID(Document document)
        {
            try
            {
                if (!document.IsWorkshared)
                {
                    return null;
                }

                var guid = document.WorksharingCentralGUID;
                return guid == Guid.Empty ? (Guid?)null : guid;
            }
            catch (Autodesk.Revit.Exceptions.InapplicableDataException)
            {
                return null;
            }
            catch (Autodesk.Revit.Exceptions.InvalidOperationException)
            {
                return null;
            }
        }

        private static Guid? GetWorksharingCentralGUID(
            Document document,
            BimDiagnosticContext diagnostics)
        {
            try
            {
                var isWorkshared = diagnostics.Enabled
                    ? BimDiagnosticProbe.Production(
                        diagnostics,
                        BimDiagnosticStage.RevitDocumentCentralIsWorkshared,
                        () => document.IsWorkshared,
                        BimDiagnosticFields.None,
                        value => value
                            ? BimDiagnosticDetailCode.True
                            : BimDiagnosticDetailCode.NotWorkshared)
                    : document.IsWorkshared;
                if (!isWorkshared)
                {
                    return null;
                }

                var guid = diagnostics.Enabled
                    ? BimDiagnosticProbe.Production(
                        diagnostics,
                        BimDiagnosticStage.RevitDocumentCentralGuid,
                        () => document.WorksharingCentralGUID,
                        BimDiagnosticFields.None,
                        value => value == Guid.Empty
                            ? BimDiagnosticDetailCode.Null
                            : BimDiagnosticDetailCode.True)
                    : document.WorksharingCentralGUID;
                return guid == Guid.Empty ? (Guid?)null : guid;
            }
            catch (Autodesk.Revit.Exceptions.InapplicableDataException)
            {
                return null;
            }
            catch (Autodesk.Revit.Exceptions.InvalidOperationException)
            {
                return null;
            }
        }

        private static void ProbeDocumentState(
            Document document,
            BimDiagnosticContext diagnostics)
        {
            if (!diagnostics.Enabled)
            {
                return;
            }

            var isModelInCloud = BimDiagnosticProbe.Auxiliary(
                diagnostics,
                BimDiagnosticStage.RevitDocumentIsModelInCloud,
                () => document.IsModelInCloud,
                BooleanDetail);
            var isDetached = BimDiagnosticProbe.Auxiliary(
                diagnostics,
                BimDiagnosticStage.RevitDocumentIsDetached,
                () => document.IsDetached,
                BooleanDetail);
            var centralModelPath = BimDiagnosticProbe.Auxiliary(
                diagnostics,
                BimDiagnosticStage.RevitDocumentCentralModelPath,
                () => document.GetWorksharingCentralModelPath(),
                value => value == null
                    ? BimDiagnosticDetailCode.Null
                    : BimDiagnosticDetailCode.True);

            BimAuxiliaryProbeResult<bool>? empty = null;
            BimAuxiliaryProbeResult<bool>? serverPath = null;
            BimAuxiliaryProbeResult<bool>? cloudPath = null;
            if (centralModelPath.Known && centralModelPath.Value != null)
            {
                var modelPath = centralModelPath.Value;
                empty = BimDiagnosticProbe.Auxiliary(
                    diagnostics,
                    BimDiagnosticStage.RevitDocumentModelPathEmpty,
                    () => modelPath.Empty,
                    BooleanDetail);
                serverPath = BimDiagnosticProbe.Auxiliary(
                    diagnostics,
                    BimDiagnosticStage.RevitDocumentModelPathServer,
                    () => modelPath.ServerPath,
                    BooleanDetail);
                cloudPath = BimDiagnosticProbe.Auxiliary(
                    diagnostics,
                    BimDiagnosticStage.RevitDocumentModelPathCloud,
                    () => modelPath.CloudPath,
                    BooleanDetail);
            }

            BimDiagnostics.Observe(
                diagnostics,
                BimDiagnosticStage.RevitDocumentCentralModelPath,
                BimDiagnosticOutcome.Success,
                new BimDiagnosticFields(
                    ClassifyDocumentState(
                        isModelInCloud,
                        isDetached,
                        centralModelPath,
                        empty,
                        serverPath,
                        cloudPath),
                    null,
                    BimDiagnosticFailureImpact.Auxiliary));
        }

        private static BimDiagnosticDetailCode ClassifyDocumentState(
            BimAuxiliaryProbeResult<bool> isModelInCloud,
            BimAuxiliaryProbeResult<bool> isDetached,
            BimAuxiliaryProbeResult<ModelPath> centralModelPath,
            BimAuxiliaryProbeResult<bool>? empty,
            BimAuxiliaryProbeResult<bool>? serverPath,
            BimAuxiliaryProbeResult<bool>? cloudPath)
        {
            if (!isModelInCloud.Known ||
                !isDetached.Known ||
                !centralModelPath.Known ||
                centralModelPath.Value != null &&
                (!empty.HasValue || !empty.Value.Known ||
                 !serverPath.HasValue || !serverPath.Value.Known ||
                 !cloudPath.HasValue || !cloudPath.Value.Known))
            {
                return BimDiagnosticDetailCode.Unknown;
            }

            if (isDetached.Known && isDetached.Value)
            {
                return BimDiagnosticDetailCode.Detached;
            }

            if (centralModelPath.Known && centralModelPath.Value == null ||
                empty.HasValue && empty.Value.Known && empty.Value.Value)
            {
                return BimDiagnosticDetailCode.Unsaved;
            }

            if (isModelInCloud.Known && isModelInCloud.Value ||
                cloudPath.HasValue && cloudPath.Value.Known && cloudPath.Value.Value)
            {
                return BimDiagnosticDetailCode.Cloud;
            }

            if (serverPath.HasValue && serverPath.Value.Known && serverPath.Value.Value)
            {
                return BimDiagnosticDetailCode.Server;
            }

            if (centralModelPath.Known && centralModelPath.Value != null &&
                empty.HasValue && empty.Value.Known &&
                serverPath.HasValue && serverPath.Value.Known &&
                cloudPath.HasValue && cloudPath.Value.Known)
            {
                return BimDiagnosticDetailCode.File;
            }

            return BimDiagnosticDetailCode.Unknown;
        }

        private static BimDiagnosticDetailCode BooleanDetail(bool value)
        {
            return value
                ? BimDiagnosticDetailCode.True
                : BimDiagnosticDetailCode.False;
        }

        private static string? TryGetUniqueId(Element element)
        {
            try
            {
                return element.UniqueId;
            }
            catch (Autodesk.Revit.Exceptions.InvalidOperationException)
            {
                return null;
            }
        }

        private static string? NullIfWhiteSpace(string? value)
        {
            return string.IsNullOrWhiteSpace(value) ? null : value;
        }

        private static int? ToInt32OrNull(ElementId? id)
        {
            if (id == null)
            {
                return null;
            }

            var value = id.Value;
            if (value < int.MinValue || value > int.MaxValue)
            {
                return null;
            }

            return (int)value;
        }

        private static bool ElementIdMatches(ElementId actual, int expected)
        {
            var actualValue = ToInt32OrNull(actual);
            return actualValue.HasValue && actualValue.Value == expected;
        }
    }

    public sealed class BimElementResolveResult
    {
        public bool Success { get; private set; }

        public Element? Element { get; private set; }

        public BimErrorCode ErrorCode { get; private set; }

        public string? Message { get; private set; }

        public static BimElementResolveResult Ok(Element element)
        {
            return new BimElementResolveResult
            {
                Success = true,
                Element = element,
                ErrorCode = BimErrorCode.None
            };
        }

        public static BimElementResolveResult Fail(BimErrorCode errorCode, string message)
        {
            return new BimElementResolveResult
            {
                Success = false,
                ErrorCode = errorCode,
                Message = message
            };
        }
    }
}
