using System;
using System.Collections.Generic;

namespace Rook.Bim
{
    public enum BimCreationGuidProbeAction { Begin, Capture, Complete, Abort }

    public enum BimCreationGuidProbeReadStatus { NotAttempted, Success, Failure, NotApplicable }

    public enum BimCreationGuidProbeCase
    {
        SavedProjectInitial,
        SavedProjectReopen,
        FileCentral,
        FileLocal,
        FileLocalReopen,
        CopiedCentral,
        Detached,
        SavedFamily,
        UnsavedProject,
        UnsavedFamily,
        ReplacementSamePath,
    }

    public enum BimCreationGuidProbeDocumentClass
    {
        Unknown,
        FileWorksharedCentral,
        FileWorksharedLocal,
        FileWorksharedUnknownRole,
        RevitServer,
        CloudWorkshared,
        SavedNonWorksharedProject,
        SavedFamily,
        Detached,
        UnsavedProject,
        UnsavedFamily,
    }

    public enum BimCreationGuidProbeStage
    {
        IsWorkshared,
        IsDetached,
        IsModelInCloud,
        IsFamilyDocument,
        CreationGuidFirst,
        CreationGuidSecond,
        DocumentPath,
        CentralModelPath,
        ModelPathServer,
        ModelPathCloud,
        ModelPathConvert,
        DocumentPathCanonicalize,
        CentralPathCanonicalize,
        BasicFileInfoExtract,
        BasicFileInfoIsCentral,
        BasicFileInfoIsLocal,
    }

    public enum BimCreationGuidProbeModelPathKind { Unknown, File, Server, Cloud }

    public enum BimCreationGuidProbeSessionCode
    {
        Captured,
        DuplicateCase,
        NotActive,
        MissingRequiredCases,
        Completed,
        Aborted,
    }

    public sealed class BimCreationGuidProbeRequest
    {
        public BimCreationGuidProbeAction Action { get; set; }

        public BimCreationGuidProbeCase? CaseId { get; set; }
    }

    public sealed class BimCreationGuidProbeProvenance
    {
        public int ProcessId { get; set; }
        public string RevitVersion { get; set; } = string.Empty;
        public string RevitBuild { get; set; } = string.Empty;
        public string RevitApiVersion { get; set; } = string.Empty;
        public string RhinoVersion { get; set; } = string.Empty;
        public string GrasshopperVersion { get; set; } = string.Empty;
        public string RhinoInsideRevitVersion { get; set; } = string.Empty;
        public string CoreVersion { get; set; } = string.Empty;
        public string CoreCommit { get; set; } = string.Empty;
        public string ModuleVersion { get; set; } = string.Empty;
        public string ModuleCommit { get; set; } = string.Empty;
    }

    public sealed class BimCreationGuidProbeFailureFact
    {
        public BimCreationGuidProbeFailureFact(
            BimCreationGuidProbeStage stage,
            string exceptionType,
            int hresult)
        {
            BimCreationGuidProbeContracts.ValidateStage(stage);
            Stage = stage;
            ExceptionType = BimCreationGuidProbeContracts.BoundExceptionType(exceptionType);
            HResult = hresult;
        }

        public BimCreationGuidProbeStage Stage { get; }
        public string ExceptionType { get; }
        public int HResult { get; }
    }

    public sealed class BimCreationGuidProbeCapture
    {
        internal BimCreationGuidProbeCapture(BimCreationGuidProbeObservation observation,
            string? creationGuidAlias, string? documentPathAlias, string? centralPathAlias)
        {
            CaseId = observation.CaseId;
            DocumentClass = observation.DocumentClass;
            CreationGuidFirstStatus = observation.CreationGuidFirstStatus;
            CreationGuidSecondStatus = observation.CreationGuidSecondStatus;
            CreationGuidNonEmpty = observation.CreationGuidNonEmpty;
            CreationGuidStable = observation.CreationGuidStable;
            CreationGuidAlias = creationGuidAlias;
            DocumentPathStatus = observation.DocumentPathStatus;
            DocumentPathAlias = documentPathAlias;
            CentralPathStatus = observation.CentralPathStatus;
            CentralPathAlias = centralPathAlias;
            IsWorksharedStatus = observation.IsWorksharedStatus;
            IsWorkshared = observation.IsWorkshared;
            IsDetachedStatus = observation.IsDetachedStatus;
            IsDetached = observation.IsDetached;
            IsModelInCloudStatus = observation.IsModelInCloudStatus;
            IsModelInCloud = observation.IsModelInCloud;
            IsFamilyDocumentStatus = observation.IsFamilyDocumentStatus;
            IsFamilyDocument = observation.IsFamilyDocument;
            IsCentralStatus = observation.IsCentralStatus;
            IsCentral = observation.IsCentral;
            IsLocalStatus = observation.IsLocalStatus;
            IsLocal = observation.IsLocal;
            ModelPathKind = observation.ModelPathKind;
            FailureFacts = Array.AsReadOnly((BimCreationGuidProbeFailureFact[])
                (observation.FailureFacts ?? Array.Empty<BimCreationGuidProbeFailureFact>()).Clone());
        }

        public BimCreationGuidProbeCase CaseId { get; }
        public BimCreationGuidProbeDocumentClass DocumentClass { get; }
        public BimCreationGuidProbeReadStatus CreationGuidFirstStatus { get; }
        public BimCreationGuidProbeReadStatus CreationGuidSecondStatus { get; }
        public bool? CreationGuidNonEmpty { get; }
        public bool? CreationGuidStable { get; }
        public string? CreationGuidAlias { get; }
        public BimCreationGuidProbeReadStatus DocumentPathStatus { get; }
        public string? DocumentPathAlias { get; }
        public BimCreationGuidProbeReadStatus CentralPathStatus { get; }
        public string? CentralPathAlias { get; }
        public BimCreationGuidProbeReadStatus IsWorksharedStatus { get; }
        public bool? IsWorkshared { get; }
        public BimCreationGuidProbeReadStatus IsDetachedStatus { get; }
        public bool? IsDetached { get; }
        public BimCreationGuidProbeReadStatus IsModelInCloudStatus { get; }
        public bool? IsModelInCloud { get; }
        public BimCreationGuidProbeReadStatus IsFamilyDocumentStatus { get; }
        public bool? IsFamilyDocument { get; }
        public BimCreationGuidProbeReadStatus IsCentralStatus { get; }
        public bool? IsCentral { get; }
        public BimCreationGuidProbeReadStatus IsLocalStatus { get; }
        public bool? IsLocal { get; }
        public BimCreationGuidProbeModelPathKind ModelPathKind { get; }
        public IReadOnlyList<BimCreationGuidProbeFailureFact> FailureFacts { get; }
    }

    public sealed class BimCreationGuidProbeEqualityRelation
    {
        internal BimCreationGuidProbeEqualityRelation(BimCreationGuidProbeCase leftCase,
            BimCreationGuidProbeCase rightCase, bool? sameCreationGuid,
            bool? sameDocumentPath, bool? sameCentralPath)
        {
            LeftCase = leftCase;
            RightCase = rightCase;
            SameCreationGuid = sameCreationGuid;
            SameDocumentPath = sameDocumentPath;
            SameCentralPath = sameCentralPath;
            Unavailable = !sameCreationGuid.HasValue || !sameDocumentPath.HasValue || !sameCentralPath.HasValue;
        }

        public BimCreationGuidProbeCase LeftCase { get; }
        public BimCreationGuidProbeCase RightCase { get; }
        public bool? SameCreationGuid { get; }
        public bool? SameDocumentPath { get; }
        public bool? SameCentralPath { get; }
        public bool Unavailable { get; }
    }

    public sealed class BimCreationGuidProbeReport
    {
        internal BimCreationGuidProbeReport(string sessionId, DateTime startedUtc,
            DateTime endedUtc, BimCreationGuidProbeProvenance provenance,
            IReadOnlyList<BimCreationGuidProbeCapture> captures,
            IReadOnlyList<BimCreationGuidProbeEqualityRelation> equalityRelations,
            IReadOnlyList<BimCreationGuidProbeCase> missingCases, bool complete,
            bool rawStateCleared)
        {
            SessionId = sessionId;
            StartedUtc = startedUtc;
            EndedUtc = endedUtc;
            ProcessId = provenance.ProcessId;
            RevitVersion = provenance.RevitVersion;
            RevitBuild = provenance.RevitBuild;
            RevitApiVersion = provenance.RevitApiVersion;
            RhinoVersion = provenance.RhinoVersion;
            GrasshopperVersion = provenance.GrasshopperVersion;
            RhinoInsideRevitVersion = provenance.RhinoInsideRevitVersion;
            CoreVersion = provenance.CoreVersion;
            CoreCommit = provenance.CoreCommit;
            ModuleVersion = provenance.ModuleVersion;
            ModuleCommit = provenance.ModuleCommit;
            Captures = captures;
            EqualityRelations = equalityRelations;
            MissingCases = missingCases;
            Complete = complete;
            RawStateCleared = rawStateCleared;
        }

        public string SessionId { get; }
        public DateTime StartedUtc { get; }
        public DateTime EndedUtc { get; }
        public int ProcessId { get; }
        public string RevitVersion { get; }
        public string RevitBuild { get; }
        public string RevitApiVersion { get; }
        public string RhinoVersion { get; }
        public string GrasshopperVersion { get; }
        public string RhinoInsideRevitVersion { get; }
        public string CoreVersion { get; }
        public string CoreCommit { get; }
        public string ModuleVersion { get; }
        public string ModuleCommit { get; }
        public IReadOnlyList<BimCreationGuidProbeCapture> Captures { get; }
        public IReadOnlyList<BimCreationGuidProbeEqualityRelation> EqualityRelations { get; }
        public IReadOnlyList<BimCreationGuidProbeCase> MissingCases { get; }
        public bool Complete { get; }
        public bool RawStateCleared { get; }
    }

    public sealed class BimCreationGuidProbeCaptureResult
    {
        internal BimCreationGuidProbeCaptureResult(BimCreationGuidProbeSessionCode code,
            BimCreationGuidProbeCapture? capture)
        {
            Code = code;
            Capture = capture;
        }

        public BimCreationGuidProbeSessionCode Code { get; }
        public BimCreationGuidProbeCapture? Capture { get; }
    }

    public sealed class BimCreationGuidProbeCompleteResult
    {
        internal BimCreationGuidProbeCompleteResult(BimCreationGuidProbeSessionCode code,
            BimCreationGuidProbeReport? report, IReadOnlyList<BimCreationGuidProbeCase> missingCases)
        {
            Code = code;
            Report = report;
            MissingCases = missingCases;
        }

        public BimCreationGuidProbeSessionCode Code { get; }
        public BimCreationGuidProbeReport? Report { get; }
        public IReadOnlyList<BimCreationGuidProbeCase> MissingCases { get; }
    }

    public sealed class BimCreationGuidProbeAbortResult
    {
        internal BimCreationGuidProbeAbortResult(BimCreationGuidProbeSessionCode code,
            bool rawStateCleared)
        {
            Code = code;
            RawStateCleared = rawStateCleared;
        }

        public BimCreationGuidProbeSessionCode Code { get; }
        public bool RawStateCleared { get; }
    }

    internal sealed class BimCreationGuidProbeObservation
    {
        internal BimCreationGuidProbeCase CaseId { get; set; }
        internal BimCreationGuidProbeDocumentClass DocumentClass { get; set; }
        internal BimCreationGuidProbeReadStatus CreationGuidFirstStatus { get; set; }
        internal BimCreationGuidProbeReadStatus CreationGuidSecondStatus { get; set; }
        internal Guid? CreationGuid { get; set; }
        internal bool? CreationGuidNonEmpty { get; set; }
        internal bool? CreationGuidStable { get; set; }
        internal BimCreationGuidProbeReadStatus DocumentPathStatus { get; set; }
        internal string? CanonicalDocumentPath { get; set; }
        internal BimCreationGuidProbeReadStatus CentralPathStatus { get; set; }
        internal string? CanonicalCentralPath { get; set; }
        internal BimCreationGuidProbeReadStatus IsWorksharedStatus { get; set; }
        internal bool? IsWorkshared { get; set; }
        internal BimCreationGuidProbeReadStatus IsDetachedStatus { get; set; }
        internal bool? IsDetached { get; set; }
        internal BimCreationGuidProbeReadStatus IsModelInCloudStatus { get; set; }
        internal bool? IsModelInCloud { get; set; }
        internal BimCreationGuidProbeReadStatus IsFamilyDocumentStatus { get; set; }
        internal bool? IsFamilyDocument { get; set; }
        internal BimCreationGuidProbeReadStatus IsCentralStatus { get; set; }
        internal bool? IsCentral { get; set; }
        internal BimCreationGuidProbeReadStatus IsLocalStatus { get; set; }
        internal bool? IsLocal { get; set; }
        internal BimCreationGuidProbeModelPathKind ModelPathKind { get; set; }
        internal BimCreationGuidProbeFailureFact[]? FailureFacts { get; set; }
    }

    internal static class BimCreationGuidProbeContracts
    {
        private const int MaximumExceptionTypeLength = 512;

        internal static string ToWire(BimCreationGuidProbeAction value) => value switch
        {
            BimCreationGuidProbeAction.Begin => "begin",
            BimCreationGuidProbeAction.Capture => "capture",
            BimCreationGuidProbeAction.Complete => "complete",
            BimCreationGuidProbeAction.Abort => "abort",
            _ => throw new ArgumentOutOfRangeException(nameof(value)),
        };

        internal static string ToWire(BimCreationGuidProbeReadStatus value) => value switch
        {
            BimCreationGuidProbeReadStatus.NotAttempted => "not_attempted",
            BimCreationGuidProbeReadStatus.Success => "success",
            BimCreationGuidProbeReadStatus.Failure => "failure",
            BimCreationGuidProbeReadStatus.NotApplicable => "not_applicable",
            _ => throw new ArgumentOutOfRangeException(nameof(value)),
        };

        internal static string ToWire(BimCreationGuidProbeStage value) => value switch
        {
            BimCreationGuidProbeStage.IsWorkshared => "is_workshared",
            BimCreationGuidProbeStage.IsDetached => "is_detached",
            BimCreationGuidProbeStage.IsModelInCloud => "is_model_in_cloud",
            BimCreationGuidProbeStage.IsFamilyDocument => "is_family_document",
            BimCreationGuidProbeStage.CreationGuidFirst => "creation_guid_first",
            BimCreationGuidProbeStage.CreationGuidSecond => "creation_guid_second",
            BimCreationGuidProbeStage.DocumentPath => "document_path",
            BimCreationGuidProbeStage.CentralModelPath => "central_model_path",
            BimCreationGuidProbeStage.ModelPathServer => "model_path_server",
            BimCreationGuidProbeStage.ModelPathCloud => "model_path_cloud",
            BimCreationGuidProbeStage.ModelPathConvert => "model_path_convert",
            BimCreationGuidProbeStage.DocumentPathCanonicalize => "document_path_canonicalize",
            BimCreationGuidProbeStage.CentralPathCanonicalize => "central_path_canonicalize",
            BimCreationGuidProbeStage.BasicFileInfoExtract => "basic_file_info_extract",
            BimCreationGuidProbeStage.BasicFileInfoIsCentral => "basic_file_info_is_central",
            BimCreationGuidProbeStage.BasicFileInfoIsLocal => "basic_file_info_is_local",
            _ => throw new ArgumentOutOfRangeException(nameof(value)),
        };

        internal static string ToWire(BimCreationGuidProbeCase value) => value switch
        {
            BimCreationGuidProbeCase.SavedProjectInitial => "saved_project_initial",
            BimCreationGuidProbeCase.SavedProjectReopen => "saved_project_reopen",
            BimCreationGuidProbeCase.FileCentral => "file_central",
            BimCreationGuidProbeCase.FileLocal => "file_local",
            BimCreationGuidProbeCase.FileLocalReopen => "file_local_reopen",
            BimCreationGuidProbeCase.CopiedCentral => "copied_central",
            BimCreationGuidProbeCase.Detached => "detached",
            BimCreationGuidProbeCase.SavedFamily => "saved_family",
            BimCreationGuidProbeCase.UnsavedProject => "unsaved_project",
            BimCreationGuidProbeCase.UnsavedFamily => "unsaved_family",
            BimCreationGuidProbeCase.ReplacementSamePath => "replacement_same_path",
            _ => throw new ArgumentOutOfRangeException(nameof(value)),
        };

        internal static string ToWire(BimCreationGuidProbeDocumentClass value) => value switch
        {
            BimCreationGuidProbeDocumentClass.Unknown => "unknown",
            BimCreationGuidProbeDocumentClass.FileWorksharedCentral => "file_workshared_central",
            BimCreationGuidProbeDocumentClass.FileWorksharedLocal => "file_workshared_local",
            BimCreationGuidProbeDocumentClass.FileWorksharedUnknownRole => "file_workshared_unknown_role",
            BimCreationGuidProbeDocumentClass.RevitServer => "revit_server",
            BimCreationGuidProbeDocumentClass.CloudWorkshared => "cloud_workshared",
            BimCreationGuidProbeDocumentClass.SavedNonWorksharedProject => "saved_non_workshared_project",
            BimCreationGuidProbeDocumentClass.SavedFamily => "saved_family",
            BimCreationGuidProbeDocumentClass.Detached => "detached",
            BimCreationGuidProbeDocumentClass.UnsavedProject => "unsaved_project",
            BimCreationGuidProbeDocumentClass.UnsavedFamily => "unsaved_family",
            _ => throw new ArgumentOutOfRangeException(nameof(value)),
        };

        internal static void ValidateStage(BimCreationGuidProbeStage value)
        {
            if (!Enum.IsDefined(typeof(BimCreationGuidProbeStage), value))
            {
                throw new ArgumentOutOfRangeException(nameof(value));
            }
        }

        internal static string BoundExceptionType(string? value)
        {
            if (value == null || value.Length == 0)
            {
                return string.Empty;
            }

            return value.Length <= MaximumExceptionTypeLength
                ? value : value.Substring(0, MaximumExceptionTypeLength);
        }
    }
}
