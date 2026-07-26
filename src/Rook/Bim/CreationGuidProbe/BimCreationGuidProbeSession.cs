using System;
using System.Collections.Generic;
using System.Linq;

namespace Rook.Bim
{
    internal sealed class BimCreationGuidProbeSession
    {
        private static readonly (BimCreationGuidProbeCase Left, BimCreationGuidProbeCase Right)[] RequiredRelations =
        {
            (BimCreationGuidProbeCase.SavedProjectInitial, BimCreationGuidProbeCase.SavedProjectReopen),
            (BimCreationGuidProbeCase.FileCentral, BimCreationGuidProbeCase.FileLocal),
            (BimCreationGuidProbeCase.FileLocal, BimCreationGuidProbeCase.FileLocalReopen),
            (BimCreationGuidProbeCase.FileCentral, BimCreationGuidProbeCase.CopiedCentral),
            (BimCreationGuidProbeCase.SavedProjectInitial, BimCreationGuidProbeCase.ReplacementSamePath),
        };

        private readonly string _sessionId = Guid.NewGuid().ToString("D");
        private readonly DateTime _startedUtc = DateTime.UtcNow;
        private readonly BimCreationGuidProbeProvenance _provenance;
        private readonly Dictionary<Guid, string> _creationGuidAliases = new Dictionary<Guid, string>();
        private readonly Dictionary<string, string> _pathAliases = new Dictionary<string, string>(StringComparer.Ordinal);
        private readonly Dictionary<BimCreationGuidProbeCase, BimCreationGuidProbeCapture> _captures =
            new Dictionary<BimCreationGuidProbeCase, BimCreationGuidProbeCapture>();
        private readonly List<BimCreationGuidProbeObservation> _rawObservations =
            new List<BimCreationGuidProbeObservation>();
        private bool _active = true;

        internal BimCreationGuidProbeSession(BimCreationGuidProbeProvenance provenance)
        {
            _provenance = provenance ?? throw new ArgumentNullException(nameof(provenance));
        }

        internal BimCreationGuidProbeCaptureResult Capture(BimCreationGuidProbeObservation observation)
        {
            if (!_active)
            {
                return new BimCreationGuidProbeCaptureResult(BimCreationGuidProbeSessionCode.NotActive, null);
            }

            if (observation == null)
            {
                throw new ArgumentNullException(nameof(observation));
            }

            if (_captures.ContainsKey(observation.CaseId))
            {
                return new BimCreationGuidProbeCaptureResult(BimCreationGuidProbeSessionCode.DuplicateCase, null);
            }

            var capture = new BimCreationGuidProbeCapture(
                observation,
                AssignCreationAlias(observation.CreationGuid),
                AssignPathAlias(observation.CanonicalDocumentPath),
                AssignPathAlias(observation.CanonicalCentralPath));
            _rawObservations.Add(observation);
            _captures.Add(observation.CaseId, capture);
            return new BimCreationGuidProbeCaptureResult(BimCreationGuidProbeSessionCode.Captured, capture);
        }

        internal BimCreationGuidProbeCompleteResult Complete()
        {
            if (!_active)
            {
                return new BimCreationGuidProbeCompleteResult(BimCreationGuidProbeSessionCode.NotActive, null,
                    Array.Empty<BimCreationGuidProbeCase>());
            }

            var missing = GetMissingCases();
            if (missing.Count != 0)
            {
                return new BimCreationGuidProbeCompleteResult(BimCreationGuidProbeSessionCode.MissingRequiredCases,
                    null, missing);
            }

            IReadOnlyList<BimCreationGuidProbeCapture> captures;
            IReadOnlyList<BimCreationGuidProbeEqualityRelation> relations;
            bool rawStateCleared = false;
            try
            {
                captures = Array.AsReadOnly(_captures.Values.OrderBy(capture => capture.CaseId).ToArray());
                relations = Array.AsReadOnly(BuildRelations());
            }
            finally
            {
                rawStateCleared = ClearRawStateAndVerify();
                _active = false;
            }

            var report = new BimCreationGuidProbeReport(_sessionId, _startedUtc, DateTime.UtcNow,
                _provenance, captures, relations, Array.Empty<BimCreationGuidProbeCase>(), true,
                rawStateCleared);
            return new BimCreationGuidProbeCompleteResult(BimCreationGuidProbeSessionCode.Completed,
                report, Array.Empty<BimCreationGuidProbeCase>());
        }

        internal BimCreationGuidProbeAbortResult Abort()
        {
            if (!_active)
            {
                return new BimCreationGuidProbeAbortResult(BimCreationGuidProbeSessionCode.NotActive, true);
            }

            bool rawStateCleared;
            try
            {
            }
            finally
            {
                rawStateCleared = ClearRawStateAndVerify();
                _active = false;
            }

            return new BimCreationGuidProbeAbortResult(BimCreationGuidProbeSessionCode.Aborted, rawStateCleared);
        }

        private string? AssignCreationAlias(Guid? value)
        {
            if (!value.HasValue)
            {
                return null;
            }

            if (!_creationGuidAliases.TryGetValue(value.Value, out var alias))
            {
                alias = "creation-" + (_creationGuidAliases.Count + 1).ToString("D3");
                _creationGuidAliases.Add(value.Value, alias);
            }

            return alias;
        }

        private string? AssignPathAlias(string? path)
        {
            if (path == null || path.Length == 0 ||
                !BimCreationGuidProbePathCanonicalizer.TryCanonicalize(path, out var canonical))
            {
                return null;
            }

            if (!_pathAliases.TryGetValue(canonical, out var alias))
            {
                alias = "path-" + (_pathAliases.Count + 1).ToString("D3");
                _pathAliases.Add(canonical, alias);
            }

            return alias;
        }

        private IReadOnlyList<BimCreationGuidProbeCase> GetMissingCases()
        {
            return Array.AsReadOnly(Enum.GetValues(typeof(BimCreationGuidProbeCase))
                .Cast<BimCreationGuidProbeCase>().Where(caseId => !_captures.ContainsKey(caseId)).ToArray());
        }

        private BimCreationGuidProbeEqualityRelation[] BuildRelations()
        {
            return RequiredRelations.Select(pair =>
            {
                var left = _captures[pair.Left];
                var right = _captures[pair.Right];
                return new BimCreationGuidProbeEqualityRelation(pair.Left, pair.Right,
                    SameAlias(left.CreationGuidAlias, right.CreationGuidAlias),
                    SameAlias(left.DocumentPathAlias, right.DocumentPathAlias),
                    SameAlias(left.CentralPathAlias, right.CentralPathAlias));
            }).ToArray();
        }

        private static bool? SameAlias(string? left, string? right)
        {
            return left == null || right == null ? (bool?)null :
                string.Equals(left, right, StringComparison.Ordinal);
        }

        private bool ClearRawStateAndVerify()
        {
            _rawObservations.Clear();
            _creationGuidAliases.Clear();
            _pathAliases.Clear();
            return _rawObservations.Count == 0 && _creationGuidAliases.Count == 0 && _pathAliases.Count == 0;
        }
    }
}
