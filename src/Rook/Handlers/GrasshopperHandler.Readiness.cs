using System;
using System.Collections.Generic;
using System.Threading;
using Rook.InternalBridge;

namespace Rook.Handlers
{
    public partial class GrasshopperHandler
    {
        private const int DefaultReadinessWaitMs = 10_000;
        private const int MaximumReadinessWaitMs = 300_000;
        private readonly object _readinessSync = new();
        private readonly GhSolveReceiptRegistry _solveReceiptRegistry;
        private readonly GhSolutionLifecycleAdapter _solutionLifecycleAdapter;
        private readonly GhCanvasDocumentLifecycleAdapter _canvasDocumentLifecycleAdapter;
        private readonly Dictionary<string, string> _receiptLifecycleFailures = new(StringComparer.Ordinal);
        private object? _readinessCanvas;
        private object? _readinessDocument;
        private GhCanvasDocumentLifecycleSubscription? _canvasDocumentSubscription;
        private GhSolutionLifecycleSubscription? _solutionLifecycleSubscription;

        internal void EnsureReadinessSession(object document, object canvas)
        {
            if (document is null)
            {
                throw new ArgumentNullException(nameof(document));
            }

            if (canvas is null)
            {
                throw new ArgumentNullException(nameof(canvas));
            }

            lock (_readinessSync)
            {
                EnsureReadinessSessionLocked(document, canvas);
            }
        }

        internal GhReadinessIssueResult BeginSetValueReceipt(object document, object canvas)
        {
            lock (_readinessSync)
            {
                EnsureReadinessSessionLocked(document, canvas);
                var issue = _solveReceiptRegistry.IssueMutation(document);
                if (issue.Issued && issue.Receipt is not null)
                {
                    var lifecycleFailure = CurrentLifecycleFailureLocked();
                    if (lifecycleFailure is not null)
                    {
                        _receiptLifecycleFailures[issue.Receipt.ReceiptId] = lifecycleFailure;
                    }
                }

                return issue;
            }
        }

        internal GhSolveReadinessReceipt FinalizeSetValueReceipt(string receiptId, GhScheduleResult solveResult)
        {
            lock (_readinessSync)
            {
                if (_receiptLifecycleFailures.TryGetValue(receiptId, out var lifecycleFailure))
                {
                    _receiptLifecycleFailures.Remove(receiptId);
                    _solveReceiptRegistry.MarkLifecycleUnavailable(receiptId, lifecycleFailure);
                    return GetRequiredReceipt(receiptId);
                }

                if (solveResult.ScheduleAcceptance == GhScheduleAcceptance.Accepted)
                {
                    return _solveReceiptRegistry.MarkScheduleAccepted(receiptId);
                }

                if (solveResult.ScheduleClassification == GhScheduleClassification.GlobalSolverUnavailable ||
                    solveResult.ScheduleClassification == GhScheduleClassification.DocumentSolverDisabled)
                {
                    return _solveReceiptRegistry.MarkSolverLocked(receiptId);
                }

                var reason = solveResult.ScheduleFailureCode.HasValue
                    ? GhScheduleWire.ToWire(solveResult.ScheduleFailureCode.Value)
                    : GhScheduleWire.ToWire(solveResult.ScheduleClassification);
                _solveReceiptRegistry.MarkLifecycleUnavailable(receiptId, reason);
                return GetRequiredReceipt(receiptId);
            }
        }

        internal void MarkSetValueMutationFailed(string receiptId)
        {
            lock (_readinessSync)
            {
                _receiptLifecycleFailures.Remove(receiptId);
                _solveReceiptRegistry.MarkMutationFailed(receiptId);
            }
        }

        internal ApiResponse GetSolveReadiness(string? readinessReceiptId)
        {
            var lookup = _solveReceiptRegistry.Get(readinessReceiptId ?? string.Empty);
            if (!lookup.Found || lookup.Receipt is null)
            {
                return ReadinessFailure(lookup.Error!);
            }

            return new ApiResponse
            {
                Success = true,
                Data = new { receipt = ReceiptSnapshot(lookup.Receipt) },
            };
        }

        internal ApiResponse WaitForSolveReadiness(
            string? readinessReceiptId,
            int timeoutMs = DefaultReadinessWaitMs,
            CancellationToken cancellationToken = default)
        {
            if (timeoutMs < 1 || timeoutMs > MaximumReadinessWaitMs)
            {
                return ReadinessFailure("readiness_timeout_ms_out_of_range");
            }

            var result = _solveReceiptRegistry.Wait(
                readinessReceiptId ?? string.Empty,
                TimeSpan.FromMilliseconds(timeoutMs),
                cancellationToken);
            if (result.WaitStatus is null || result.Receipt is null)
            {
                return ReadinessFailure(result.Error!);
            }

            return new ApiResponse
            {
                Success = true,
                Data = new
                {
                    schema = "rook.gh_solve_readiness_wait_result:v1",
                    wait_status = WaitStatusName(result.WaitStatus.Value),
                    receipt = ReceiptSnapshot(result.Receipt),
                },
            };
        }

        internal ApiResponse ReadinessIssueFailure(string error) => ReadinessFailure(error);

        internal ApiResponse ReadinessFenceFailure(GhFencedReadGate gate)
        {
            if (gate.Receipt is null)
            {
                return ReadinessFailure(gate.Error!);
            }

            return new ApiResponse
            {
                Success = false,
                Data = new
                {
                    error = gate.Error,
                    receipt = ReceiptSnapshot(gate.Receipt),
                },
            };
        }

        private void EnsureReadinessSessionLocked(object document, object canvas)
        {
            if (!ReferenceEquals(_readinessCanvas, canvas))
            {
                _canvasDocumentSubscription?.Dispose();
                _readinessCanvas = canvas;
                _canvasDocumentSubscription = _canvasDocumentLifecycleAdapter.Attach(
                    canvas,
                    OnCanvasDocumentChanged);
            }

            if (!ReferenceEquals(_readinessDocument, document))
            {
                ReplaceReadinessDocumentLocked(document);
            }
        }

        private void OnCanvasDocumentChanged(object? oldDocument, object? newDocument)
        {
            lock (_readinessSync)
            {
                if (ReferenceEquals(_readinessDocument, newDocument))
                {
                    return;
                }

                ReplaceReadinessDocumentLocked(newDocument);
            }
        }

        private void ReplaceReadinessDocumentLocked(object? newDocument)
        {
            _solveReceiptRegistry.ReplaceDocument(newDocument);
            _solutionLifecycleSubscription?.Dispose();
            _solutionLifecycleSubscription = null;
            _readinessDocument = newDocument;

            if (newDocument is not null)
            {
                _solutionLifecycleSubscription = _solutionLifecycleAdapter.Attach(
                    newDocument,
                    _solveReceiptRegistry.OnSolutionStart,
                    _solveReceiptRegistry.OnSolutionEnd);
            }
        }

        private string? CurrentLifecycleFailureLocked()
        {
            if (_canvasDocumentSubscription?.IsAvailable != true)
            {
                return _canvasDocumentSubscription?.Reason ?? "canvas_document_lifecycle_unavailable";
            }

            if (_solutionLifecycleSubscription?.IsAvailable != true)
            {
                return _solutionLifecycleSubscription?.Reason ?? "solution_lifecycle_unavailable";
            }

            return null;
        }

        private GhSolveReadinessReceipt GetRequiredReceipt(string receiptId)
        {
            var lookup = _solveReceiptRegistry.Get(receiptId);
            if (!lookup.Found || lookup.Receipt is null)
            {
                throw new InvalidOperationException(lookup.Error);
            }

            return lookup.Receipt;
        }

        private static ApiResponse ReadinessFailure(string error) => new()
        {
            Success = false,
            Data = new { error },
        };

        private static object ReceiptSnapshot(GhSolveReadinessReceipt receipt) => new
        {
            schema = "rook.gh_solve_readiness_receipt:v1",
            receipt_id = receipt.ReceiptId,
            document_session_id = receipt.DocumentSessionId,
            mutation_epoch = receipt.MutationEpoch,
            solution_run_epoch = receipt.SolutionRunEpoch,
            completed_solution_run_epoch = receipt.CompletedSolutionRunEpoch,
            status = ReceiptStatusName(receipt.Status),
            reason = receipt.Reason,
            completion_signal = receipt.CompletionSignal,
            issued_at = receipt.IssuedAt,
            completed_at = receipt.CompletedAt,
        };

        private static string ReceiptStatusName(GhSolveReadinessStatus status) => status switch
        {
            GhSolveReadinessStatus.Pending => "pending",
            GhSolveReadinessStatus.Ready => "ready",
            GhSolveReadinessStatus.Superseded => "superseded",
            GhSolveReadinessStatus.DocumentReplaced => "document_replaced",
            GhSolveReadinessStatus.SolverLocked => "solver_locked",
            _ => "unknown",
        };

        private static string WaitStatusName(GhReadinessWaitStatus status) => status switch
        {
            GhReadinessWaitStatus.Ready => "ready",
            GhReadinessWaitStatus.Timeout => "timeout",
            _ => "terminal",
        };
    }
}
