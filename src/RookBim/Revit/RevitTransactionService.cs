using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Events;
using Autodesk.Revit.UI;
using Rook.Bim;

namespace RookBim.Revit
{
    /// <summary>
    /// The only place in RookBIM that writes the Revit document, and the only
    /// writer of a transaction receipt's status.
    ///
    /// It owns one transaction on the active document from the document check
    /// to the confirmed end: it starts the transaction, runs the edit by
    /// calling it and observing it return, commits or rolls back, and records
    /// each thing Revit reports in the receipt the moment Revit reports it.
    /// What the caller is told is then derived from that receipt in one place
    /// (<see cref="BimTransactionReport"/>).
    ///
    /// What it guarantees is the fate of that one transaction. The edit is
    /// trusted code with the whole Revit API: changes it makes to another
    /// document, or work it schedules for later, are outside this transaction
    /// and outside this guarantee.
    /// </summary>
    internal sealed class RevitTransactionService
    {
        internal const int MaxReportedElements = 100;
        internal const int MaxReportedFailures = 50;
        internal const int MaxFailureTextLength = 500;
        private readonly Func<RevitScriptChannel, string?> runScript;

        public RevitTransactionService()
            : this(RevitPythonScriptRunner.Run)
        {
        }

        internal RevitTransactionService(Func<RevitScriptChannel, string?> runScript)
        {
            this.runScript = runScript ?? throw new ArgumentNullException(nameof(runScript));
        }

        public BimApiResponse Run(
            UIDocument uiDocument,
            Document document,
            RevitDocumentIdentityEvidence evidence,
            BimRunTransactionRequest request,
            BimTransactionCall call)
        {
            if (uiDocument == null)
            {
                throw new ArgumentNullException(nameof(uiDocument));
            }

            if (document == null)
            {
                throw new ArgumentNullException(nameof(document));
            }

            if (request == null)
            {
                throw new ArgumentNullException(nameof(request));
            }

            if (call == null)
            {
                throw new ArgumentNullException(nameof(call));
            }

            var receipt = call.Receipt;
            var gate = call.Gate;
            var name = request.EffectiveName;

            if (evidence == null || !RevitDocumentIdentityResolver.IsSameDocument(document, evidence.Owner))
            {
                receipt.Refuse(
                    BimErrorCode.DocumentIdentityInvalid,
                    "Transaction document does not match the captured identity evidence.");
                return BimTransactionReport.Build(receipt.Snapshot());
            }

            var activeDocument = RevitDocumentIdentityResolver.ProjectDocument(evidence);
            receipt.SetDocument(activeDocument);

            if (request.HasDocumentKey &&
                !string.Equals(request.DocumentKey, activeDocument.DocumentKey, StringComparison.Ordinal))
            {
                // The caller read one document; a different one is active now.
                // Element ids repeat across documents, so writing here would
                // change the wrong model without any error.
                receipt.Refuse(
                    BimErrorCode.DocumentMismatch,
                    "The active Revit document is not the one this write was prepared for. " +
                    $"Expected documentKey '{request.DocumentKey}'; the active document is '{activeDocument.Title}' " +
                    $"with documentKey '{activeDocument.DocumentKey ?? "unavailable"}'. " +
                    "Ask the user to switch back to the intended document, or read the elements again in the " +
                    "active document and call again with its documentKey.");
                return BimTransactionReport.Build(
                    receipt.Snapshot(),
                    new Dictionary<string, object?> { ["expectedDocumentKey"] = request.DocumentKey });
            }

            if (document.IsReadOnly)
            {
                receipt.Refuse(
                    BimErrorCode.DocumentNotModifiable,
                    "The active Revit document is read-only. Open an editable copy of the model in Revit, then retry.");
                return BimTransactionReport.Build(receipt.Snapshot());
            }

            if (document.IsModifiable)
            {
                receipt.Refuse(
                    BimErrorCode.DocumentNotModifiable,
                    "Another transaction is already open in the active Revit document. An active command or edit " +
                    "mode in Revit is the likely cause: finish or cancel it in Revit, then retry.");
                return BimTransactionReport.Build(receipt.Snapshot());
            }

            if (gate.CommitProhibited)
            {
                receipt.Refuse(
                    BimErrorCode.TransactionTimeout,
                    "The caller stopped waiting before the transaction was started.");
                return BimTransactionReport.Build(receipt.Snapshot());
            }

            var changes = new ChangeCollector(document);
            var failures = new CollectingFailuresPreprocessor();
            var application = uiDocument.Application.Application;
            var subscribed = false;
            BimTransactionScriptResult? script = null;
            Transaction? transaction = null;
            try
            {
                application.DocumentChanged += changes.OnDocumentChanged;
                subscribed = true;

                transaction = new Transaction(document, name);
                TransactionStatus started;
                try
                {
                    started = transaction.Start();
                }
                catch (Autodesk.Revit.Exceptions.InvalidOperationException ex)
                {
                    // Revit refuses to start: read-only command context,
                    // changes temporarily disabled, or failure mode.
                    receipt.Refuse(
                        BimErrorCode.DocumentNotModifiable,
                        $"Revit refused to start the transaction: {ex.Message} " +
                        "Finish or cancel any active command in Revit, then retry.");
                    return BimTransactionReport.Build(receipt.Snapshot());
                }

                if (started != TransactionStatus.Started)
                {
                    receipt.Refuse(
                        BimErrorCode.DocumentNotModifiable,
                        $"Revit did not start the transaction (status {started}). " +
                        "Finish or cancel any active command in Revit, then retry.");
                    return BimTransactionReport.Build(receipt.Snapshot());
                }

                receipt.MarkOpen();

                // Start() resets failure handling to its defaults, so the
                // options must be applied after it, never before.
                var options = transaction.GetFailureHandlingOptions();
                options.SetFailuresPreprocessor(failures);
                // The preprocessor resolves every failure without UI. Forced
                // modal handling keeps Commit() synchronous: with it off, Revit
                // may leave a modeless dialog and return a Pending commit.
                options.SetForcedModalHandling(true);
                options.SetClearAfterRollback(true);
                transaction.SetFailureHandlingOptions(options);

                if (!gate.TryEnterScript())
                {
                    receipt.ProhibitCommit(
                        BimErrorCode.TransactionTimeout,
                        "The caller stopped waiting before the script could start, so the script was not run.");
                    receipt.Settle(Settle(transaction));
                    return BimTransactionReport.Build(receipt.Snapshot());
                }

                script = RunScript(uiDocument, document, request);
                gate.MarkScriptReturned();
                if (!script.Success)
                {
                    receipt.ProhibitCommit(
                        BimErrorCode.TransactionScriptFailed,
                        script.ScriptRaised
                            ? "The script raised " + script.Error + "."
                            : "The script did not run to its end: " + script.Error);
                    receipt.Settle(Settle(transaction));
                    return BimTransactionReport.Build(receipt.Snapshot(), Details(script, failures, gate));
                }

                if (!gate.TryBeginCommit())
                {
                    // Either the caller was already told nothing would be
                    // committed, or the script ran past its budget. Both end
                    // the same way: no commit.
                    receipt.ProhibitCommit(
                        BimErrorCode.TransactionTimeout,
                        gate.ScriptRanOverBudget
                            ? $"The script ran for {Seconds(gate.ScriptDuration)} s, longer than timeoutSeconds " +
                              $"({Seconds(gate.ScriptTimeout)}), so it was not committed."
                            : "The script finished after the caller stopped waiting, so it was not committed.");
                    receipt.Settle(Settle(transaction));
                    return BimTransactionReport.Build(receipt.Snapshot(), Details(script, failures, gate));
                }

                var committed = transaction.Commit();
                if (committed == TransactionStatus.RolledBack)
                {
                    receipt.ProhibitCommit(
                        BimErrorCode.TransactionRolledBack,
                        "The script ran, but Revit refused to commit the transaction" +
                        (failures.Errors.Count > 0
                            ? ". Revit reported: " + string.Join(" | ", failures.Errors)
                            : string.Empty) + ".");
                }

                // Recorded the moment Revit answers, before anything that
                // could fail or take time: from here on the receipt, not this
                // method, is the answer to "was it committed?".
                receipt.Settle(StatusOf(committed));

                var details = Details(script, failures, gate);
                if (committed == TransactionStatus.Committed)
                {
                    AddCommittedDetails(details, changes, document, evidence);
                }

                return BimTransactionReport.Build(
                    receipt.Snapshot(),
                    details,
                    committed == TransactionStatus.Committed ? changes.Total > 0 : (bool?)null);
            }
            catch (Exception ex)
            {
                if (receipt.Snapshot().Status == BimTransactionStatus.Committed)
                {
                    // The commit already happened and is on record; only the
                    // optional reporting failed.
                    var details = script == null
                        ? new Dictionary<string, object?>()
                        : Details(script, failures, gate);
                    details["elementsOmittedReason"] =
                        $"Reporting failed after the commit ({ex.GetType().Name}: {ex.Message}).";
                    return BimTransactionReport.Build(receipt.Snapshot(), details);
                }

                receipt.ProhibitCommit(
                    BimErrorCode.InternalError,
                    $"RookBIM failed while running the transaction: {ex.GetType().Name}: {ex.Message}.");
                receipt.Settle(Settle(transaction));
                return BimTransactionReport.Build(
                    receipt.Snapshot(),
                    script == null ? null : Details(script, failures, gate));
            }
            finally
            {
                if (subscribed)
                {
                    try
                    {
                        application.DocumentChanged -= changes.OnDocumentChanged;
                    }
                    catch
                    {
                    }
                }

                // Whatever path led here, a transaction this call started is
                // not left open, and the receipt records where it ended.
                if (transaction != null)
                {
                    receipt.Settle(Settle(transaction));
                    try
                    {
                        transaction.Dispose();
                    }
                    catch
                    {
                    }
                }
            }
        }

        private BimTransactionScriptResult RunScript(
            UIDocument uiDocument,
            Document document,
            BimRunTransactionRequest request)
        {
            var uiApplication = uiDocument.Application;
            var channel = new RevitScriptChannel(
                request.Code ?? string.Empty,
                document,
                uiDocument,
                uiApplication,
                uiApplication.Application);

            // The host calls the script engine itself and is here again only
            // when that call has returned or thrown.
            string? hostError;
            try
            {
                hostError = runScript(channel);
            }
            catch (Exception ex)
            {
                hostError = ex.GetType().Name + ": " + ex.Message;
            }

            return BimTransactionScriptResult.FromHostRun(
                hostObservedReturn: hostError == null,
                hostError: hostError,
                scriptReportedCompletion: channel.Completed,
                stage: channel.Stage,
                scriptError: channel.ScriptError,
                scriptTraceback: channel.ScriptTraceback,
                output: channel.Output,
                outputTruncated: channel.OutputTruncated,
                stderr: channel.Stderr,
                stderrTruncated: channel.StderrTruncated,
                resultJson: channel.ResultJson,
                resultOmittedReason: channel.ResultOmittedReason);
        }

        /// <summary>
        /// Brings the Revit transaction to rest and returns where it ended, as
        /// Revit reports it. A started transaction is rolled back; one Revit
        /// is still finalizing cannot be rolled back from here and is reported
        /// as unresolved, never as rolled back.
        /// </summary>
        private static BimTransactionStatus Settle(Transaction? transaction)
        {
            if (transaction == null)
            {
                return BimTransactionStatus.NotStarted;
            }

            try
            {
                var status = transaction.GetStatus();
                if (status == TransactionStatus.Started)
                {
                    status = transaction.RollBack();
                }

                return StatusOf(status);
            }
            catch
            {
                return BimTransactionStatus.Unresolved;
            }
        }

        private static BimTransactionStatus StatusOf(TransactionStatus status)
        {
            switch (status)
            {
                case TransactionStatus.Uninitialized:
                    return BimTransactionStatus.NotStarted;
                case TransactionStatus.Started:
                    return BimTransactionStatus.Open;
                case TransactionStatus.RolledBack:
                    return BimTransactionStatus.RolledBack;
                case TransactionStatus.Committed:
                    return BimTransactionStatus.Committed;
                default:
                    // Pending, Error, Proceed: Revit has not given a final answer.
                    return BimTransactionStatus.Unresolved;
            }
        }

        private static string Seconds(TimeSpan? value)
        {
            return value.HasValue
                ? value.Value.TotalSeconds.ToString("0.#", System.Globalization.CultureInfo.InvariantCulture)
                : "an unknown number of";
        }

        private static Dictionary<string, object?> Details(
            BimTransactionScriptResult script,
            CollectingFailuresPreprocessor failures,
            BimTransactionCommitGate gate)
        {
            return new Dictionary<string, object?>(StringComparer.Ordinal)
            {
                // Whether the script itself raised, or never ran to its end
                // for another reason (engine unavailable, for example).
                ["scriptRaised"] = script.ScriptRaised,
                ["stage"] = script.Stage,
                ["error"] = script.Success ? null : script.Error,
                ["traceback"] = script.Success ? null : script.Traceback,
                ["scriptSeconds"] = gate.ScriptDuration?.TotalSeconds,
                ["output"] = script.Output,
                ["outputTruncated"] = script.OutputTruncated,
                ["stderr"] = script.Stderr,
                ["stderrTruncated"] = script.StderrTruncated,
                ["result"] = script.Result,
                ["resultOmittedReason"] = script.ResultOmittedReason,
                ["warnings"] = failures.Warnings,
                ["warningsOmitted"] = failures.WarningsOmitted,
                ["failures"] = failures.Errors,
                ["failuresOmitted"] = failures.ErrorsOmitted,
            };
        }

        /// <summary>Optional detail, gathered after the commit is on record. It cannot fail the response.</summary>
        private static void AddCommittedDetails(
            Dictionary<string, object?> details,
            ChangeCollector changes,
            Document document,
            RevitDocumentIdentityEvidence evidence)
        {
            details["changed"] = changes.Total > 0;
            try
            {
                details["elements"] = changes.Describe(document, evidence);
            }
            catch (Exception ex)
            {
                details["elements"] = changes.CountsOnly();
                details["elementsOmittedReason"] =
                    $"The changed elements could not be listed ({ex.GetType().Name}: {ex.Message}); only counts are given.";
            }
        }

        /// <summary>Records what Revit itself reports as changed when the transaction commits.</summary>
        private sealed class ChangeCollector
        {
            private readonly Document document;
            private readonly List<ElementId> added = new List<ElementId>();
            private readonly List<ElementId> modified = new List<ElementId>();
            private readonly List<ElementId> deleted = new List<ElementId>();

            public ChangeCollector(Document document)
            {
                this.document = document;
            }

            public int Total
            {
                get { return added.Count + modified.Count + deleted.Count; }
            }

            public void OnDocumentChanged(object? sender, DocumentChangedEventArgs args)
            {
                if (!RevitDocumentIdentityResolver.IsSameDocument(args.GetDocument(), document))
                {
                    return;
                }

                added.AddRange(args.GetAddedElementIds());
                modified.AddRange(args.GetModifiedElementIds());
                deleted.AddRange(args.GetDeletedElementIds());
            }

            public object CountsOnly()
            {
                return new
                {
                    addedCount = added.Count,
                    modifiedCount = modified.Count,
                    deletedCount = deleted.Count,
                    limit = MaxReportedElements
                };
            }

            public object Describe(Document owner, RevitDocumentIdentityEvidence evidence)
            {
                return new
                {
                    addedCount = added.Count,
                    modifiedCount = modified.Count,
                    deletedCount = deleted.Count,
                    limit = MaxReportedElements,
                    truncated =
                        added.Count > MaxReportedElements ||
                        modified.Count > MaxReportedElements ||
                        deleted.Count > MaxReportedElements,
                    added = DescribeLive(owner, evidence, added),
                    modified = DescribeLive(owner, evidence, modified),
                    // Deleted elements no longer exist, so only their former ids can be reported.
                    deleted = deleted.Take(MaxReportedElements).Select(id => id.Value).ToList()
                };
            }

            private static List<object> DescribeLive(
                Document owner,
                RevitDocumentIdentityEvidence evidence,
                List<ElementId> ids)
            {
                var described = new List<object>();
                foreach (var id in ids.Take(MaxReportedElements))
                {
                    // One element that cannot be described must neither fail
                    // the response nor vanish from it.
                    try
                    {
                        var element = owner.GetElement(id);
                        if (element == null)
                        {
                            described.Add(Undescribed(id, "Revit reported the id but the element could not be fetched."));
                            continue;
                        }

                        var identity = RevitDocumentIdentityResolver.ProjectElement(evidence, element);
                        // Only hand back an identity the read tools will accept:
                        // the same preflight they apply to their input.
                        var usable = RevitDocumentIdentityResolver.PreflightBatch(
                            evidence,
                            new BimElementIdentity?[] { identity },
                            BimDiagnosticContext.Disabled);
                        if (!usable.Success)
                        {
                            described.Add(Undescribed(
                                id,
                                "The read tools would refuse this identity: " +
                                (usable.Message ?? usable.ErrorCode.ToString()) +
                                " (an unsaved document has no stable document identity)."));
                            continue;
                        }

                        described.Add(new
                        {
                            identity = identity,
                            name = SafeRead(() => element.Name),
                            category = SafeRead(() => element.Category?.Name),
                            className = element.GetType().Name
                        });
                    }
                    catch (Exception ex)
                    {
                        described.Add(Undescribed(id, ex.GetType().Name + ": " + ex.Message));
                    }
                }

                return described;
            }

            private static object Undescribed(ElementId id, string reason)
            {
                return new
                {
                    identity = (object?)null,
                    elementId = id.Value,
                    identityOmittedReason = reason
                };
            }

            private static string? SafeRead(Func<string?> read)
            {
                try
                {
                    var value = read();
                    return string.IsNullOrWhiteSpace(value) ? null : value;
                }
                catch
                {
                    return null;
                }
            }
        }

        /// <summary>
        /// Answers Revit's failure processing without a dialog: warnings are
        /// dismissed and reported, errors roll the transaction back.
        /// </summary>
        private sealed class CollectingFailuresPreprocessor : IFailuresPreprocessor
        {
            public List<string> Warnings { get; } = new List<string>();

            public List<string> Errors { get; } = new List<string>();

            /// <summary>How many warnings were dismissed but not listed.</summary>
            public int WarningsOmitted { get; private set; }

            public int ErrorsOmitted { get; private set; }

            public FailureProcessingResult PreprocessFailures(FailuresAccessor failuresAccessor)
            {
                var hasError = false;
                foreach (var failure in failuresAccessor.GetFailureMessages())
                {
                    var text = Bounded(failure.GetDescriptionText());
                    if (failure.GetSeverity() == FailureSeverity.Warning)
                    {
                        if (Warnings.Count < MaxReportedFailures)
                        {
                            Warnings.Add(text);
                        }
                        else
                        {
                            WarningsOmitted++;
                        }

                        failuresAccessor.DeleteWarning(failure);
                    }
                    else
                    {
                        if (Errors.Count < MaxReportedFailures)
                        {
                            Errors.Add(text);
                        }
                        else
                        {
                            ErrorsOmitted++;
                        }

                        hasError = true;
                    }
                }

                return hasError
                    ? FailureProcessingResult.ProceedWithRollBack
                    : FailureProcessingResult.Continue;
            }

            private static string Bounded(string? text)
            {
                var value = text ?? string.Empty;
                return value.Length <= MaxFailureTextLength
                    ? value
                    : value.Substring(0, MaxFailureTextLength) + "...";
            }
        }
    }
}
