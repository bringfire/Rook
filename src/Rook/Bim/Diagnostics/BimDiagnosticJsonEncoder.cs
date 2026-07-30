using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace Rook.Bim
{
    internal static class BimDiagnosticJsonEncoder
    {
        private const int MaximumEncodedBytes = 16 * 1024;
        private const int MaximumExceptionDepth = 4;
        private const int MaximumInnerExceptions = 8;
        private const int MaximumStackLength = 8192;

        internal static string? Encode(BimDiagnosticRecord record)
        {
            if (record == null)
            {
                throw new ArgumentNullException(nameof(record));
            }

            var exceptionInfo = record.Kind == BimDiagnosticRecordKind.Terminal
                ? null
                : CloneBounded(record.ExceptionInfo);
            var truncated = exceptionInfo?.Truncated ?? false;
            var encoded = Build(record, exceptionInfo, truncated);
            if (Fits(encoded))
            {
                return encoded;
            }

            if (exceptionInfo == null)
            {
                return null;
            }

            exceptionInfo.Truncated = true;
            truncated = true;
            encoded = Build(record, exceptionInfo, truncated);
            if (Fits(encoded))
            {
                return encoded;
            }

            var maximumDepth = GetMaximumDepth(exceptionInfo);
            while (maximumDepth > 1)
            {
                RemoveNodesAtDepth(exceptionInfo, maximumDepth);
                encoded = Build(record, exceptionInfo, truncated);
                if (Fits(encoded))
                {
                    return encoded;
                }

                maximumDepth = GetMaximumDepth(exceptionInfo);
            }

            if (exceptionInfo.InnerExceptions.Count > 0)
            {
                exceptionInfo.InnerExceptions =
                    Array.Empty<BimDiagnosticExceptionInfo>();
                encoded = Build(record, exceptionInfo, truncated);
                if (Fits(encoded))
                {
                    return encoded;
                }
            }

            while (!string.IsNullOrEmpty(exceptionInfo.Stack))
            {
                var currentStack = exceptionInfo.Stack;
                if (currentStack == null)
                {
                    break;
                }

                var newLength = currentStack.Length / 2;
                exceptionInfo.Stack = newLength == 0
                    ? string.Empty
                    : currentStack.Substring(0, newLength);
                encoded = Build(record, exceptionInfo, truncated);
                if (Fits(encoded))
                {
                    return encoded;
                }
            }

            encoded = Build(record, exceptionInfo, truncated);
            return Fits(encoded) ? encoded : null;
        }

        internal static string ToWire(BimDiagnosticRecordKind value)
        {
            switch (value)
            {
                case BimDiagnosticRecordKind.Milestone:
                    return "milestone";
                case BimDiagnosticRecordKind.Failure:
                    return "failure";
                case BimDiagnosticRecordKind.Terminal:
                    return "terminal";
                default:
                    throw new ArgumentOutOfRangeException(nameof(value));
            }
        }

        internal static string ToWire(BimDiagnosticOutcome value)
        {
            switch (value)
            {
                case BimDiagnosticOutcome.Start:
                    return "start";
                case BimDiagnosticOutcome.Success:
                    return "success";
                case BimDiagnosticOutcome.Failure:
                    return "failure";
                default:
                    throw new ArgumentOutOfRangeException(nameof(value));
            }
        }

        internal static string ToWire(BimDiagnosticFailureImpact value)
        {
            switch (value)
            {
                case BimDiagnosticFailureImpact.None:
                    return "none";
                case BimDiagnosticFailureImpact.Production:
                    return "production";
                case BimDiagnosticFailureImpact.Auxiliary:
                    return "auxiliary";
                default:
                    throw new ArgumentOutOfRangeException(nameof(value));
            }
        }

        internal static string ToWire(BimDiagnosticDetailCode value)
        {
            switch (value)
            {
                case BimDiagnosticDetailCode.None:
                    return "none";
                case BimDiagnosticDetailCode.True:
                    return "true";
                case BimDiagnosticDetailCode.False:
                    return "false";
                case BimDiagnosticDetailCode.Null:
                    return "null";
                case BimDiagnosticDetailCode.NotApplicable:
                    return "not_applicable";
                case BimDiagnosticDetailCode.NotWorkshared:
                    return "not_workshared";
                case BimDiagnosticDetailCode.AlreadyInitialized:
                    return "already_initialized";
                case BimDiagnosticDetailCode.NoActiveView:
                    return "no_active_view";
                case BimDiagnosticDetailCode.Unsaved:
                    return "unsaved";
                case BimDiagnosticDetailCode.File:
                    return "file";
                case BimDiagnosticDetailCode.Server:
                    return "server";
                case BimDiagnosticDetailCode.Cloud:
                    return "cloud";
                case BimDiagnosticDetailCode.Detached:
                    return "detached";
                case BimDiagnosticDetailCode.FileWorkshared:
                    return "file_workshared";
                case BimDiagnosticDetailCode.SavedProject:
                    return "saved_project";
                case BimDiagnosticDetailCode.Family:
                    return "family";
                case BimDiagnosticDetailCode.Match:
                    return "match";
                case BimDiagnosticDetailCode.Mismatch:
                    return "mismatch";
                case BimDiagnosticDetailCode.Unavailable:
                    return "unavailable";
                case BimDiagnosticDetailCode.InvalidEvidence:
                    return "invalid_evidence";
                case BimDiagnosticDetailCode.Unknown:
                    return "unknown";
                case BimDiagnosticDetailCode.ProbeFailure:
                    return "probe_failure";
                case BimDiagnosticDetailCode.NotDisposable:
                    return "not_disposable";
                case BimDiagnosticDetailCode.Truncated:
                    return "truncated";
                case BimDiagnosticDetailCode.SerializationFailure:
                    return "serialization_failure";
                case BimDiagnosticDetailCode.ExceptionCaptureFailed:
                    return "exception_capture_failed";
                default:
                    throw new ArgumentOutOfRangeException(nameof(value));
            }
        }

        internal static string ToWire(BimDiagnosticSinkState value)
        {
            switch (value)
            {
                case BimDiagnosticSinkState.Disabled:
                    return "disabled";
                case BimDiagnosticSinkState.Starting:
                    return "starting";
                case BimDiagnosticSinkState.Ready:
                    return "ready";
                case BimDiagnosticSinkState.Degraded:
                    return "degraded";
                case BimDiagnosticSinkState.FileLimitReached:
                    return "file_limit_reached";
                case BimDiagnosticSinkState.Failed:
                    return "failed";
                case BimDiagnosticSinkState.Stopped:
                    return "stopped";
                default:
                    throw new ArgumentOutOfRangeException(nameof(value));
            }
        }

        internal static string ToWire(BimDiagnosticSinkFailureCode value)
        {
            switch (value)
            {
                case BimDiagnosticSinkFailureCode.None:
                    return "none";
                case BimDiagnosticSinkFailureCode.QueueFull:
                    return "queue_full";
                case BimDiagnosticSinkFailureCode.QueueContention:
                    return "queue_contention";
                case BimDiagnosticSinkFailureCode.PriorityEviction:
                    return "priority_eviction";
                case BimDiagnosticSinkFailureCode.RecordInvalid:
                    return "record_invalid";
                case BimDiagnosticSinkFailureCode.RecordOversize:
                    return "record_oversize";
                case BimDiagnosticSinkFailureCode.FileLimitReached:
                    return "file_limit_reached";
                case BimDiagnosticSinkFailureCode.DirectoryCreateFailure:
                    return "directory_create_failure";
                case BimDiagnosticSinkFailureCode.FileOpenFailure:
                    return "file_open_failure";
                case BimDiagnosticSinkFailureCode.FileWriteFailure:
                    return "file_write_failure";
                case BimDiagnosticSinkFailureCode.FileFlushFailure:
                    return "file_flush_failure";
                case BimDiagnosticSinkFailureCode.EncoderFailure:
                    return "encoder_failure";
                default:
                    throw new ArgumentOutOfRangeException(nameof(value));
            }
        }

        internal static string ToWire(BimDiagnosticStage value)
        {
            switch (value)
            {
                case BimDiagnosticStage.CoreInitialize:
                    return "core.initialize";
                case BimDiagnosticStage.ModuleResolve:
                    return "module.resolve";
                case BimDiagnosticStage.ModuleLoad:
                    return "module.load";
                case BimDiagnosticStage.ModuleActivate:
                    return "module.activate";
                case BimDiagnosticStage.ModuleMetadata:
                    return "module.metadata";
                case BimDiagnosticStage.HandlerDeserialize:
                    return "handler.deserialize";
                case BimDiagnosticStage.HandlerRuntime:
                    return "handler.runtime";
                case BimDiagnosticStage.HandlerSerialize:
                    return "handler.serialize";
                case BimDiagnosticStage.HandlerTerminal:
                    return "handler.terminal";
                case BimDiagnosticStage.RevitDispatchEnqueue:
                    return "revit.dispatch.enqueue";
                case BimDiagnosticStage.RevitDispatchExecute:
                    return "revit.dispatch.execute";
                case BimDiagnosticStage.RevitDocumentAcquire:
                    return "revit.document.acquire";
                case BimDiagnosticStage.RevitViewActiveGraphical:
                    return "revit.view.active_graphical";
                case BimDiagnosticStage.RevitDocumentCentralIsWorkshared:
                    return "revit.document.central_is_workshared";
                case BimDiagnosticStage.RevitDocumentCentralGuid:
                    return "revit.document.central_guid";
                case BimDiagnosticStage.RevitDocumentTitle:
                    return "revit.document.title";
                case BimDiagnosticStage.RevitDocumentPath:
                    return "revit.document.path";
                case BimDiagnosticStage.RevitDocumentIsFamily:
                    return "revit.document.is_family";
                case BimDiagnosticStage.RevitDocumentOutputIsWorkshared:
                    return "revit.document.output_is_workshared";
                case BimDiagnosticStage.RevitDocumentIsModelInCloud:
                    return "revit.document.is_model_in_cloud";
                case BimDiagnosticStage.RevitDocumentIsDetached:
                    return "revit.document.is_detached";
                case BimDiagnosticStage.RevitDocumentCentralModelPath:
                    return "revit.document.central_model_path";
                case BimDiagnosticStage.RevitDocumentModelPathEmpty:
                    return "revit.document.model_path_empty";
                case BimDiagnosticStage.RevitDocumentModelPathServer:
                    return "revit.document.model_path_server";
                case BimDiagnosticStage.RevitDocumentModelPathCloud:
                    return "revit.document.model_path_cloud";
                case BimDiagnosticStage.RevitDocumentIdentityClassify:
                    return "revit.document.identity_classify";
                case BimDiagnosticStage.RevitDocumentCreationGuid:
                    return "revit.document.creation_guid";
                case BimDiagnosticStage.RevitDocumentModelPathConvert:
                    return "revit.document.model_path_convert";
                case BimDiagnosticStage.RevitDocumentPathCanonicalize:
                    return "revit.document.path_canonicalize";
                case BimDiagnosticStage.RevitDocumentKeySource:
                    return "revit.document.key_source";
                case BimDiagnosticStage.RevitDocumentIdentityCompare:
                    return "revit.document.identity_compare";
                case BimDiagnosticStage.RevitCategoriesSettings:
                    return "revit.categories.settings";
                case BimDiagnosticStage.RevitCategoriesCollection:
                    return "revit.categories.collection";
                case BimDiagnosticStage.RevitCategoriesIterator:
                    return "revit.categories.iterator";
                case BimDiagnosticStage.RevitCategoriesMoveNext:
                    return "revit.categories.move_next";
                case BimDiagnosticStage.RevitCategoriesCurrent:
                    return "revit.categories.current";
                case BimDiagnosticStage.RevitCategoriesIteratorDispose:
                    return "revit.categories.iterator_dispose";
                case BimDiagnosticStage.RevitCategoryId:
                    return "revit.category.id";
                case BimDiagnosticStage.RevitCategoryName:
                    return "revit.category.name";
                case BimDiagnosticStage.RevitCategoryBuiltIn:
                    return "revit.category.built_in";
                case BimDiagnosticStage.RevitCategoryType:
                    return "revit.category.type";
                case BimDiagnosticStage.SinkWriter:
                    return "sink.writer";
                default:
                    throw new ArgumentOutOfRangeException(nameof(value));
            }
        }

        private static string Build(
            BimDiagnosticRecord record,
            BimDiagnosticExceptionInfo? exceptionInfo,
            bool truncated)
        {
            var builder = new StringBuilder(2048);
            builder.Append('{');
            AppendInteger(builder, "schemaVersion", 1, false);
            AppendString(builder, "recordKind", ToWire(record.Kind));
            AppendInteger(builder, "sequence", record.Sequence);
            AppendString(builder, "timestampUtc",
                record.TimestampUtc.ToUniversalTime().ToString(
                    "O", CultureInfo.InvariantCulture));
            AppendInteger(builder, "processId", record.ProcessId);
            AppendInteger(builder, "threadId", record.ThreadId);
            AppendString(builder, "correlationId", record.CorrelationId);
            AppendString(builder, "operation", record.Operation);
            AppendString(builder, "stage", ToWire(record.Stage));
            AppendString(builder, "outcome", ToWire(record.Outcome));
            AppendString(builder, "detailCode", ToWire(record.Fields.DetailCode));
            AppendNullableInteger(builder, "itemIndex", record.Fields.ItemIndex);
            AppendString(builder, "failureImpact",
                ToWire(record.Fields.FailureImpact));
            AppendNullableEnum(builder, "lastStage", record.LastStage, ToWire);
            AppendNullableEnum(builder, "lastOutcome", record.LastOutcome, ToWire);
            AppendNullableInteger(builder, "lastItemIndex", record.LastItemIndex);
            AppendNullableEnum(builder, "firstFailureStage",
                record.FirstFailureStage, ToWire);
            AppendString(builder, "firstFailureExceptionType",
                record.FirstFailureExceptionType);
            AppendNullableInteger(builder, "firstFailureHResult",
                record.FirstFailureHResult);
            AppendInteger(builder, "requestDroppedCount",
                record.RequestDroppedCount);
            AppendBoolean(builder, "traceComplete", record.TraceComplete);
            AppendString(builder, "coreVersion", record.CoreVersion);
            AppendString(builder, "coreCommit", record.CoreCommit);
            AppendString(builder, "moduleVersion", record.ModuleVersion);
            AppendString(builder, "moduleCommit", record.ModuleCommit);
            AppendString(builder, "exceptionType", exceptionInfo?.TypeName);
            AppendNullableInteger(builder, "exceptionHResult",
                exceptionInfo == null ? (int?)null : exceptionInfo.HResult);
            AppendString(builder, "exceptionStack", exceptionInfo?.Stack);
            AppendPropertyName(builder, "innerExceptions");
            AppendInnerExceptions(builder, exceptionInfo?.InnerExceptions);
            AppendBoolean(builder, "truncated", truncated);
            builder.Append('}');
            builder.Append('\n');
            return builder.ToString();
        }

        private static void AppendInnerExceptions(
            StringBuilder builder,
            IReadOnlyList<BimDiagnosticExceptionInfo>? values)
        {
            builder.Append('[');
            if (values != null)
            {
                for (var index = 0; index < values.Count; index++)
                {
                    if (index > 0)
                    {
                        builder.Append(',');
                    }

                    AppendException(builder, values[index]);
                }
            }

            builder.Append(']');
        }

        private static void AppendException(
            StringBuilder builder,
            BimDiagnosticExceptionInfo value)
        {
            builder.Append('{');
            AppendString(builder, "exceptionType", value.TypeName, false);
            AppendInteger(builder, "exceptionHResult", value.HResult);
            AppendString(builder, "exceptionStack", value.Stack);
            AppendPropertyName(builder, "innerExceptions");
            AppendInnerExceptions(builder, value.InnerExceptions);
            AppendBoolean(builder, "truncated", value.Truncated);
            builder.Append('}');
        }

        private static void AppendString(
            StringBuilder builder,
            string name,
            string? value,
            bool comma = true)
        {
            AppendPropertyName(builder, name, comma);
            if (value == null)
            {
                builder.Append("null");
                return;
            }

            builder.Append('"');
            AppendEscaped(builder, value);
            builder.Append('"');
        }

        private static void AppendInteger(
            StringBuilder builder,
            string name,
            long value,
            bool comma = true)
        {
            AppendPropertyName(builder, name, comma);
            builder.Append(value.ToString(CultureInfo.InvariantCulture));
        }

        private static void AppendNullableInteger(
            StringBuilder builder,
            string name,
            long? value)
        {
            AppendPropertyName(builder, name);
            if (value.HasValue)
            {
                builder.Append(value.Value.ToString(CultureInfo.InvariantCulture));
            }
            else
            {
                builder.Append("null");
            }
        }

        private static void AppendBoolean(
            StringBuilder builder,
            string name,
            bool value)
        {
            AppendPropertyName(builder, name);
            builder.Append(value ? "true" : "false");
        }

        private static void AppendNullableEnum<T>(
            StringBuilder builder,
            string name,
            T? value,
            Func<T, string> toWire)
            where T : struct
        {
            AppendString(builder, name,
                value.HasValue ? toWire(value.Value) : null);
        }

        private static void AppendPropertyName(
            StringBuilder builder,
            string name,
            bool comma = true)
        {
            if (comma)
            {
                builder.Append(',');
            }

            builder.Append('"');
            builder.Append(name);
            builder.Append("\":");
        }

        private static void AppendEscaped(StringBuilder builder, string value)
        {
            for (var index = 0; index < value.Length; index++)
            {
                var character = value[index];
                switch (character)
                {
                    case '"':
                        builder.Append("\\\"");
                        break;
                    case '\\':
                        builder.Append("\\\\");
                        break;
                    case '\b':
                        builder.Append("\\b");
                        break;
                    case '\f':
                        builder.Append("\\f");
                        break;
                    case '\n':
                        builder.Append("\\n");
                        break;
                    case '\r':
                        builder.Append("\\r");
                        break;
                    case '\t':
                        builder.Append("\\t");
                        break;
                    default:
                        if (character < 0x20)
                        {
                            builder.Append("\\u00");
                            builder.Append(((int)character).ToString(
                                "X2", CultureInfo.InvariantCulture));
                        }
                        else if (char.IsHighSurrogate(character))
                        {
                            if (index + 1 < value.Length &&
                                char.IsLowSurrogate(value[index + 1]))
                            {
                                builder.Append(character);
                                builder.Append(value[++index]);
                            }
                            else
                            {
                                builder.Append("\\uFFFD");
                            }
                        }
                        else if (char.IsLowSurrogate(character))
                        {
                            builder.Append("\\uFFFD");
                        }
                        else
                        {
                            builder.Append(character);
                        }

                        break;
                }
            }
        }

        private static bool Fits(string value)
        {
            return Encoding.UTF8.GetByteCount(value) <= MaximumEncodedBytes;
        }

        private static BimDiagnosticExceptionInfo? CloneBounded(
            BimDiagnosticExceptionInfo? source)
        {
            if (source == null)
            {
                return null;
            }

            var innerCount = 0;
            var root = CloneNode(source);
            CloneChildren(source, root, 0, ref innerCount, root);
            return root;
        }

        private static void CloneChildren(
            BimDiagnosticExceptionInfo source,
            BimDiagnosticExceptionInfo target,
            int depth,
            ref int innerCount,
            BimDiagnosticExceptionInfo root)
        {
            if (source.InnerExceptions.Count == 0)
            {
                return;
            }

            if (depth >= MaximumExceptionDepth)
            {
                target.Truncated = true;
                root.Truncated = true;
                return;
            }

            var children = new List<BimDiagnosticExceptionInfo>();
            for (var index = 0; index < source.InnerExceptions.Count; index++)
            {
                if (innerCount >= MaximumInnerExceptions)
                {
                    target.Truncated = true;
                    root.Truncated = true;
                    break;
                }

                var child = CloneNode(source.InnerExceptions[index]);
                children.Add(child);
                if (child.Truncated)
                {
                    root.Truncated = true;
                }

                innerCount++;
                CloneChildren(source.InnerExceptions[index], child,
                    depth + 1, ref innerCount, root);
            }

            target.InnerExceptions = children;
        }

        private static BimDiagnosticExceptionInfo CloneNode(
            BimDiagnosticExceptionInfo source)
        {
            var stack = source.Stack;
            var truncated = source.Truncated;
            if (stack != null && stack.Length > MaximumStackLength)
            {
                stack = stack.Substring(0, MaximumStackLength);
                truncated = true;
            }

            return new BimDiagnosticExceptionInfo
            {
                TypeName = BimDiagnosticContracts.BoundExceptionTypeName(
                    source.TypeName),
                HResult = source.HResult,
                Stack = stack,
                Truncated = truncated
            };
        }

        private static int GetMaximumDepth(BimDiagnosticExceptionInfo root)
        {
            var maximum = 0;
            var pending = new Stack<BimDiagnosticExceptionInfo>();
            var depths = new Stack<int>();
            pending.Push(root);
            depths.Push(0);
            while (pending.Count > 0)
            {
                var current = pending.Pop();
                var depth = depths.Pop();
                if (depth > maximum)
                {
                    maximum = depth;
                }

                for (var index = current.InnerExceptions.Count - 1;
                     index >= 0;
                     index--)
                {
                    pending.Push(current.InnerExceptions[index]);
                    depths.Push(depth + 1);
                }
            }

            return maximum;
        }

        private static void RemoveNodesAtDepth(
            BimDiagnosticExceptionInfo root,
            int targetDepth)
        {
            var pending = new Stack<BimDiagnosticExceptionInfo>();
            var depths = new Stack<int>();
            pending.Push(root);
            depths.Push(0);
            while (pending.Count > 0)
            {
                var current = pending.Pop();
                var depth = depths.Pop();
                if (depth == targetDepth - 1)
                {
                    if (current.InnerExceptions.Count > 0)
                    {
                        current.InnerExceptions =
                            Array.Empty<BimDiagnosticExceptionInfo>();
                        current.Truncated = true;
                    }

                    continue;
                }

                for (var index = current.InnerExceptions.Count - 1;
                     index >= 0;
                     index--)
                {
                    pending.Push(current.InnerExceptions[index]);
                    depths.Push(depth + 1);
                }
            }
        }
    }
}
