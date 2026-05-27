using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim
{
    public class RookBimContractsTests
    {
        [Fact]
        public void QueryElementsRequest_UsesPhaseOneDefaults()
        {
            var request = new BimQueryElementsRequest();

            Assert.Equal(BimQueryScope.ActiveView, request.EffectiveScope);
            Assert.Equal(100, request.EffectiveLimit);
            Assert.Equal(1000, BimQueryElementsRequest.HardMaxLimit);
        }

        [Fact]
        public void Validate_RejectsDocumentScopeWithFiltersAndNoCategory()
        {
            var request = new BimQueryElementsRequest
            {
                Scope = BimQueryScope.Document,
                Filters =
                {
                    new BimQueryFilter
                    {
                        Parameter = "Mark",
                        Operation = BimFilterOperation.Equals,
                        Value = "A101"
                    }
                }
            };

            var result = request.Validate();

            Assert.False(result.Success);
            Assert.Equal(BimErrorCode.UnboundedDocumentQuery, result.ErrorCode);
            Assert.Contains("document scope requires category", result.Message);
        }

        [Fact]
        public void Validate_RejectsUndefinedScope()
        {
            var request = new BimQueryElementsRequest
            {
                Scope = (BimQueryScope)999
            };

            var result = request.Validate();

            Assert.False(result.Success);
            Assert.Equal(BimErrorCode.InvalidScope, result.ErrorCode);
            Assert.Contains("scope is invalid", result.Message);
        }

        [Fact]
        public void Validate_RejectsUndefinedFilterOperation()
        {
            var request = new BimQueryElementsRequest
            {
                Filters =
                {
                    new BimQueryFilter
                    {
                        Parameter = "Mark",
                        Operation = (BimFilterOperation)999,
                        Value = "A101"
                    }
                }
            };

            var result = request.Validate();

            Assert.False(result.Success);
            Assert.Equal(BimErrorCode.InvalidScope, result.ErrorCode);
            Assert.Contains("invalid filter operation", result.Message);
        }

        [Fact]
        public void Validate_TreatsNullFiltersAsEmpty()
        {
            var request = new BimQueryElementsRequest
            {
                Filters = null!
            };

            var exception = Record.Exception(() => request.Validate());
            var result = request.Validate();

            Assert.Null(exception);
            Assert.True(result.Success);
            Assert.Equal(BimErrorCode.None, result.ErrorCode);
            Assert.Empty(request.EffectiveFilters);
        }

        [Fact]
        public void Validate_RejectsNullFilterEntry()
        {
            var request = new BimQueryElementsRequest();
            request.Filters.Add(null!);

            var result = request.Validate();

            Assert.False(result.Success);
            Assert.Equal(BimErrorCode.InvalidScope, result.ErrorCode);
            Assert.Contains("filter is required", result.Message);
        }

        [Theory]
        [InlineData(BimFilterOperation.Equals, false)]
        [InlineData(BimFilterOperation.Contains, false)]
        [InlineData(BimFilterOperation.NotEquals, true)]
        [InlineData(BimFilterOperation.IsEmpty, true)]
        [InlineData(BimFilterOperation.IsNotEmpty, false)]
        public void MissingParameterMatches_UsesPinnedFilterSemantics(
            BimFilterOperation operation,
            bool expected)
        {
            Assert.Equal(expected, BimFilterSemantics.MissingParameterMatches(operation));
        }

        [Fact]
        public void DocumentIdentity_IncludesApprovedDocumentFields()
        {
            var identity = new BimDocumentIdentity
            {
                Guid = "doc-guid"
            };

            string? guid = identity.Guid;
            string? title = identity.Title;
            string? path = identity.Path;

            Assert.Equal("doc-guid", guid);
            Assert.Equal(BimDocumentGuidSource.Unavailable, identity.GuidSource);
            Assert.Null(title);
            Assert.Null(path);
            Assert.False(identity.IsFamilyDocument);
            Assert.False(identity.IsWorkshared);
        }

        [Fact]
        public void ViewIdentity_UsesApprovedIntIdContract()
        {
            var identity = new BimViewIdentity
            {
                Id = 17
            };

            int id = identity.Id;

            Assert.Equal(17, id);
        }

        [Fact]
        public void ElementIdentity_UsesApprovedIdentityShape()
        {
            var identity = new BimElementIdentity
            {
                DocumentGuid = "doc-guid",
                ElementId = 123,
                LinkInstanceId = 456,
                LinkedDocumentGuid = "linked-doc-guid",
                LinkedElementId = 789
            };

            string? documentGuid = identity.DocumentGuid;
            string? documentTitle = identity.DocumentTitle;
            string? documentPath = identity.DocumentPath;
            int? elementId = identity.ElementId;
            string? uniqueId = identity.UniqueId;
            string? fullUniqueId = identity.FullUniqueId;
            int? linkInstanceId = identity.LinkInstanceId;
            string? linkInstanceUniqueId = identity.LinkInstanceUniqueId;
            string? linkedDocumentGuid = identity.LinkedDocumentGuid;
            int? linkedElementId = identity.LinkedElementId;
            string? linkedElementUniqueId = identity.LinkedElementUniqueId;

            Assert.Equal("revit", identity.Source);
            Assert.Equal("doc-guid", documentGuid);
            Assert.Equal(BimDocumentGuidSource.Unavailable, identity.DocumentGuidSource);
            Assert.Null(documentTitle);
            Assert.Null(documentPath);
            Assert.Equal(123, elementId);
            Assert.Null(uniqueId);
            Assert.Null(fullUniqueId);
            Assert.False(identity.Linked);
            Assert.Equal(456, linkInstanceId);
            Assert.Null(linkInstanceUniqueId);
            Assert.Equal("linked-doc-guid", linkedDocumentGuid);
            Assert.Equal(789, linkedElementId);
            Assert.Null(linkedElementUniqueId);
            Assert.False(identity.Resolved);
            Assert.Equal(BimIdentityConfidence.Unresolved, identity.Confidence);
        }

        [Fact]
        public void QueryElementsResult_UsesStructuredQueryAndElementSummaries()
        {
            var result = new BimQueryElementsResult
            {
                Query =
                {
                    Category = "Walls",
                    Limit = 100,
                    Returned = 1,
                    Truncated = false,
                    MissingParameterCounts =
                    {
                        ["FireRating"] = 2
                    }
                },
                Elements =
                {
                    new BimElementSummary
                    {
                        Name = "Basic Wall",
                        Category =
                        {
                            Id = 2000011,
                            Name = "Walls"
                        },
                        Type =
                        {
                            Id = 42,
                            UniqueId = "type-unique-id",
                            FamilyName = "Basic Wall",
                            Name = "Generic - 8\""
                        }
                    }
                }
            };

            Assert.NotNull(result.Query);
            Assert.Equal("Walls", result.Query.Category);
            Assert.Equal(100, result.Query.Limit);
            Assert.Equal(1, result.Query.Returned);
            Assert.False(result.Query.Truncated);
            Assert.Equal(2, result.Query.MissingParameterCounts["FireRating"]);

            var element = Assert.Single(result.Elements);
            Assert.NotNull(element.Category);
            int? categoryId = element.Category.Id;
            Assert.Equal(2000011, element.Category.Id);
            Assert.Equal(2000011, categoryId);
            Assert.Equal("Walls", element.Category.Name);
            Assert.NotNull(element.Type);
            int? typeId = element.Type.Id;
            Assert.Equal(42, element.Type.Id);
            Assert.Equal(42, typeId);
            Assert.Equal("type-unique-id", element.Type.UniqueId);
            Assert.Equal("Basic Wall", element.Type.FamilyName);
            Assert.Equal("Generic - 8\"", element.Type.Name);
        }
    }
}
