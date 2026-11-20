using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Events;
using Autodesk.Revit.UI;
using Rook.Bim;

namespace RookBim.Revit
{
    /// <summary>
    /// The only place in RookBIM that writes the Revit document. Runs one
    /// caller-supplied Python script inside one named transaction, on Revit's
    /// API thread, and commits only when the script ran to its end.
    ///
    /// What it guarantees is the fate of that one transaction on the active
    /// document. A script is trusted code with the whole Revit API: edits it
    /// makes to another document, or work it schedules for later, are outside
    /// this transaction and outside this guarantee.
    /// </summary>
    internal sealed class RevitTransactionService
    {
        internal const int MaxReportedElements = 100;
        internal const int MaxReportedFailures = 50;
        internal const int MaxFailureTextLength = 500;
        internal const long MaxResultFileBytes = 2 * 1024 * 1024;
        private const string WrapperResourceName = "RookBim.run_transaction_wrapper.py";
        private readonly Func<string, bool> runRhinoScript;

        public RevitTransactionService()
            : this(RunRhinoScriptForActiveDocument)
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
            BimTransactionCommitGate gate)
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

            gate.MarkPickedUp();

            if (evidence == null || !RevitDocumentIdentityResolver.IsSameDocument(document, evidence.Owner))
            {
                return BimApiResponse.Fail(
                    BimErrorCode.DocumentIdentityInvalid,
                    "Transaction document does not match the captured identity evidence.",
                    400);
            }

            var name = request.EffectiveName;
            var activeDocument = RevitDocumentIdentityResolver.ProjectDocument(evidence);
            if (request.HasDocumentKey &&
                !string.Equals(request.DocumentKey, activeDocument.DocumentKey, StringComparison.Ordinal))
            {
                // The caller read one document; a different one is active now.
                // Element ids repeat across documents, so writing here would
                // change the wrong model without any error.
                var mismatch = BimApiResponse.Fail(
                    BimErrorCode.DocumentMismatch,
                    $"The active Revit document is not the one this write was prepared for, so transaction '{name}' " +
                    "was not started and nothing changed. " +
                    $"Expected documentKey '{request.DocumentKey}'; the active document is '{activeDocument.Title}' " +
                    $"with documentKey '{activeDocument.DocumentKey ?? "unavailable"}'. " +
                    "Ask the user to switch back to the intended document, or read the elements again in the " +
                    "active document and call again with its documentKey.",
                    409);
                mismatch.Data = new
                {
                    transaction = new { name = name, status = "not_started" },
                    documentChanged = false,
                    expectedDocumentKey = request.DocumentKey,
                    document = activeDocument
                };
                return mismatch;
            }

            if (document.IsReadOnly)
            {
                return Refuse(
                    BimErrorCode.DocumentNotModifiable,
                    $"The active Revit document is read-only, so transaction '{name}' was not started and nothing changed. " +
                    "Open an editable copy of the model in Revit, then retry.",
                    name);
            }

            if (document.IsModifiable)
            {
                return Refuse(
                    BimErrorCode.DocumentNotModifiable,
                    $"Another transaction is already open in the active Revit document, so transaction '{name}' was not started and nothing changed. " +
                    "An active command or edit mode in Revit is the likely cause: finish or cancel it in Revit, then retry.",
                    name);
            }

            var changes = new ChangeCollector(document);
            var failures = new CollectingFailuresPreprocessor();
            var application = uiDocument.Application.Application;
            var subscribed = false;
            ScriptFiles? files = null;
            Transaction? transaction = null;
            try
            {
                files = ScriptFiles.Create();
                File.WriteAllText(files.Code, request.Code ?? string.Empty, new UTF8Encoding(false));
                File.WriteAllText(files.Wrapper, BuildWrapper(files), new UTF8Encoding(false));

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
                    return Refuse(
                        BimErrorCode.DocumentNotModifiable,
                        $"Revit refused to start transaction '{name}', so nothing changed: {ex.Message} " +
                        "Finish or cancel any active command in Revit, then retry.",
                        name);
                }

                if (started != TransactionStatus.Started)
                {
                    return Refuse(
                        BimErrorCode.DocumentNotModifiable,
                        $"Revit did not start transaction '{name}' (status {started}); nothing changed. " +
                        "Finish or cancel any active command in Revit, then retry.",
                        name);
                }

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
                    var settled = Settle(transaction);
                    return Fail(
                        BimErrorCode.TransactionTimeout,
                        "The caller stopped waiting before the script could start, so the script was not run. " +
                        $"Transaction '{name}' was " + SettledClause(settled),
                        504,
                        name,
                        settled,
                        null,
                        failures);
                }

                var script = RunScript(files);
                if (!script.Success)
                {
                    return ScriptFailure(name, script, Settle(transaction));
                }

                if (!gate.TryBeginCommit())
                {
                    // Either the caller was already told nothing would be
                    // committed, or the script ran past its budget. Both end
                    // the same way: no commit.
                    var settled = Settle(transaction);
                    var cause = gate.ScriptRanOverBudget
                        ? $"The script ran for {Seconds(gate.ScriptDuration)} s, longer than timeoutSeconds " +
                          $"({Seconds(gate.ScriptTimeout)}), so it was not committed."
                        : "The script finished after the caller stopped waiting, so it was not committed.";
                    return Fail(
                        BimErrorCode.TransactionTimeout,
                        $"{cause} Transaction '{name}' was " + SettledClause(settled) +
                        " Retry with a faster script or a larger timeoutSeconds.",
                        504,
                        name,
                        settled,
                        script,
                        failures);
                }

                var committed = transaction.Commit();
                if (committed == TransactionStatus.Committed)
                {
                    return Committed(name, document, evidence, changes, failures, script, activeDocument);
                }

                if (committed == TransactionStatus.RolledBack)
                {
                    var reasons = failures.Errors.Count > 0
                        ? " Revit reported: " + string.Join(" | ", failures.Errors)
                        : string.Empty;
                    return Fail(
                        BimErrorCode.TransactionRolledBack,
                        $"The script ran, but Revit refused to commit transaction '{name}' and rolled it back; " +
                        "the Revit document is unchanged." + reasons +
                        " Change the script so the model stays valid, then call again.",
                        409,
                        name,
                        "rolled_back",
                        script,
                        failures);
                }

                // Pending (Revit is still resolving failures and will finish
                // the commit or the rollback later) or any other status: the
                // outcome is not known here, and saying "rolled back" would
                // invite a duplicate edit.
                return Fail(
                    BimErrorCode.TransactionOutcomeUnknown,
                    $"Revit has not finished committing transaction '{name}' (status {committed}). It may still be " +
                    "committed or rolled back, for example after the user answers a Revit dialog. Do not run the " +
                    "script again. Call rookbim_status until Revit is idle, then read the model back " +
                    "(rookbim_query_elements or rookbim_element_parameters) to see whether the change is there.",
                    409,
                    name,
                    StatusName(committed),
                    script,
                    failures);
            }
            catch (Exception ex)
            {
                var settled = Settle(transaction);
                if (settled == "committed")
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
                        transaction = new { name = name, status = "committed" },
                        documentChanged = true
                    };
                    return committedResponse;
                }

                return Fail(
                    BimErrorCode.InternalError,
                    $"RookBIM failed while running transaction '{name}': {ex.GetType().Name}: {ex.Message}. The transaction was " +
                    SettledClause(settled),
                    500,
                    name,
                    settled,
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

                Settle(transaction);
                try
                {
                    transaction?.Dispose();
                }
                catch
                {
                }

                files?.Delete();
            }
        }

        private static bool RunRhinoScriptForActiveDocument(string command)
        {
            // The document-serial-number overload is the one POST /execute
            // uses from the native plug-in, where it runs the script to its
            // end before returning.
            var rhinoDocument = Rhino.RhinoDoc.ActiveDoc;
            return rhinoDocument != null
                ? Rhino.RhinoApp.RunScript(rhinoDocument.RuntimeSerialNumber, command, false)
                : Rhino.RhinoApp.RunScript(command, false);
        }

        private BimTransactionScriptResult RunScript(ScriptFiles files)
        {
            // Same engine as POST /execute: Rhino's RunPythonScript command.
            // The difference is the caller: this runs inside Revit's API
            // context with a transaction already open.
            var accepted = runRhinoScript("_-RunPythonScript \"" + files.Wrapper + "\"");
            if (!accepted)
            {
                // Never read a payload for a command Rhino did not accept.
                return BimTransactionScriptResult.Missing(
                    "Rhino refused to start the script command. A Rhino command is probably " +
                    "still running; finish or cancel it in the Rhino window, then retry.");
            }

            var result = new FileInfo(files.Result);
            if (!result.Exists)
            {
                return BimTransactionScriptResult.Missing(
                    "Rhino accepted the script command but the script had not reported a result when the " +
                    "command returned. It may have asked for interactive input, which a transaction script " +
                    "must not do, or Rhino did not run it to its end.");
            }

            if (result.Length > MaxResultFileBytes)
            {
                return BimTransactionScriptResult.Missing(
                    $"The script result payload was {result.Length} bytes; the limit is {MaxResultFileBytes}.");
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

        /// <summary>
        /// Brings the transaction to rest and names where it ended:
        /// not_started, rolled_back, committed, pending or unknown. A started
        /// transaction is rolled back; one Revit is still finalizing (pending)
        /// is left alone, because it cannot be rolled back from here.
        /// </summary>
        private static string Settle(Transaction? transaction)
        {
            if (transaction == null)
            {
                return "not_started";
            }

            try
            {
                var status = transaction.GetStatus();
                if (status == TransactionStatus.Started)
                {
                    status = transaction.RollBack();
                }

                return StatusName(status);
            }
            catch
            {
                return "unknown";
            }
        }

        private static string StatusName(TransactionStatus status)
        {
            switch (status)
            {
                case TransactionStatus.Uninitialized:
                    return "not_started";
                case TransactionStatus.RolledBack:
                    return "rolled_back";
                case TransactionStatus.Committed:
                    return "committed";
                case TransactionStatus.Pending:
                    return "pending";
                default:
                    return "unknown";
            }
        }

        private static string SettledClause(string settled)
        {
            switch (settled)
            {
                case "rolled_back":
                    return "rolled back; the Revit document is unchanged.";
                case "not_started":
                    return "never started; the Revit document is unchanged.";
                default:
                    return $"not confirmed rolled back (status {settled}); check the Revit undo list and read the " +
                        "model back before continuing.";
            }
        }

        private static bool? DocumentChangedFor(string settled)
        {
            switch (settled)
            {
                case "rolled_back":
                case "not_started":
                    return false;
                case "committed":
                    return true;
                default:
                    // null means RookBIM could not confirm either way.
                    return null;
            }
        }

        private static string Seconds(TimeSpan? value)
        {
            return value.HasValue
                ? value.Value.TotalSeconds.ToString("0.#", System.Globalization.CultureInfo.InvariantCulture)
                : "an unknown number of";
        }

        private static BimApiResponse Committed(
            string name,
            Document document,
            RevitDocumentIdentityEvidence evidence,
            ChangeCollector changes,
            CollectingFailuresPreprocessor failures,
            BimTransactionScriptResult script,
            BimDocumentIdentity activeDocument)
        {
            // Everything below runs after the commit and is optional detail.
            // It must never be able to turn the committed status into an error.
            object elements;
            string? elementsOmittedReason = null;
            try
            {
                elements = changes.Describe(document, evidence);
            }
            catch (Exception ex)
            {
                elements = changes.CountsOnly();
                elementsOmittedReason =
                    $"The changed elements could not be listed ({ex.GetType().Name}: {ex.Message}); only counts are given.";
            }

            return BimApiResponse.Ok(new
            {
                transaction = new
                {
                    name = name,
                    status = "committed"
                },
                changed = changes.Total > 0,
                elements = elements,
                elementsOmittedReason = elementsOmittedReason,
                warnings = failures.Warnings,
                warningsTruncated = failures.WarningsTruncated,
                output = script.Output,
                outputTruncated = script.OutputTruncated,
                stderr = script.Stderr,
                stderrTruncated = script.StderrTruncated,
                result = script.Result,
                resultOmittedReason = script.ResultOmittedReason,
                document = activeDocument
            });
        }

        private static BimApiResponse ScriptFailure(
            string name,
            BimTransactionScriptResult script,
            string settled)
        {
            var cause = script.PayloadPresent
                ? "The script raised " + script.Error + "."
                : script.Error;
            return Fail(
                BimErrorCode.TransactionScriptFailed,
                $"{cause} Transaction '{name}' was " + SettledClause(settled) +
                (script.PayloadPresent ? " Fix the script (see details.traceback) and call again." : string.Empty),
                422,
                name,
                settled,
                script,
                null);
        }

        /// <summary>A refusal issued before any transaction existed.</summary>
        private static BimApiResponse Refuse(
            BimErrorCode code,
            string message,
            string name)
        {
            var response = BimApiResponse.Fail(code, message, 409);
            response.Data = new
            {
                transaction = new
                {
                    name = name,
                    status = "not_started"
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
            string settled,
            BimTransactionScriptResult? script,
            CollectingFailuresPreprocessor? failures)
        {
            var response = BimApiResponse.Fail(code, message, httpStatus);
            response.Data = new
            {
                transaction = new
                {
                    name = name,
                    status = settled
                },
                documentChanged = DocumentChangedFor(settled),
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
                // A fresh GUID per call: a result file left behind by an
                // earlier call (or an earlier process with the same id) can
                // never be read as this call's payload.
                var stem = Path.Combine(
                    directory,
                    "bimtx_" + Process.GetCurrentProcess().Id + "_" + Guid.NewGuid().ToString("N"));
                var files = new ScriptFiles(
                    stem + "_code.py",
                    stem + "_wrapper.py",
                    stem + "_result.json");
                if (File.Exists(files.Result))
                {
                    File.Delete(files.Result);
                }

                return files;
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

                        described.Add(new
                        {
                            // The identity envelope rookbim_element_info and
                            // rookbim_select_elements take as input.
                            identity = RevitDocumentIdentityResolver.ProjectElement(evidence, element),
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

            public bool WarningsTruncated { get; private set; }

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
                            WarningsTruncated = true;
                        }

                        failuresAccessor.DeleteWarning(failure);
                    }
                    else
                    {
                        if (Errors.Count < MaxReportedFailures)
                        {
                            Errors.Add(text);
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
