using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim.Diagnostics
{
    public sealed class BimDiagnosticPrivacyTests
    {
        [Fact]
        public void CaptureAndEncode_NeverReadOrPersistHostileMessageOrToString()
        {
            var exception = new HostileException();

            var capture = BimDiagnosticExceptionCapture.Capture(exception);

            Assert.Equal(BimDiagnosticDetailCode.None, capture.DetailCode);
            var root = Assert.IsType<BimDiagnosticExceptionInfo>(capture.Root);
            var record = CreateRecord(root);
            var encoded = Assert.IsType<string>(BimDiagnosticJsonEncoder.Encode(record));
            Assert.DoesNotContain("Snowdon Towers", encoded,
                StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("Walls", encoded,
                StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain(".rvt", encoded,
                StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("01234567-89ab-cdef-0123-456789abcdef", encoded,
                StringComparison.OrdinalIgnoreCase);
            Assert.Equal(typeof(HostileException).FullName, root.TypeName);
            Assert.Equal(exception.HResult, root.HResult);
        }

        [Fact]
        public void Capture_HostileStackDegradesToFixedCodeAndKeepsBoundedRootEvidence()
        {
            var exception = new ThrowingStackException();

            var capture = BimDiagnosticExceptionCapture.Capture(exception);

            Assert.Equal(BimDiagnosticDetailCode.ExceptionCaptureFailed,
                capture.DetailCode);
            var root = Assert.IsType<BimDiagnosticExceptionInfo>(capture.Root);
            Assert.Equal(typeof(ThrowingStackException).FullName, root.TypeName);
            Assert.Equal(exception.HResult, root.HResult);
            Assert.Null(root.Stack);
            Assert.True(root.Truncated);
        }

        [Fact]
        public void RedactStack_RemovesPathsAndGuidFormsButPreservesMethodsAndLines()
        {
            const string Hyphenated = "01234567-89ab-cdef-0123-456789abcdef";
            const string Compact = "0123456789abcdef0123456789abcdef";
            var stack =
                "at Example.Type.Drive() in C:\\Users\\example\\Model.rvt:line 42\n" +
                "at Example.Type.Unc() in \\\\server\\share\\Other.rvt:line 17\n" +
                "at Example.Type.Uris() file:///C:/Models/File.rvt " +
                "rsn://server/project/model.rvt cloud://tenant/model/" +
                "{" + Hyphenated + "}\n" +
                "at Example.Type.Guids() " + Hyphenated + " " + Compact + "\n" +
                "C:\\Projects\\Snowdon Towers\\Model.rvt\n" +
                "\\\\server\\share\\Snowdon Towers\\Other.rvt";

            var redacted = BimDiagnosticRedactor.RedactStack(stack);

            Assert.Contains("Example.Type.Drive()", redacted);
            Assert.Contains(":line 42", redacted);
            Assert.Contains("Example.Type.Unc()", redacted);
            Assert.Contains(":line 17", redacted);
            Assert.Contains("[path:redacted]", redacted);
            Assert.Contains("[guid:redacted]", redacted);
            Assert.DoesNotContain("Model.rvt", redacted,
                StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("Other.rvt", redacted,
                StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("Snowdon Towers", redacted,
                StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("file:///", redacted,
                StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("rsn://", redacted,
                StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("cloud://", redacted,
                StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain(Hyphenated, redacted,
                StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain(Compact, redacted,
                StringComparison.OrdinalIgnoreCase);
        }

        [Fact]
        public void RedactStack_RemovesSpaceBearingFileServerAndCloudUris()
        {
            var stack =
                "at Example.Type.File() file:///C:/Snowdon Towers/Model.rvt\n" +
                "at Example.Type.Server() rsn://server/Shared Models/School.rvt\n" +
                "at Example.Type.Cloud() cloud://tenant/Project Files/Walls.rvt\n" +
                "at Example.Type.Source() in file:///C:/Source Trees/Probe.cs:line 73";

            var redacted = BimDiagnosticRedactor.RedactStack(stack);

            Assert.Contains("Example.Type.File()", redacted);
            Assert.Contains("Example.Type.Server()", redacted);
            Assert.Contains("Example.Type.Cloud()", redacted);
            Assert.Contains("Example.Type.Source()", redacted);
            Assert.Contains(":line 73", redacted);
            Assert.DoesNotContain("Snowdon Towers", redacted,
                StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("Model.rvt", redacted,
                StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("Shared Models", redacted,
                StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("School.rvt", redacted,
                StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("Project Files", redacted,
                StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("Walls.rvt", redacted,
                StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("Source Trees", redacted,
                StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("Probe.cs", redacted,
                StringComparison.OrdinalIgnoreCase);
        }

        [Fact]
        public void Capture_BoundsRedactedStackTo8192Characters()
        {
            var capture = BimDiagnosticExceptionCapture.Capture(
                new FixedStackException(new string('s', 9000)));

            var root = Assert.IsType<BimDiagnosticExceptionInfo>(capture.Root);
            Assert.Equal(8192, root.Stack?.Length);
            Assert.True(root.Truncated);
        }

        [Fact]
        public void Capture_AllowsRootPlusFourNestedLevelsAndTruncatesTheRest()
        {
            Exception current = new LeafException();
            for (var index = 0; index < 6; index++)
            {
                current = new WrapperException(current);
            }

            var capture = BimDiagnosticExceptionCapture.Capture(current);

            var root = Assert.IsType<BimDiagnosticExceptionInfo>(capture.Root);
            var nodes = Flatten(root).ToArray();
            Assert.Equal(5, nodes.Length);
            Assert.True(root.Truncated);
            Assert.Empty(nodes[nodes.Length - 1].InnerExceptions);
        }

        [Fact]
        public void Capture_LimitsAggregateInnerExceptionsToEightDeterministically()
        {
            var exception = new AggregateException(
                Enumerable.Range(0, 10)
                    .Select(index => (Exception)new IndexedException(index)));

            var first = BimDiagnosticExceptionCapture.Capture(exception);
            var second = BimDiagnosticExceptionCapture.Capture(exception);

            var firstRoot = Assert.IsType<BimDiagnosticExceptionInfo>(first.Root);
            var secondRoot = Assert.IsType<BimDiagnosticExceptionInfo>(second.Root);
            Assert.Equal(8, Flatten(firstRoot).Count() - 1);
            Assert.True(firstRoot.Truncated);
            Assert.Equal(
                Enumerable.Range(0, 8),
                firstRoot.InnerExceptions.Select(item => item.HResult));
            Assert.Equal(
                firstRoot.InnerExceptions.Select(item => item.HResult),
                secondRoot.InnerExceptions.Select(item => item.HResult));
        }

        [Fact]
        public void Capture_NestedAggregateUsesOneGlobalEightInnerBudget()
        {
            var exception = new AggregateException(
                new AggregateException(Enumerable.Range(0, 6)
                    .Select(index => (Exception)new IndexedException(index))),
                new AggregateException(Enumerable.Range(6, 6)
                    .Select(index => (Exception)new IndexedException(index))));

            var capture = BimDiagnosticExceptionCapture.Capture(exception);

            var root = Assert.IsType<BimDiagnosticExceptionInfo>(capture.Root);
            Assert.Equal(8, Flatten(root).Count() - 1);
            Assert.True(root.Truncated);
            Assert.Equal(2, root.InnerExceptions.Count);
            Assert.Equal(Enumerable.Range(0, 6),
                root.InnerExceptions[0].InnerExceptions
                    .Select(item => item.HResult));
            Assert.Empty(root.InnerExceptions[1].InnerExceptions);
            Assert.True(root.InnerExceptions[1].Truncated);
        }

        [Fact]
        public void ProductionFiles_HaveNoJsonDependencyOrMessageAccess()
        {
            var files = new[]
            {
                "BimDiagnosticSession.cs",
                "BimDiagnosticExceptionCapture.cs",
                "BimDiagnosticJsonEncoder.cs"
            };

            foreach (var file in files)
            {
                var source = ReadSourceFile(
                    "src", "Rook", "Bim", "Diagnostics", file);
                Assert.DoesNotContain("System.Text.Json", source);
                Assert.DoesNotContain("JsonSerializer", source);
                Assert.DoesNotContain("JsonNode", source);
                Assert.DoesNotContain("Exception.Message", source);
                Assert.DoesNotContain("Exception.ToString", source);
                Assert.DoesNotContain("exception.Message", source);
                Assert.DoesNotContain("exception.ToString", source);
            }
        }

        private static BimDiagnosticRecord CreateRecord(
            BimDiagnosticExceptionInfo exceptionInfo)
        {
            var accumulator = new BimDiagnosticOutcomeAccumulator();
            var envelope = new BimDiagnosticEnvelope(
                BimDiagnosticRecordKind.Failure,
                1,
                new DateTime(2026, 7, 25, 12, 0, 0, DateTimeKind.Utc),
                100,
                7,
                "11111111-2222-3333-4444-555555555555",
                "list_categories",
                BimDiagnosticStage.RevitCategoryName,
                BimDiagnosticOutcome.Failure,
                BimDiagnosticFields.None,
                exceptionInfo,
                accumulator);
            return new BimDiagnosticRecord(
                envelope,
                accumulator.Snapshot(),
                "1.5.16",
                "abc123",
                "unavailable",
                "unavailable");
        }

        private static IEnumerable<BimDiagnosticExceptionInfo> Flatten(
            BimDiagnosticExceptionInfo root)
        {
            var pending = new Stack<BimDiagnosticExceptionInfo>();
            pending.Push(root);
            while (pending.Count > 0)
            {
                var current = pending.Pop();
                yield return current;
                for (var index = current.InnerExceptions.Count - 1;
                     index >= 0;
                     index--)
                {
                    pending.Push(current.InnerExceptions[index]);
                }
            }
        }

        private static string ReadSourceFile(params string[] pathParts)
        {
            var directory = new DirectoryInfo(AppContext.BaseDirectory);
            while (directory != null)
            {
                var candidate = Path.Combine(
                    new[] { directory.FullName }.Concat(pathParts).ToArray());
                if (File.Exists(candidate))
                {
                    return File.ReadAllText(candidate);
                }

                directory = directory.Parent;
            }

            throw new FileNotFoundException(string.Join("/", pathParts));
        }

        private sealed class HostileException : Exception
        {
            public override string Message =>
                throw new InvalidOperationException(
                    "Snowdon Towers Walls Model.rvt " +
                    "01234567-89ab-cdef-0123-456789abcdef\r\nprivate");

            public override IDictionary Data =>
                throw new InvalidOperationException("Data must not be read");

            public override string? Source
            {
                get => throw new InvalidOperationException("Source must not be read");
                set => throw new InvalidOperationException("Source must not be written");
            }

            public override string ToString()
            {
                throw new InvalidOperationException("ToString must not be read");
            }
        }

        private sealed class ThrowingStackException : Exception
        {
            public override string? StackTrace =>
                throw new InvalidOperationException("stack access failed");
        }

        private sealed class FixedStackException : Exception
        {
            private readonly string stack;

            internal FixedStackException(string stack)
            {
                this.stack = stack;
            }

            public override string StackTrace => stack;
        }

        private sealed class WrapperException : Exception
        {
            internal WrapperException(Exception inner)
                : base(null, inner)
            {
            }
        }

        private sealed class LeafException : Exception { }

        private sealed class IndexedException : Exception
        {
            internal IndexedException(int index)
            {
                HResult = index;
            }
        }
    }
}
