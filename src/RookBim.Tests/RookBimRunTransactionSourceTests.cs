using System;
using System.IO;
using System.Linq;
using System.Xml.Linq;
using Xunit;

namespace RookBim.Tests
{
    /// <summary>
    /// Source contracts for POST /bim/run-transaction, the only RookBIM route
    /// that writes the Revit document. RookBim.dll cannot be loaded without
    /// Revit, so these bind to the exact members that carry each guarantee.
    /// </summary>
    public class RookBimRunTransactionSourceTests
    {
        private const string RuntimeType =
            "public sealed class RevitRookBimRuntime : IRookBimRuntime";
        private const string ServiceType =
            "internal sealed class RevitTransactionService";
        private const string RunSignature =
            "public BimApiResponse Run(UIDocument uiDocument, Document document, RevitDocumentIdentityEvidence evidence, BimRunTransactionRequest request, RevitTransactionCommitGate gate)";
        private const string TransactionServiceFile = "RevitTransactionService.cs";
        private static readonly string RepoRoot = FindRepoRoot();

        private static readonly string[] RevitWriteMarkers =
        {
            "new Transaction(",
            "new TransactionGroup(",
            "new SubTransaction(",
            ".Commit()",
            ".RollBack()",
            "TransactionStatus",
        };

        internal static void AssertRevitWritesStayInTransactionService()
        {
            var revitDirectory = Path.Combine(RepoRoot, "src", "RookBim", "Revit");
            var files = Directory.GetFiles(revitDirectory, "*.cs");
            Assert.Contains(files, path => Path.GetFileName(path) == TransactionServiceFile);

            foreach (var path in files.Where(path => Path.GetFileName(path) != TransactionServiceFile))
            {
                var source = File.ReadAllText(path);
                foreach (var marker in RevitWriteMarkers)
                {
                    Assert.False(
                        source.Contains(marker),
                        Path.GetFileName(path) + " must not use Revit transactions (found '" + marker +
                        "'); document writes belong in " + TransactionServiceFile + ".");
                }
            }
        }

        [Fact]
        public void RevitWrites_AreConfinedToTheTransactionService()
        {
            AssertRevitWritesStayInTransactionService();
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
        }

        [Fact]
        public void TransactionService_RefusesBeforeStartingWhenTheDocumentCannotBeModified()
        {
            var service = Read("src/RookBim/Revit/RevitTransactionService.cs");
            var run = ExtractExecutableMember(service, ServiceType, RunSignature);

            var readOnly = run.IndexOf("document.IsReadOnly", StringComparison.Ordinal);
            var alreadyOpen = run.IndexOf("document.IsModifiable", StringComparison.Ordinal);
            var create = run.IndexOf("new Transaction(document, name)", StringComparison.Ordinal);

            Assert.True(readOnly >= 0 && readOnly < create);
            Assert.True(alreadyOpen >= 0 && alreadyOpen < create);
            Assert.Contains("BimErrorCode.DocumentNotModifiable", run);
            AssertSingleInvocationArguments(
                run,
                "RevitDocumentIdentityResolver.IsSameDocument",
                "document",
                "evidence.Owner");
        }

        [Fact]
        public void TransactionService_RollsBackOnScriptFailureAndNeverCommitsIt()
        {
            var service = Read("src/RookBim/Revit/RevitTransactionService.cs");
            var run = ExtractExecutableMember(service, ServiceType, RunSignature);

            var start = run.IndexOf("transaction.Start()", StringComparison.Ordinal);
            var script = run.IndexOf("RunScript(files)", StringComparison.Ordinal);
            var failureCheck = run.IndexOf("if (!script.Success)", StringComparison.Ordinal);
            var failureReturn = run.IndexOf("return ScriptFailure(name, script, rolledBack);", StringComparison.Ordinal);
            var gate = run.IndexOf("gate.TryBeginCommit()", StringComparison.Ordinal);
            var commit = run.IndexOf("transaction.Commit()", StringComparison.Ordinal);

            Assert.True(start >= 0 && start < script, "The transaction must be open before the script runs.");
            Assert.True(script < failureCheck && failureCheck < failureReturn);
            Assert.True(
                failureReturn < gate && gate < commit,
                "A failed script must return before the commit gate and the commit.");
            Assert.Equal(1, CountOccurrences(run, "transaction.Commit()"));
            Assert.Contains("var rolledBack = RollBack(transaction);", run);

            var scriptFailure = ExtractExecutableMember(
                service,
                ServiceType,
                "private static BimApiResponse ScriptFailure(string name, BimTransactionScriptResult script, bool rolledBack)");
            Assert.Contains("BimErrorCode.TransactionScriptFailed", scriptFailure);
            Assert.Contains("RollbackClause(rolledBack)", scriptFailure);
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
            var committedCheck = catchBlock.IndexOf("if (IsCommitted(transaction))", StringComparison.Ordinal);
            var rollBackCall = catchBlock.IndexOf("RollBack(transaction)", StringComparison.Ordinal);
            Assert.True(committedCheck >= 0 && committedCheck < rollBackCall);
            Assert.Contains("documentChanged = true", catchBlock);
            Assert.Contains("RollBack(transaction)", catchBlock);
            Assert.Contains("BimErrorCode.InternalError", catchBlock);
            Assert.Contains("RollbackClause(rolledBack)", catchBlock);
            Assert.Contains("RollBack(transaction);", finallyBlock);
            Assert.Contains("application.DocumentChanged -= changes.OnDocumentChanged;", finallyBlock);
            Assert.Contains("files.Delete();", finallyBlock);

            var rollBack = ExtractExecutableMember(
                service,
                ServiceType,
                "private static bool RollBack(Transaction? transaction)");
            Assert.Contains("transaction.HasStarted()", rollBack);
            Assert.Contains("transaction.HasEnded()", rollBack);
            Assert.Contains("transaction.RollBack() == TransactionStatus.RolledBack", rollBack);
        }

        [Fact]
        public void TransactionService_ReportsACommitThatRevitRolledBackAsFailure()
        {
            var service = Read("src/RookBim/Revit/RevitTransactionService.cs");
            var run = ExtractExecutableMember(service, ServiceType, RunSignature);

            Assert.Contains("var committed = transaction.Commit();", run);
            Assert.Contains("if (committed != TransactionStatus.Committed)", run);
            Assert.Contains("BimErrorCode.TransactionRolledBack", run);

            var committedCheck = run.IndexOf("if (committed != TransactionStatus.Committed)", StringComparison.Ordinal);
            var ok = run.IndexOf("return BimApiResponse.Ok(", StringComparison.Ordinal);
            Assert.True(committedCheck >= 0 && committedCheck < ok, "Success may only be reported after a confirmed commit.");
            Assert.Equal(1, CountOccurrences(run, "BimApiResponse.Ok("));
        }

        [Fact]
        public void TransactionService_NeverLetsRevitOpenAFailureDialog()
        {
            var service = Read("src/RookBim/Revit/RevitTransactionService.cs");
            var run = ExtractExecutableMember(service, ServiceType, RunSignature);
            var preprocess = ExtractExecutableMember(
                service,
                "private sealed class CollectingFailuresPreprocessor : IFailuresPreprocessor",
                "public FailureProcessingResult PreprocessFailures(FailuresAccessor failuresAccessor)");

            Assert.Contains("options.SetFailuresPreprocessor(failures);", run);
            Assert.Contains("options.SetForcedModalHandling(false);", run);
            Assert.Contains("options.SetClearAfterRollback(true);", run);
            Assert.Contains("transaction.SetFailureHandlingOptions(options);", run);
            Assert.True(
                run.IndexOf("transaction.SetFailureHandlingOptions(options);", StringComparison.Ordinal) <
                run.IndexOf("transaction.Start()", StringComparison.Ordinal));

            Assert.Contains("failuresAccessor.DeleteWarning(failure);", preprocess);
            Assert.Contains("Warnings.Add(text);", preprocess);
            Assert.Contains("Errors.Add(text);", preprocess);
            Assert.Contains("FailureProcessingResult.ProceedWithRollBack", preprocess);
            Assert.Contains("FailureProcessingResult.Continue", preprocess);
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
            var describeLive = ExtractExecutableMember(
                service,
                "private sealed class ChangeCollector",
                "private static List<object> DescribeLive(Document owner, RevitDocumentIdentityEvidence evidence, List<ElementId> ids)");

            Assert.Contains("application.DocumentChanged += changes.OnDocumentChanged;", run);
            Assert.True(
                run.IndexOf("application.DocumentChanged += changes.OnDocumentChanged;", StringComparison.Ordinal) <
                run.IndexOf("transaction.Start()", StringComparison.Ordinal));
            Assert.Contains("elements = changes.Describe(document, evidence)", run);

            Assert.Contains("args.GetAddedElementIds()", onChanged);
            Assert.Contains("args.GetModifiedElementIds()", onChanged);
            Assert.Contains("args.GetDeletedElementIds()", onChanged);
            AssertSingleInvocationArguments(
                onChanged,
                "RevitDocumentIdentityResolver.IsSameDocument",
                "args.GetDocument()",
                "document");

            // Added and modified elements come back as the identity envelope the read tools accept.
            Assert.Contains("RevitDocumentIdentityResolver.ProjectElement(evidence, element)", describeLive);
            Assert.Contains("ids.Take(MaxReportedElements)", describeLive);
        }

        [Fact]
        public void TransactionService_RunsTheScriptThroughRhinoWithTheEmbeddedWrapper()
        {
            var service = Read("src/RookBim/Revit/RevitTransactionService.cs");
            var runScript = ExtractExecutableMember(
                service,
                ServiceType,
                "private BimTransactionScriptResult RunScript(ScriptFiles files)");
            var buildWrapper = ExtractExecutableMember(
                service,
                ServiceType,
                "private static string BuildWrapper(ScriptFiles files)");
            var project = XDocument.Parse(Read("src/RookBim/RookBim.csproj"));
            var resource = project.Descendants("EmbeddedResource").Single();

            Assert.Contains("runRhinoScript(", runScript);
            Assert.Contains("File.Exists(files.Result)", runScript);
            Assert.Contains("BimTransactionScriptResult.Missing(", runScript);
            Assert.Contains("BimTransactionScriptResult.Parse(", runScript);
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
        public void Wrapper_NeverTouchesTheTransactionItself()
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
            Assert.Contains("ROOK_CODE_PATH", code);
            Assert.Contains("ROOK_RESULT_PATH", code);
            Assert.Contains("except BaseException", code);
        }

        [Fact]
        public void CommitGate_GivesTheOutcomeToExactlyOneSide()
        {
            var service = Read("src/RookBim/Revit/RevitTransactionService.cs");
            var begin = ExtractExecutableMember(
                service,
                "internal sealed class RevitTransactionCommitGate",
                "public bool TryBeginCommit()");
            var cancel = ExtractExecutableMember(
                service,
                "internal sealed class RevitTransactionCommitGate",
                "public bool TryCancel()");

            var run = ExtractExecutableMember(service, ServiceType, RunSignature);
            // The script timeout is measured from this signal, so it must
            // come before anything that can take time.
            Assert.True(
                run.IndexOf("gate.MarkStarted();", StringComparison.Ordinal) >= 0 &&
                run.IndexOf("gate.MarkStarted();", StringComparison.Ordinal) <
                run.IndexOf("document.IsReadOnly", StringComparison.Ordinal));
            Assert.Contains("Interlocked.CompareExchange(ref state, Committing, Open) == Open", begin);
            Assert.Contains("Interlocked.CompareExchange(ref state, Cancelled, Open) == Open", cancel);
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
            Assert.Equal(1, CountOccurrences(run, "new RevitTransactionCommitGate()"));
            AssertSingleInvocationArguments(
                run,
                "transactions.Run",
                "uidoc",
                "document",
                "evidence",
                "request",
                "gate");
            Assert.Contains("TimeSpan.FromSeconds(request.EffectiveTimeoutSeconds)", run);
        }

        [Fact]
        public void Runtime_TransactionDispatchSeparatesNotIdleFromSlowScriptAndCancelsTheCommit()
        {
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");
            var dispatch = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "private BimApiResponse DispatchTransaction(BimDiagnosticContext diagnostics, Func<UIApplication, BimApiResponse> work, TimeSpan scriptTimeout, RevitTransactionCommitGate gate)");

            var idleWait = dispatch.IndexOf("new Task[] { dispatch.Task, gate.Started }", StringComparison.Ordinal);
            var abandon = dispatch.IndexOf("if (first < 0 && dispatch.Abandon())", StringComparison.Ordinal);
            var notIdle = dispatch.IndexOf(
                "throw new RevitDispatchTimeoutException(false, TransactionIdleTimeout);",
                StringComparison.Ordinal);
            var scriptWait = dispatch.IndexOf("scriptTimeout) >= 0", StringComparison.Ordinal);
            var cancel = dispatch.IndexOf("if (gate.TryCancel())", StringComparison.Ordinal);
            var graceWait = dispatch.IndexOf("TransactionCommitGrace) >= 0", StringComparison.Ordinal);

            Assert.True(idleWait >= 0 && idleWait < abandon);
            Assert.True(abandon < notIdle && notIdle < scriptWait);
            Assert.True(scriptWait < cancel && cancel < graceWait);
            Assert.Contains("BimErrorCode.TransactionTimeout", dispatch);
            Assert.Contains("rollback_pending", runtime);
            Assert.DoesNotContain("NotRhinoInside", dispatch);
        }

        [Fact]
        public void Runtime_IdleTimeoutIsReportedAsRevitNotIdleNotAsMissingHost()
        {
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");
            var execute = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "private BimApiResponse ExecuteInDocumentContext(BimDiagnosticContext diagnostics, string operation, Func<UIDocument, Document, RevitDocumentIdentityEvidence, BimApiResponse> work, TimeSpan? timeout = null, RevitTransactionCommitGate? transactionGate = null)");
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
