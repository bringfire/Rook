using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using Rook.InternalBridge;
using Xunit;

namespace Rook.Tests.InternalBridge
{
    [CollectionDefinition(Name, DisableParallelization = true)]
    public sealed class GhDocumentLifecycleCollection
    {
        public const string Name = "GhDocumentLifecycle";
    }

    [Collection(GhDocumentLifecycleCollection.Name)]
    public sealed class GhDocumentLifecycleTests
    {
        [Fact]
        public void CreateNew_RegistersActivatesAndCommitsInTransactionOrder()
        {
            var host = new FakeHost();
            var candidate = host.NextCreatedDocument;

            var result = new GhDocumentLifecycle(host).CreateNew();

            Assert.True(result.Committed);
            Assert.Same(candidate, result.Document);
            Assert.True(result.DocumentRegistered);
            Assert.True(result.DocumentActive);
            Assert.Equal(0, result.RegistrationIndex);
            Assert.Equal(new[]
            {
                "snapshot", "create_empty", "active_canvas_before_add_new", "add_new_with_out_success",
                "active_canvas_after_add_new", "verify_registration", "active_canvas_before_activation",
                "activate_candidate", "active_canvas_after_activation", "verify_commit",
            }, host.Events);
        }

        [Fact]
        public void CreateNew_OutSuccessFalseRollsBackNeverRegisteredCandidate()
        {
            var host = new FakeHost { AddNewSuccess = false };
            var candidate = host.NextCreatedDocument;

            var result = new GhDocumentLifecycle(host).CreateNew();

            Assert.False(result.Committed);
            Assert.Equal(GhDocumentLifecycleCode.RegistrationFailed, result.Code);
            Assert.True(result.RollbackAttempted);
            Assert.Contains(candidate, host.Disposed);
            Assert.DoesNotContain(candidate, host.Removed);
        }

        [Fact]
        public void CreateNew_MissingIndexRollsBackRegisteredCandidate()
        {
            var host = new FakeHost { IndexOverride = -1 };
            var candidate = host.NextCreatedDocument;

            var result = new GhDocumentLifecycle(host).CreateNew();

            Assert.False(result.Committed);
            Assert.Equal(GhDocumentLifecycleCode.RegistrationFailed, result.Code);
            Assert.Contains(candidate, host.Removed);
            Assert.DoesNotContain(candidate, host.Disposed);
        }

        [Fact]
        public void CreateNew_ServerReferenceMismatchRollsBackRegisteredCandidate()
        {
            var host = new FakeHost { ReplaceIndexedCandidate = true, IndexOverride = 0 };
            var candidate = host.NextCreatedDocument;

            var result = new GhDocumentLifecycle(host).CreateNew();

            Assert.False(result.Committed);
            Assert.Equal(GhDocumentLifecycleCode.InconsistentState, result.Code);
            Assert.DoesNotContain(candidate, host.Removed);
            Assert.Contains(candidate, host.Disposed);
        }

        [Fact]
        public void CreateNew_ActivationFailureRollsBackRegisteredCandidate()
        {
            var host = new FakeHost { IgnoreCanvasAssignments = true };
            var candidate = host.NextCreatedDocument;

            var result = new GhDocumentLifecycle(host).CreateNew();

            Assert.False(result.Committed);
            Assert.Equal(GhDocumentLifecycleCode.ActivationFailed, result.Code);
            Assert.Contains(candidate, host.Removed);
        }

        [Theory]
        [InlineData(FakeHostCanvasChange.BeforeAdd)]
        [InlineData(FakeHostCanvasChange.AfterAdd)]
        [InlineData(FakeHostCanvasChange.BeforeActivation)]
        [InlineData(FakeHostCanvasChange.AfterActivation)]
        public void CreateNew_CanvasChangesAtMutatingBoundaryFailsClosed(FakeHostCanvasChange change)
        {
            var host = new FakeHost { CanvasChange = change };

            var result = new GhDocumentLifecycle(host).CreateNew();

            Assert.False(result.Committed);
            Assert.Equal(GhDocumentLifecycleCode.CanvasChanged, result.Code);
            Assert.True(result.RollbackIncomplete);
            Assert.Empty(host.Removed);
            Assert.Empty(host.Disposed);
        }

        [Fact]
        public void CreateNew_ReentryIsRejectedBeforeMutationAndGuardReleasesAfterSuccess()
        {
            var host = new FakeHost();
            GhDocumentLifecycleResult? reentrant = null;
            host.OnAddNew = () => reentrant = new GhDocumentLifecycle(host).CreateNew();

            var result = new GhDocumentLifecycle(host).CreateNew();
            var after = new GhDocumentLifecycle(new FakeHost()).CreateNew();

            Assert.True(result.Committed);
            Assert.NotNull(reentrant);
            Assert.Equal(GhDocumentLifecycleCode.Reentrant, reentrant!.Code);
            Assert.Equal(new[] { "snapshot", "create_empty", "active_canvas_before_add_new", "add_new_with_out_success" }, host.Events.Take(4));
            Assert.True(after.Committed);
        }

        [Fact]
        public void CreateNew_GuardReleasesAfterExceptionAndRollback()
        {
            var host = new FakeHost { ThrowOnAddNew = true };

            var failed = new GhDocumentLifecycle(host).CreateNew();
            var after = new GhDocumentLifecycle(new FakeHost()).CreateNew();

            Assert.False(failed.Committed);
            Assert.True(failed.RollbackAttempted);
            Assert.True(after.Committed);
        }

        [Fact]
        public void Open_DuplicatePathActivatesThePreexistingReferenceWithoutGrowingServer()
        {
            var host = new FakeHost();
            var existing = new FakeDocument("C:/plans/duplicate.gh");
            host.Documents.Add(existing);
            host.DuplicateOpenReturn = existing;

            var result = new GhDocumentLifecycle(host).Open(existing.FilePath!);

            Assert.True(result.Committed);
            Assert.True(result.PathAlreadyRegistered);
            Assert.Same(existing, result.Document);
            Assert.Single(host.Documents);
            Assert.Same(existing, host.CanvasDocument);
            Assert.Equal(1, host.OpenCalls);
        }

        [Fact]
        public void Open_NullReturnAfterSingleRegisteredActiveAdditionCommitsWithWarning()
        {
            var host = new FakeHost { OpenReturnsNullAfterRegistering = true };

            var result = new GhDocumentLifecycle(host).Open("C:/plans/new.gh");

            Assert.True(result.Committed);
            Assert.True(result.RegisteredByThisCall);
            Assert.Contains(GhDocumentLifecycleWarning.OpenReturnedNullAfterCommit, result.Warnings);
            Assert.Equal("open_returned_null_after_commit", GhDocumentLifecycleWire.Warning(GhDocumentLifecycleWarning.OpenReturnedNullAfterCommit));
        }

        [Fact]
        public void Open_ConflictingReturnedRegisteredAndActiveReferencesCannotCommit()
        {
            var host = new FakeHost { OpenConflict = true };

            var result = new GhDocumentLifecycle(host).Open("C:/plans/conflict.gh");

            Assert.False(result.Committed);
            Assert.Equal(GhDocumentLifecycleCode.InconsistentState, result.Code);
            Assert.Contains(host.OpenCandidate, host.Removed);
        }

        [Fact]
        public void Open_AmbiguousPostCallAdditionsCannotCommit()
        {
            var host = new FakeHost { OpenAddsTwoDocuments = true };

            var result = new GhDocumentLifecycle(host).Open("C:/plans/ambiguous.gh");

            Assert.False(result.Committed);
            Assert.Equal(GhDocumentLifecycleCode.InconsistentState, result.Code);
            Assert.Empty(host.Removed);
        }

        [Fact]
        public void Open_RollbackRestoresPreviousCanvasBeforeRemovingNewCandidate()
        {
            var previous = new FakeDocument("C:/plans/previous.gh");
            var host = new FakeHost { CanvasDocument = previous, FailOpenCommitVerification = true };
            host.Documents.Add(previous);

            var result = new GhDocumentLifecycle(host).Open("C:/plans/new.gh");

            Assert.True(host.Events.IndexOf("restore_previous_canvas") >= 0);
            Assert.True(host.Events.IndexOf("remove_new_candidate") > host.Events.IndexOf("restore_previous_canvas"));
            Assert.True(result.RollbackAttempted);
            Assert.False(result.RollbackIncomplete);
        }

        [Fact]
        public void Open_RollbackFromEmptyCapturedCanvasAssignsNullBeforeRemovingCandidate()
        {
            var host = new FakeHost { FailOpenCommitVerification = true };
            var candidate = host.OpenCandidate;

            var result = new GhDocumentLifecycle(host).Open("C:/plans/new.gh");

            Assert.Contains("restore_previous_canvas", host.Events);
            Assert.Null(host.CanvasDocument);
            Assert.Contains(candidate, host.Removed);
            Assert.True(result.RollbackAttempted);
            Assert.False(result.RollbackIncomplete);
        }

        [Fact]
        public void Open_NeverRemovesOrDisposesPreexistingDuplicate()
        {
            var host = new FakeHost { FailDuplicateCommitVerification = true };
            var existing = new FakeDocument("C:/plans/duplicate.gh");
            host.Documents.Add(existing);

            var result = new GhDocumentLifecycle(host).Open(existing.FilePath!);

            Assert.False(result.Committed);
            Assert.DoesNotContain(existing, host.Removed);
            Assert.DoesNotContain(existing, host.Disposed);
        }

        [Fact]
        public void CreateNew_RegisteredInactiveCandidateIsRemovedRatherThanDisposed()
        {
            var host = new FakeHost { IgnoreCanvasAssignments = true };
            var candidate = host.NextCreatedDocument;

            new GhDocumentLifecycle(host).CreateNew();

            Assert.Contains(candidate, host.Removed);
            Assert.DoesNotContain(candidate, host.Disposed);
        }

        [Fact]
        public void CreateNew_NeverRegisteredInactiveCandidateIsDirectlyDisposed()
        {
            var host = new FakeHost { AddNewSuccess = false };
            var candidate = host.NextCreatedDocument;

            new GhDocumentLifecycle(host).CreateNew();

            Assert.Contains(candidate, host.Disposed);
            Assert.DoesNotContain(candidate, host.Removed);
        }

        [Theory]
        [InlineData(true, false)]
        [InlineData(false, true)]
        public void CreateNew_ActiveCandidateOnAnySupportedCanvasIsPreserved(bool activeOnCaptured, bool activeOnCurrent)
        {
            var host = new FakeHost
            {
                IgnoreCanvasAssignments = true,
                ActiveOnCapturedCanvas = activeOnCaptured,
                ActiveOnCurrentCanvas = activeOnCurrent,
            };
            var candidate = host.NextCreatedDocument;

            var result = new GhDocumentLifecycle(host).CreateNew();

            Assert.True(result.RollbackIncomplete);
            Assert.DoesNotContain(candidate, host.Removed);
            Assert.DoesNotContain(candidate, host.Disposed);
        }

        [Fact]
        public void CreateNew_UnknownCanvasEnumerationPreservesCandidateAndReportsIncompleteRollback()
        {
            var host = new FakeHost { IgnoreCanvasAssignments = true, ActiveCanvasEnumerationKnown = false };
            var candidate = host.NextCreatedDocument;

            var result = new GhDocumentLifecycle(host).CreateNew();

            Assert.True(result.RollbackIncomplete);
            Assert.DoesNotContain(candidate, host.Removed);
            Assert.DoesNotContain(candidate, host.Disposed);
        }

        [Fact]
        public void Open_CallbackCanvasReplacementAfterRestoreStopsDestructiveCleanupAndReportsObservedState()
        {
            var host = new FakeHost { FailOpenCommitVerification = true, ReplaceCanvasAfterRestore = true };
            var candidate = host.OpenCandidate;

            var result = new GhDocumentLifecycle(host).Open("C:/plans/new.gh");

            Assert.True(result.RollbackIncomplete);
            Assert.DoesNotContain(candidate, host.Removed);
            Assert.DoesNotContain(candidate, host.Disposed);
            Assert.False(result.DocumentActive);
        }

        [Fact]
        public void InspectRegistration_UsesReferenceIdentityAndServerIndex()
        {
            var host = new FakeHost();
            var document = new FakeDocument("C:/plans/registered.gh");
            host.Documents.Add(document);

            var state = new GhDocumentLifecycle(host).InspectRegistration(document);

            Assert.True(state.Known);
            Assert.True(state.Registered);
            Assert.Equal(0, state.Index);
        }

        [Fact]
        public void ReflectionHost_SelectsTheDocumentIndexOfOverload()
        {
            var selector = typeof(ReflectionGhDocumentLifecycleHost).GetMethod(
                "FindDocumentIndexMethod",
                BindingFlags.Static | BindingFlags.NonPublic);

            Assert.NotNull(selector);
            var method = (MethodInfo)selector!.Invoke(null, new object[]
            {
                typeof(OverloadedDocumentServer),
                typeof(FakeDocument),
            })!;

            Assert.Equal("IndexOf", method.Name);
            Assert.Equal(typeof(FakeDocument), method.GetParameters()[0].ParameterType);
        }

        [Fact]
        public void CreateNew_UnknownMembershipAfterPartialMutationPreservesCandidate()
        {
            var host = new FakeHost { SnapshotThrowsAfterAdd = true };
            var candidate = host.NextCreatedDocument;

            var result = new GhDocumentLifecycle(host).CreateNew();

            Assert.False(result.Committed);
            Assert.True(result.RollbackAttempted);
            Assert.True(result.RollbackIncomplete);
            Assert.DoesNotContain(candidate, host.Removed);
            Assert.DoesNotContain(candidate, host.Disposed);
        }

        [Fact]
        public void Open_DuplicatePathStillCallsServerAndReconcilesThePreexistingReference()
        {
            var host = new FakeHost();
            var existing = new FakeDocument("C:/plans/duplicate-reconciled.gh");
            host.Documents.Add(existing);
            host.DuplicateOpenReturn = existing;

            var result = new GhDocumentLifecycle(host).Open(existing.FilePath!);

            Assert.True(result.Committed);
            Assert.True(result.PathAlreadyRegistered);
            Assert.True(result.RegistrationSucceeded);
            Assert.Equal(1, host.OpenCalls);
            Assert.Single(host.Documents);
            Assert.Same(existing, result.Document);
        }

        [Fact]
        public void Open_WrongPathPostCallAdditionCannotCommit()
        {
            var host = new FakeHost { OpenAddsWrongPath = true };

            var result = new GhDocumentLifecycle(host).Open("C:/plans/requested.gh");

            Assert.False(result.Committed);
            Assert.Equal(GhDocumentLifecycleCode.InconsistentState, result.Code);
            Assert.Contains(host.OpenCandidate, host.Removed);
        }

        [Fact]
        public void Open_NullReturnWithAmbiguousAdditionsAttemptsIncompleteRollback()
        {
            var host = new FakeHost { OpenAddsTwoDocuments = true, OpenReturnsNullAfterRegistering = true };

            var result = new GhDocumentLifecycle(host).Open("C:/plans/ambiguous-null.gh");

            Assert.False(result.Committed);
            Assert.True(result.RollbackAttempted);
            Assert.True(result.RollbackIncomplete);
        }

        [Fact]
        public void Open_NullReturnWithAmbiguousAdditionsAndNoCandidateRecordsIncompleteReconciliation()
        {
            var host = new FakeHost
            {
                OpenAddsTwoDocuments = true,
                OpenReturnsNullAfterRegistering = true,
                OpenLeavesCanvasInactive = true,
            };

            var result = new GhDocumentLifecycle(host).Open("C:/plans/ambiguous-no-candidate.gh");

            Assert.False(result.Committed);
            Assert.Null(result.Document);
            Assert.True(result.RollbackAttempted);
            Assert.True(result.RollbackIncomplete);
            Assert.False(result.DocumentRegistered);
            Assert.False(result.DocumentActive);
            Assert.Empty(host.Removed);
            Assert.Empty(host.Disposed);
        }

        [Fact]
        public void Open_NullReturnAndPostCallSnapshotFailureRecordsIncompleteReconciliation()
        {
            var host = new FakeHost
            {
                OpenReturnsNullAfterRegistering = true,
                OpenLeavesCanvasInactive = true,
                SnapshotThrowsAfterAdd = true,
            };

            var result = new GhDocumentLifecycle(host).Open("C:/plans/snapshot-failed.gh");

            Assert.False(result.Committed);
            Assert.Null(result.Document);
            Assert.True(result.RollbackAttempted);
            Assert.True(result.RollbackIncomplete);
            Assert.False(result.DocumentRegistered);
            Assert.False(result.DocumentActive);
            Assert.Empty(host.Removed);
            Assert.Empty(host.Disposed);
        }

        [Fact]
        public void Open_ReturnedNewReferenceIsRemovedWhenActiveReferenceConflicts()
        {
            var host = new FakeHost { OpenConflict = true };
            var candidate = host.OpenCandidate;

            var result = new GhDocumentLifecycle(host).Open("C:/plans/new.gh");

            Assert.False(result.Committed);
            Assert.Contains(candidate, host.Removed);
            Assert.DoesNotContain(candidate, host.Disposed);
        }

        [Fact]
        public void CreateNew_UnverifiedRemovalReportsIncompleteRollback()
        {
            var host = new FakeHost { IgnoreCanvasAssignments = true, RemoveLeavesRegistered = true };
            var candidate = host.NextCreatedDocument;

            var result = new GhDocumentLifecycle(host).CreateNew();

            Assert.True(result.RollbackAttempted);
            Assert.True(result.RollbackIncomplete);
            Assert.True(result.DocumentRegistered);
            Assert.Contains(candidate, host.Removed);
        }

        [Fact]
        public void CreateNew_CanvasChangeDuringRemovalReportsIncompleteRollback()
        {
            var host = new FakeHost { IgnoreCanvasAssignments = true, CanvasChangesDuringRemove = true };
            var candidate = host.NextCreatedDocument;

            var result = new GhDocumentLifecycle(host).CreateNew();

            Assert.True(result.RollbackIncomplete);
            Assert.Contains(candidate, host.Removed);
        }

        [Fact]
        public void CreateNew_ReportsCandidateActiveOnReplacementCurrentCanvas()
        {
            var host = new FakeHost
            {
                CanvasChange = FakeHostCanvasChange.AfterAdd,
                CandidateActiveOnReplacement = true,
            };

            var result = new GhDocumentLifecycle(host).CreateNew();

            Assert.False(result.Committed);
            Assert.True(result.DocumentActive);
            Assert.True(result.RollbackIncomplete);
        }

        [Fact]
        public void CreateNew_RestoreCallbackRegistersCandidate_UsesServerRemovalAndNeverDirectDisposal()
        {
            var previous = new FakeDocument("C:/plans/previous.gh");
            var host = new FakeHost { AddNewSuccess = false, CanvasDocument = previous };
            var candidate = host.NextCreatedDocument;
            host.OnRestorePrevious = () => host.Documents.Add(candidate);

            var result = new GhDocumentLifecycle(host).CreateNew();

            Assert.True(result.RollbackAttempted);
            Assert.Same(previous, host.CanvasDocument);
            Assert.Contains(candidate, host.Removed);
            Assert.DoesNotContain(candidate, host.Disposed);
        }

        [Fact]
        public void CreateNew_RestoreCallbackRemovesEverRegisteredCandidate_DoesNotDisposeOrRemoveAgain()
        {
            var previous = new FakeDocument("C:/plans/previous.gh");
            var host = new FakeHost { IgnoreCanvasAssignments = true, CanvasDocument = previous };
            var candidate = host.NextCreatedDocument;
            host.OnRestorePrevious = () => host.Documents.RemoveAll(item => ReferenceEquals(item, candidate));

            var result = new GhDocumentLifecycle(host).CreateNew();

            Assert.True(result.RollbackAttempted);
            Assert.Empty(host.Removed);
            Assert.DoesNotContain(candidate, host.Disposed);
        }

        [Fact]
        public void CreateNew_MembershipChangeDuringActivityInspection_IsResnapshottedBeforeCleanup()
        {
            var host = new FakeHost { AddNewSuccess = false };
            var candidate = host.NextCreatedDocument;
            host.OnActiveInspection = () => host.Documents.Add(candidate);

            new GhDocumentLifecycle(host).CreateNew();

            Assert.Contains(candidate, host.Removed);
            Assert.DoesNotContain(candidate, host.Disposed);
        }

        [Fact]
        public void Open_IndeterminateNoCandidateStillRestoresNonNullPreviousCanvasDocument()
        {
            var previous = new FakeDocument("C:/plans/previous.gh");
            var host = new FakeHost
            {
                CanvasDocument = previous,
                OpenAddsTwoDocuments = true,
                OpenReturnsNullAfterRegistering = true,
                OpenLeavesCanvasInactive = true,
            };

            var result = new GhDocumentLifecycle(host).Open("C:/plans/ambiguous-no-candidate.gh");

            Assert.False(result.Committed);
            Assert.Null(result.Document);
            Assert.True(result.RollbackAttempted);
            Assert.Same(previous, host.CanvasDocument);
            Assert.Contains("restore_previous_canvas", host.Events);
        }

        [Fact]
        public void Open_CanonicalEquivalentPathUsesDocumentServerStringIndexSemantics()
        {
            var host = new FakeHost { UseCanonicalPathIndex = true };
            var existing = new FakeDocument("C:/plans/duplicate.gh");
            host.Documents.Add(existing);
            host.DuplicateOpenReturn = existing;

            var result = new GhDocumentLifecycle(host).Open("C:/plans/sub/../duplicate.gh");

            Assert.True(result.Committed);
            Assert.True(result.PathAlreadyRegistered);
            Assert.Same(existing, result.Document);
            Assert.Single(host.Documents);
        }

        [Fact]
        public void CreateNew_AddThenThrowReconcilesRegistrationAndRollsBackThroughServer()
        {
            var previous = new FakeDocument("C:/plans/previous.gh");
            var host = new FakeHost { AddThenThrow = true, CanvasDocument = previous };
            var candidate = host.NextCreatedDocument;

            var result = new GhDocumentLifecycle(host).CreateNew();

            Assert.False(result.Committed);
            Assert.True(result.RegisteredByThisCall);
            Assert.Same(previous, host.CanvasDocument);
            Assert.Contains(candidate, host.Removed);
            Assert.DoesNotContain(candidate, host.Disposed);
        }

        [Fact]
        public void CreateNew_AssignThenThrowReconcilesObservedActivationBeforeRollback()
        {
            var previous = new FakeDocument("C:/plans/previous.gh");
            var host = new FakeHost { AssignThenThrow = true, CanvasDocument = previous };
            var candidate = host.NextCreatedDocument;

            var result = new GhDocumentLifecycle(host).CreateNew();

            Assert.False(result.Committed);
            Assert.True(result.ActivationSucceeded);
            Assert.False(result.DocumentActive);
            Assert.Same(previous, host.CanvasDocument);
            Assert.Contains(candidate, host.Removed);
        }

        [Fact]
        public void ReflectionHost_SelectsDocumentServerStringIndexOverload()
        {
            var selector = typeof(ReflectionGhDocumentLifecycleHost).GetMethod(
                "FindPathIndexMethod",
                BindingFlags.Static | BindingFlags.NonPublic);

            Assert.NotNull(selector);
            var method = (MethodInfo)selector!.Invoke(null, new object[] { typeof(OverloadedDocumentServer) })!;

            Assert.Equal("IndexOf", method.Name);
            Assert.Equal(typeof(string), method.GetParameters()[0].ParameterType);
        }

        private sealed class FakeDocument
        {
            internal FakeDocument(string? filePath = null) => FilePath = filePath;
            internal string? FilePath { get; }
        }

        private sealed class OverloadedDocumentServer
        {
            public int IndexOf(FakeDocument document) => 0;
            public int IndexOf(string path) => 0;
        }

        public enum FakeHostCanvasChange { None, BeforeAdd, AfterAdd, BeforeActivation, AfterActivation }

        private sealed class FakeHost : IGhDocumentLifecycleHost
        {
            private int _activeCanvasReads;
            private int _indexCalls;
            private bool _capturedPreviousDocument;
            private object? _previousDocument;
            internal readonly List<string> Events = new();
            internal readonly List<object> Documents = new();
            internal readonly List<object> Removed = new();
            internal readonly List<object> Disposed = new();
            internal readonly object CapturedCanvas = new();
            internal readonly object ReplacementCanvas = new();
            internal readonly FakeDocument NextCreatedDocument = new();
            internal readonly FakeDocument OpenCandidate = new("C:/plans/new.gh");
            internal object? ActiveCanvas;
            internal object? CanvasDocument;
            internal bool AddNewSuccess = true;
            internal bool ThrowOnAddNew;
            internal bool AddThenThrow;
            internal bool AssignThenThrow;
            internal int IndexOverride = int.MinValue;
            internal bool ReplaceIndexedCandidate;
            internal bool IgnoreCanvasAssignments;
            internal FakeHostCanvasChange CanvasChange;
            internal Action? OnAddNew;
            internal Action? OnRestorePrevious;
            internal Action? OnActiveInspection;
            internal bool UseCanonicalPathIndex;
            internal bool OpenReturnsNullAfterRegistering;
            internal bool OpenConflict;
            internal bool OpenAddsTwoDocuments;
            internal bool OpenAddsWrongPath;
            internal bool FailOpenCommitVerification;
            internal bool FailDuplicateCommitVerification;
            internal bool ReplaceCanvasAfterRestore;
            internal bool ActiveOnCapturedCanvas;
            internal bool ActiveOnCurrentCanvas;
            internal bool ActiveCanvasEnumerationKnown = true;
            internal bool SnapshotThrowsAfterAdd;
            internal object? DuplicateOpenReturn;
            internal bool RemoveLeavesRegistered;
            internal bool CanvasChangesDuringRemove;
            internal bool CandidateActiveOnReplacement;
            internal bool OpenLeavesCanvasInactive;
            internal object? ReplacementCanvasDocument;
            internal int OpenCalls;

            internal FakeHost()
            {
                ActiveCanvas = CapturedCanvas;
            }

            public object? GetActiveCanvas()
            {
                _activeCanvasReads++;
                var eventName = ActiveCanvasEvent();
                if (eventName is not null)
                {
                    Events.Add(eventName);
                }
                if (CanvasChange == FakeHostCanvasChange.BeforeAdd && _activeCanvasReads == 2 ||
                    CanvasChange == FakeHostCanvasChange.BeforeActivation && _activeCanvasReads == 4)
                {
                    ActiveCanvas = ReplacementCanvas;
                }
                return ActiveCanvas;
            }

            public object? GetCanvasDocument(object canvas)
            {
                if (ReferenceEquals(canvas, ReplacementCanvas)) return ReplacementCanvasDocument;
                if (!ReferenceEquals(canvas, CapturedCanvas)) return null;
                if (!_capturedPreviousDocument)
                {
                    _capturedPreviousDocument = true;
                    _previousDocument = CanvasDocument;
                }
                return CanvasDocument;
            }

            public void SetCanvasDocument(object canvas, object? document)
            {
                var restoringPrevious = _capturedPreviousDocument && ReferenceEquals(document, _previousDocument);
                Events.Add(restoringPrevious ? "restore_previous_canvas" : "activate_candidate");
                if (!ReferenceEquals(canvas, CapturedCanvas) || IgnoreCanvasAssignments)
                {
                    if (restoringPrevious) OnRestorePrevious?.Invoke();
                    return;
                }

                CanvasDocument = document;
                if (restoringPrevious)
                {
                    OnRestorePrevious?.Invoke();
                }
                else if (AssignThenThrow)
                {
                    throw new InvalidOperationException("activation_mutated_then_threw");
                }
                if (document is not null && CanvasChange == FakeHostCanvasChange.AfterActivation)
                {
                    ActiveCanvas = ReplacementCanvas;
                }
                if (document is null && ReplaceCanvasAfterRestore)
                {
                    ActiveCanvas = ReplacementCanvas;
                }
            }

            public IReadOnlyList<object> SnapshotDocuments()
            {
                if (SnapshotThrowsAfterAdd && Documents.Count > 0)
                {
                    throw new InvalidOperationException("snapshot_after_add_failed");
                }
                if (!Events.Contains("snapshot"))
                {
                    Events.Add("snapshot");
                }
                return Documents.ToArray();
            }

            public object CreateEmptyDocument()
            {
                Events.Add("create_empty");
                return NextCreatedDocument;
            }

            public bool AddNewDocument(object document)
            {
                Events.Add("add_new_with_out_success");
                OnAddNew?.Invoke();
                if (ThrowOnAddNew)
                {
                    throw new InvalidOperationException("add_new_failed");
                }

                if (AddNewSuccess)
                {
                    Documents.Add(document);
                    if (CandidateActiveOnReplacement)
                    {
                        ReplacementCanvasDocument = document;
                    }
                    if (ReplaceIndexedCandidate)
                    {
                        Documents[Documents.Count - 1] = new FakeDocument();
                    }
                }

                if (AddThenThrow)
                {
                    throw new InvalidOperationException("registration_mutated_then_threw");
                }

                if (CanvasChange == FakeHostCanvasChange.AfterAdd)
                {
                    ActiveCanvas = ReplacementCanvas;
                }
                return AddNewSuccess;
            }

            public object? OpenDocument(string path, bool makeActive)
            {
                Events.Add("open_with_make_active");
                OpenCalls++;
                if (OpenAddsTwoDocuments)
                {
                    Documents.Add(OpenCandidate);
                    Documents.Add(new FakeDocument(path));
                    CanvasDocument = OpenLeavesCanvasInactive ? null : OpenCandidate;
                    return OpenReturnsNullAfterRegistering ? null : OpenCandidate;
                }

                if (DuplicateOpenReturn is not null)
                {
                    CanvasDocument = DuplicateOpenReturn;
                    return DuplicateOpenReturn;
                }

                if (OpenAddsWrongPath)
                {
                    var wrongPath = new FakeDocument("C:/plans/wrong.gh");
                    Documents.Add(OpenCandidate);
                    CanvasDocument = OpenCandidate;
                    return wrongPath;
                }

                Documents.Add(OpenCandidate);
                CanvasDocument = OpenLeavesCanvasInactive ? null : OpenConflict ? new FakeDocument(path) : OpenCandidate;
                return OpenReturnsNullAfterRegistering ? null : OpenCandidate;
            }

            public int IndexOf(object document)
            {
                Events.Add(Events.Contains("activate_candidate") ? "verify_commit" : "verify_registration");
                _indexCalls++;
                if ((FailOpenCommitVerification && OpenCalls > 0 && _indexCalls > 1) ||
                    (FailDuplicateCommitVerification && _indexCalls > 1))
                {
                    return -1;
                }
                if (IndexOverride != int.MinValue)
                {
                    return IndexOverride;
                }
                return Documents.FindIndex(item => ReferenceEquals(item, document));
            }

            public int IndexOfPath(string path)
            {
                return Documents.FindIndex(item =>
                {
                    var documentPath = (item as FakeDocument)?.FilePath;
                    if (!UseCanonicalPathIndex)
                    {
                        return string.Equals(documentPath, path, StringComparison.OrdinalIgnoreCase);
                    }

                    return documentPath is not null && string.Equals(
                        System.IO.Path.GetFullPath(documentPath),
                        System.IO.Path.GetFullPath(path),
                        StringComparison.OrdinalIgnoreCase);
                });
            }

            public string? GetDocumentFilePath(object document) => (document as FakeDocument)?.FilePath;

            public bool? IsActiveOnAnySupportedCanvas(object document, object capturedCanvas)
            {
                var onActiveInspection = OnActiveInspection;
                OnActiveInspection = null;
                onActiveInspection?.Invoke();
                if (!ActiveCanvasEnumerationKnown)
                {
                    return null;
                }
                return ActiveOnCapturedCanvas || ActiveOnCurrentCanvas ||
                    ReferenceEquals(CanvasDocument, document) ||
                    ReferenceEquals(ReplacementCanvasDocument, document);
            }

            public void RemoveDocument(object document)
            {
                Events.Add("remove_new_candidate");
                Removed.Add(document);
                if (!RemoveLeavesRegistered)
                {
                    Documents.RemoveAll(item => ReferenceEquals(item, document));
                }
                if (CanvasChangesDuringRemove)
                {
                    ActiveCanvas = ReplacementCanvas;
                }
            }

            public void DisposeDocument(object document)
            {
                Events.Add("dispose_new_candidate");
                Disposed.Add(document);
            }

            private string? ActiveCanvasEvent()
            {
                switch (_activeCanvasReads)
                {
                    case 1: return null;
                    case 2: return "active_canvas_before_add_new";
                    case 3: return "active_canvas_after_add_new";
                    case 4: return "active_canvas_before_activation";
                    case 5: return "active_canvas_after_activation";
                    default: return null;
                }
            }
        }
    }
}
