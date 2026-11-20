using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Events;
using Autodesk.Revit.UI;
using Rook.Bim;

namespace RookBim.Revit
{
    /// <summary>
    /// Decides, exactly once, whether a transaction may be committed. The
    /// request thread cancels when it stops waiting; the Revit API thread asks
    /// before committing. Whichever wins the exchange owns the outcome, so a
    /// caller that was told "timed out" never gets a commit behind its back.
    /// </summary>
    internal sealed class RevitTransactionCommitGate
    {
        private const int Open = 0;
        private const int Committing = 1;
        private const int Cancelled = 2;
        private int state = Open;
        private readonly TaskCompletionSource<bool> started =
            new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);

        /// <summary>Completes when Revit's API thread has picked the work up.</summary>
        public Task Started
        {
            get { return started.Task; }
        }

        public void MarkStarted()
        {
            started.TrySetResult(true);
        }

        public bool TryBeginCommit()
        {
            return Interlocked.CompareExchange(ref state, Committing, Open) == Open;
        }

        public bool TryCancel()
        {
            return Interlocked.CompareExchange(ref state, Cancelled, Open) == Open;
        }
    }

    /// <summary>
    /// The only place in RookBIM that writes the Revit document. Runs one
    /// caller-supplied Python script inside one named transaction, on Revit's
    /// API thread, and commits only when the script ran to its end.
    /// </summary>
    internal sealed class RevitTransactionService
    {
        internal const int MaxReportedElements = 200;
        private const string WrapperResourceName = "RookBim.run_transaction_wrapper.py";
        private static int scriptCounter;
        private readonly Func<string, bool> runRhinoScript;

        public RevitTransactionService()
            : this(command => Rhino.RhinoApp.RunScript(command, false))
        {
        }

        internal RevitTransactionService(Func<string, bool> runRhinoScript)
        {
            this.runRhinoScript = runRhinoScript ?? throw new ArgumentNullException(nameof(runRhinoScript));
        }

        public BimApiResponse Run(
            UIDocument uiDocument,
            Document document,
            RevitDocumentIdentityEvidence evidence,
            BimRunTransactionRequest request,
            RevitTransactionCommitGate gate)
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

            if (gate == null)
            {
                throw new ArgumentNullException(nameof(gate));
            }

            // From here the request thread measures the script timeout.
            gate.MarkStarted();

            if (evidence == null || !RevitDocumentIdentityResolver.IsSameDocument(document, evidence.Owner))
            {
                return BimApiResponse.Fail(
                    BimErrorCode.DocumentIdentityInvalid,
                    "Transaction document does not match the captured identity evidence.",
                    400);
            }

            var name = request.EffectiveName;
            if (document.IsReadOnly)
            {
                return Refuse(
                    BimErrorCode.DocumentNotModifiable,
                    $"The active Revit document is read-only, so transaction '{name}' was not started and nothing changed. " +
                    "Open an editable copy of the model in Revit, then retry.",
                    409,
                    name,
                    "not_started");
            }

            if (document.IsModifiable)
            {
                return Refuse(
                    BimErrorCode.DocumentNotModifiable,
                    $"Another transaction is already open in the active Revit document, so transaction '{name}' was not started and nothing changed. " +
                    "An active command or edit mode in Revit is the likely cause: finish or cancel it in Revit, then retry.",
                    409,
                    name,
                    "not_started");
            }

            var files = ScriptFiles.Create();
            var changes = new ChangeCollector(document);
            var failures = new CollectingFailuresPreprocessor();
            var application = uiDocument.Application.Application;
            var subscribed = false;
            Transaction? transaction = null;
            try
            {
                File.WriteAllText(files.Code, request.Code ?? string.Empty, new UTF8Encoding(false));
                File.WriteAllText(files.Wrapper, BuildWrapper(files), new UTF8Encoding(false));

                application.DocumentChanged += changes.OnDocumentChanged;
                subscribed = true;

                transaction = new Transaction(document, name);
                var options = transaction.GetFailureHandlingOptions();
                options.SetFailuresPreprocessor(failures);
                // Never let Revit open a failure dialog: a modal dialog would
                // stall the idle queue and hang this request.
                options.SetForcedModalHandling(false);
                options.SetClearAfterRollback(true);
                transaction.SetFailureHandlingOptions(options);

                var started = transaction.Start();
                if (started != TransactionStatus.Started)
                {
                    return Refuse(
                        BimErrorCode.DocumentNotModifiable,
                        $"Revit did not start transaction '{name}' (status {started}); nothing changed. " +
                        "Finish or cancel any active command in Revit, then retry.",
                        409,
                        name,
                        "not_started");
                }

                var script = RunScript(files);
                if (!script.Success)
                {
                    var rolledBack = RollBack(transaction);
                    return ScriptFailure(name, script, rolledBack);
                }

                if (!gate.TryBeginCommit())
                {
                    // The caller already got transaction_timeout and was told
                    // nothing would be committed. Keep that promise.
                    var rolledBack = RollBack(transaction);
                    return Fail(
                        BimErrorCode.TransactionTimeout,
                        $"The script finished after the caller stopped waiting. Transaction '{name}' was " +
                        RollbackClause(rolledBack),
                        504,
                        name,
                        rolledBack,
                        script,
                        failures);
                }

                var committed = transaction.Commit();
                if (committed != TransactionStatus.Committed)
                {
                    var reasons = failures.Errors.Count > 0
                        ? " Revit reported: " + string.Join(" | ", failures.Errors)
                        : string.Empty;
                    return Fail(
                        BimErrorCode.TransactionRolledBack,
                        $"The script ran, but Revit refused to commit transaction '{name}' (status {committed}) and rolled it back; " +
                        "the Revit document is unchanged." + reasons +
                        " Change the script so the model stays valid, then call again.",
                        409,
                        name,
                        committed == TransactionStatus.RolledBack,
                        script,
                        failures);
                }

                return BimApiResponse.Ok(new
                {
                    transaction = new
                    {
                        name = name,
                        status = "committed"
                    },
                    changed = changes.Total > 0,
                    elements = changes.Describe(document, evidence),
                    warnings = failures.Warnings,
                    output = script.Output,
                    outputTruncated = script.OutputTruncated,
                    stderr = script.Stderr,
                    stderrTruncated = script.StderrTruncated,
                    result = script.Result,
                    resultOmittedReason = script.ResultOmittedReason,
                    document = RevitDocumentIdentityResolver.ProjectDocument(evidence)
                });
            }
            catch (Exception ex)
            {
                if (IsCommitted(transaction))
                {
                    // The commit already happened; saying "rolled back" or
                    // "unknown" here would invite a second, duplicate run.
                    var committedResponse = BimApiResponse.Fail(
                        BimErrorCode.InternalError,
                        $"Transaction '{name}' was committed, but RookBIM failed while reporting it: " +
                        $"{ex.GetType().Name}: {ex.Message}. The change is in the Revit document and its undo list. " +
                        "Do not run the script again; read the model back with rookbim_query_elements to see the result.",
                        500);
                    committedResponse.Data = new
                    {
                        transaction = new
                        {
                            name = name,
                            status = "committed"
                        },
                        documentChanged = true
                    };
                    return committedResponse;
                }

                var rolledBack = RollBack(transaction);
                return Fail(
                    BimErrorCode.InternalError,
                    $"RookBIM failed while running transaction '{name}': {ex.GetType().Name}: {ex.Message}. The transaction was " +
                    RollbackClause(rolledBack),
                    500,
                    name,
                    rolledBack,
                    null,
                    failures);
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

                RollBack(transaction);
                transaction?.Dispose();
                files.Delete();
            }
        }

        private BimTransactionScriptResult RunScript(ScriptFiles files)
        {
            // Same engine as POST /execute: Rhino's RunPythonScript command.
            // The difference is the caller: this runs inside Revit's API
            // context with a transaction already open.
            var accepted = runRhinoScript("_-RunPythonScript \"" + files.Wrapper + "\"");
            if (!File.Exists(files.Result))
            {
                return BimTransactionScriptResult.Missing(
                    accepted
                        ? "Rhino ran the script command but the script never reported a result. " +
                          "It may have asked for interactive input, which a transaction script must not do."
                        : "Rhino refused to start the script command. A Rhino command is probably " +
                          "still running; finish or cancel it in the Rhino window, then retry.");
            }

            return BimTransactionScriptResult.Parse(File.ReadAllText(files.Result, Encoding.UTF8));
        }

        private static string BuildWrapper(ScriptFiles files)
        {
            return "#! python 3\n" +
                "ROOK_CODE_PATH = '" + EscapePythonString(files.Code) + "'\n" +
                "ROOK_RESULT_PATH = '" + EscapePythonString(files.Result) + "'\n" +
                ReadWrapperBody();
        }

        private static string ReadWrapperBody()
        {
            using (var stream = typeof(RevitTransactionService).Assembly
                .GetManifestResourceStream(WrapperResourceName))
            {
                if (stream == null)
                {
                    throw new InvalidOperationException(
                        "RookBim.dll is missing its embedded resource " + WrapperResourceName + ".");
                }

                using (var reader = new StreamReader(stream, Encoding.UTF8))
                {
                    return reader.ReadToEnd();
                }
            }
        }

        private static string EscapePythonString(string value)
        {
            return value.Replace("\\", "\\\\").Replace("'", "\\'");
        }

        /// <summary>Rolls back only a transaction that is still open. True when the document is unchanged.</summary>
        private static bool RollBack(Transaction? transaction)
        {
            if (transaction == null)
            {
                return true;
            }

            try
            {
                if (!transaction.HasStarted() || transaction.HasEnded())
                {
                    return transaction.GetStatus() != TransactionStatus.Committed;
                }

                return transaction.RollBack() == TransactionStatus.RolledBack;
            }
            catch
            {
                return false;
            }
        }

        private static bool IsCommitted(Transaction? transaction)
        {
            try
            {
                return transaction != null && transaction.GetStatus() == TransactionStatus.Committed;
            }
            catch
            {
                return false;
            }
        }

        private static string RollbackClause(bool rolledBack)
        {
            return rolledBack
                ? "rolled back; the Revit document is unchanged."
                : "not confirmed rolled back; check the Revit undo list and the document before continuing.";
        }

        private static BimApiResponse ScriptFailure(
            string name,
            BimTransactionScriptResult script,
            bool rolledBack)
        {
            var cause = script.PayloadPresent
                ? "The script raised " + script.Error + "."
                : script.Error;
            return Fail(
                BimErrorCode.TransactionScriptFailed,
                $"{cause} Transaction '{name}' was " + RollbackClause(rolledBack) +
                (script.PayloadPresent ? " Fix the script (see details.traceback) and call again." : string.Empty),
                422,
                name,
                rolledBack,
                script,
                null);
        }

        private static BimApiResponse Refuse(
            BimErrorCode code,
            string message,
            int httpStatus,
            string name,
            string status)
        {
            var response = BimApiResponse.Fail(code, message, httpStatus);
            response.Data = new
            {
                transaction = new
                {
                    name = name,
                    status = status
                },
                documentChanged = false
            };
            return response;
        }

        private static BimApiResponse Fail(
            BimErrorCode code,
            string message,
            int httpStatus,
            string name,
            bool rolledBack,
            BimTransactionScriptResult? script,
            CollectingFailuresPreprocessor? failures)
        {
            var response = BimApiResponse.Fail(code, message, httpStatus);
            response.Data = new
            {
                transaction = new
                {
                    name = name,
                    status = rolledBack ? "rolled_back" : "unknown"
                },
                // null means RookBIM could not confirm the rollback.
                documentChanged = rolledBack ? (bool?)false : null,
                stage = script?.Stage,
                error = script?.Error,
                traceback = script?.Traceback,
                output = script?.Output,
                outputTruncated = script?.OutputTruncated,
                stderr = script?.Stderr,
                stderrTruncated = script?.StderrTruncated,
                failures = failures?.Errors ?? new List<string>(),
                warnings = failures?.Warnings ?? new List<string>()
            };
            return response;
        }

        private sealed class ScriptFiles
        {
            private ScriptFiles(string code, string wrapper, string result)
            {
                Code = code;
                Wrapper = wrapper;
                Result = result;
            }

            public string Code { get; }

            public string Wrapper { get; }

            public string Result { get; }

            public static ScriptFiles Create()
            {
                var directory = Path.Combine(Path.GetTempPath(), "rook");
                Directory.CreateDirectory(directory);
                var stem = Path.Combine(
                    directory,
                    "bimtx_" + Process.GetCurrentProcess().Id + "_" +
                    Interlocked.Increment(ref scriptCounter));
                return new ScriptFiles(
                    stem + "_code.py",
                    stem + "_wrapper.py",
                    stem + "_result.json");
            }

            public void Delete()
            {
                foreach (var path in new[] { Code, Wrapper, Result })
                {
                    try
                    {
                        File.Delete(path);
                    }
                    catch
                    {
                    }
                }
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
                    // This runs after the commit. One element that cannot be
                    // described must not turn a committed change into an error.
                    try
                    {
                        var element = owner.GetElement(id);
                        if (element == null)
                        {
                            continue;
                        }

                        described.Add(new
                        {
                            // Same identity envelope rookbim_element_info and
                            // rookbim_select_elements accept.
                            identity = RevitDocumentIdentityResolver.ProjectElement(evidence, element),
                            name = SafeRead(() => element.Name),
                            category = SafeRead(() => element.Category?.Name),
                            className = element.GetType().Name
                        });
                    }
                    catch
                    {
                        described.Add(new
                        {
                            elementId = id.Value,
                            undescribed = true
                        });
                    }
                }

                return described;
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

            public FailureProcessingResult PreprocessFailures(FailuresAccessor failuresAccessor)
            {
                var hasError = false;
                foreach (var failure in failuresAccessor.GetFailureMessages())
                {
                    var text = failure.GetDescriptionText();
                    if (failure.GetSeverity() == FailureSeverity.Warning)
                    {
                        Warnings.Add(text);
                        failuresAccessor.DeleteWarning(failure);
                    }
                    else
                    {
                        Errors.Add(text);
                        hasError = true;
                    }
                }

                return hasError
                    ? FailureProcessingResult.ProceedWithRollBack
                    : FailureProcessingResult.Continue;
            }
        }
    }
}
