using System;
using System.Collections.Generic;
using System.Text.RegularExpressions;

namespace Rook.Bim
{
    internal sealed class BimDiagnosticExceptionInfo
    {
        public string? TypeName { get; set; }

        public int HResult { get; set; }

        public string? Stack { get; set; }

        public IReadOnlyList<BimDiagnosticExceptionInfo> InnerExceptions { get; set; }
            = Array.Empty<BimDiagnosticExceptionInfo>();

        public bool Truncated { get; set; }
    }

    internal sealed class BimDiagnosticExceptionCaptureResult
    {
        internal BimDiagnosticExceptionCaptureResult(
            BimDiagnosticExceptionInfo? root,
            BimDiagnosticDetailCode detailCode)
        {
            BimDiagnosticContracts.ValidateDetailCode(detailCode);
            Root = root;
            DetailCode = detailCode;
        }

        internal BimDiagnosticExceptionInfo? Root { get; }

        internal BimDiagnosticDetailCode DetailCode { get; }
    }

    internal static class BimDiagnosticRedactor
    {
        private const string PathReplacement = "[path:redacted]";
        private const string GuidReplacement = "[guid:redacted]";
        private static readonly TimeSpan MatchTimeout = TimeSpan.FromMilliseconds(100);

        private static readonly Regex SourcePath = new Regex(
            @"(?<=\bin\s)(?:(?:[A-Za-z]:[\\/])|(?:\\\\)|(?:[A-Za-z][A-Za-z0-9+.-]*://)).*?(?=:line\s+\d+)",
            RegexOptions.CultureInvariant,
            MatchTimeout);

        private static readonly Regex UriPath = new Regex(
            @"\b[A-Za-z][A-Za-z0-9+.-]*://[^\s]+",
            RegexOptions.CultureInvariant,
            MatchTimeout);

        private static readonly Regex UncPath = new Regex(
            @"\\\\[^\r\n""<>|]+",
            RegexOptions.CultureInvariant,
            MatchTimeout);

        private static readonly Regex DrivePath = new Regex(
            @"\b[A-Za-z]:[\\/][^\r\n""<>|]+",
            RegexOptions.CultureInvariant,
            MatchTimeout);

        private static readonly Regex GuidValue = new Regex(
            @"(?<![0-9A-Fa-f])(?:\{[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}|[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}|[0-9A-Fa-f]{32})(?![0-9A-Fa-f])",
            RegexOptions.CultureInvariant,
            MatchTimeout);

        internal static string RedactStack(string value)
        {
            if (value == null)
            {
                throw new ArgumentNullException(nameof(value));
            }

            var redacted = SourcePath.Replace(value, PathReplacement);
            redacted = UriPath.Replace(redacted, PathReplacement);
            redacted = UncPath.Replace(redacted, PathReplacement);
            redacted = DrivePath.Replace(redacted, PathReplacement);
            return GuidValue.Replace(redacted, GuidReplacement);
        }
    }

    internal static class BimDiagnosticExceptionCapture
    {
        private const int MaximumNestedDepth = 4;
        private const int MaximumInnerExceptions = 8;
        private const int MaximumStackLength = 8192;
        private const int MaximumRawStackLength = MaximumStackLength * 4;

        internal static BimDiagnosticExceptionCaptureResult Capture(
            Exception exception)
        {
            if (exception == null)
            {
                return new BimDiagnosticExceptionCaptureResult(
                    null,
                    BimDiagnosticDetailCode.ExceptionCaptureFailed);
            }

            BimDiagnosticExceptionInfo root;
            try
            {
                root = CreateNode(exception);
            }
            catch
            {
                return new BimDiagnosticExceptionCaptureResult(
                    null,
                    BimDiagnosticDetailCode.ExceptionCaptureFailed);
            }

            var detailCode = BimDiagnosticDetailCode.None;
            var pendingExceptions = new Stack<Exception>();
            var pendingNodes = new Stack<BimDiagnosticExceptionInfo>();
            var pendingDepths = new Stack<int>();
            pendingExceptions.Push(exception);
            pendingNodes.Push(root);
            pendingDepths.Push(0);
            var innerCount = 0;

            while (pendingExceptions.Count > 0)
            {
                var currentException = pendingExceptions.Pop();
                var currentNode = pendingNodes.Pop();
                var depth = pendingDepths.Pop();

                try
                {
                    CaptureStack(currentException, currentNode);
                    if (currentNode.Truncated)
                    {
                        root.Truncated = true;
                    }
                }
                catch
                {
                    currentNode.Stack = null;
                    currentNode.Truncated = true;
                    root.Truncated = true;
                    detailCode = BimDiagnosticDetailCode.ExceptionCaptureFailed;
                }

                IReadOnlyList<Exception> innerExceptions;
                try
                {
                    innerExceptions = GetInnerExceptions(currentException);
                }
                catch
                {
                    currentNode.Truncated = true;
                    root.Truncated = true;
                    detailCode = BimDiagnosticDetailCode.ExceptionCaptureFailed;
                    continue;
                }

                if (innerExceptions.Count == 0)
                {
                    continue;
                }

                if (depth >= MaximumNestedDepth)
                {
                    currentNode.Truncated = true;
                    root.Truncated = true;
                    continue;
                }

                var capturedChildren = new List<BimDiagnosticExceptionInfo>();
                var capturedExceptions = new List<Exception>();
                for (var index = 0; index < innerExceptions.Count; index++)
                {
                    if (innerCount >= MaximumInnerExceptions)
                    {
                        currentNode.Truncated = true;
                        root.Truncated = true;
                        break;
                    }

                    try
                    {
                        capturedChildren.Add(CreateNode(innerExceptions[index]));
                        capturedExceptions.Add(innerExceptions[index]);
                        innerCount++;
                    }
                    catch
                    {
                        currentNode.Truncated = true;
                        root.Truncated = true;
                        detailCode = BimDiagnosticDetailCode.ExceptionCaptureFailed;
                    }
                }

                currentNode.InnerExceptions = capturedChildren;
                for (var index = capturedChildren.Count - 1; index >= 0; index--)
                {
                    pendingExceptions.Push(capturedExceptions[index]);
                    pendingNodes.Push(capturedChildren[index]);
                    pendingDepths.Push(depth + 1);
                }
            }

            return new BimDiagnosticExceptionCaptureResult(root, detailCode);
        }

        private static BimDiagnosticExceptionInfo CreateNode(Exception exception)
        {
            return new BimDiagnosticExceptionInfo
            {
                TypeName = BimDiagnosticContracts.BoundExceptionTypeName(
                    exception.GetType().FullName),
                HResult = exception.HResult
            };
        }

        private static void CaptureStack(
            Exception exception,
            BimDiagnosticExceptionInfo node)
        {
            var stack = exception.StackTrace;
            if (stack == null)
            {
                return;
            }

            if (stack.Length > MaximumRawStackLength)
            {
                stack = stack.Substring(0, MaximumRawStackLength);
                node.Truncated = true;
            }

            stack = BimDiagnosticRedactor.RedactStack(stack);
            if (stack.Length > MaximumStackLength)
            {
                stack = stack.Substring(0, MaximumStackLength);
                node.Truncated = true;
            }

            node.Stack = stack;
        }

        private static IReadOnlyList<Exception> GetInnerExceptions(
            Exception exception)
        {
            if (exception is AggregateException aggregate)
            {
                return aggregate.InnerExceptions;
            }

            return exception.InnerException == null
                ? Array.Empty<Exception>()
                : new[] { exception.InnerException };
        }
    }
}
