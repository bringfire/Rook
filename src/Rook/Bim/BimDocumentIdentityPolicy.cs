using System;
using System.Collections.Generic;

namespace Rook.Bim
{
    public static class BimDocumentIdentityPolicy
    {
        public enum DocumentClass { FileWorkshared, RevitServer, CloudWorkshared, SavedProject, SavedFamily, UnsavedProject, UnsavedFamily, Detached, Unknown }
        public enum UnavailableReason { None, DiscriminatorUnavailable, KeyMaterialUnavailable, UnsupportedClass }
        public enum CentralPathKind { File, Server, Cloud }
        public enum Comparison { Match, Mismatch, Unavailable, InvalidEvidence }
        public enum PreflightOutcome { Valid, InvalidEvidence, LinkedElementUnsupported, Mismatch, Unavailable, ElementLocatorInvalid }

        public readonly struct ReadResult<T>
        {
            private ReadResult(bool available, T value, UnavailableReason reason) { Available = available; Value = value; Reason = reason; }
            public bool Available { get; }
            public T Value { get; }
            public UnavailableReason Reason { get; }
            public static ReadResult<T> Success(T value) { return new ReadResult<T>(true, value, UnavailableReason.None); }
            public static ReadResult<T> Unavailable(UnavailableReason reason) { return new ReadResult<T>(false, default!, reason); }
        }

        public readonly struct CentralPath
        {
            public CentralPath(CentralPathKind kind, string? filePath) { Kind = kind; FilePath = filePath; }
            public CentralPathKind Kind { get; }
            public string? FilePath { get; }
        }

        public sealed class Readers
        {
            public Readers(Func<ReadResult<bool>> readIsDetached, Func<ReadResult<bool>> readIsWorkshared, Func<ReadResult<bool>> readIsModelInCloud, Func<ReadResult<bool>> readIsFamilyDocument, Func<ReadResult<string?>> readDocumentPath, Func<ReadResult<CentralPath>> readCentralModelPath, Func<ReadResult<Guid>> readCreationGuid, Func<ReadResult<Guid>> readServerCentralGuid)
            {
                ReadIsDetached = readIsDetached ?? throw new ArgumentNullException(nameof(readIsDetached));
                ReadIsWorkshared = readIsWorkshared ?? throw new ArgumentNullException(nameof(readIsWorkshared));
                ReadIsModelInCloud = readIsModelInCloud ?? throw new ArgumentNullException(nameof(readIsModelInCloud));
                ReadIsFamilyDocument = readIsFamilyDocument ?? throw new ArgumentNullException(nameof(readIsFamilyDocument));
                ReadDocumentPath = readDocumentPath ?? throw new ArgumentNullException(nameof(readDocumentPath));
                ReadCentralModelPath = readCentralModelPath ?? throw new ArgumentNullException(nameof(readCentralModelPath));
                ReadCreationGuid = readCreationGuid ?? throw new ArgumentNullException(nameof(readCreationGuid));
                ReadServerCentralGuid = readServerCentralGuid ?? throw new ArgumentNullException(nameof(readServerCentralGuid));
            }
            public Func<ReadResult<bool>> ReadIsDetached { get; }
            public Func<ReadResult<bool>> ReadIsWorkshared { get; }
            public Func<ReadResult<bool>> ReadIsModelInCloud { get; }
            public Func<ReadResult<bool>> ReadIsFamilyDocument { get; }
            public Func<ReadResult<string?>> ReadDocumentPath { get; }
            public Func<ReadResult<CentralPath>> ReadCentralModelPath { get; }
            public Func<ReadResult<Guid>> ReadCreationGuid { get; }
            public Func<ReadResult<Guid>> ReadServerCentralGuid { get; }
        }

        public sealed class Evidence
        {
            internal Evidence(DocumentClass documentClass, string? documentKey, BimDocumentKeySource documentKeySource, Guid? legacyGuid, BimDocumentGuidSource legacyGuidSource, UnavailableReason reason)
            { Class = documentClass; DocumentKey = documentKey; DocumentKeySource = documentKeySource; LegacyGuid = legacyGuid; LegacyGuidSource = legacyGuidSource; Reason = reason; }
            public DocumentClass Class { get; }
            public string? DocumentKey { get; }
            public BimDocumentKeySource DocumentKeySource { get; }
            public Guid? LegacyGuid { get; }
            public BimDocumentGuidSource LegacyGuidSource { get; }
            public UnavailableReason Reason { get; }
        }

        public sealed class Claim
        {
            public Claim(string? source, string? documentKey, BimDocumentKeySource documentKeySource, string? documentGuid, BimDocumentGuidSource documentGuidSource, bool linked, int? linkInstanceId, string? linkInstanceUniqueId, string? linkedDocumentGuid, int? linkedElementId, string? linkedElementUniqueId, string? uniqueId, int? elementId)
            { Source = source; DocumentKey = documentKey; DocumentKeySource = documentKeySource; DocumentGuid = documentGuid; DocumentGuidSource = documentGuidSource; Linked = linked; LinkInstanceId = linkInstanceId; LinkInstanceUniqueId = linkInstanceUniqueId; LinkedDocumentGuid = linkedDocumentGuid; LinkedElementId = linkedElementId; LinkedElementUniqueId = linkedElementUniqueId; UniqueId = uniqueId; ElementId = elementId; }
            public string? Source { get; } public string? DocumentKey { get; } public BimDocumentKeySource DocumentKeySource { get; } public string? DocumentGuid { get; } public BimDocumentGuidSource DocumentGuidSource { get; } public bool Linked { get; } public int? LinkInstanceId { get; } public string? LinkInstanceUniqueId { get; } public string? LinkedDocumentGuid { get; } public int? LinkedElementId { get; } public string? LinkedElementUniqueId { get; } public string? UniqueId { get; } public int? ElementId { get; }
        }

        public readonly struct PreflightResult
        {
            public PreflightResult(PreflightOutcome outcome, int? itemIndex) { Outcome = outcome; ItemIndex = itemIndex; }
            public PreflightOutcome Outcome { get; } public int? ItemIndex { get; }
        }

        public static ReadResult<T> CaptureRead<T>(Func<T> read, Func<Exception, bool> isExpected, UnavailableReason failureReason)
        {
            if (read == null) throw new ArgumentNullException(nameof(read));
            if (isExpected == null) throw new ArgumentNullException(nameof(isExpected));
            try { return ReadResult<T>.Success(read()); }
            catch (Exception exception) when (isExpected(exception)) { return ReadResult<T>.Unavailable(failureReason); }
        }

        public static Evidence Capture(Readers readers)
        {
            if (readers == null) throw new ArgumentNullException(nameof(readers));
            var detached = readers.ReadIsDetached();
            var workshared = readers.ReadIsWorkshared();
            if (!detached.Available) return Unavailable(DocumentClass.Unknown, detached.Reason);
            if (!workshared.Available) return Unavailable(DocumentClass.Unknown, workshared.Reason);
            if (detached.Value) return Unavailable(DocumentClass.Detached, UnavailableReason.UnsupportedClass);
            if (workshared.Value) return CaptureWorkshared(readers);
            var family = readers.ReadIsFamilyDocument();
            if (!family.Available) return Unavailable(DocumentClass.Unknown, family.Reason);
            if (family.Value) return Unavailable(DocumentClass.SavedFamily, UnavailableReason.UnsupportedClass);
            var path = readers.ReadDocumentPath();
            if (!path.Available) return Unavailable(DocumentClass.Unknown, path.Reason);
            if (string.IsNullOrEmpty(path.Value)) return Unavailable(DocumentClass.UnsavedProject, UnavailableReason.UnsupportedClass);
            var creation = readers.ReadCreationGuid();
            if (!creation.Available) return Unavailable(DocumentClass.SavedProject, creation.Reason);
            return CreateKey(DocumentClass.SavedProject, BimDocumentKeySource.RevitCreationGuidDocumentPathV1, creation.Value, path.Value);
        }

        public static Comparison Compare(Evidence active, Claim incoming)
        {
            if (active == null || incoming == null || !string.Equals(incoming.Source, "revit", StringComparison.Ordinal)) return Comparison.InvalidEvidence;
            if (incoming.DocumentKey != null)
            {
                if (string.IsNullOrWhiteSpace(incoming.DocumentKey) || !BimDocumentKeyCodec.IsValid(incoming.DocumentKeySource, incoming.DocumentKey)) return Comparison.InvalidEvidence;
                if (incoming.DocumentGuid != null || incoming.DocumentGuidSource != BimDocumentGuidSource.Unavailable) return Comparison.InvalidEvidence;
                if (active.DocumentKeySource == BimDocumentKeySource.Unavailable || active.DocumentKey == null || !BimDocumentKeyCodec.IsValid(active.DocumentKeySource, active.DocumentKey)) return Comparison.Unavailable;
                if (active.DocumentKeySource != incoming.DocumentKeySource) return Comparison.Mismatch;
                return string.Equals(active.DocumentKey, incoming.DocumentKey, StringComparison.Ordinal) ? Comparison.Match : Comparison.Mismatch;
            }
            if (incoming.DocumentKeySource != BimDocumentKeySource.Unavailable) return Comparison.InvalidEvidence;
            if (incoming.DocumentGuidSource == BimDocumentGuidSource.Unavailable && incoming.DocumentGuid == null) return Comparison.Unavailable;
            if (incoming.DocumentGuidSource == BimDocumentGuidSource.PathFallback && !string.IsNullOrWhiteSpace(incoming.DocumentGuid)) return Comparison.Unavailable;
            if (incoming.DocumentGuidSource != BimDocumentGuidSource.RevitPersistentGuid || !TryParsePersistentGuid(incoming.DocumentGuid, out var incomingGuid)) return Comparison.InvalidEvidence;
            if (active.Class != DocumentClass.RevitServer)
            {
                return active.Class == DocumentClass.Unknown ? Comparison.Unavailable : Comparison.Mismatch;
            }
            if (active.LegacyGuidSource != BimDocumentGuidSource.RevitPersistentGuid || !active.LegacyGuid.HasValue || active.LegacyGuid.Value == Guid.Empty) return Comparison.Unavailable;
            return active.LegacyGuid.Value == incomingGuid ? Comparison.Match : Comparison.Mismatch;
        }

        public static PreflightResult PreflightBatch(Evidence active, IReadOnlyList<Claim?> claims)
        {
            if (active == null || claims == null) return new PreflightResult(PreflightOutcome.InvalidEvidence, null);
            for (var index = 0; index < claims.Count; index++)
            {
                var claim = claims[index];
                if (claim == null) return new PreflightResult(PreflightOutcome.InvalidEvidence, index);
                if (HasLinkedEvidence(claim)) return new PreflightResult(PreflightOutcome.LinkedElementUnsupported, index);
                var comparison = Compare(active, claim);
                if (comparison != Comparison.Match)
                {
                    return new PreflightResult(Map(comparison), index);
                }
                if (string.IsNullOrWhiteSpace(claim.UniqueId) && !claim.ElementId.HasValue)
                {
                    return new PreflightResult(PreflightOutcome.ElementLocatorInvalid, index);
                }
            }
            return new PreflightResult(PreflightOutcome.Valid, null);
        }

        private static Evidence CaptureWorkshared(Readers readers)
        {
            var cloud = readers.ReadIsModelInCloud();
            if (!cloud.Available) return Unavailable(DocumentClass.Unknown, cloud.Reason);
            if (cloud.Value) return Unavailable(DocumentClass.CloudWorkshared, UnavailableReason.UnsupportedClass);
            var central = readers.ReadCentralModelPath();
            if (!central.Available) return Unavailable(DocumentClass.Unknown, central.Reason);
            switch (central.Value.Kind)
            {
                case CentralPathKind.Cloud:
                    return Unavailable(DocumentClass.CloudWorkshared, UnavailableReason.UnsupportedClass);
                case CentralPathKind.Server:
                    var server = readers.ReadServerCentralGuid();
                    if (!server.Available || server.Value == Guid.Empty) return Unavailable(DocumentClass.RevitServer, server.Available ? UnavailableReason.KeyMaterialUnavailable : server.Reason);
                    return new Evidence(DocumentClass.RevitServer, null, BimDocumentKeySource.Unavailable, server.Value, BimDocumentGuidSource.RevitPersistentGuid, UnavailableReason.None);
                case CentralPathKind.File:
                    var creation = readers.ReadCreationGuid();
                    if (!creation.Available) return Unavailable(DocumentClass.FileWorkshared, creation.Reason);
                    return CreateKey(DocumentClass.FileWorkshared, BimDocumentKeySource.RevitCreationGuidCentralPathV1, creation.Value, central.Value.FilePath);
                default:
                    return Unavailable(DocumentClass.Unknown, UnavailableReason.UnsupportedClass);
            }
        }

        private static Evidence CreateKey(DocumentClass documentClass, BimDocumentKeySource source, Guid creationGuid, string? path)
        {
            if (path == null || !BimDocumentKeyCodec.TryCreate(source, creationGuid, path, out var key)) return Unavailable(documentClass, UnavailableReason.KeyMaterialUnavailable);
            return new Evidence(documentClass, key, source, null, BimDocumentGuidSource.Unavailable, UnavailableReason.None);
        }

        private static Evidence Unavailable(DocumentClass documentClass, UnavailableReason reason)
        { return new Evidence(documentClass, null, BimDocumentKeySource.Unavailable, null, BimDocumentGuidSource.Unavailable, reason); }
        private static bool TryParsePersistentGuid(string? value, out Guid guid)
        { guid = Guid.Empty; return value != null && value.Length == 36 && Guid.TryParseExact(value, "D", out guid) && guid != Guid.Empty; }
        private static bool HasLinkedEvidence(Claim claim)
        { return claim.Linked || claim.LinkInstanceId.HasValue || claim.LinkInstanceUniqueId != null || claim.LinkedDocumentGuid != null || claim.LinkedElementId.HasValue || claim.LinkedElementUniqueId != null; }
        private static PreflightOutcome Map(Comparison comparison)
        { return comparison == Comparison.InvalidEvidence ? PreflightOutcome.InvalidEvidence : comparison == Comparison.Mismatch ? PreflightOutcome.Mismatch : PreflightOutcome.Unavailable; }
    }
}
