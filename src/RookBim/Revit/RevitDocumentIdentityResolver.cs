using System;
using System.Collections.Generic;
using Autodesk.Revit.DB;
using Rook.Bim;

namespace RookBim.Revit
{
    internal sealed class RevitDocumentIdentityEvidence
    {
        internal RevitDocumentIdentityEvidence(
            Document owner,
            BimDocumentIdentityPolicy.Evidence identity,
            string? title,
            string? path,
            bool isFamilyDocument,
            bool isWorkshared)
        {
            Owner = owner ?? throw new ArgumentNullException(nameof(owner));
            Identity = identity ?? throw new ArgumentNullException(nameof(identity));
            Title = title;
            Path = path;
            IsFamilyDocument = isFamilyDocument;
            IsWorkshared = isWorkshared;
        }

        internal Document Owner { get; }

        internal BimDocumentIdentityPolicy.Evidence Identity { get; }

        internal string? Title { get; }

        internal string? Path { get; }

        internal bool IsFamilyDocument { get; }

        internal bool IsWorkshared { get; }
    }

    internal static class RevitDocumentIdentityResolver
    {
        internal static RevitDocumentIdentityEvidence Capture(
            Document document,
            BimDiagnosticContext diagnostics)
        {
            if (document == null)
            {
                throw new ArgumentNullException(nameof(document));
            }

            if (diagnostics == null)
            {
                throw new ArgumentNullException(nameof(diagnostics));
            }

            var title = ReadIdentityProperty<string?>(
                diagnostics,
                BimDiagnosticStage.RevitDocumentTitle,
                () => document.Title,
                BimDocumentIdentityPolicy.UnavailableReason.KeyMaterialUnavailable);
            var path = ReadIdentityProperty<string?>(
                diagnostics,
                BimDiagnosticStage.RevitDocumentPath,
                () => document.PathName,
                BimDocumentIdentityPolicy.UnavailableReason.KeyMaterialUnavailable);

            BimDocumentIdentityPolicy.ReadResult<bool>? detached = null;
            BimDocumentIdentityPolicy.ReadResult<bool>? workshared = null;
            BimDocumentIdentityPolicy.ReadResult<bool>? cloud = null;
            BimDocumentIdentityPolicy.ReadResult<bool>? family = null;
            BimDocumentIdentityPolicy.ReadResult<BimDocumentIdentityPolicy.CentralPath>? central = null;
            BimDocumentIdentityPolicy.ReadResult<Guid>? creationGuid = null;
            BimDocumentIdentityPolicy.ReadResult<Guid>? serverCentralGuid = null;

            BimDocumentIdentityPolicy.ReadResult<bool> ReadIsDetached()
            {
                if (!detached.HasValue)
                {
                    detached = ReadIdentityProperty(
                        diagnostics,
                        BimDiagnosticStage.RevitDocumentIsDetached,
                        () => document.IsDetached,
                        BimDocumentIdentityPolicy.UnavailableReason.DiscriminatorUnavailable);
                }

                return detached.Value;
            }

            BimDocumentIdentityPolicy.ReadResult<bool> ReadIsWorkshared()
            {
                if (!workshared.HasValue)
                {
                    workshared = ReadIdentityProperty(
                        diagnostics,
                        BimDiagnosticStage.RevitDocumentCentralIsWorkshared,
                        () => document.IsWorkshared,
                        BimDocumentIdentityPolicy.UnavailableReason.DiscriminatorUnavailable);
                }

                return workshared.Value;
            }

            BimDocumentIdentityPolicy.ReadResult<bool> ReadIsModelInCloud()
            {
                if (!cloud.HasValue)
                {
                    cloud = ReadIdentityProperty(
                        diagnostics,
                        BimDiagnosticStage.RevitDocumentIsModelInCloud,
                        () => document.IsModelInCloud,
                        BimDocumentIdentityPolicy.UnavailableReason.DiscriminatorUnavailable);
                }

                return cloud.Value;
            }

            BimDocumentIdentityPolicy.ReadResult<bool> ReadIsFamilyDocument()
            {
                if (!family.HasValue)
                {
                    family = ReadIdentityProperty(
                        diagnostics,
                        BimDiagnosticStage.RevitDocumentIsFamily,
                        () => document.IsFamilyDocument,
                        BimDocumentIdentityPolicy.UnavailableReason.DiscriminatorUnavailable);
                }

                return family.Value;
            }

            BimDocumentIdentityPolicy.ReadResult<BimDocumentIdentityPolicy.CentralPath> ReadCentralPath()
            {
                if (!central.HasValue)
                {
                    central = ReadCentralModelPath(document, diagnostics);
                }

                return central.Value;
            }

            BimDocumentIdentityPolicy.ReadResult<Guid> ReadCreationGuid()
            {
                if (!creationGuid.HasValue)
                {
                    creationGuid = ReadIdentityProperty(
                        diagnostics,
                        BimDiagnosticStage.RevitDocumentCreationGuid,
                        () => document.CreationGUID,
                        BimDocumentIdentityPolicy.UnavailableReason.KeyMaterialUnavailable);
                }

                return creationGuid.Value;
            }

            BimDocumentIdentityPolicy.ReadResult<Guid> ReadServerGuid()
            {
                if (!serverCentralGuid.HasValue)
                {
                    serverCentralGuid = ReadServerCentralGuid(document, diagnostics);
                }

                return serverCentralGuid.Value;
            }

            var readers = new BimDocumentIdentityPolicy.Readers(
                ReadIsDetached,
                ReadIsWorkshared,
                ReadIsModelInCloud,
                ReadIsFamilyDocument,
                () => path,
                ReadCentralPath,
                ReadCreationGuid,
                ReadServerGuid);
            var identity = BimDocumentIdentityPolicy.Capture(readers);

            ObserveIdentityResult(diagnostics, identity);

            return new RevitDocumentIdentityEvidence(
                document,
                identity,
                title.Available ? NullIfWhiteSpace(title.Value) : null,
                path.Available ? NullIfWhiteSpace(path.Value) : null,
                family.HasValue && family.Value.Available && family.Value.Value,
                workshared.HasValue && workshared.Value.Available && workshared.Value.Value);
        }

        internal static BimDocumentIdentity ProjectDocument(
            RevitDocumentIdentityEvidence evidence)
        {
            if (evidence == null)
            {
                throw new ArgumentNullException(nameof(evidence));
            }

            var identity = evidence.Identity;
            return new BimDocumentIdentity
            {
                DocumentKey = identity.DocumentKey,
                DocumentKeySource = identity.DocumentKeySource,
                Guid = identity.LegacyGuidSource == BimDocumentGuidSource.RevitPersistentGuid &&
                    identity.LegacyGuid.HasValue
                        ? identity.LegacyGuid.Value.ToString("D")
                        : null,
                GuidSource = identity.LegacyGuidSource,
                Title = evidence.Title,
                Path = evidence.Path,
                IsFamilyDocument = evidence.IsFamilyDocument,
                IsWorkshared = evidence.IsWorkshared,
            };
        }

        internal static bool IsSameDocument(Document? left, Document? right)
        {
            if (left is null || right is null)
            {
                return false;
            }

            return left.Equals(right);
        }

        internal static BimElementIdentity ProjectElement(
            RevitDocumentIdentityEvidence evidence,
            Element element)
        {
            if (evidence == null)
            {
                throw new ArgumentNullException(nameof(evidence));
            }

            if (element == null)
            {
                throw new ArgumentNullException(nameof(element));
            }

            if (!RevitDocumentIdentityResolver.IsSameDocument(element.Document, evidence.Owner))
            {
                throw new InvalidOperationException(
                    "The Revit element is not owned by the captured document evidence.");
            }

            var identity = evidence.Identity;
            var uniqueId = NullIfWhiteSpace(TryGetUniqueId(element));
            return new BimElementIdentity
            {
                Source = "revit",
                DocumentKey = identity.DocumentKey,
                DocumentKeySource = identity.DocumentKeySource,
                DocumentGuid = identity.LegacyGuidSource == BimDocumentGuidSource.RevitPersistentGuid &&
                    identity.LegacyGuid.HasValue
                        ? identity.LegacyGuid.Value.ToString("D")
                        : null,
                DocumentGuidSource = identity.LegacyGuidSource,
                DocumentTitle = evidence.Title,
                DocumentPath = evidence.Path,
                ElementId = ToInt32OrNull(element.Id),
                UniqueId = uniqueId,
                FullUniqueId = uniqueId,
                Linked = false,
                Resolved = true,
                Confidence = BimIdentityConfidence.Exact,
            };
        }

        internal static BimDocumentIdentityPolicy.Claim CreateClaim(
            BimElementIdentity identity)
        {
            if (identity == null)
            {
                throw new ArgumentNullException(nameof(identity));
            }

            return new BimDocumentIdentityPolicy.Claim(
                identity.Source,
                identity.DocumentKey,
                identity.DocumentKeySource,
                identity.DocumentGuid,
                identity.DocumentGuidSource,
                identity.Linked,
                identity.LinkInstanceId,
                identity.LinkInstanceUniqueId,
                identity.LinkedDocumentGuid,
                identity.LinkedElementId,
                identity.LinkedElementUniqueId,
                identity.UniqueId,
                identity.ElementId);
        }

        internal static BimElementResolveResult PreflightBatch(
            RevitDocumentIdentityEvidence evidence,
            IReadOnlyList<BimElementIdentity?> identities,
            BimDiagnosticContext diagnostics)
        {
            if (evidence == null)
            {
                throw new ArgumentNullException(nameof(evidence));
            }

            if (identities == null)
            {
                throw new ArgumentNullException(nameof(identities));
            }

            var claims = new List<BimDocumentIdentityPolicy.Claim?>(identities.Count);
            foreach (var identity in identities)
            {
                claims.Add(identity == null ? null : CreateClaim(identity));
            }

            var result = BimDocumentIdentityPolicy.PreflightBatch(evidence.Identity, claims);
            ObserveComparison(diagnostics, result.Outcome);
            var suffix = result.ItemIndex.HasValue
                ? $" at index {result.ItemIndex.Value}"
                : string.Empty;
            switch (result.Outcome)
            {
                case BimDocumentIdentityPolicy.PreflightOutcome.Valid:
                    return BimElementResolveResult.PreflightValid();
                case BimDocumentIdentityPolicy.PreflightOutcome.Mismatch:
                    return BimElementResolveResult.Fail(
                        BimErrorCode.DocumentMismatch,
                        $"Element identity belongs to a different Revit document{suffix}.");
                case BimDocumentIdentityPolicy.PreflightOutcome.Unavailable:
                    return BimElementResolveResult.Fail(
                        BimErrorCode.DocumentIdentityUnavailable,
                        $"The active Revit document cannot establish comparable identity evidence{suffix}.");
                case BimDocumentIdentityPolicy.PreflightOutcome.InvalidEvidence:
                    return BimElementResolveResult.Fail(
                        BimErrorCode.DocumentIdentityInvalid,
                        $"Element identity contains invalid or conflicting document evidence{suffix}.");
                case BimDocumentIdentityPolicy.PreflightOutcome.LinkedElementUnsupported:
                    return BimElementResolveResult.Fail(
                        BimErrorCode.LinkedElementUnsupported,
                        $"Linked Revit element identities are not supported in Phase 1{suffix}.");
                case BimDocumentIdentityPolicy.PreflightOutcome.ElementLocatorInvalid:
                    return BimElementResolveResult.Fail(
                        BimErrorCode.ElementNotFound,
                        $"Element identity requires a uniqueId or elementId{suffix}.");
                default:
                    return BimElementResolveResult.Fail(
                        BimErrorCode.DocumentIdentityInvalid,
                        $"Element identity preflight returned an invalid outcome{suffix}.");
            }
        }

        internal static BimElementResolveResult ResolveAfterPreflight(
            RevitDocumentIdentityEvidence evidence,
            BimElementIdentity identity)
        {
            if (evidence == null)
            {
                throw new ArgumentNullException(nameof(evidence));
            }

            if (identity == null)
            {
                throw new ArgumentNullException(nameof(identity));
            }

            var document = evidence.Owner;
            if (!string.IsNullOrWhiteSpace(identity.UniqueId))
            {
                var byUniqueId = document.GetElement(identity.UniqueId);
                if (byUniqueId != null)
                {
                    if (!RevitDocumentIdentityResolver.IsSameDocument(byUniqueId.Document, evidence.Owner))
                    {
                        return BimElementResolveResult.Fail(
                            BimErrorCode.DocumentIdentityInvalid,
                            "Resolved Revit element is not owned by the captured document.");
                    }

                    if (identity.ElementId.HasValue &&
                        !ElementIdMatches(byUniqueId.Id, identity.ElementId.Value))
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

            if (identity.ElementId.HasValue)
            {
                var byElementId = document.GetElement(new ElementId((long)identity.ElementId.Value));
                if (byElementId != null && RevitDocumentIdentityResolver.IsSameDocument(byElementId.Document, evidence.Owner))
                {
                    return BimElementResolveResult.Ok(byElementId);
                }
            }

            return BimElementResolveResult.Fail(
                BimErrorCode.ElementNotFound,
                "Element identity did not resolve in the active Revit document.");
        }

        internal static int HttpStatusFor(BimErrorCode code)
        {
            switch (code)
            {
                case BimErrorCode.DocumentMismatch:
                case BimErrorCode.DocumentIdentityUnavailable:
                case BimErrorCode.LinkedElementUnsupported:
                    return 409;
                case BimErrorCode.ElementNotFound:
                    return 404;
                case BimErrorCode.DocumentIdentityInvalid:
                default:
                    return 400;
            }
        }

        private static BimDocumentIdentityPolicy.ReadResult<BimDocumentIdentityPolicy.CentralPath> ReadCentralModelPath(
            Document document,
            BimDiagnosticContext diagnostics)
        {
            var central = ReadIdentityProperty(
                diagnostics,
                BimDiagnosticStage.RevitDocumentCentralModelPath,
                () => document.GetWorksharingCentralModelPath(),
                BimDocumentIdentityPolicy.UnavailableReason.KeyMaterialUnavailable);
            if (!central.Available)
            {
                return BimDocumentIdentityPolicy.ReadResult<BimDocumentIdentityPolicy.CentralPath>
                    .Unavailable(central.Reason);
            }

            if (central.Value == null)
            {
                return BimDocumentIdentityPolicy.ReadResult<BimDocumentIdentityPolicy.CentralPath>
                    .Unavailable(BimDocumentIdentityPolicy.UnavailableReason.KeyMaterialUnavailable);
            }

            var modelPath = central.Value;
            var empty = ReadIdentityProperty(
                diagnostics,
                BimDiagnosticStage.RevitDocumentModelPathEmpty,
                () => modelPath.Empty,
                BimDocumentIdentityPolicy.UnavailableReason.KeyMaterialUnavailable);
            if (!empty.Available || empty.Value)
            {
                return BimDocumentIdentityPolicy.ReadResult<BimDocumentIdentityPolicy.CentralPath>
                    .Unavailable(empty.Available
                        ? BimDocumentIdentityPolicy.UnavailableReason.KeyMaterialUnavailable
                        : empty.Reason);
            }

            var cloud = ReadIdentityProperty(
                diagnostics,
                BimDiagnosticStage.RevitDocumentModelPathCloud,
                () => modelPath.CloudPath,
                BimDocumentIdentityPolicy.UnavailableReason.DiscriminatorUnavailable);
            if (!cloud.Available)
            {
                return BimDocumentIdentityPolicy.ReadResult<BimDocumentIdentityPolicy.CentralPath>
                    .Unavailable(cloud.Reason);
            }

            if (cloud.Value)
            {
                return BimDocumentIdentityPolicy.ReadResult<BimDocumentIdentityPolicy.CentralPath>
                    .Success(new BimDocumentIdentityPolicy.CentralPath(
                        BimDocumentIdentityPolicy.CentralPathKind.Cloud,
                        null));
            }

            var server = ReadIdentityProperty(
                diagnostics,
                BimDiagnosticStage.RevitDocumentModelPathServer,
                () => modelPath.ServerPath,
                BimDocumentIdentityPolicy.UnavailableReason.DiscriminatorUnavailable);
            if (!server.Available)
            {
                return BimDocumentIdentityPolicy.ReadResult<BimDocumentIdentityPolicy.CentralPath>
                    .Unavailable(server.Reason);
            }

            if (server.Value)
            {
                return BimDocumentIdentityPolicy.ReadResult<BimDocumentIdentityPolicy.CentralPath>
                    .Success(new BimDocumentIdentityPolicy.CentralPath(
                        BimDocumentIdentityPolicy.CentralPathKind.Server,
                        null));
            }

            var converted = ReadIdentityProperty(
                diagnostics,
                BimDiagnosticStage.RevitDocumentModelPathConvert,
                () => ModelPathUtils.ConvertModelPathToUserVisiblePath(modelPath),
                BimDocumentIdentityPolicy.UnavailableReason.KeyMaterialUnavailable);
            return converted.Available
                ? BimDocumentIdentityPolicy.ReadResult<BimDocumentIdentityPolicy.CentralPath>
                    .Success(new BimDocumentIdentityPolicy.CentralPath(
                        BimDocumentIdentityPolicy.CentralPathKind.File,
                        converted.Value))
                : BimDocumentIdentityPolicy.ReadResult<BimDocumentIdentityPolicy.CentralPath>
                    .Unavailable(converted.Reason);
        }

        private static BimDocumentIdentityPolicy.ReadResult<Guid> ReadServerCentralGuid(
            Document document,
            BimDiagnosticContext diagnostics)
        {
            return ReadIdentityProperty(
                diagnostics,
                BimDiagnosticStage.RevitDocumentCentralGuid,
                () => document.WorksharingCentralGUID,
                BimDocumentIdentityPolicy.UnavailableReason.KeyMaterialUnavailable);
        }

        private static BimDocumentIdentityPolicy.ReadResult<T> ReadIdentityProperty<T>(
            BimDiagnosticContext diagnostics,
            BimDiagnosticStage stage,
            Func<T> getter,
            BimDocumentIdentityPolicy.UnavailableReason failureReason)
        {
            Func<T> effectiveRead = diagnostics.Enabled
                ? () => BimDiagnosticProbe.Production(
                    diagnostics, stage, getter, BimDiagnosticFields.None)
                : getter;
            return BimDocumentIdentityPolicy.CaptureRead(
                effectiveRead,
                IsExpectedIdentityException,
                failureReason);
        }

        private static bool IsExpectedIdentityException(Exception exception)
        {
            return exception is Autodesk.Revit.Exceptions.InapplicableDataException ||
                exception is Autodesk.Revit.Exceptions.InvalidOperationException ||
                exception is Autodesk.Revit.Exceptions.InternalException ||
                exception is Autodesk.Revit.Exceptions.InvalidObjectException ||
                exception is Autodesk.Revit.Exceptions.ArgumentException ||
                exception is Autodesk.Revit.Exceptions.ArgumentNullException;
        }

        private static void ObserveIdentityResult(
            BimDiagnosticContext diagnostics,
            BimDocumentIdentityPolicy.Evidence identity)
        {
            if (!diagnostics.Enabled)
            {
                return;
            }

            var classDetail = ClassDetail(identity.Class);
            BimDiagnostics.Observe(
                diagnostics,
                BimDiagnosticStage.RevitDocumentIdentityClassify,
                identity.Class == BimDocumentIdentityPolicy.DocumentClass.Unknown
                    ? BimDiagnosticOutcome.Failure
                    : BimDiagnosticOutcome.Success,
                new BimDiagnosticFields(
                    classDetail,
                    null,
                    BimDiagnosticFailureImpact.Production));

            if (identity.Class == BimDocumentIdentityPolicy.DocumentClass.FileWorkshared ||
                identity.Class == BimDocumentIdentityPolicy.DocumentClass.SavedProject)
            {
                BimDiagnostics.Observe(
                    diagnostics,
                    BimDiagnosticStage.RevitDocumentPathCanonicalize,
                    identity.DocumentKey == null
                        ? BimDiagnosticOutcome.Failure
                        : BimDiagnosticOutcome.Success,
                    new BimDiagnosticFields(
                        classDetail,
                        null,
                        BimDiagnosticFailureImpact.Production));
            }

            BimDiagnostics.Observe(
                diagnostics,
                BimDiagnosticStage.RevitDocumentKeySource,
                identity.DocumentKeySource == BimDocumentKeySource.Unavailable
                    ? BimDiagnosticOutcome.Failure
                    : BimDiagnosticOutcome.Success,
                new BimDiagnosticFields(
                    identity.DocumentKeySource == BimDocumentKeySource.Unavailable
                        ? BimDiagnosticDetailCode.Unavailable
                        : classDetail,
                    null,
                    BimDiagnosticFailureImpact.Production));
        }

        private static void ObserveComparison(
            BimDiagnosticContext diagnostics,
            BimDocumentIdentityPolicy.PreflightOutcome outcome)
        {
            if (!diagnostics.Enabled)
            {
                return;
            }

            BimDiagnostics.Observe(
                diagnostics,
                BimDiagnosticStage.RevitDocumentIdentityCompare,
                outcome == BimDocumentIdentityPolicy.PreflightOutcome.Valid
                    ? BimDiagnosticOutcome.Success
                    : BimDiagnosticOutcome.Failure,
                new BimDiagnosticFields(
                    outcome == BimDocumentIdentityPolicy.PreflightOutcome.Valid
                        ? BimDiagnosticDetailCode.Match
                        : outcome == BimDocumentIdentityPolicy.PreflightOutcome.Mismatch
                            ? BimDiagnosticDetailCode.Mismatch
                            : outcome == BimDocumentIdentityPolicy.PreflightOutcome.Unavailable
                                ? BimDiagnosticDetailCode.Unavailable
                                : BimDiagnosticDetailCode.InvalidEvidence,
                    null,
                    BimDiagnosticFailureImpact.Production));
        }

        private static BimDiagnosticDetailCode ClassDetail(
            BimDocumentIdentityPolicy.DocumentClass documentClass)
        {
            switch (documentClass)
            {
                case BimDocumentIdentityPolicy.DocumentClass.FileWorkshared:
                    return BimDiagnosticDetailCode.FileWorkshared;
                case BimDocumentIdentityPolicy.DocumentClass.SavedProject:
                    return BimDiagnosticDetailCode.SavedProject;
                case BimDocumentIdentityPolicy.DocumentClass.RevitServer:
                    return BimDiagnosticDetailCode.Server;
                case BimDocumentIdentityPolicy.DocumentClass.CloudWorkshared:
                    return BimDiagnosticDetailCode.Cloud;
                case BimDocumentIdentityPolicy.DocumentClass.SavedFamily:
                case BimDocumentIdentityPolicy.DocumentClass.UnsavedFamily:
                    return BimDiagnosticDetailCode.Family;
                case BimDocumentIdentityPolicy.DocumentClass.UnsavedProject:
                    return BimDiagnosticDetailCode.Unsaved;
                case BimDocumentIdentityPolicy.DocumentClass.Detached:
                    return BimDiagnosticDetailCode.Detached;
                default:
                    return BimDiagnosticDetailCode.Unknown;
            }
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
            if (id == null || id.Value < int.MinValue || id.Value > int.MaxValue)
            {
                return null;
            }

            return (int)id.Value;
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

        internal static BimElementResolveResult PreflightValid()
        {
            return new BimElementResolveResult
            {
                Success = true,
                ErrorCode = BimErrorCode.None,
            };
        }

        public static BimElementResolveResult Ok(Element element)
        {
            return new BimElementResolveResult
            {
                Success = true,
                Element = element,
                ErrorCode = BimErrorCode.None,
            };
        }

        public static BimElementResolveResult Fail(BimErrorCode errorCode, string message)
        {
            return new BimElementResolveResult
            {
                Success = false,
                ErrorCode = errorCode,
                Message = message,
            };
        }
    }
}
