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
    ///
    /// The parts that decide what a caller is told (the receipt, the report
    /// built from it, the commit gate, the script result) are Revit-free and
    /// have real unit tests in Rook.Tests. The script wrapper has behavioural
    /// tests in mcp_server/tests. What remains here is the wiring between
    /// those parts and the Revit API.
    /// </summary>
    public class RookBimRunTransactionSourceTests
    {
        private const string RuntimeType =
            "public sealed class RevitRookBimRuntime : IRookBimRuntime";
        private const string ServiceType =
            "internal sealed class RevitTransactionService";
        private const string RunSignature =
            "public BimApiResponse Run(UIDocument uiDocument, Document document, RevitDocumentIdentityEvidence evidence, BimRunTransactionRequest request, BimTransactionCall call)";
        private const string ExecutorSignature =
            "private IDictionary<string, object?>? Execute(UIDocument uiDocument, Document document, RevitDocumentIdentityEvidence evidence, BimRunTransactionRequest request, BimTransactionCall call)";
        private const string ExecuteSignature =
            "private BimApiResponse ExecuteInDocumentContext(BimDiagnosticContext diagnostics, string operation, Func<UIDocument, Document, RevitDocumentIdentityEvidence, BimApiResponse> work, TimeSpan? timeout = null, BimTransactionCall? transactionCall = null)";
        private const string TransactionServiceFile = "RevitTransactionService.cs";
        private const string RuntimeFile = "RevitRookBimRuntime.cs";
        private static readonly string RepoRoot = FindRepoRoot();

        // The runtime only wires the operation. These are the Rook-owned names
        // it needs for that; nothing else containing "Transaction" may appear.
        private static readonly string[] RuntimeWiringIdentifiers =
        {
            "RevitTransactionService",
            "BimTransactionCall",
            "BimTransactionCancelOutcome",
            "BimTransactionReport",
            "BimRunTransactionRequest",
            "RunTransaction",
            "DispatchTransaction",
            "TransactionSetupTimeout",
            "TransactionCommitGrace",
            "TransactionTimeout",
        };

        /// <summary>
        /// True when a source file other than the transaction service mentions
        /// Revit transactions. <paramref name="relativePath"/> is relative to
        /// src/RookBim/Revit with forward slashes, so a file of the same name
        /// in a subfolder is not exempt. For every file but the runtime this
        /// is the old rule unchanged: the word "Transaction" may not appear.
        /// </summary>
        internal static bool MentionsTransactionsOutsideTheService(string relativePath, string source)
        {
            if (string.Equals(relativePath, TransactionServiceFile, StringComparison.Ordinal))
            {
                return false;
            }

            var remaining = source;
            if (string.Equals(relativePath, RuntimeFile, StringComparison.Ordinal))
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
            var relative = files
                .Select(path => path.Substring(revitDirectory.Length).TrimStart('\\', '/').Replace('\\', '/'))
                .ToArray();
            Assert.Contains(TransactionServiceFile, relative);
            Assert.Contains(RuntimeFile, relative);

            for (var index = 0; index < files.Length; index++)
            {
                Assert.False(
                    MentionsTransactionsOutsideTheService(relative[index], File.ReadAllText(files[index])),
                    relative[index] + " must not mention Revit transactions; document writes belong in " +
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
        [InlineData("RevitPythonScriptRunner.cs", "var t = new Transaction(document, \"x\");")]
        [InlineData("RevitScriptChannel.cs", "public Transaction Open { get; }")]
        [InlineData("RevitRookBimRuntime.cs", "var t = new Transaction(document, \"x\");")]
        [InlineData("RevitRookBimRuntime.cs", "Autodesk.Revit.DB.Transaction t = new(document, \"x\"); t.Commit(options);")]
        [InlineData("RevitRookBimRuntime.cs", "TransactionStatus status = other.Start();")]
        [InlineData("RevitRookBimRuntime.cs", "var call = BimTransactionCall.Begin(n, t); var x = new MyRunTransactionHelper();")]
        // The exemptions are for two exact paths, not for a file name anywhere.
        [InlineData("Other/RevitTransactionService.cs", "var t = new Transaction(document, \"x\");")]
        [InlineData("Other/RevitRookBimRuntime.cs", "return DispatchTransaction(diagnostics, callback, call);")]
        public void WriteGuard_RejectsTransactionUseOutsideTheService(string relativePath, string source)
        {
            Assert.True(MentionsTransactionsOutsideTheService(relativePath, source));
        }

        [Theory]
        [InlineData("RevitRookBimRuntime.cs", "var call = BimTransactionCall.Begin(n, t); return DispatchTransaction(diagnostics, callback, call);")]
        [InlineData("RevitRookBimRuntime.cs", "BimErrorCode.TransactionTimeout; BimTransactionReport.Build(s); transactions.Run(a);")]
        [InlineData("RevitTransactionService.cs", "var t = new Transaction(document, name); t.Commit();")]
        [InlineData("RevitQueryService.cs", "var transactionless = true;")]
        public void WriteGuard_AllowsOnlyTheServiceAndTheRuntimeWiringNames(string relativePath, string source)
        {
            Assert.False(MentionsTransactionsOutsideTheService(relativePath, source));
        }

        // ---- the executor owns one transaction --------------------------------

        [Fact]
        public void Executor_OpensExactlyOneNamedTransactionPerCall()
        {
            var service = Read("src/RookBim/Revit/RevitTransactionService.cs");
            var run = ExtractExecutableMember(service, ServiceType, ExecutorSignature);

            Assert.Equal(1, CountOccurrences(service, "new Transaction("));
            Assert.Contains("transaction = new Transaction(document, name);", run);
            Assert.Contains("var name = request.EffectiveName;", run);
            // One Transaction, no group: one entry in Revit's undo list.
            Assert.DoesNotContain("TransactionGroup", service);
            Assert.DoesNotContain("SubTransaction", service);
            Assert.Equal(1, CountOccurrences(run, "transaction.Start()"));
            Assert.Equal(1, CountOccurrences(run, "transaction.Commit()"));
            Assert.Equal(1, CountOccurrences(service, "transaction.RollBack()"));
        }

        [Fact]
        public void Executor_GivesOneAnswerBuiltFromTheReceiptAfterItsLastObservation()
        {
            var service = Read("src/RookBim/Revit/RevitTransactionService.cs");
            var wrapper = ExtractExecutableMember(service, ServiceType, RunSignature);
            var execute = ExtractExecutableMember(service, ServiceType, ExecutorSignature);

            // The work records observations and returns optional details only.
            // It cannot say how the call ended.
            Assert.DoesNotContain("BimTransactionReport", execute);
            Assert.DoesNotContain("BimApiResponse", execute);

            // One answer for the whole service, built in the wrapper from the
            // receipt, after the work (including its finally) is over and the
            // receipt has been closed to further change.
            Assert.Equal(1, CountOccurrences(service, "BimTransactionReport.Build("));
            Assert.DoesNotContain("BimApiResponse.Ok(", service);
            Assert.DoesNotContain("BimApiResponse.Fail(", service);
            var work = wrapper.IndexOf("details = Execute(uiDocument, document, evidence, request, call);", StringComparison.Ordinal);
            var unexpected = wrapper.IndexOf("catch (Exception ex)", StringComparison.Ordinal);
            var close = wrapper.IndexOf("call.Receipt.EndObservation();", StringComparison.Ordinal);
            var answer = wrapper.IndexOf(
                "return BimTransactionReport.Build(call.Receipt.Snapshot(), details);",
                StringComparison.Ordinal);
            Assert.True(work >= 0 && work < unexpected && unexpected < close && close < answer);
            // Even a failure Execute did not handle ends up on the receipt.
            Assert.Contains("call.Receipt.ProhibitCommit(", wrapper.Substring(unexpected, close - unexpected));
            Assert.Equal(1, CountOccurrences(wrapper, "return "));
        }

        [Fact]
        public void Executor_RefusesBeforeStartingAndRecordsWhy()
        {
            var service = Read("src/RookBim/Revit/RevitTransactionService.cs");
            var run = ExtractExecutableMember(service, ServiceType, ExecutorSignature);

            var setDocument = run.IndexOf("receipt.SetDocument(activeDocument);", StringComparison.Ordinal);
            var documentKey = run.IndexOf("request.HasDocumentKey", StringComparison.Ordinal);
            var readOnly = run.IndexOf("document.IsReadOnly", StringComparison.Ordinal);
            var alreadyOpen = run.IndexOf("document.IsModifiable", StringComparison.Ordinal);
            var cancelled = run.IndexOf("if (gate.CommitProhibited)", StringComparison.Ordinal);
            var create = run.IndexOf("new Transaction(document, name)", StringComparison.Ordinal);

            // The document is on record before any check can refuse.
            Assert.True(setDocument >= 0 && setDocument < documentKey);
            Assert.True(documentKey < readOnly && readOnly < alreadyOpen && alreadyOpen < cancelled && cancelled < create);
            Assert.Contains(
                "string.Equals(request.DocumentKey, activeDocument.DocumentKey, StringComparison.Ordinal)",
                run);
            Assert.Contains("BimErrorCode.DocumentMismatch", run);
            Assert.Equal(4, CountOccurrences(run, "BimErrorCode.DocumentNotModifiable"));
            // Every refusal is written to the receipt; none is only returned.
            Assert.True(CountOccurrences(run, "receipt.Refuse(") >= 7);
            AssertSingleInvocationArguments(
                run,
                "RevitDocumentIdentityResolver.IsSameDocument",
                "document",
                "evidence.Owner");
        }

        [Fact]
        public void Executor_AStartThatRevitRefusesIsARefusalNotARollback()
        {
            var service = Read("src/RookBim/Revit/RevitTransactionService.cs");
            var run = ExtractExecutableMember(service, ServiceType, ExecutorSignature);

            var start = run.IndexOf("started = transaction.Start();", StringComparison.Ordinal);
            var startCatch = run.IndexOf(
                "catch (Autodesk.Revit.Exceptions.InvalidOperationException ex)",
                StringComparison.Ordinal);
            var statusCheck = run.IndexOf("if (started != TransactionStatus.Started)", StringComparison.Ordinal);
            var markOpen = run.IndexOf("receipt.MarkOpen();", StringComparison.Ordinal);

            Assert.True(start >= 0 && start < startCatch && startCatch < statusCheck);
            // The receipt says "open" only after Revit confirmed the start.
            Assert.True(statusCheck < markOpen);
            Assert.Equal(1, CountOccurrences(run, "receipt.MarkOpen();"));
        }

        [Fact]
        public void Executor_AppliesFailureHandlingAfterStartBecauseStartResetsIt()
        {
            var service = Read("src/RookBim/Revit/RevitTransactionService.cs");
            var run = ExtractExecutableMember(service, ServiceType, ExecutorSignature);
            var preprocess = ExtractExecutableMember(
                service,
                "private sealed class CollectingFailuresPreprocessor : IFailuresPreprocessor",
                "public FailureProcessingResult PreprocessFailures(FailuresAccessor failuresAccessor)");

            var start = run.IndexOf("transaction.Start()", StringComparison.Ordinal);
            var getOptions = run.IndexOf("transaction.GetFailureHandlingOptions()", StringComparison.Ordinal);
            var setOptions = run.IndexOf("transaction.SetFailureHandlingOptions(options);", StringComparison.Ordinal);
            var enter = run.IndexOf("gate.TryEnterScript()", StringComparison.Ordinal);

            // Revit's Transaction.Start() resets failure handling options to
            // their defaults, so options set before it are discarded.
            Assert.True(start >= 0 && start < getOptions, "Failure handling options must be read after Start().");
            Assert.True(getOptions < setOptions, "Failure handling options must be applied after Start().");
            Assert.True(setOptions < enter, "Options must be in place before the script runs.");
            Assert.Equal(1, CountOccurrences(run, "transaction.SetFailureHandlingOptions(options);"));

            Assert.Contains("options.SetFailuresPreprocessor(failures);", run);
            // Forced modal handling keeps Commit() synchronous; with it off a
            // commit can come back Pending behind a modeless dialog.
            Assert.Contains("options.SetForcedModalHandling(true);", run);
            Assert.DoesNotContain("SetForcedModalHandling(false)", run);
            Assert.Contains("options.SetClearAfterRollback(true);", run);

            Assert.Contains("failuresAccessor.DeleteWarning(failure);", preprocess);
            Assert.Contains("FailureProcessingResult.ProceedWithRollBack", preprocess);
            Assert.Contains("FailureProcessingResult.Continue", preprocess);
            // Nothing is dropped from the lists without being counted.
            Assert.Contains("WarningsOmitted++;", preprocess);
            Assert.Contains("ErrorsOmitted++;", preprocess);
        }

        [Fact]
        public void Executor_AsksTheGateBeforeTheScriptAndBeforeTheCommit()
        {
            var service = Read("src/RookBim/Revit/RevitTransactionService.cs");
            var run = ExtractExecutableMember(service, ServiceType, ExecutorSignature);

            var enter = run.IndexOf("if (!gate.TryEnterScript())", StringComparison.Ordinal);
            var script = run.IndexOf("script = RunScript(uiDocument, document, request);", StringComparison.Ordinal);
            var returned = run.IndexOf("gate.MarkScriptReturned();", StringComparison.Ordinal);
            var failed = run.IndexOf("if (!script.Success)", StringComparison.Ordinal);
            var beginCommit = run.IndexOf("if (!gate.TryBeginCommit())", StringComparison.Ordinal);
            var commit = run.IndexOf("transaction.Commit()", StringComparison.Ordinal);

            // A caller who already stopped waiting must not have its script started.
            Assert.True(enter >= 0 && enter < script, "The gate must be asked immediately before the script runs.");
            // The budget stops the moment the host sees the script return.
            Assert.True(script < returned && returned < failed);
            Assert.True(
                failed < beginCommit && beginCommit < commit,
                "A failed script must return before the commit gate, and the gate must be asked before the commit.");
            Assert.Equal(1, CountOccurrences(run, "RunScript(uiDocument, document, request)"));
            Assert.Contains("gate.ScriptRanOverBudget", run);
        }

        [Fact]
        public void Executor_RecordsRevitsAnswerToTheCommitBeforeAnythingElse()
        {
            var service = Read("src/RookBim/Revit/RevitTransactionService.cs");
            var run = ExtractExecutableMember(service, ServiceType, ExecutorSignature);

            var commit = run.IndexOf("var committed = transaction.Commit();", StringComparison.Ordinal);
            var rolledBack = run.IndexOf("if (committed == TransactionStatus.RolledBack)", StringComparison.Ordinal);
            var settle = run.IndexOf("StatusOf(committed),", StringComparison.Ordinal);
            var details = run.IndexOf("var details = Details(script, failures, gate);", StringComparison.Ordinal);
            var optional = run.IndexOf("AddCommittedDetails(details, changes, document, evidence);", StringComparison.Ordinal);

            Assert.True(commit >= 0 && commit < rolledBack && rolledBack < settle);
            // The status is on record before any reporting is gathered, so
            // nothing that reporting does can change or lose it.
            Assert.True(settle < details && details < optional);
            Assert.Equal(1, CountOccurrences(run, "StatusOf(committed),"));
            // Whether the commit changed anything is recorded with the commit,
            // so a later lookup gives the same answer as this call.
            Assert.Contains(
                "committed == TransactionStatus.Committed ? changes.Total > 0 : (bool?)null);",
                run);

            var statusOf = ExtractExecutableMember(
                service,
                ServiceType,
                "private static BimTransactionStatus StatusOf(TransactionStatus status)");
            Assert.Contains("case TransactionStatus.Committed:", statusOf);
            Assert.Contains("case TransactionStatus.RolledBack:", statusOf);
            // Pending (and anything else Revit has not finished) is unresolved,
            // never rolled back.
            Assert.DoesNotContain("TransactionStatus.Pending", statusOf);
            var fallback = statusOf.Substring(statusOf.IndexOf("default:", StringComparison.Ordinal));
            Assert.Contains("return BimTransactionStatus.Unresolved;", fallback);
        }

        [Fact]
        public void Executor_SettleRollsBackOnlyAStartedTransactionAndReportsWhatRevitSays()
        {
            var service = Read("src/RookBim/Revit/RevitTransactionService.cs");
            var settle = ExtractExecutableMember(
                service,
                ServiceType,
                "private static BimTransactionStatus Settle(Transaction? transaction)");

            Assert.Contains("if (status == TransactionStatus.Started)", settle);
            Assert.Contains("status = transaction.RollBack();", settle);
            Assert.Contains("return StatusOf(status);", settle);
            // A rollback that throws is not assumed to have worked.
            var catchIndex = settle.IndexOf("catch", StringComparison.Ordinal);
            Assert.True(catchIndex >= 0);
            Assert.Contains("return BimTransactionStatus.Unresolved;", settle.Substring(catchIndex));
        }

        [Fact]
        public void Executor_NeverLeavesItsTransactionOpenAndAlwaysRecordsWhereItEnded()
        {
            var service = Read("src/RookBim/Revit/RevitTransactionService.cs");
            var run = ExtractExecutableMember(service, ServiceType, ExecutorSignature);

            var catchIndex = run.LastIndexOf("catch (Exception ex)", StringComparison.Ordinal);
            var finallyIndex = run.LastIndexOf("finally", StringComparison.Ordinal);
            Assert.True(catchIndex >= 0 && finallyIndex > catchIndex);
            var catchBlock = run.Substring(catchIndex, finallyIndex - catchIndex);
            var finallyBlock = run.Substring(finallyIndex);

            // A failure after the commit is reported as committed: the catch
            // reads the receipt instead of assuming.
            var committedCheck = catchBlock.IndexOf(
                "if (receipt.Snapshot().Status == BimTransactionStatus.Committed)",
                StringComparison.Ordinal);
            var prohibit = catchBlock.IndexOf("receipt.ProhibitCommit(", StringComparison.Ordinal);
            Assert.True(committedCheck >= 0 && committedCheck < prohibit);
            Assert.Contains("BimErrorCode.InternalError", catchBlock);
            Assert.Contains("receipt.Settle(Settle(transaction));", catchBlock);

            Assert.Contains("receipt.Settle(Settle(transaction));", finallyBlock);
            Assert.Contains("transaction.Dispose();", finallyBlock);
            Assert.Contains("application.DocumentChanged -= changes.OnDocumentChanged;", finallyBlock);
        }

        // ---- the host observes the script itself -------------------------------

        [Fact]
        public void Executor_CallsTheScriptEngineItselfAndNeedsBothSignalsToSucceed()
        {
            var service = Read("src/RookBim/Revit/RevitTransactionService.cs");
            var runScript = ExtractExecutableMember(
                service,
                ServiceType,
                "private BimTransactionScriptResult RunScript(UIDocument uiDocument, Document document, BimRunTransactionRequest request)");

            Assert.Contains("hostError = runScript(channel);", runScript);
            Assert.Contains("hostObservedReturn: hostError == null,", runScript);
            Assert.Contains("scriptReportedCompletion: channel.Completed,", runScript);
            Assert.Contains("BimTransactionScriptResult.FromHostRun(", runScript);

            // No Rhino command, no completion file, no temp files.
            Assert.DoesNotContain("RhinoApp", service);
            Assert.DoesNotContain("RunPythonScript", service);
            Assert.DoesNotContain("File.", service);
            Assert.DoesNotContain("GetTempPath", service);
            Assert.DoesNotContain("System.IO", service);
        }

        [Fact]
        public void Runner_InvokesRhinosPythonEngineDirectlyAndReturnsOnlyWhenItHas()
        {
            var runner = Read("src/RookBim/Revit/RevitPythonScriptRunner.cs");
            var run = ExtractExecutableMember(
                runner,
                "public static class RevitPythonScriptRunner",
                "public static string? Run(RevitScriptChannel channel)");
            var project = XDocument.Parse(Read("src/RookBim/RookBim.csproj"));
            var resource = project.Descendants("EmbeddedResource").Single();

            Assert.Contains("RhinoCode.Languages.QueryLatest(LanguageSpec.Python3)", run);
            Assert.Contains("language.CreateCode(ReadWrapperBody())", run);
            Assert.Contains("context.Inputs.Set(ChannelInputName, channel, false, false);", run);
            Assert.Contains("AutoApplyParams = true", run);
            // The synchronous call: Run, not RunAsync, not a queued command.
            Assert.Contains("code.Run(context);", run);
            Assert.DoesNotContain("Async", run);
            var call = run.IndexOf("code.Run(context);", StringComparison.Ordinal);
            var success = run.IndexOf("return null;", StringComparison.Ordinal);
            var failure = run.IndexOf("catch (Exception ex)", StringComparison.Ordinal);
            Assert.True(call >= 0 && call < success && success < failure);

            Assert.DoesNotContain("RhinoApp", runner);
            Assert.DoesNotContain("RunPythonScript", runner);
            Assert.DoesNotContain("GetTempPath", runner);
            Assert.DoesNotContain("File.", runner);
            Assert.Contains("public const string ChannelInputName = \"__rook__\";", runner);
            Assert.Equal(
                "Revit/Scripts/run_transaction_wrapper.py",
                resource.Attribute("Include")!.Value.Replace('\\', '/'));
            Assert.Equal("RookBim.run_transaction_wrapper.py", resource.Attribute("LogicalName")!.Value);
            Assert.Contains("\"RookBim.run_transaction_wrapper.py\"", runner);

            // Rhino's own script engine, referenced like RhinoCommon: not copied.
            var reference = project.Descendants("Reference")
                .Single(item => item.Attribute("Include")!.Value == "Rhino.Runtime.Code");
            Assert.Equal("false", reference.Element("Private")!.Value);
        }

        [Fact]
        public void Wrapper_TalksOnlyToTheChannelAndNeverTouchesTheTransaction()
        {
            var wrapper = Read("src/RookBim/Revit/Scripts/run_transaction_wrapper.py");
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
            // No files: everything crosses through the host channel.
            Assert.DoesNotContain("open(", code);
            Assert.DoesNotContain("ROOK_RESULT_PATH", code);
            Assert.DoesNotContain("import os", code);
            // No silent str() fallback for values JSON cannot carry.
            Assert.DoesNotContain("default=str", code);

            // Completion is reported once, at the end; an exception is
            // reported and re-raised so the host's own call sees it too.
            Assert.Equal(1, CountOccurrences(code, "__rook__.Complete("));
            var done = code.IndexOf("__rook__.SetStage(\"done\")", StringComparison.Ordinal);
            var complete = code.IndexOf("__rook__.Complete(", StringComparison.Ordinal);
            var except = code.IndexOf("except BaseException as _rook_err:", StringComparison.Ordinal);
            var fail = code.IndexOf("__rook__.Fail(", StringComparison.Ordinal);
            var reraise = code.IndexOf("\n    raise\n", except, StringComparison.Ordinal);
            Assert.True(done >= 0 && done < complete && complete < except);
            Assert.True(except < fail && fail < reraise);
            // Every bound comes from the host, not from a second copy here.
            Assert.Contains("__rook__.MaxResultLength", code);
            Assert.Contains("__rook__.MaxResultDepth", code);
            Assert.Contains("__rook__.MaxTracebackLength", code);
            Assert.Contains("__rook__.MaxErrorLength", code);
        }

        [Fact]
        public void Channel_BoundsOutputAsItArrivesAndAgreesWithTheResultLimits()
        {
            var channel = Read("src/RookBim/Revit/RevitScriptChannel.cs");
            var result = Read("src/Rook/Bim/BimTransactionScriptResult.cs");
            var append = ExtractExecutableMember(
                channel,
                "public sealed class RevitScriptChannel",
                "private static bool Append(StringBuilder buffer, string? text)");

            Assert.Contains("var room = StreamLimit - buffer.Length;", append);
            Assert.Contains("buffer.Append(text, 0, room);", append);
            // A plain object, so Rhino passes it to the script as itself, and
            // free of Revit types so it loads in a plain Rhino.
            Assert.Contains("public sealed class RevitScriptChannel", channel);
            Assert.DoesNotContain("Autodesk", channel);
            Assert.DoesNotContain("using Rook", channel);

            Assert.Contains("public const int StreamLimit = 20000;", channel);
            Assert.Contains("public const int MaxStreamLength = 20000;", result);
            Assert.Contains("public const int ResultLimit = 50000;", channel);
            Assert.Contains("public const int MaxResultJsonLength = 50000;", result);
            Assert.Contains("public const int ResultDepthLimit = 32;", channel);
            Assert.Contains("public const int MaxResultDepth = 32;", result);
            Assert.Contains("public const int TracebackLimit = 20000;", channel);
            Assert.Contains("public const int MaxTracebackLength = 20000;", result);
            Assert.Contains("public const int ErrorLimit = 2000;", channel);
            Assert.Contains("public const int MaxErrorLength = 2000;", result);
        }

        // ---- optional reporting ------------------------------------------------

        [Fact]
        public void Executor_OptionalReportingCannotFailTheResponse()
        {
            var service = Read("src/RookBim/Revit/RevitTransactionService.cs");
            var add = ExtractExecutableMember(
                service,
                ServiceType,
                "private static void AddCommittedDetails(IDictionary<string, object?> details, ChangeCollector changes, Document document, RevitDocumentIdentityEvidence evidence)");
            var describeLive = ExtractExecutableMember(
                service,
                "private sealed class ChangeCollector",
                "private static List<object> DescribeLive(Document owner, RevitDocumentIdentityEvidence evidence, List<ElementId> ids)");
            var onChanged = ExtractExecutableMember(
                service,
                "private sealed class ChangeCollector",
                "public void OnDocumentChanged(object? sender, DocumentChangedEventArgs args)");

            var describe = add.IndexOf("changes.Describe(document, evidence);", StringComparison.Ordinal);
            var describeCatch = add.IndexOf("catch (Exception ex)", StringComparison.Ordinal);
            var countsOnly = add.IndexOf("changes.CountsOnly();", StringComparison.Ordinal);
            Assert.True(describe >= 0 && describe < describeCatch && describeCatch < countsOnly);
            Assert.Contains("details[\"elementsOmittedReason\"] =", service);

            // Changed ids come from Revit, for this document only.
            Assert.Contains("args.GetAddedElementIds()", onChanged);
            Assert.Contains("args.GetModifiedElementIds()", onChanged);
            Assert.Contains("args.GetDeletedElementIds()", onChanged);
            AssertSingleInvocationArguments(
                onChanged,
                "RevitDocumentIdentityResolver.IsSameDocument",
                "args.GetDocument()",
                "document");

            // An identity is handed back only if the read tools would accept
            // it; otherwise the entry says why. No entry is silently dropped.
            var project = describeLive.IndexOf("RevitDocumentIdentityResolver.ProjectElement(evidence, element)", StringComparison.Ordinal);
            var preflight = describeLive.IndexOf("RevitDocumentIdentityResolver.PreflightBatch(", StringComparison.Ordinal);
            var unusable = describeLive.IndexOf("if (!usable.Success)", StringComparison.Ordinal);
            Assert.True(project >= 0 && project < preflight && preflight < unusable);
            Assert.Equal(3, CountOccurrences(describeLive, "described.Add(Undescribed("));
            Assert.Contains("ids.Take(MaxReportedElements)", describeLive);
            Assert.Contains("identityOmittedReason = reason", service);
        }

        // ---- the runtime: waiting, and what a waiter may say -------------------

        [Fact]
        public void Runtime_CreatesTheReceiptBeforeAnythingIsQueued()
        {
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");
            var run = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "public BimApiResponse RunTransaction(BimDiagnosticContext diagnostics, BimRunTransactionRequest request)");

            var validate = run.IndexOf("request.Validate()", StringComparison.Ordinal);
            var begin = run.IndexOf("BimTransactionCall.Begin(", StringComparison.Ordinal);
            var execute = run.IndexOf("ExecuteInDocumentContext(", StringComparison.Ordinal);
            var stillQueued = run.IndexOf("if (!response.Success && call.Receipt.Snapshot().IsQueued)", StringComparison.Ordinal);
            var record = run.IndexOf("call.Receipt.Refuse(response.ErrorCode", StringComparison.Ordinal);
            var close = run.IndexOf("call.Receipt.EndObservation();", StringComparison.Ordinal);
            var answer = run.IndexOf("return BimTransactionReport.Build(", StringComparison.Ordinal);

            Assert.True(validate >= 0 && validate < begin, "An invalid request must be refused before anything is created.");
            Assert.True(begin < execute && execute < stillQueued);
            // A refusal issued before the executor ran (no document, Revit not
            // idle) is recorded, closed, and answered from the receipt, so the
            // caller gets the transaction id like for every other outcome.
            Assert.True(stillQueued < record && record < close && close < answer);
            Assert.Equal(1, CountOccurrences(run, "BimTransactionCall.Begin("));
            Assert.Contains("TimeSpan.FromSeconds(request.EffectiveTimeoutSeconds)", run);
            AssertSingleInvocationArguments(
                run,
                "transactions.Run",
                "uidoc",
                "document",
                "evidence",
                "request",
                "call");
        }

        [Fact]
        public void Runtime_AWaiterThatStopsWaitingReportsTheReceiptAndDecidesNothing()
        {
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");
            var dispatch = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "private BimApiResponse DispatchTransaction(BimDiagnosticContext diagnostics, Func<UIApplication, BimApiResponse> work, BimTransactionCall call)");

            var queue = dispatch.IndexOf("new Task[] { dispatch.Task, dispatch.Started }", StringComparison.Ordinal);
            var abandon = dispatch.IndexOf("if (first < 0 && dispatch.Abandon())", StringComparison.Ordinal);
            var notIdle = dispatch.IndexOf(
                "throw new RevitDispatchTimeoutException(false, QueuePickupTimeout);",
                StringComparison.Ordinal);
            var setup = dispatch.IndexOf("new Task[] { dispatch.Task, gate.ScriptEntered }", StringComparison.Ordinal);
            var script = dispatch.IndexOf("gate.ScriptTimeout + ScriptReturnAllowance", StringComparison.Ordinal);
            var cancel = dispatch.IndexOf("switch (gate.Cancel())", StringComparison.Ordinal);
            var grace = dispatch.IndexOf("TransactionCommitGrace) >= 0", StringComparison.Ordinal);
            var report = dispatch.IndexOf("return BimTransactionReport.Build(", StringComparison.Ordinal);

            // Queue, then setup, then the script, each with its own deadline;
            // the script's deadline starts at the entry signal.
            Assert.True(queue >= 0 && queue < abandon && abandon < notIdle);
            Assert.True(notIdle < setup && setup < script && script < cancel && cancel < grace && grace < report);

            // The waiter withdraws permission and records why. It never names
            // an error code for the outcome and never builds its own answer.
            Assert.Equal(2, CountOccurrences(dispatch, "call.Receipt.ProhibitCommit("));
            Assert.Equal(1, CountOccurrences(dispatch, "BimTransactionReport.Build("));
            Assert.Contains("call.Receipt.Snapshot()", dispatch);
            Assert.DoesNotContain("BimApiResponse.Fail(", dispatch);
            Assert.DoesNotContain("BimApiResponse.Ok(", dispatch);
            Assert.DoesNotContain("TransactionOutcomeUnknown", dispatch);
            Assert.DoesNotContain("NotRhinoInside", dispatch);
            // The only extra field is one it observed itself.
            Assert.Contains("!dispatch.Task.IsCompleted", dispatch);
            Assert.Contains("[\"revitStillBusy\"] = !dispatch.Task.IsCompleted,", runtime);
            Assert.DoesNotContain("scriptStarted", runtime);
            Assert.DoesNotContain("scriptStillRunning", runtime);

            // The whole wait must fit under the 120 s client read timeout.
            Assert.Contains("QueuePickupTimeout = TimeSpan.FromSeconds(10);", runtime);
            Assert.Contains("TransactionSetupTimeout = TimeSpan.FromSeconds(4);", runtime);
            Assert.Contains("ScriptReturnAllowance = TimeSpan.FromSeconds(1);", runtime);
            Assert.Contains("TransactionCommitGrace = TimeSpan.FromSeconds(8);", runtime);
        }

        [Fact]
        public void Runtime_EveryOperationGivesTheQueueItsOwnDeadline()
        {
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");
            var dispatcher = Read("src/RookBim/Revit/RevitApiDispatcher.cs");
            var withTimeout = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "private T DispatchWithTimeout<T>(BimDiagnosticContext diagnostics, Func<UIApplication, T> work, TimeSpan timeout)");
            var execute = ExtractExecutableMember(
                dispatcher,
                "private sealed class RevitApiWorkItem<T>",
                "public void Execute()");

            // An export has a 120 s work budget, the same as the client's read
            // timeout. A blocked queue must be reported well before that.
            var pickup = withTimeout.IndexOf(
                "var pickup = timeout < QueuePickupTimeout ? timeout : QueuePickupTimeout;",
                StringComparison.Ordinal);
            var wait = withTimeout.IndexOf("new Task[] { dispatch.Task, dispatch.Started }, pickup", StringComparison.Ordinal);
            var notIdle = withTimeout.IndexOf("throw new RevitDispatchTimeoutException(false, pickup);", StringComparison.Ordinal);
            var slow = withTimeout.IndexOf("throw new RevitDispatchTimeoutException(true, timeout);", StringComparison.Ordinal);
            Assert.True(pickup >= 0 && pickup < wait && wait < notIdle && notIdle < slow);
            Assert.Contains("var remaining = timeout - waited.Elapsed;", withTimeout);

            // The start signal is raised by the work item itself, after it won
            // the queued-to-running transition that Abandon() competes for.
            var claim = execute.IndexOf("CompareExchange(ref state, Running, Pending)", StringComparison.Ordinal);
            var signal = execute.IndexOf("started.TrySetResult(true);", StringComparison.Ordinal);
            Assert.True(claim >= 0 && claim < signal);
        }

        [Fact]
        public void Runtime_IdleTimeoutIsReportedAsRevitNotIdleNotAsMissingHost()
        {
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");
            var execute = ExtractExecutableMember(runtime, RuntimeType, ExecuteSignature);
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
        public void Runtime_AFailureInsideRevitIsNeverBlamedOnTheHost()
        {
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");
            var execute = ExtractExecutableMember(runtime, RuntimeType, ExecuteSignature);
            var status = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "public BimStatusResponse Status(BimDiagnosticContext diagnostics)");

            // Document operations: acquisition and identity capture run inside
            // Revit's API context and are handled there.
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

            // Status: the same failure inside its own callback.
            var statusCapture = status.IndexOf("RevitDocumentIdentityResolver.Capture(document, diagnostics);", StringComparison.Ordinal);
            var insideCatch = status.IndexOf("failureInsideRevit = DescribeDispatchException(ex);", StringComparison.Ordinal);
            var insideReport = status.IndexOf("if (failureInsideRevit != null)", StringComparison.Ordinal);
            var noDocument = status.IndexOf("if (!hasActiveDocument)", StringComparison.Ordinal);
            var hostFallback = status.LastIndexOf("catch (Exception ex)", StringComparison.Ordinal);
            Assert.True(statusCapture >= 0 && statusCapture < insideCatch && insideCatch < insideReport);
            // Reported on its own, before "no document" and far from the host-missing fallback.
            Assert.True(insideReport < noDocument && noDocument < hostFallback);
            Assert.Contains("\"RookBIM reached Revit, but reading the active document failed: \"", runtime);
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
