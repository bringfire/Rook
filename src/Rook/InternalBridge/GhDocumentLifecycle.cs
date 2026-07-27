using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Threading;

namespace Rook.InternalBridge
{
    internal interface IGhDocumentLifecycleHost
    {
        object? GetActiveCanvas();
        object? GetCanvasDocument(object canvas);
        void SetCanvasDocument(object canvas, object? document);
        IReadOnlyList<object> SnapshotDocuments();
        object CreateEmptyDocument();
        bool AddNewDocument(object document);
        object? OpenDocument(string path, bool makeActive);
        int IndexOf(object document);
        string? GetDocumentFilePath(object document);
        bool? IsActiveOnAnySupportedCanvas(object document, object capturedCanvas);
        void RemoveDocument(object document);
        void DisposeDocument(object document);
    }

    internal readonly struct GhDocumentRegistrationState
    {
        public bool Known { get; init; }
        public bool Registered { get; init; }
        public int? Index { get; init; }
    }

    internal enum GhDocumentLifecycleOperation { New, Open }

    internal enum GhDocumentLifecycleCode
    {
        None,
        Reentrant,
        CanvasUnavailable,
        CanvasChanged,
        RegistrationFailed,
        ActivationFailed,
        InconsistentState,
        RollbackIncomplete,
    }

    internal enum GhDocumentLifecycleWarning
    {
        OpenReturnedNullAfterCommit,
        ReadinessAttachmentFailed,
        IdRegistryResetFailed,
        CanvasRefreshFailed,
        ObjectCountFailed,
        TelemetryProjectionFailed,
    }

    internal static class GhDocumentLifecycleWire
    {
        internal static string Code(GhDocumentLifecycleCode code)
        {
            switch (code)
            {
                case GhDocumentLifecycleCode.None: return "none";
                case GhDocumentLifecycleCode.Reentrant: return "gh_document_lifecycle_reentrant";
                case GhDocumentLifecycleCode.CanvasUnavailable: return "gh_document_canvas_unavailable";
                case GhDocumentLifecycleCode.CanvasChanged: return "gh_document_canvas_changed";
                case GhDocumentLifecycleCode.RegistrationFailed: return "gh_document_registration_failed";
                case GhDocumentLifecycleCode.ActivationFailed: return "gh_document_activation_failed";
                case GhDocumentLifecycleCode.InconsistentState: return "gh_document_inconsistent_state";
                case GhDocumentLifecycleCode.RollbackIncomplete: return "gh_document_rollback_incomplete";
                default: throw new ArgumentOutOfRangeException(nameof(code));
            }
        }

        internal static string Warning(GhDocumentLifecycleWarning warning)
        {
            switch (warning)
            {
                case GhDocumentLifecycleWarning.OpenReturnedNullAfterCommit: return "open_returned_null_after_commit";
                case GhDocumentLifecycleWarning.ReadinessAttachmentFailed: return "readiness_attachment_failed";
                case GhDocumentLifecycleWarning.IdRegistryResetFailed: return "id_registry_reset_failed";
                case GhDocumentLifecycleWarning.CanvasRefreshFailed: return "canvas_refresh_failed";
                case GhDocumentLifecycleWarning.ObjectCountFailed: return "object_count_failed";
                case GhDocumentLifecycleWarning.TelemetryProjectionFailed: return "telemetry_projection_failed";
                default: throw new ArgumentOutOfRangeException(nameof(warning));
            }
        }
    }

    internal sealed class GhDocumentLifecycleResult
    {
        private const int MaximumWarnings = 6;
        private readonly List<GhDocumentLifecycleWarning> _warnings = new List<GhDocumentLifecycleWarning>();

        internal GhDocumentLifecycleResult(GhDocumentLifecycleOperation operation)
        {
            Operation = operation;
        }

        internal GhDocumentLifecycleOperation Operation { get; }
        internal object? Document { get; set; }
        internal object? PreviousDocument { get; set; }
        internal object? CapturedCanvas { get; set; }
        internal bool PathAlreadyRegistered { get; set; }
        internal bool CreatedDocument { get; set; }
        internal bool RegisteredByThisCall { get; set; }
        internal bool RegistrationSucceeded { get; set; }
        internal int? RegistrationIndex { get; set; }
        internal bool ActivationSucceeded { get; set; }
        internal bool Committed { get; set; }
        internal bool RollbackAttempted { get; set; }
        internal bool RollbackIncomplete { get; set; }
        internal bool DocumentRegistered { get; set; }
        internal bool DocumentActive { get; set; }
        internal GhDocumentLifecycleCode Code { get; set; }
        internal IReadOnlyList<GhDocumentLifecycleWarning> Warnings => _warnings;

        internal void AddWarning(GhDocumentLifecycleWarning warning)
        {
            if (_warnings.Count < MaximumWarnings && !_warnings.Contains(warning))
            {
                _warnings.Add(warning);
            }
        }
    }

    internal sealed class GhDocumentLifecycle
    {
        private enum MembershipState { Unknown, Absent, Present }

        private static int activeTransaction;
        private readonly IGhDocumentLifecycleHost _host;

        internal GhDocumentLifecycle() : this(new ReflectionGhDocumentLifecycleHost()) { }

        internal GhDocumentLifecycle(IGhDocumentLifecycleHost host)
        {
            _host = host ?? throw new ArgumentNullException(nameof(host));
        }

        internal GhDocumentRegistrationState InspectRegistration(object document)
        {
            if (document is null)
            {
                return new GhDocumentRegistrationState { Known = false };
            }

            try
            {
                var index = _host.IndexOf(document);
                if (index < 0)
                {
                    return new GhDocumentRegistrationState { Known = true, Registered = false };
                }

                var documents = _host.SnapshotDocuments();
                return new GhDocumentRegistrationState
                {
                    Known = true,
                    Registered = index < documents.Count && ReferenceEquals(documents[index], document),
                    Index = index,
                };
            }
            catch
            {
                return new GhDocumentRegistrationState { Known = false };
            }
        }

        internal GhDocumentLifecycleResult CreateNew() => Execute(GhDocumentLifecycleOperation.New, null);

        internal GhDocumentLifecycleResult Open(string path) => Execute(GhDocumentLifecycleOperation.Open, path);

        private GhDocumentLifecycleResult Execute(GhDocumentLifecycleOperation operation, string? path)
        {
            var result = new GhDocumentLifecycleResult(operation);
            if (Interlocked.CompareExchange(ref activeTransaction, 1, 0) != 0)
            {
                result.Code = GhDocumentLifecycleCode.Reentrant;
                return result;
            }

            var membership = MembershipState.Unknown;
            try
            {
                var before = Snapshot(result);
                if (before is null)
                {
                    return result;
                }

                if (!TryCaptureCanvas(result))
                {
                    return result;
                }

                if (operation == GhDocumentLifecycleOperation.New)
                {
                    ExecuteNew(result, before, ref membership);
                }
                else
                {
                    ExecuteOpen(result, path ?? string.Empty, before, ref membership);
                }

                return result;
            }
            catch
            {
                if (result.Code == GhDocumentLifecycleCode.None)
                {
                    result.Code = GhDocumentLifecycleCode.InconsistentState;
                }
                return result;
            }
            finally
            {
                if (!result.Committed && result.Document is not null)
                {
                    Rollback(result, membership);
                }
                else if (!result.Committed)
                {
                    ObserveFinalState(result);
                }
                Interlocked.Exchange(ref activeTransaction, 0);
            }
        }

        private void ExecuteNew(GhDocumentLifecycleResult result, IReadOnlyList<object> before, ref MembershipState membership)
        {
            try
            {
                result.Document = _host.CreateEmptyDocument();
                result.CreatedDocument = true;
            }
            catch
            {
                result.Code = GhDocumentLifecycleCode.RegistrationFailed;
                return;
            }

            if (!RequireSameCanvas(result)) return;
            bool addSucceeded;
            try { addSucceeded = _host.AddNewDocument(result.Document); }
            catch { result.Code = GhDocumentLifecycleCode.RegistrationFailed; return; }
            if (!RequireSameCanvas(result)) return;

            var registration = InspectRegistration(result.Document);
            membership = InspectMembership(result.Document);
            result.DocumentRegistered = registration.Registered;
            result.RegistrationIndex = registration.Index;
            result.RegistrationSucceeded = addSucceeded && registration.Registered;
            result.RegisteredByThisCall = membership == MembershipState.Present && !ContainsReference(before, result.Document);
            if (!addSucceeded || !registration.Registered)
            {
                result.Code = addSucceeded && registration.Index.HasValue
                    ? GhDocumentLifecycleCode.InconsistentState
                    : GhDocumentLifecycleCode.RegistrationFailed;
                return;
            }

            if (!RequireSameCanvas(result)) return;
            try { _host.SetCanvasDocument(result.CapturedCanvas!, result.Document); }
            catch { result.Code = GhDocumentLifecycleCode.ActivationFailed; return; }
            if (!RequireSameCanvas(result)) return;

            result.ActivationSucceeded = IsCapturedCanvasDocument(result, result.Document);
            result.DocumentActive = result.ActivationSucceeded;
            if (!result.ActivationSucceeded)
            {
                result.Code = GhDocumentLifecycleCode.ActivationFailed;
                return;
            }

            var finalRegistration = InspectRegistration(result.Document);
            result.DocumentRegistered = finalRegistration.Registered;
            result.RegistrationIndex = finalRegistration.Index;
            result.Committed = finalRegistration.Registered && result.ActivationSucceeded;
            result.Code = result.Committed ? GhDocumentLifecycleCode.None : GhDocumentLifecycleCode.InconsistentState;
        }

        private void ExecuteOpen(GhDocumentLifecycleResult result, string path, IReadOnlyList<object> before, ref MembershipState membership)
        {
            var existing = FindPathMatch(before, path);
            if (!RequireSameCanvas(result)) return;
            object? returned;
            try { returned = _host.OpenDocument(path, true); }
            catch { result.Code = GhDocumentLifecycleCode.RegistrationFailed; return; }
            result.Document = returned;
            result.PathAlreadyRegistered = existing is not null;
            result.CreatedDocument = returned is not null && !ReferenceEquals(returned, existing);
            if (!RequireSameCanvas(result)) return;

            var after = Snapshot(result);
            if (after is null)
            {
                if (returned is null) MarkIndeterminateReconciliation(result);
                return;
            }
            var additions = after.Where(document => !ContainsReference(before, document)).ToArray();
            object? active = GetCapturedCanvasDocument(result);
            if (active is null && result.Code != GhDocumentLifecycleCode.None) return;

            if (existing is not null)
            {
                result.Document = existing;
                var existingRegistration = InspectRegistration(existing);
                result.DocumentRegistered = existingRegistration.Registered;
                result.RegistrationIndex = existingRegistration.Index;
                result.RegistrationSucceeded = existingRegistration.Registered;
                result.ActivationSucceeded = ReferenceEquals(active, existing);
                result.DocumentActive = result.ActivationSucceeded;
                if (additions.Length != 0 || !ReferenceEquals(returned, existing) || !existingRegistration.Registered || !result.ActivationSucceeded)
                {
                    result.Code = GhDocumentLifecycleCode.InconsistentState;
                    return;
                }

                result.Committed = true;
                result.Code = GhDocumentLifecycleCode.None;
                return;
            }

            var candidate = additions.Length == 1 ? additions[0] : active ?? returned;
            result.Document = candidate;
            result.CreatedDocument = result.CreatedDocument || additions.Length > 0;
            if (candidate is not null && additions.Length == 1)
            {
                result.CreatedDocument = true;
                result.RegisteredByThisCall = true;
                membership = MembershipState.Present;
            }

            if (candidate is null || additions.Length != 1 || !HasRequestedPath(candidate, path) ||
                (returned is not null && !ReferenceEquals(returned, candidate)) || !ReferenceEquals(active, candidate))
            {
                if (candidate is null) MarkIndeterminateReconciliation(result);
                result.Code = GhDocumentLifecycleCode.InconsistentState;
                return;
            }

            if (returned is null)
            {
                result.AddWarning(GhDocumentLifecycleWarning.OpenReturnedNullAfterCommit);
            }

            var candidateRegistration = InspectRegistration(candidate);
            result.DocumentRegistered = candidateRegistration.Registered;
            result.RegistrationIndex = candidateRegistration.Index;
            result.RegistrationSucceeded = candidateRegistration.Registered;
            result.ActivationSucceeded = IsCapturedCanvasDocument(result, candidate);
            result.DocumentActive = result.ActivationSucceeded;
            if (!candidateRegistration.Registered || !result.ActivationSucceeded)
            {
                result.Code = !candidateRegistration.Registered ? GhDocumentLifecycleCode.RegistrationFailed : GhDocumentLifecycleCode.ActivationFailed;
                return;
            }

            if (!RequireSameCanvas(result)) return;
            var finalRegistration = InspectRegistration(candidate);
            result.DocumentRegistered = finalRegistration.Registered;
            result.RegistrationIndex = finalRegistration.Index;
            if (!finalRegistration.Registered)
            {
                result.Code = GhDocumentLifecycleCode.InconsistentState;
                return;
            }
            result.Committed = true;
            result.Code = GhDocumentLifecycleCode.None;
        }

        private void Rollback(GhDocumentLifecycleResult result, MembershipState membership)
        {
            result.RollbackAttempted = true;
            var candidate = result.Document;
            var capturedCanvas = result.CapturedCanvas;
            if (candidate is null || capturedCanvas is null)
            {
                result.RollbackIncomplete = true;
                if (result.Code == GhDocumentLifecycleCode.None) result.Code = GhDocumentLifecycleCode.RollbackIncomplete;
                ObserveFinalState(result);
                return;
            }

            bool sameCanvas;
            try { sameCanvas = ReferenceEquals(_host.GetActiveCanvas(), capturedCanvas); }
            catch { sameCanvas = false; }
            if (sameCanvas)
            {
                try { _host.SetCanvasDocument(capturedCanvas, result.PreviousDocument); }
                catch { }
            }

            bool previousRestored;
            try
            {
                previousRestored = ReferenceEquals(_host.GetActiveCanvas(), capturedCanvas)
                    && ReferenceEquals(_host.GetCanvasDocument(capturedCanvas), result.PreviousDocument);
            }
            catch { previousRestored = false; }

            bool? candidateStillActive;
            try { candidateStillActive = _host.IsActiveOnAnySupportedCanvas(candidate, capturedCanvas); }
            catch { candidateStillActive = null; }

            if (previousRestored && result.RegisteredByThisCall && membership == MembershipState.Present && candidateStillActive == false)
            {
                if (!IsSameCapturedCanvas(result))
                {
                    result.RollbackIncomplete = true;
                }
                else
                {
                    try { _host.RemoveDocument(candidate); }
                    catch { result.RollbackIncomplete = true; }
                    var sameCanvasAfterRemoval = IsSameCapturedCanvas(result);
                    var removal = InspectRegistration(candidate);
                    if (!sameCanvasAfterRemoval || !removal.Known || removal.Registered)
                    {
                        result.RollbackIncomplete = true;
                    }
                }
            }
            else if (previousRestored && result.CreatedDocument && membership == MembershipState.Absent && candidateStillActive == false)
            {
                if (!IsSameCapturedCanvas(result))
                {
                    result.RollbackIncomplete = true;
                }
                else
                {
                    try { _host.DisposeDocument(candidate); }
                    catch { result.RollbackIncomplete = true; }
                    if (!IsSameCapturedCanvas(result)) result.RollbackIncomplete = true;
                }
            }
            else if (result.RegisteredByThisCall || result.CreatedDocument)
            {
                result.RollbackIncomplete = true;
            }

            if (!previousRestored || candidateStillActive is null)
            {
                result.RollbackIncomplete = true;
            }
            ObserveFinalState(result);
            if (result.RollbackIncomplete && result.Code == GhDocumentLifecycleCode.None)
            {
                result.Code = GhDocumentLifecycleCode.RollbackIncomplete;
            }
        }

        private bool TryCaptureCanvas(GhDocumentLifecycleResult result)
        {
            try
            {
                result.CapturedCanvas = _host.GetActiveCanvas();
                if (result.CapturedCanvas is null)
                {
                    result.Code = GhDocumentLifecycleCode.CanvasUnavailable;
                    return false;
                }
                result.PreviousDocument = _host.GetCanvasDocument(result.CapturedCanvas);
                return true;
            }
            catch
            {
                result.Code = GhDocumentLifecycleCode.CanvasUnavailable;
                return false;
            }
        }

        private IReadOnlyList<object>? Snapshot(GhDocumentLifecycleResult result)
        {
            try { return _host.SnapshotDocuments(); }
            catch { result.Code = GhDocumentLifecycleCode.InconsistentState; return null; }
        }

        private bool RequireSameCanvas(GhDocumentLifecycleResult result)
        {
            try
            {
                if (result.CapturedCanvas is not null && ReferenceEquals(_host.GetActiveCanvas(), result.CapturedCanvas))
                {
                    return true;
                }
            }
            catch { }
            result.Code = GhDocumentLifecycleCode.CanvasChanged;
            return false;
        }

        private bool IsCapturedCanvasDocument(GhDocumentLifecycleResult result, object document)
        {
            try { return result.CapturedCanvas is not null && ReferenceEquals(_host.GetCanvasDocument(result.CapturedCanvas), document); }
            catch { return false; }
        }

        private object? GetCapturedCanvasDocument(GhDocumentLifecycleResult result)
        {
            try { return result.CapturedCanvas is null ? null : _host.GetCanvasDocument(result.CapturedCanvas); }
            catch { result.Code = GhDocumentLifecycleCode.InconsistentState; return null; }
        }

        private void ObserveFinalState(GhDocumentLifecycleResult result)
        {
            if (result.Document is null) return;
            var registration = InspectRegistration(result.Document);
            result.DocumentRegistered = registration.Registered;
            result.RegistrationIndex = registration.Index;
            try
            {
                result.DocumentActive = result.CapturedCanvas is not null &&
                    _host.IsActiveOnAnySupportedCanvas(result.Document, result.CapturedCanvas) == true;
            }
            catch { result.DocumentActive = false; }
        }

        private object? FindPathMatch(IEnumerable<object> documents, string path)
        {
            foreach (var document in documents)
            {
                try
                {
                    if (string.Equals(_host.GetDocumentFilePath(document), path, StringComparison.OrdinalIgnoreCase)) return document;
                }
                catch { return null; }
            }
            return null;
        }

        private static bool ContainsReference(IEnumerable<object> documents, object document) => documents.Any(item => ReferenceEquals(item, document));

        private MembershipState InspectMembership(object document)
        {
            try { return ContainsReference(_host.SnapshotDocuments(), document) ? MembershipState.Present : MembershipState.Absent; }
            catch { return MembershipState.Unknown; }
        }

        private bool IsSameCapturedCanvas(GhDocumentLifecycleResult result)
        {
            try { return result.CapturedCanvas is not null && ReferenceEquals(_host.GetActiveCanvas(), result.CapturedCanvas); }
            catch { return false; }
        }

        private bool HasRequestedPath(object document, string path)
        {
            try { return string.Equals(_host.GetDocumentFilePath(document), path, StringComparison.OrdinalIgnoreCase); }
            catch { return false; }
        }

        private static void MarkIndeterminateReconciliation(GhDocumentLifecycleResult result)
        {
            result.Document = null;
            result.RegistrationIndex = null;
            result.DocumentRegistered = false;
            result.DocumentActive = false;
            result.RollbackAttempted = true;
            result.RollbackIncomplete = true;
        }
    }

    internal sealed class ReflectionGhDocumentLifecycleHost : IGhDocumentLifecycleHost
    {
        public object? GetActiveCanvas() => GetInstancesProperty("ActiveCanvas");

        public object? GetCanvasDocument(object canvas) => GetRequiredProperty(canvas.GetType(), "Document").GetValue(canvas);

        public void SetCanvasDocument(object canvas, object? document) => GetRequiredProperty(canvas.GetType(), "Document").SetValue(canvas, document);

        public IReadOnlyList<object> SnapshotDocuments()
        {
            var server = GetDocumentServer();
            if (!(server is IEnumerable enumerable)) throw new InvalidOperationException("grasshopper_document_server_not_enumerable");
            return enumerable.Cast<object>().ToArray();
        }

        public object CreateEmptyDocument()
        {
            var type = FindType("Grasshopper.Kernel.GH_Document") ?? throw new InvalidOperationException("grasshopper_document_type_missing");
            return Activator.CreateInstance(type) ?? throw new InvalidOperationException("grasshopper_document_create_failed");
        }

        public bool AddNewDocument(object document)
        {
            var method = GetDocumentServer().GetType().GetMethods(BindingFlags.Instance | BindingFlags.Public)
                .Single(method => method.Name == "AddDocument" && method.GetParameters().Length == 2 &&
                    method.GetParameters()[1].ParameterType == typeof(bool).MakeByRefType());
            var arguments = new object?[] { document, false };
            method.Invoke(GetDocumentServer(), arguments);
            return arguments[1] is bool success && success;
        }

        public object? OpenDocument(string path, bool makeActive) => GetDocumentServer().GetType().GetMethod("AddDocument", new[] { typeof(string), typeof(bool) })!.Invoke(GetDocumentServer(), new object[] { path, makeActive });

        public int IndexOf(object document)
        {
            var server = GetDocumentServer();
            return (int)FindDocumentIndexMethod(server.GetType(), document.GetType()).Invoke(server, new[] { document })!;
        }

        public string? GetDocumentFilePath(object document) => GetRequiredProperty(document.GetType(), "FilePath").GetValue(document) as string;

        public bool? IsActiveOnAnySupportedCanvas(object document, object capturedCanvas)
        {
            try
            {
                if (ReferenceEquals(GetCanvasDocument(capturedCanvas), document)) return true;
                var activeCanvas = GetActiveCanvas();
                return activeCanvas is null ? false : ReferenceEquals(GetCanvasDocument(activeCanvas), document);
            }
            catch { return null; }
        }

        public void RemoveDocument(object document) => GetDocumentServer().GetType().GetMethod("RemoveDocument")!.Invoke(GetDocumentServer(), new[] { document });

        public void DisposeDocument(object document) => document.GetType().GetMethod("Dispose", Type.EmptyTypes)!.Invoke(document, null);

        internal static MethodInfo FindDocumentIndexMethod(Type serverType, Type documentType) =>
            serverType.GetMethod("IndexOf", BindingFlags.Instance | BindingFlags.Public, null, new[] { documentType }, null)
            ?? throw new MissingMethodException(serverType.FullName, "IndexOf(" + documentType.FullName + ")");

        private static object GetDocumentServer() => GetInstancesProperty("DocumentServer") ?? throw new InvalidOperationException("grasshopper_document_server_missing");

        private static object? GetInstancesProperty(string name)
        {
            var instances = FindType("Grasshopper.Instances") ?? throw new InvalidOperationException("grasshopper_instances_missing");
            return GetRequiredProperty(instances, name).GetValue(null);
        }

        private static Type? FindType(string fullName) => Type.GetType(fullName + ", Grasshopper", false) ?? AppDomain.CurrentDomain.GetAssemblies().Select(assembly => assembly.GetType(fullName, false)).FirstOrDefault(type => type is not null);

        private static PropertyInfo GetRequiredProperty(Type type, string name) => type.GetProperty(name, BindingFlags.Public | BindingFlags.Static | BindingFlags.Instance) ?? throw new MissingMemberException(type.FullName, name);
    }
}
