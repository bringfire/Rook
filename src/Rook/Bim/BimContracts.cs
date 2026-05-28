using System;
using System.Collections.Generic;

namespace Rook.Bim
{
    public enum BimErrorCode
    {
        None,
        RookBimUnavailable,
        NotRhinoInside,
        RevitUnavailable,
        NoActiveDocument,
        NoActiveView,
        InvalidScope,
        UnboundedDocumentQuery,
        InvalidCategory,
        AmbiguousParameter,
        QueryLimitExceeded,
        ElementNotFound,
        DocumentMismatch,
        LinkedElementUnsupported,
        CapabilityUnavailable,
        SelectionFailed,
        InternalError
    }

    public enum BimDocumentGuidSource
    {
        RevitPersistentGuid,
        PathFallback,
        Unavailable
    }

    public enum BimIdentityConfidence
    {
        Exact,
        Inferred,
        Unresolved,
        Unsupported
    }

    public enum BimQueryScope
    {
        ActiveView,
        Document
    }

    public enum BimFilterOperation
    {
        Equals,
        NotEquals,
        Contains,
        IsEmpty,
        IsNotEmpty
    }

    public sealed class BimValidationResult
    {
        public bool Success { get; set; }

        public BimErrorCode ErrorCode { get; set; }

        public string? Message { get; set; }

        public static BimValidationResult Ok
        {
            get
            {
                return new BimValidationResult
                {
                    Success = true,
                    ErrorCode = BimErrorCode.None
                };
            }
        }
    }

    public static class BimFilterSemantics
    {
        public static bool MissingParameterMatches(BimFilterOperation operation)
        {
            switch (operation)
            {
                case BimFilterOperation.NotEquals:
                case BimFilterOperation.IsEmpty:
                    return true;
                case BimFilterOperation.Equals:
                case BimFilterOperation.Contains:
                case BimFilterOperation.IsNotEmpty:
                default:
                    return false;
            }
        }
    }

    public sealed class BimApiResponse
    {
        public bool Success { get; set; }

        public BimErrorCode ErrorCode { get; set; }

        public string? Message { get; set; }

        public object? Data { get; set; }

        public int HttpStatus { get; set; } = 200;

        public static BimApiResponse Ok(object? data)
        {
            return new BimApiResponse
            {
                Success = true,
                ErrorCode = BimErrorCode.None,
                Data = data,
                HttpStatus = 200
            };
        }

        public static BimApiResponse Fail(
            BimErrorCode code,
            string message,
            int httpStatus)
        {
            return new BimApiResponse
            {
                Success = false,
                ErrorCode = code,
                Message = message,
                HttpStatus = httpStatus
            };
        }
    }

    public sealed class BimStatusResponse
    {
        public bool Available { get; set; }

        public string Runtime { get; set; } = "unavailable";

        public string? ErrorCode { get; set; }

        public string? Message { get; set; }

        public string Host { get; set; } = "unknown";

        public string Module { get; set; } = "core";
    }

    public sealed class BimDocumentIdentity
    {
        public string? Guid { get; set; }

        public BimDocumentGuidSource GuidSource { get; set; } = BimDocumentGuidSource.Unavailable;

        public string? Title { get; set; }

        public string? Path { get; set; }

        public bool IsFamilyDocument { get; set; }

        public bool IsWorkshared { get; set; }
    }

    public sealed class BimViewIdentity
    {
        public int Id { get; set; }

        public string? UniqueId { get; set; }

        public string? Name { get; set; }
    }

    public sealed class BimElementIdentity
    {
        public string Source { get; set; } = "revit";

        public string? DocumentGuid { get; set; }

        public BimDocumentGuidSource DocumentGuidSource { get; set; } = BimDocumentGuidSource.Unavailable;

        public string? DocumentTitle { get; set; }

        public string? DocumentPath { get; set; }

        public int? ElementId { get; set; }

        public string? UniqueId { get; set; }

        public string? FullUniqueId { get; set; }

        public bool Linked { get; set; }

        public int? LinkInstanceId { get; set; }

        public string? LinkInstanceUniqueId { get; set; }

        public string? LinkedDocumentGuid { get; set; }

        public int? LinkedElementId { get; set; }

        public string? LinkedElementUniqueId { get; set; }

        public bool Resolved { get; set; }

        public BimIdentityConfidence Confidence { get; set; } = BimIdentityConfidence.Unresolved;
    }

    public sealed class BimCategorySummary
    {
        public int? Id { get; set; }

        public string? Name { get; set; }
    }

    public sealed class BimElementTypeSummary
    {
        public int? Id { get; set; }

        public string? UniqueId { get; set; }

        public string? FamilyName { get; set; }

        public string? Name { get; set; }
    }

    public sealed class BimElementSummary
    {
        public BimElementIdentity Identity { get; set; } = new BimElementIdentity();

        public string? Name { get; set; }

        public BimCategorySummary Category { get; set; } = new BimCategorySummary();

        public BimElementTypeSummary Type { get; set; } = new BimElementTypeSummary();
    }

    public sealed class BimQuerySummary
    {
        public string? Category { get; set; }

        public int Limit { get; set; }

        public int Returned { get; set; }

        public bool Truncated { get; set; }

        public Dictionary<string, int> MissingParameterCounts { get; set; } = new Dictionary<string, int>();
    }

    public sealed class BimQueryElementsResult
    {
        public BimDocumentIdentity Document { get; set; } = new BimDocumentIdentity();

        public BimQueryScope Scope { get; set; } = BimQueryScope.ActiveView;

        public BimViewIdentity? View { get; set; }

        public BimQuerySummary Query { get; set; } = new BimQuerySummary();

        public List<BimElementSummary> Elements { get; set; } = new List<BimElementSummary>();
    }

    public sealed class BimQueryFilter
    {
        public string? Parameter { get; set; }

        public BimFilterOperation Operation { get; set; }

        public string? Value { get; set; }
    }

    public sealed class BimQueryElementsRequest
    {
        public const int DefaultLimit = 100;

        public const int HardMaxLimit = 1000;

        public BimQueryScope? Scope { get; set; }

        public string? Category { get; set; }

        public int? Limit { get; set; }

        public List<BimQueryFilter> Filters { get; set; } = new List<BimQueryFilter>();

        public BimQueryScope EffectiveScope
        {
            get { return Scope ?? BimQueryScope.ActiveView; }
        }

        public int EffectiveLimit
        {
            get { return Limit ?? DefaultLimit; }
        }

        public IReadOnlyList<BimQueryFilter> EffectiveFilters
        {
            get
            {
                if (Filters == null)
                {
                    return Array.Empty<BimQueryFilter>();
                }

                return Filters;
            }
        }

        public BimValidationResult Validate()
        {
            if (EffectiveLimit < 1 || EffectiveLimit > HardMaxLimit)
            {
                return Fail(
                    BimErrorCode.QueryLimitExceeded,
                    "limit must be between 1 and 1000");
            }

            if (Scope.HasValue && !Enum.IsDefined(typeof(BimQueryScope), Scope.Value))
            {
                return Fail(
                    BimErrorCode.InvalidScope,
                    "scope is invalid");
            }

            if (EffectiveScope == BimQueryScope.Document && string.IsNullOrWhiteSpace(Category))
            {
                return Fail(
                    BimErrorCode.UnboundedDocumentQuery,
                    "document scope requires category in Phase 1");
            }

            foreach (var filter in EffectiveFilters)
            {
                if (filter == null)
                {
                    return Fail(
                        BimErrorCode.InvalidScope,
                        "filter is required");
                }

                if (!Enum.IsDefined(typeof(BimFilterOperation), filter.Operation))
                {
                    return Fail(
                        BimErrorCode.InvalidScope,
                        "invalid filter operation");
                }

                if (string.IsNullOrWhiteSpace(filter.Parameter))
                {
                    return Fail(
                        BimErrorCode.InvalidScope,
                        "filter parameter is required");
                }
            }

            return BimValidationResult.Ok;
        }

        private static BimValidationResult Fail(BimErrorCode code, string message)
        {
            return new BimValidationResult
            {
                Success = false,
                ErrorCode = code,
                Message = message
            };
        }
    }

    public sealed class BimElementRequest
    {
        public BimElementIdentity Identity { get; set; } = new BimElementIdentity();
    }

    public sealed class BimSelectElementsRequest
    {
        public List<BimElementIdentity> Identities { get; set; } = new List<BimElementIdentity>();
    }
}
