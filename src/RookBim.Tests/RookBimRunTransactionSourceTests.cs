using System;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using System.Xml.Linq;
using Xunit;

namespace RookBim.Tests
{
    /// <summary>
    /// Source contracts for POST /bim/run-transaction, the only RookBIM route
    /// that writes the Revit document. RookBim.dll cannot be loaded without
    /// Revit, so these bind to the exact members that carry each guarantee.
    /// The commit gate and the payload parser are Revit-free and have real
    /// unit tests in Rook.Tests.
    /// </summary>
    public class RookBimRunTransactionSourceTests
    {
        private const string RuntimeType =
            "public sealed class RevitRookBimRuntime : IRookBimRuntime";
        private const string ServiceType =
            "internal sealed class RevitTransactionService";
        private const string RunSignature =
            "public BimApiResponse Run(UIDocument uiDocument, Document document, RevitDocumentIdentityEvidence evidence, BimRunTransactionRequest request, BimTransactionCommitGate gate)";
        private const string CommittedSignature =
            "private static BimApiResponse Committed(string name, Document document, RevitDocumentIdentityEvidence evidence, ChangeCollector changes, CollectingFailuresPreprocessor failures, BimTransactionScriptResult script, BimDocumentIdentity activeDocument)";
        private const string TransactionServiceFile = "RevitTransactionService.cs";
        private const string RuntimeFile = "RevitRookBimRuntime.cs";
        private static readonly string RepoRoot = FindRepoRoot();

        // The runtime only wires the operation. These are the Rook-owned names
        // it needs for that; nothing else containing "Transaction" may appear.
        private static readonly string[] RuntimeWiringIdentifiers =
        {
            "RevitTransactionService",
            "BimTransactionCommitGate",
            "BimTransactionCancelOutcome",
            "BimRunTransactionRequest",
            "RunTransaction",
            "DispatchTransaction",
            "TransactionIdleTimeout",
            "TransactionSetupAllowance",
            "TransactionCommitGrace",
            "TransactionTimeout",
            "TransactionOutcomeUnknown",
        };

        /// <summary>
        /// True when a source file other than the transaction service mentions
        /// Revit transactions. For every file but the runtime this is the old
        /// rule unchanged: the word "Transaction" may not appear at all.
        /// </summary>
        internal static bool MentionsTransactionsOutsideTheService(string fileName, string source)
        {
            if (string.Equals(fileName, TransactionServiceFile, StringComparison.Ordinal))
            {
                return false;
            }

            var remaining = source;
            if (string.Equals(fileName, RuntimeFile, StringComparison.Ordinal))
            {
                foreach (var identifier in RuntimeWiringIdentifiers.OrderByDescending(item => item.Length))
                {
                    remaining = Regex.Replace(
                        remaining,
                        @"(?<![A-Za-z0-9_])" + Regex.Escape(identifier) + @"(?![A-Za-z0-9_])",
                        string.Empty);
                }
            }

            return remaining.IndexOf("Transaction", StringComparison.Ordinal) >= 0;
        }

        internal static void AssertRevitWritesStayInTransactionService()
        {
            var revitDirectory = Path.Combine(RepoRoot, "src", "RookBim", "Revit");
            var files = Directory.GetFiles(revitDirectory, "*.cs", SearchOption.AllDirectories);
            Assert.Contains(files, path => Path.GetFileName(path) == TransactionServiceFile);
            Assert.Contains(files, path => Path.GetFileName(path) == RuntimeFile);

            foreach (var path in files)
            {
                Assert.False(
                    MentionsTransactionsOutsideTheService(Path.GetFileName(path), File.ReadAllText(path)),
                    Path.GetFileName(path) + " must not mention Revit transactions; document writes belong in " +
                    TransactionServiceFile + ".");
            }
        }

        [Fact]
        public void RevitWrites_AreConfinedToTheTransactionService()
        {
            AssertRevitWritesStayInTransactionService();
        }

        [Theory]
        [InlineData("RevitExportService.cs", "var t = new Transaction(document, \"x\");")]
        [InlineData("RevitExportService.cs", "Autodesk.Revit.DB.Transaction t = new(document, \"x\");")]
        [InlineData("RevitExportService.cs", "using (TransactionGroup group = Open()) { group.Assimilate(); }")]
        [InlineData("RevitQueryService.cs", "SubTransaction sub = Begin(); sub.Commit(options);")]
        [InlineData("RevitRookBimRuntime.cs", "var t = new Transaction(document, \"x\");")]
        [InlineData("RevitRookBimRuntime.cs", "Autodesk.Revit.DB.Transaction t = new(document, \"x\"); t.Commit(options);")]
        [InlineData("RevitRookBimRuntime.cs", "TransactionStatus status = other.Start();")]
        [InlineData("RevitRookBimRuntime.cs", "var gate = new BimTransactionCommitGate(timeout); var t = new MyRunTransactionHelper();")]
        public void WriteGuard_RejectsTransactionUseOutsideTheService(string fileName, string source)
        {
            Assert.True(MentionsTransactionsOutsideTheService(fileName, source));
        }

        [Theory]
        [InlineData("RevitRookBimRuntime.cs", "var gate = new BimTransactionCommitGate(timeout); return DispatchTransaction(diagnostics, callback, gate);")]
        [InlineData("RevitRookBimRuntime.cs", "BimErrorCode.TransactionTimeout; BimErrorCode.TransactionOutcomeUnknown; transactions.Run(a);")]
        [InlineData("RevitTransactionService.cs", "var t = new Transaction(document, name); t.Commit();")]
        [InlineData("RevitQueryService.cs", "var transactionless = true;")]
        public void WriteGuard_AllowsOnlyTheServiceAndTheRuntimeWiringNames(string fileName, string source)
        {
            Assert.False(MentionsTransactionsOutsideTheService(fileName, source));
        }

        [Fact]
        public void TransactionService_OpensExactlyOneNamedTransactionPerCall()
        {
            var service = Read("src/RookBim/Revit/RevitTransactionService.cs");
            var run = ExtractExecutableMember(service, ServiceType, RunSignature);

            Assert.Equal(1, CountOccurrences(service, "new Transaction("));
            Assert.Contains("transaction = new Transaction(document, name);", run);
            Assert.Contains("var name = request.EffectiveName;", run);
            // One Transaction, no group: one entry in Revit's undo list.
            Assert.DoesNotContain("TransactionGroup", service);
            Assert.DoesNotContain("SubTransaction", service);
            Assert.Equal(1, CountOccurrences(run, "transaction.Start()"));
            Assert.Equal(1, CountOccurrences(run, "transaction.Commit()"));
        }

        [Fact]
        public void TransactionService_RefusesBeforeStartingWhenTheDocumentIsWrongOrCannotBeModified()
        {
            var service = Read("src/RookBim/Revit/RevitTransactionService.cs");
            var run = ExtractExecutableMember(service, ServiceType, RunSignature);

            var documentKey = run.IndexOf("request.HasDocumentKey", StringComparison.Ordinal);
            var readOnly = run.IndexOf("document.IsReadOnly", StringComparison.Ordinal);
            var alreadyOpen = run.IndexOf("document.IsModifiable", StringComparison.Ordinal);
            var create = run.IndexOf("new Transaction(document, name)", StringComparison.Ordinal);

            Assert.True(documentKey >= 0 && documentKey < create);
            Assert.True(readOnly >= 0 && readOnly < create);
            Assert.True(alreadyOpen >= 0 && alreadyOpen < create);
            Assert.Contains("BimErrorCode.DocumentMismatch", run);
            Assert.Contains(
                "string.Equals(request.DocumentKey, activeDocument.DocumentKey, StringComparison.Ordinal)",
                run);
            Assert.Contains("BimErrorCode.DocumentNotModifiable", run);
            AssertSingleInvocationArguments(
                run,
                "RevitDocumentIdentityResolver.IsSameDocument",
                "document",
                "evidence.Owner");
        }

        [Fact]
        public void TransactionService_ReportsAStartThatRevitRefusesAsNotStarted()
        {
            var service = Read("src/RookBim/Revit/RevitTransactionService.cs");
            var run = ExtractExecutableMember(service, ServiceType, RunSignature);
            var refuse = ExtractExecutableMember(
                service,
                ServiceType,
                "private static BimApiResponse Refuse(BimErrorCode code, string message, string name)");

            var start = run.IndexOf("started = transaction.Start();", StringComparison.Ordinal);
            var startCatch = run.IndexOf(
                "catch (Autodesk.Revit.Exceptions.InvalidOperationException ex)",
                StringComparison.Ordinal);
            var statusCheck = run.IndexOf("if (started != TransactionStatus.Started)", StringComparison.Ordinal);
            Assert.True(start >= 0 && start < startCatch && startCatch < statusCheck);
            // The refusal is built by Refuse, which always says not_started.
            Assert.Contains("documentChanged = false", refuse);
            Assert.Contains("BimApiResponse.Fail(code, message, 409)", refuse);
            Assert.Contains("\"not_started\"", service);
        }

        [Fact]
        public void TransactionService_AppliesFailureHandlingAfterStartBecauseStartResetsIt()
        {
            var service = Read("src/RookBim/Revit/RevitTransactionService.cs");
            var run = ExtractExecutableMember(service, ServiceType, RunSignature);
            var preprocess = ExtractExecutableMember(
                service,
                "private sealed class CollectingFailuresPreprocessor : IFailuresPreprocessor",
                "public FailureProcessingResult PreprocessFailures(FailuresAccessor failuresAccessor)");

            var start = run.IndexOf("transaction.Start()", StringComparison.Ordinal);
            var getOptions = run.IndexOf("transaction.GetFailureHandlingOptions()", StringComparison.Ordinal);
            var setOptions = run.IndexOf("transaction.SetFailureHandlingOptions(options);", StringComparison.Ordinal);
            var enter = run.IndexOf("gate.TryEnterScript()", StringComparison.Ordinal);
            var script = run.IndexOf("RunScript(files)", StringComparison.Ordinal);

            // Revit's Transaction.Start() resets failure handling options to
            // their defaults, so options set before it are discarded.
            Assert.True(start >= 0 && start < getOptions, "Failure handling options must be read after Start().");
            Assert.True(getOptions < setOptions, "Failure handling options must be applied after Start().");
            Assert.True(setOptions < enter && enter < script, "Options must be in place before the script runs.");
            Assert.Equal(1, CountOccurrences(run, "transaction.SetFailureHandlingOptions(options);"));

            Assert.Contains("options.SetFailuresPreprocessor(failures);", run);
            // Forced modal handling keeps Commit() synchronous; with it off a
            // commit can come back Pending behind a modeless dialog.
            Assert.Contains("options.SetForcedModalHandling(true);", run);
            Assert.DoesNotContain("SetForcedModalHandling(false)", run);
            Assert.Contains("options.SetClearAfterRollback(true);", run);

            Assert.Contains("failuresAccessor.DeleteWarning(failure);", preprocess);
            Assert.Contains("Warnings.Add(text);", preprocess);
            Assert.Contains("Errors.Add(text);", preprocess);
            Assert.Contains("FailureProcessingResult.ProceedWithRollBack", preprocess);
            Assert.Contains("FailureProcessingResult.Continue", preprocess);
        }

        [Fact]
        public void TransactionService_AsksTheGateBeforeTheScriptAndBeforeTheCommit()
        {
            var service = Read("src/RookBim/Revit/RevitTransactionService.cs");
            var run = ExtractExecutableMember(service, ServiceType, RunSignature);

            var pickedUp = run.IndexOf("gate.MarkPickedUp();", StringComparison.Ordinal);
            var firstCheck = run.IndexOf("RevitDocumentIdentityResolver.IsSameDocument", StringComparison.Ordinal);
            var enter = run.IndexOf("if (!gate.TryEnterScript())", StringComparison.Ordinal);
            var script = run.IndexOf("var script = RunScript(files);", StringComparison.Ordinal);
            var beginCommit = run.IndexOf("if (!gate.TryBeginCommit())", StringComparison.Ordinal);
            var commit = run.IndexOf("transaction.Commit()", StringComparison.Ordinal);

            Assert.True(pickedUp >= 0 && pickedUp < firstCheck);
            // A caller who already stopped waiting must not have its script started.
            Assert.True(enter >= 0 && enter < script, "The gate must be asked immediately before the script runs.");
            Assert.True(script < beginCommit && beginCommit < commit, "The gate must be asked immediately before the commit.");
            Assert.Equal(1, CountOccurrences(run, "RunScript(files)"));
            Assert.Contains("gate.ScriptRanOverBudget", run);
        }

        [Fact]
        public void TransactionService_RollsBackOnScriptFailureAndNeverCommitsIt()
        {
            var service = Read("src/RookBim/Revit/RevitTransactionService.cs");
            var run = ExtractExecutableMember(service, ServiceType, RunSignature);

            var script = run.IndexOf("var script = RunScript(files);", StringComparison.Ordinal);
            var failureCheck = run.IndexOf("if (!script.Success)", StringComparison.Ordinal);
            var failureReturn = run.IndexOf(
                "return ScriptFailure(name, script, Settle(transaction));",
                StringComparison.Ordinal);
            var beginCommit = run.IndexOf("gate.TryBeginCommit()", StringComparison.Ordinal);
            var commit = run.IndexOf("transaction.Commit()", StringComparison.Ordinal);

            Assert.True(script >= 0 && script < failureCheck && failureCheck < failureReturn);
            Assert.True(
                failureReturn < beginCommit && beginCommit < commit,
                "A failed script must return before the commit gate and the commit.");

            var scriptFailure = ExtractExecutableMember(
                service,
                ServiceType,
                "private static BimApiResponse ScriptFailure(string name, BimTransactionScriptResult script, string settled)");
            Assert.Contains("BimErrorCode.TransactionScriptFailed", scriptFailure);
            Assert.Contains("SettledClause(settled)", scriptFailure);
        }

        [Fact]
        public void TransactionService_SettleRollsBackOnlyAStartedTransactionAndNamesWhereItEnded()
        {
            var service = Read("src/RookBim/Revit/RevitTransactionService.cs");
            var settle = ExtractExecutableMember(
                service,
                ServiceType,
                "private static string Settle(Transaction? transaction)");
            var statusName = ExtractExecutableMember(
                service,
                ServiceType,
                "private static string StatusName(TransactionStatus status)");
            var changedFor = ExtractExecutableMember(
                service,
                ServiceType,
                "private static bool? DocumentChangedFor(string settled)");

            Assert.Contains("if (status == TransactionStatus.Started)", settle);
            Assert.Contains("status = transaction.RollBack();", settle);
            Assert.Contains("return StatusName(status);", settle);
            Assert.Equal(1, CountOccurrences(service, "transaction.RollBack()"));

            Assert.Contains("case TransactionStatus.Uninitialized:", statusName);
            Assert.Contains("case TransactionStatus.RolledBack:", statusName);
            Assert.Contains("case TransactionStatus.Committed:", statusName);
            Assert.Contains("case TransactionStatus.Pending:", statusName);

            // Only a confirmed end state may claim the document is unchanged.
            Assert.Contains("return false;", changedFor);
            Assert.Contains("return true;", changedFor);
            Assert.Contains("return null;", changedFor);
        }

        [Fact]
        public void TransactionService_RollsBackOnAnyExceptionAndInFinally()
        {
            var service = Read("src/RookBim/Revit/RevitTransactionService.cs");
            var run = ExtractExecutableMember(service, ServiceType, RunSignature);

            var catchIndex = run.IndexOf("catch (Exception ex)", StringComparison.Ordinal);
            var finallyIndex = run.IndexOf("finally", StringComparison.Ordinal);
            Assert.True(catchIndex >= 0 && finallyIndex > catchIndex);

            var catchBlock = run.Substring(catchIndex, finallyIndex - catchIndex);
            var finallyBlock = run.Substring(finallyIndex);
            // A failure after the commit must be reported as committed, never as rolled back.
            var settle = catchBlock.IndexOf("var settled = Settle(transaction);", StringComparison.Ordinal);
            var committedCheck = catchBlock.IndexOf("if (settled ==", StringComparison.Ordinal);
            Assert.True(settle >= 0 && settle < committedCheck);
            Assert.Contains("documentChanged = true", catchBlock);
            Assert.Contains("BimErrorCode.InternalError", catchBlock);
            Assert.Contains("SettledClause(settled)", catchBlock);
            Assert.Contains("Settle(transaction);", finallyBlock);
            Assert.Contains("application.DocumentChanged -= changes.OnDocumentChanged;", finallyBlock);
            Assert.Contains("files?.Delete();", finallyBlock);
        }

        [Fact]
        public void TransactionService_TellsCommittedRolledBackAndPendingApart()
        {
            var service = Read("src/RookBim/Revit/RevitTransactionService.cs");
            var run = ExtractExecutableMember(service, ServiceType, RunSignature);
            var committedHelper = ExtractExecutableMember(service, ServiceType, CommittedSignature);

            var commit = run.IndexOf("var committed = transaction.Commit();", StringComparison.Ordinal);
            var isCommitted = run.IndexOf("if (committed == TransactionStatus.Committed)", StringComparison.Ordinal);
            var isRolledBack = run.IndexOf("if (committed == TransactionStatus.RolledBack)", StringComparison.Ordinal);
            var rolledBackCode = run.IndexOf("BimErrorCode.TransactionRolledBack", StringComparison.Ordinal);
            var unknownCode = run.IndexOf("BimErrorCode.TransactionOutcomeUnknown", StringComparison.Ordinal);

            Assert.True(commit >= 0 && commit < isCommitted && isCommitted < isRolledBack);
            Assert.True(isRolledBack < rolledBackCode && rolledBackCode < unknownCode);
            // "Unchanged" is claimed only inside the RolledBack branch; a
            // Pending commit may still finish, so its branch reports the
            // actual status and forbids a rerun.
            var unknownBranch = run.Substring(unknownCode);
            Assert.Contains("StatusName(committed)", unknownBranch);
            Assert.Equal(1, CountOccurrences(run, "BimErrorCode.TransactionRolledBack"));

            // Success is reported only from the Committed branch.
            Assert.Equal(0, CountOccurrences(run, "BimApiResponse.Ok("));
            Assert.Equal(1, CountOccurrences(run, "return Committed("));
            Assert.Equal(1, CountOccurrences(committedHelper, "BimApiResponse.Ok("));
            Assert.Equal(1, CountOccurrences(service, "BimApiResponse.Ok("));
        }

        [Fact]
        public void TransactionService_OptionalReportingCannotUndoACommittedStatus()
        {
            var service = Read("src/RookBim/Revit/RevitTransactionService.cs");
            var committedHelper = ExtractExecutableMember(service, ServiceType, CommittedSignature);
            var describeLive = ExtractExecutableMember(
                service,
                "private sealed class ChangeCollector",
                "private static List<object> DescribeLive(Document owner, RevitDocumentIdentityEvidence evidence, List<ElementId> ids)");

            var describe = committedHelper.IndexOf("elements = changes.Describe(document, evidence);", StringComparison.Ordinal);
            var describeCatch = committedHelper.IndexOf("catch (Exception ex)", StringComparison.Ordinal);
            var countsOnly = committedHelper.IndexOf("elements = changes.CountsOnly();", StringComparison.Ordinal);
            Assert.True(describe >= 0 && describe < describeCatch && describeCatch < countsOnly);
            Assert.Contains("elementsOmittedReason", committedHelper);

            // Every reported id either carries an identity or says why not.
            Assert.Contains("RevitDocumentIdentityResolver.ProjectElement(evidence, element)", describeLive);
            Assert.Contains("ids.Take(MaxReportedElements)", describeLive);
            Assert.Equal(2, CountOccurrences(describeLive, "described.Add(Undescribed("));
            Assert.Contains("identityOmittedReason = reason", service);
        }

        [Fact]
        public void TransactionService_ReportsChangedElementsFromRevitNotFromTheScript()
        {
            var service = Read("src/RookBim/Revit/RevitTransactionService.cs");
            var run = ExtractExecutableMember(service, ServiceType, RunSignature);
            var onChanged = ExtractExecutableMember(
                service,
                "private sealed class ChangeCollector",
                "public void OnDocumentChanged(object? sender, DocumentChangedEventArgs args)");

            Assert.Contains("application.DocumentChanged += changes.OnDocumentChanged;", run);
            Assert.True(
                run.IndexOf("application.DocumentChanged += changes.OnDocumentChanged;", StringComparison.Ordinal) <
                run.IndexOf("transaction.Start()", StringComparison.Ordinal));

            Assert.Contains("args.GetAddedElementIds()", onChanged);
            Assert.Contains("args.GetModifiedElementIds()", onChanged);
            Assert.Contains("args.GetDeletedElementIds()", onChanged);
            AssertSingleInvocationArguments(
                onChanged,
                "RevitDocumentIdentityResolver.IsSameDocument",
                "args.GetDocument()",
                "document");
        }

        [Fact]
        public void TransactionService_TrustsOnlyAPayloadFromAnAcceptedFreshInvocation()
        {
            var service = Read("src/RookBim/Revit/RevitTransactionService.cs");
            var runScript = ExtractExecutableMember(
                service,
                ServiceType,
                "private BimTransactionScriptResult RunScript(ScriptFiles files)");
            var create = ExtractExecutableMember(
                service,
                "private sealed class ScriptFiles",
                "public static ScriptFiles Create()");
            var rhino = ExtractExecutableMember(
                service,
                ServiceType,
                "private static bool RunRhinoScriptForActiveDocument(string command)");

            var accepted = runScript.IndexOf("var accepted = runRhinoScript(", StringComparison.Ordinal);
            var refused = runScript.IndexOf("if (!accepted)", StringComparison.Ordinal);
            var exists = runScript.IndexOf("if (!result.Exists)", StringComparison.Ordinal);
            var size = runScript.IndexOf("if (result.Length > MaxResultFileBytes)", StringComparison.Ordinal);
            var parse = runScript.IndexOf("BimTransactionScriptResult.Parse(", StringComparison.Ordinal);

            // A command Rhino refused can never have produced this call's payload.
            Assert.True(accepted >= 0 && accepted < refused && refused < exists);
            Assert.True(exists < size && size < parse, "The payload size must be bounded before it is read.");
            Assert.Equal(3, CountOccurrences(runScript, "BimTransactionScriptResult.Missing("));

            // Fresh names per call, so a leftover file is never this call's result.
            Assert.Contains("Guid.NewGuid()", create);
            Assert.Contains("File.Delete(files.Result);", create);

            // The same RunScript overload the native POST /execute route uses.
            Assert.Contains("rhinoDocument.RuntimeSerialNumber", rhino);
        }

        [Fact]
        public void TransactionService_BuildsTheWrapperFromTheEmbeddedBody()
        {
            var service = Read("src/RookBim/Revit/RevitTransactionService.cs");
            var buildWrapper = ExtractExecutableMember(
                service,
                ServiceType,
                "private static string BuildWrapper(ScriptFiles files)");
            var project = XDocument.Parse(Read("src/RookBim/RookBim.csproj"));
            var resource = project.Descendants("EmbeddedResource").Single();

            Assert.Contains("ReadWrapperBody()", buildWrapper);
            Assert.Contains("EscapePythonString(files.Code)", buildWrapper);
            Assert.Contains("EscapePythonString(files.Result)", buildWrapper);
            Assert.Contains("\"RookBim.run_transaction_wrapper.py\"", service);
            Assert.Equal(
                "Revit/Scripts/run_transaction_wrapper.py",
                resource.Attribute("Include")!.Value.Replace('\\', '/'));
            Assert.Equal(
                "RookBim.run_transaction_wrapper.py",
                resource.Attribute("LogicalName")!.Value);
            Assert.True(File.Exists(Path.Combine(
                RepoRoot, "src", "RookBim", "Revit", "Scripts", "run_transaction_wrapper.py")));
        }

        [Fact]
        public void Wrapper_NeverTouchesTheTransactionItselfAndAgreesWithTheParsersLimits()
        {
            var wrapper = Read("src/RookBim/Revit/Scripts/run_transaction_wrapper.py");
            var parser = Read("src/Rook/Bim/BimTransactionScriptResult.cs");
            var code = string.Join(
                "\n",
                wrapper
                    .Replace("\r\n", "\n")
                    .Split('\n')
                    .Where(line => !line.TrimStart().StartsWith("#", StringComparison.Ordinal)));

            Assert.DoesNotContain("Transaction", code);
            Assert.DoesNotContain("EnqueueIdlingAction", code);
            Assert.DoesNotContain(".Commit(", code);
            Assert.DoesNotContain(".RollBack(", code);
            Assert.Contains("ROOK_CODE_PATH", code);
            Assert.Contains("ROOK_RESULT_PATH", code);
            Assert.Contains("except BaseException", code);
            // No silent str() fallback for values JSON cannot carry.
            Assert.DoesNotContain("default=str", code);

            // The producer and the parser must agree on every bound.
            Assert.Contains("_ROOK_STREAM_LIMIT = 20000", code);
            Assert.Contains("public const int MaxStreamLength = 20000;", parser);
            Assert.Contains("_ROOK_RESULT_LIMIT = 50000", code);
            Assert.Contains("public const int MaxResultJsonLength = 50000;", parser);
            Assert.Contains("_ROOK_TRACEBACK_LIMIT = 20000", code);
            Assert.Contains("public const int MaxTracebackLength = 20000;", parser);
            Assert.Contains("_ROOK_ERROR_LIMIT = 2000", code);
            Assert.Contains("public const int MaxErrorLength = 2000;", parser);
            Assert.Contains("public const string DoneStage = \"done\";", parser);
            Assert.Contains("_rook_payload[\"stage\"] = \"done\"", code);
        }

        [Fact]
        public void Runtime_WiresRunTransactionThroughTheDocumentBoundaryWithOneGate()
        {
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");
            var run = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "public BimApiResponse RunTransaction(BimDiagnosticContext diagnostics, BimRunTransactionRequest request)");

            Assert.Contains("request.Validate()", run);
            Assert.True(
                run.IndexOf("request.Validate()", StringComparison.Ordinal) <
                run.IndexOf("ExecuteInDocumentContext", StringComparison.Ordinal),
                "An invalid request must be refused before the Revit API context is entered.");
            Assert.Equal(1, CountOccurrences(run, "new BimTransactionCommitGate("));
            Assert.Contains("TimeSpan.FromSeconds(request.EffectiveTimeoutSeconds)", run);
            AssertSingleInvocationArguments(
                run,
                "transactions.Run",
                "uidoc",
                "document",
                "evidence",
                "request",
                "gate");
        }

        [Fact]
        public void Runtime_TransactionDispatchSeparatesEveryWayAWaitCanEnd()
        {
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");
            var dispatch = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "private BimApiResponse DispatchTransaction(BimDiagnosticContext diagnostics, Func<UIApplication, BimApiResponse> work, BimTransactionCommitGate gate)");

            var idleWait = dispatch.IndexOf("new Task[] { dispatch.Task, gate.PickedUp }", StringComparison.Ordinal);
            var abandon = dispatch.IndexOf("if (first < 0 && dispatch.Abandon())", StringComparison.Ordinal);
            var notIdle = dispatch.IndexOf(
                "throw new RevitDispatchTimeoutException(false, TransactionIdleTimeout);",
                StringComparison.Ordinal);
            var runWait = dispatch.IndexOf(
                "var runWait = gate.ScriptTimeout + TransactionSetupAllowance;",
                StringComparison.Ordinal);
            var cancel = dispatch.IndexOf("switch (gate.Cancel())", StringComparison.Ordinal);
            var beforeScript = dispatch.IndexOf("case BimTransactionCancelOutcome.BeforeScript:", StringComparison.Ordinal);
            var duringScript = dispatch.IndexOf("case BimTransactionCancelOutcome.DuringScript:", StringComparison.Ordinal);
            var graceWait = dispatch.IndexOf("TransactionCommitGrace) >= 0", StringComparison.Ordinal);
            var unknown = dispatch.IndexOf("BimErrorCode.TransactionOutcomeUnknown", StringComparison.Ordinal);

            Assert.True(idleWait >= 0 && idleWait < abandon && abandon < notIdle);
            Assert.True(notIdle < runWait && runWait < cancel);
            Assert.True(cancel < beforeScript && beforeScript < duringScript);
            Assert.True(duringScript < graceWait && graceWait < unknown);
            // "Never committed" is only said for a cancellation the gate
            // confirmed; an unconfirmed outcome has its own code.
            Assert.Equal(2, CountOccurrences(dispatch, "BimErrorCode.TransactionTimeout"));
            Assert.Equal(1, CountOccurrences(dispatch, "BimErrorCode.TransactionOutcomeUnknown"));
            Assert.DoesNotContain("NotRhinoInside", dispatch);

            // The wait budget must fit under the 120 s client read timeout.
            Assert.Contains("TransactionIdleTimeout = TimeSpan.FromSeconds(10);", runtime);
            Assert.Contains("TransactionSetupAllowance = TimeSpan.FromSeconds(2);", runtime);
            Assert.Contains("TransactionCommitGrace = TimeSpan.FromSeconds(10);", runtime);
        }

        [Fact]
        public void Runtime_IdleTimeoutIsReportedAsRevitNotIdleNotAsMissingHost()
        {
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");
            var execute = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "private BimApiResponse ExecuteInDocumentContext(BimDiagnosticContext diagnostics, string operation, Func<UIDocument, Document, RevitDocumentIdentityEvidence, BimApiResponse> work, TimeSpan? timeout = null, BimTransactionCommitGate? transactionGate = null)");
            var status = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "public BimStatusResponse Status(BimDiagnosticContext diagnostics)");
            var dispatch = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "private T Dispatch<T>(BimDiagnosticContext diagnostics, Func<UIApplication, T> work)");
            var exception = Read("src/RookBim/Revit/RevitDispatchTimeoutException.cs");

            var timeoutCatch = execute.IndexOf("catch (RevitDispatchTimeoutException ex)", StringComparison.Ordinal);
            var genericCatch = execute.IndexOf("catch (Exception ex)", timeoutCatch + 1, StringComparison.Ordinal);
            Assert.True(timeoutCatch >= 0 && genericCatch > timeoutCatch);
            var timeoutBlock = execute.Substring(timeoutCatch, genericCatch - timeoutCatch);
            Assert.Contains(
                "ex.WorkStarted ? BimErrorCode.RevitOperationTimeout : BimErrorCode.RevitNotIdle",
                timeoutBlock);
            Assert.Contains("DescribeDispatchTimeout(ex, operation)", timeoutBlock);
            Assert.DoesNotContain("NotRhinoInside", timeoutBlock);

            var statusTimeoutCatch = status.IndexOf("catch (RevitDispatchTimeoutException ex)", StringComparison.Ordinal);
            var statusGenericCatch = status.IndexOf("catch (Exception ex)", statusTimeoutCatch + 1, StringComparison.Ordinal);
            Assert.True(statusTimeoutCatch >= 0 && statusGenericCatch > statusTimeoutCatch);
            Assert.DoesNotContain(
                "not_rhino_inside",
                status.Substring(statusTimeoutCatch, statusGenericCatch - statusTimeoutCatch));

            Assert.Contains("var neverStarted = dispatch.Abandon();", dispatch);
            Assert.Contains(
                "throw new RevitDispatchTimeoutException(!neverStarted, DispatchTimeout);",
                dispatch);
            Assert.Contains("internal sealed class RevitDispatchTimeoutException : TimeoutException", exception);

            // The message is in string literals, so read the raw source for it.
            Assert.Contains("Revit did not become idle within", runtime);
            Assert.Contains("an open dialog or an active command in Revit", runtime);
            Assert.Contains("nothing was read or changed", runtime);
        }

        [Fact]
        public void Runtime_AFailureReadingTheActiveDocumentInsideRevitIsNotBlamedOnTheHost()
        {
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");
            var execute = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "private BimApiResponse ExecuteInDocumentContext(BimDiagnosticContext diagnostics, string operation, Func<UIDocument, Document, RevitDocumentIdentityEvidence, BimApiResponse> work, TimeSpan? timeout = null, BimTransactionCommitGate? transactionGate = null)");

            // Acquisition and identity capture run inside Revit's API context;
            // they are handled there and never reach the host-entry catch.
            var acquire = execute.IndexOf("AcquireActiveUiDocument(uiapp, diagnostics)", StringComparison.Ordinal);
            var capture = execute.IndexOf("RevitDocumentIdentityResolver.Capture(", StringComparison.Ordinal);
            var acquisitionCatch = execute.IndexOf("catch (Exception ex)", StringComparison.Ordinal);
            var work = execute.IndexOf("work(uidoc, document, evidence)", StringComparison.Ordinal);
            var hostCode = execute.IndexOf("BimErrorCode.NotRhinoInside", StringComparison.Ordinal);

            Assert.True(acquire >= 0 && acquire < capture && capture < acquisitionCatch);
            Assert.True(acquisitionCatch < work && work < hostCode);
            var acquisitionBlock = execute.Substring(acquisitionCatch, work - acquisitionCatch);
            Assert.Contains("BimErrorCode.InternalError", acquisitionBlock);
            Assert.DoesNotContain("NotRhinoInside", acquisitionBlock);
            Assert.Contains("could not read the active Revit document", runtime);
        }

        private static int CountOccurrences(string source, string value)
        {
            var count = 0;
            var index = 0;
            while ((index = source.IndexOf(value, index, StringComparison.Ordinal)) >= 0)
            {
                count++;
                index += value.Length;
            }

            return count;
        }

        private static string ExtractExecutableMember(
            string source,
            string typeDeclaration,
            string memberDeclaration)
        {
            return RookBimModuleSourceTests.ExtractExecutableMember(
                source,
                typeDeclaration,
                memberDeclaration);
        }

        private static void AssertSingleInvocationArguments(
            string source,
            string invocationTarget,
            params string[] expectedArguments)
        {
            RookBimModuleSourceTests.AssertSingleInvocationArguments(
                source,
                invocationTarget,
                expectedArguments);
        }

        private static string Read(string relativePath)
        {
            return File.ReadAllText(Path.Combine(RepoRoot, relativePath.Replace('/', Path.DirectorySeparatorChar)));
        }

        private static string FindRepoRoot()
        {
            var directory = new DirectoryInfo(AppContext.BaseDirectory);
            while (directory != null)
            {
                if (File.Exists(Path.Combine(directory.FullName, "Rook.sln")))
                {
                    return directory.FullName;
                }

                directory = directory.Parent;
            }

            throw new InvalidOperationException("Could not find repository root.");
        }
    }
}
