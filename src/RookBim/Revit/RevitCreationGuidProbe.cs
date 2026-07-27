using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using Rook.Bim;

namespace RookBim.Revit
{
    internal sealed class RevitCreationGuidProbe
    {
        private readonly object sync = new object();
        private BimCreationGuidProbeSession? session;

        internal BimApiResponse Execute(UIApplication uiapp, Document? document,
            BimDiagnosticContext diagnostics, BimCreationGuidProbeRequest request)
        {
            if (uiapp == null)
            {
                throw new ArgumentNullException(nameof(uiapp));
            }

            if (request == null)
            {
                return BimApiResponse.Fail(BimErrorCode.InvalidScope,
                    "CreationGUID probe request is required.", 400);
            }

            lock (sync)
            {
                switch (request.Action)
                {
                    case BimCreationGuidProbeAction.Begin:
                        return Begin(uiapp);
                    case BimCreationGuidProbeAction.Capture:
                        return Capture(document, request.CaseId);
                    case BimCreationGuidProbeAction.Complete:
                        return Complete();
                    case BimCreationGuidProbeAction.Abort:
                        return Abort();
                    default:
                        return BimApiResponse.Fail(BimErrorCode.InvalidScope,
                            "CreationGUID probe action is invalid.", 400);
                }
            }
        }

        private BimApiResponse Begin(UIApplication uiapp)
        {
            if (session != null)
            {
                return BimApiResponse.Fail(BimErrorCode.InvalidScope,
                    "A CreationGUID probe session is already active.", 409);
            }

            var provenance = BuildProvenance(uiapp);
            session = new BimCreationGuidProbeSession(provenance);
            return BimApiResponse.Ok(new
            {
                code = "begun",
                provenance,
            });
        }

        private BimApiResponse Capture(Document? document, BimCreationGuidProbeCase? caseId)
        {
            if (session == null)
            {
                return BimApiResponse.Fail(BimErrorCode.InvalidScope,
                    "No CreationGUID probe session is active.", 409);
            }

            if (!caseId.HasValue)
            {
                return BimApiResponse.Fail(BimErrorCode.InvalidScope,
                    "CreationGUID capture requires a case.", 400);
            }

            if (document == null)
            {
                return BimApiResponse.Fail(BimErrorCode.NoActiveDocument,
                    "No active Revit document is open.", 409);
            }

            var result = session.Capture(Collect(document, caseId.Value));
            return result.Code == BimCreationGuidProbeSessionCode.Captured
                ? BimApiResponse.Ok(result)
                : BimApiResponse.Fail(BimErrorCode.InvalidScope,
                    "The requested CreationGUID case could not be captured.", 409);
        }

        private BimApiResponse Complete()
        {
            if (session == null)
            {
                return BimApiResponse.Fail(BimErrorCode.InvalidScope,
                    "No CreationGUID probe session is active.", 409);
            }

            var result = session.Complete();
            if (result.Code != BimCreationGuidProbeSessionCode.Completed)
            {
                return BimApiResponse.Fail(BimErrorCode.InvalidScope,
                    "The CreationGUID probe matrix is incomplete.", 409);
            }

            session = null;
            return BimApiResponse.Ok(result);
        }

        private BimApiResponse Abort()
        {
            if (session == null)
            {
                return BimApiResponse.Ok(new BimCreationGuidProbeAbortResult(
                    BimCreationGuidProbeSessionCode.NotActive, true));
            }

            var result = session.Abort();
            session = null;
            return BimApiResponse.Ok(result);
        }

        private static BimCreationGuidProbeObservation Collect(Document document, BimCreationGuidProbeCase caseId)
        {
            var failures = new List<BimCreationGuidProbeFailureFact>();
            var isWorkshared = Read(BimCreationGuidProbeStage.IsWorkshared, () => document.IsWorkshared);
            var isDetached = Read(BimCreationGuidProbeStage.IsDetached, () => document.IsDetached);
            var isModelInCloud = Read(BimCreationGuidProbeStage.IsModelInCloud, () => document.IsModelInCloud);
            var isFamilyDocument = Read(BimCreationGuidProbeStage.IsFamilyDocument, () => document.IsFamilyDocument);
            var creationFirst = Read(BimCreationGuidProbeStage.CreationGuidFirst, () => document.CreationGUID);
            var creationSecond = Read(BimCreationGuidProbeStage.CreationGuidSecond, () => document.CreationGUID);
            var documentPath = Read(BimCreationGuidProbeStage.DocumentPath, () => document.PathName);
            var centralModelPath = Read(BimCreationGuidProbeStage.CentralModelPath,
                () => document.GetWorksharingCentralModelPath());

            AddFailure(failures, isWorkshared);
            AddFailure(failures, isDetached);
            AddFailure(failures, isModelInCloud);
            AddFailure(failures, isFamilyDocument);
            AddFailure(failures, creationFirst);
            AddFailure(failures, creationSecond);
            AddFailure(failures, documentPath);
            AddFailure(failures, centralModelPath);

            ProbeValue<bool> serverPath = ProbeValue<bool>.NotApplicable(
                BimCreationGuidProbeStage.ModelPathServer);
            ProbeValue<bool> cloudPath = ProbeValue<bool>.NotApplicable(
                BimCreationGuidProbeStage.ModelPathCloud);
            ProbeValue<string> convertedCentralPath = ProbeValue<string>.NotApplicable(
                BimCreationGuidProbeStage.ModelPathConvert);
            if (centralModelPath.Succeeded && centralModelPath.Value != null)
            {
                serverPath = Read(BimCreationGuidProbeStage.ModelPathServer,
                    () => centralModelPath.Value.ServerPath);
                cloudPath = Read(BimCreationGuidProbeStage.ModelPathCloud,
                    () => centralModelPath.Value.CloudPath);
                AddFailure(failures, serverPath);
                AddFailure(failures, cloudPath);

                if (serverPath.NullableValue == false && cloudPath.NullableValue == false)
                {
                    convertedCentralPath = Read(BimCreationGuidProbeStage.ModelPathConvert,
                        () => ModelPathUtils.ConvertModelPathToUserVisiblePath(centralModelPath.Value));
                    AddFailure(failures, convertedCentralPath);
                }
            }

            string? canonicalDocumentPath = null;
            var documentPathStatus = documentPath.Status;
            if (documentPath.Succeeded && !string.IsNullOrWhiteSpace(documentPath.Value))
            {
                var canonical = Read(BimCreationGuidProbeStage.DocumentPathCanonicalize,
                    () => BimCreationGuidProbePathCanonicalizer.TryCanonicalize(
                        documentPath.Value, out var value) ? value : null);
                AddFailure(failures, canonical);
                canonicalDocumentPath = canonical.Succeeded ? canonical.Value : null;
                if (canonical.Succeeded && canonical.Value == null)
                {
                    documentPathStatus = BimCreationGuidProbeReadStatus.Failure;
                }
            }

            string? canonicalCentralPath = null;
            var centralPathStatus = centralModelPath.Succeeded && centralModelPath.Value != null
                ? convertedCentralPath.Status
                : centralModelPath.Status;
            if (convertedCentralPath.Succeeded && !string.IsNullOrWhiteSpace(convertedCentralPath.Value))
            {
                var canonical = Read(BimCreationGuidProbeStage.CentralPathCanonicalize,
                    () => BimCreationGuidProbePathCanonicalizer.TryCanonicalize(
                        convertedCentralPath.Value, out var value) ? value : null);
                AddFailure(failures, canonical);
                canonicalCentralPath = canonical.Succeeded ? canonical.Value : null;
                if (canonical.Succeeded && canonical.Value == null)
                {
                    centralPathStatus = BimCreationGuidProbeReadStatus.Failure;
                }
            }

            var fileEvidence = documentPath.Succeeded && !string.IsNullOrWhiteSpace(documentPath.Value)
                ? ReadBasicFileInfo(documentPath.Value)
                : BasicFileEvidence.NotApplicable();
            failures.AddRange(fileEvidence.Failures);

            var creationNonEmpty = creationFirst.Succeeded
                ? creationFirst.Value != Guid.Empty : (bool?)null;
            var creationStable = creationFirst.Succeeded && creationSecond.Succeeded &&
                creationFirst.Value != Guid.Empty && creationSecond.Value != Guid.Empty
                    ? creationFirst.Value == creationSecond.Value : (bool?)null;

            return new BimCreationGuidProbeObservation
            {
                CaseId = caseId,
                DocumentClass = BimCreationGuidProbeEvidenceClassifier.Classify(
                    isWorkshared.NullableValue,
                    isDetached.NullableValue,
                    isModelInCloud.NullableValue,
                    isFamilyDocument.NullableValue,
                    documentPath.Succeeded
                        ? !string.IsNullOrWhiteSpace(documentPath.Value) : (bool?)null,
                    centralModelPath.Succeeded
                        ? centralModelPath.Value != null : (bool?)null,
                    serverPath.NullableValue,
                    cloudPath.NullableValue,
                    fileEvidence.IsCentral.NullableValue,
                    fileEvidence.IsLocal.NullableValue),
                CreationGuidFirstStatus = creationFirst.Status,
                CreationGuidSecondStatus = creationSecond.Status,
                CreationGuid = creationFirst.Succeeded && creationFirst.Value != Guid.Empty
                    ? creationFirst.Value : (Guid?)null,
                CreationGuidNonEmpty = creationNonEmpty,
                CreationGuidStable = creationStable,
                DocumentPathStatus = documentPathStatus,
                CanonicalDocumentPath = canonicalDocumentPath,
                CentralPathStatus = centralPathStatus,
                CanonicalCentralPath = canonicalCentralPath,
                IsWorksharedStatus = isWorkshared.Status,
                IsWorkshared = isWorkshared.NullableValue,
                IsDetachedStatus = isDetached.Status,
                IsDetached = isDetached.NullableValue,
                IsModelInCloudStatus = isModelInCloud.Status,
                IsModelInCloud = isModelInCloud.NullableValue,
                IsFamilyDocumentStatus = isFamilyDocument.Status,
                IsFamilyDocument = isFamilyDocument.NullableValue,
                IsCentralStatus = fileEvidence.IsCentral.Status,
                IsCentral = fileEvidence.IsCentral.NullableValue,
                IsLocalStatus = fileEvidence.IsLocal.Status,
                IsLocal = fileEvidence.IsLocal.NullableValue,
                ModelPathKind = BimCreationGuidProbeEvidenceClassifier.ModelPathKind(
                    centralModelPath.Succeeded
                        ? centralModelPath.Value != null : (bool?)null,
                    serverPath.NullableValue,
                    cloudPath.NullableValue),
                FailureFacts = failures.ToArray(),
            };
        }

        private static BasicFileEvidence ReadBasicFileInfo(string documentPath)
        {
            var failures = new List<BimCreationGuidProbeFailureFact>();
            var fileInfo = Read(BimCreationGuidProbeStage.BasicFileInfoExtract,
                () => BasicFileInfo.Extract(documentPath));
            AddFailure(failures, fileInfo);
            if (!fileInfo.Succeeded || fileInfo.Value == null)
            {
                return new BasicFileEvidence(
                    ProbeValue<bool>.NotAttempted(BimCreationGuidProbeStage.BasicFileInfoIsCentral),
                    ProbeValue<bool>.NotAttempted(BimCreationGuidProbeStage.BasicFileInfoIsLocal),
                    failures);
            }

            try
            {
                var isCentral = Read(BimCreationGuidProbeStage.BasicFileInfoIsCentral,
                    () => fileInfo.Value.IsCentral);
                var isLocal = Read(BimCreationGuidProbeStage.BasicFileInfoIsLocal,
                    () => fileInfo.Value.IsLocal);
                AddFailure(failures, isCentral);
                AddFailure(failures, isLocal);
                return new BasicFileEvidence(isCentral, isLocal, failures);
            }
            finally
            {
                try
                {
                    fileInfo.Value.Dispose();
                }
                catch (Exception ex) when (!IsProcessFatal(ex))
                {
                    failures.Add(new BimCreationGuidProbeFailureFact(
                        BimCreationGuidProbeStage.BasicFileInfoExtract,
                        ex.GetType(),
                        ex.HResult));
                }
            }
        }

        private static ProbeValue<T> Read<T>(BimCreationGuidProbeStage stage, Func<T> read)
        {
            try
            {
                return ProbeValue<T>.Success(stage, read());
            }
            catch (Exception ex) when (!IsProcessFatal(ex))
            {
                return ProbeValue<T>.Failure(stage, ex.GetType(), ex.HResult);
            }
        }

        private static void AddFailure<T>(ICollection<BimCreationGuidProbeFailureFact> failures,
            ProbeValue<T> value)
        {
            if (value.FailureFact != null)
            {
                failures.Add(value.FailureFact);
            }
        }

        private static BimCreationGuidProbeProvenance BuildProvenance(UIApplication uiapp)
        {
            var status = BimDiagnostics.SnapshotStatus();
            return new BimCreationGuidProbeProvenance
            {
                ProcessId = Process.GetCurrentProcess().Id,
                RevitVersion = uiapp.Application.VersionName ?? string.Empty,
                RevitBuild = uiapp.Application.VersionBuild ?? string.Empty,
                RevitApiVersion = typeof(Document).Assembly.GetName().Version?.ToString() ?? string.Empty,
                RhinoVersion = AssemblyVersion("RhinoCommon"),
                GrasshopperVersion = AssemblyVersion("Grasshopper"),
                RhinoInsideRevitVersion = AssemblyVersion("RhinoInside.Revit"),
                CoreVersion = status.CoreVersion,
                CoreCommit = status.CoreCommit,
                ModuleVersion = status.ModuleVersion,
                ModuleCommit = status.ModuleCommit,
            };
        }

        private static string AssemblyVersion(string name)
        {
            return AppDomain.CurrentDomain.GetAssemblies()
                .FirstOrDefault(assembly => string.Equals(
                    assembly.GetName().Name, name, StringComparison.OrdinalIgnoreCase))?
                .GetName().Version?.ToString() ?? string.Empty;
        }

        private static bool IsProcessFatal(Exception exception)
        {
            return exception is OutOfMemoryException || exception is StackOverflowException ||
                exception is AccessViolationException || exception is AppDomainUnloadedException ||
                exception is BadImageFormatException || exception is CannotUnloadAppDomainException ||
                exception is System.Threading.ThreadAbortException;
        }

        private sealed class ProbeValue<T>
        {
            private ProbeValue(BimCreationGuidProbeStage stage,
                BimCreationGuidProbeReadStatus status, T value,
                BimCreationGuidProbeFailureFact? failure)
            {
                Stage = stage;
                Status = status;
                Value = value;
                FailureFact = failure;
            }

            internal BimCreationGuidProbeStage Stage { get; }
            internal BimCreationGuidProbeReadStatus Status { get; }
            internal T Value { get; }
            internal BimCreationGuidProbeFailureFact? FailureFact { get; }
            internal bool Succeeded => Status == BimCreationGuidProbeReadStatus.Success;
            internal bool? NullableValue => Succeeded && Value is bool boolean ? boolean : (bool?)null;

            internal static ProbeValue<T> Success(BimCreationGuidProbeStage stage, T value) =>
                new ProbeValue<T>(stage, BimCreationGuidProbeReadStatus.Success, value, null);
            internal static ProbeValue<T> Failure(BimCreationGuidProbeStage stage,
                Type exceptionType, int hresult) => new ProbeValue<T>(stage,
                    BimCreationGuidProbeReadStatus.Failure, default!,
                    new BimCreationGuidProbeFailureFact(stage, exceptionType, hresult));
            internal static ProbeValue<T> NotAttempted(BimCreationGuidProbeStage stage) =>
                new ProbeValue<T>(stage, BimCreationGuidProbeReadStatus.NotAttempted, default!, null);
            internal static ProbeValue<T> NotApplicable(BimCreationGuidProbeStage stage) =>
                new ProbeValue<T>(stage, BimCreationGuidProbeReadStatus.NotApplicable, default!, null);
        }

        private sealed class BasicFileEvidence
        {
            internal BasicFileEvidence(ProbeValue<bool> isCentral, ProbeValue<bool> isLocal,
                IReadOnlyList<BimCreationGuidProbeFailureFact> failures)
            {
                IsCentral = isCentral;
                IsLocal = isLocal;
                Failures = failures;
            }

            internal ProbeValue<bool> IsCentral { get; }
            internal ProbeValue<bool> IsLocal { get; }
            internal IReadOnlyList<BimCreationGuidProbeFailureFact> Failures { get; }

            internal static BasicFileEvidence NotApplicable() => new BasicFileEvidence(
                ProbeValue<bool>.NotApplicable(BimCreationGuidProbeStage.BasicFileInfoIsCentral),
                ProbeValue<bool>.NotApplicable(BimCreationGuidProbeStage.BasicFileInfoIsLocal),
                Array.Empty<BimCreationGuidProbeFailureFact>());
        }
    }
}
