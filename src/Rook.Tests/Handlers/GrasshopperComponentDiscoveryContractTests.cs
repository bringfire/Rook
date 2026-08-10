using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using Rook;
using Rook.Handlers;
using Xunit;

namespace Rook.Tests.Handlers
{
    public sealed class GrasshopperComponentDiscoveryContractTests
    {
        private static readonly JsonSerializerOptions JsonOptions = new()
        {
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase
        };

        [Fact]
        public void Search_present_calls_FindObjects_once_with_exact_string_and_proxy_count()
        {
            var selected = Proxy("Series", kind: FakeProxyKind.CompiledObject);
            var server = new FakeServer(selected, Proxy("Other"));
            server.SearchResults = new object[] { selected };
            server.SearchScores = new[] { 17.5 };

            var response = Search(server, "  Series  ", null, 50, exact: false);

            Assert.True(response.Success);
            Assert.Equal(1, server.FindObjectsCalls);
            Assert.Equal("  Series  ", Assert.Single(server.LastTerms!));
            Assert.Equal(2, server.LastMaximumResults);
            var component = Assert.Single(Components(response));
            Assert.Equal(17.5, component.GetProperty("nativeScore").GetDouble());
            Assert.Equal("native_search", component.GetProperty("matchSource").GetString());
        }

        [Fact]
        public void Search_filters_category_and_exact_before_limit()
        {
            var wrongName = Proxy("Series Extra", category: "Sets");
            var wrongCategory = Proxy("Series", category: "Maths");
            var first = Proxy("Series", category: "Sets", subCategory: "Sequence", compareRank: 1);
            var second = Proxy("Series", category: "Sets", subCategory: "Sequence", compareRank: 2);
            var server = new FakeServer(wrongName, wrongCategory, first, second)
            {
                SearchResults = new object[] { wrongName, wrongCategory, second, first },
                SearchScores = new[] { 100.0, 90.0, 80.0, 70.0 }
            };

            var response = Search(server, "Series", "Sequence", 1, exact: true);

            Assert.True(response.Success);
            var data = Data(response);
            Assert.Equal(1, data.GetProperty("count").GetInt32());
            Assert.Equal(2, data.GetProperty("totalMatches").GetInt32());
            Assert.True(data.GetProperty("truncated").GetBoolean());
            Assert.Equal("Series", Assert.Single(Components(response)).GetProperty("name").GetString());
        }

        [Fact]
        public void Search_orders_score_then_CompareProxies_then_guid()
        {
            var lowerScore = Proxy("Lower", guid: "00000000-0000-0000-0000-000000000001", compareRank: 0);
            var tieLater = Proxy("Tie Later", guid: "00000000-0000-0000-0000-000000000003", compareRank: 2);
            var tieGuidHigh = Proxy("Tie Guid High", guid: "00000000-0000-0000-0000-000000000002", compareRank: 1);
            var tieGuidLow = Proxy("Tie Guid Low", guid: "00000000-0000-0000-0000-000000000001", compareRank: 1);
            var server = new FakeServer(lowerScore, tieLater, tieGuidHigh, tieGuidLow)
            {
                SearchResults = new object[] { lowerScore, tieLater, tieGuidHigh, tieGuidLow },
                SearchScores = new[] { 1.0, 2.0, 2.0, 2.0 }
            };

            var names = Components(Search(server, "Tie", null, 50, exact: false))
                .Select(item => item.GetProperty("name").GetString())
                .ToArray();

            Assert.Equal(new[] { "Tie Guid Low", "Tie Guid High", "Tie Later", "Lower" }, names);
            Assert.True(FakeServer.CompareCalls > 0);
        }

        [Fact]
        public void Search_rejects_nonfinite_or_misaligned_native_projection()
        {
            var proxy = Proxy("Series");
            var nonfinite = new FakeServer(proxy)
            {
                SearchResults = new object[] { proxy },
                SearchScores = new[] { double.NaN }
            };
            var misaligned = new FakeServer(proxy)
            {
                SearchResults = new object[] { proxy },
                SearchScores = Array.Empty<double>()
            };

            Assert.False(Search(nonfinite, "Series", null, 50, exact: false).Success);
            Assert.False(Search(misaligned, "Series", null, 50, exact: false).Success);
            Assert.Equal(1, nonfinite.FindObjectsCalls);
            Assert.Equal(1, misaligned.FindObjectsCalls);
        }

        [Fact]
        public void Native_search_or_compare_failure_has_no_fallback_result()
        {
            var proxy = Proxy("Series");
            var findFailure = new FakeServer(proxy) { ThrowOnFind = true };
            var compareFailureProxy = Proxy("Series 2", compareThrows: true);
            var compareFailure = new FakeServer(proxy, compareFailureProxy)
            {
                SearchResults = new object[] { proxy, compareFailureProxy },
                SearchScores = new[] { 1.0, 1.0 }
            };

            Assert.False(Search(findFailure, "Series", null, 50, exact: false).Success);
            Assert.False(Search(compareFailure, "Series", null, 50, exact: false).Success);
            Assert.Equal(1, findFailure.FindObjectsCalls);
            Assert.Equal(1, compareFailure.FindObjectsCalls);
        }

        [Fact]
        public void Catalog_omitted_or_empty_search_never_calls_FindObjects_and_omits_match_fields()
        {
            var later = Proxy("Later", guid: "00000000-0000-0000-0000-000000000002", compareRank: 2);
            var first = Proxy("First", guid: "00000000-0000-0000-0000-000000000001", compareRank: 1);
            var server = new FakeServer(later, first);

            var omitted = Search(server, null, null, 50, exact: true);
            var empty = Search(server, "", null, 50, exact: true);

            Assert.Equal(0, server.FindObjectsCalls);
            Assert.Equal(new[] { "First", "Later" }, Components(omitted)
                .Select(item => item.GetProperty("name").GetString()).ToArray());
            foreach (var component in Components(empty))
            {
                Assert.False(component.TryGetProperty("nativeScore", out _));
                Assert.False(component.TryGetProperty("matchSource", out _));
            }
        }

        [Fact]
        public void Empty_category_means_no_filter_and_whitespace_category_is_literal()
        {
            var ordinary = Proxy("Ordinary", category: "Maths");
            var whitespace = Proxy("Whitespace", category: "A   B");
            var server = new FakeServer(ordinary, whitespace);

            Assert.Equal(2, Components(Search(server, null, "", 50, exact: false)).Length);
            Assert.Equal("Whitespace", Assert.Single(
                Components(Search(server, null, "   ", 50, exact: false)))
                .GetProperty("name").GetString());
        }

        [Fact]
        public void Ordinary_eligibility_excludes_hidden_and_obsolete_only()
        {
            var visible = Proxy("Visible", exposure: 1, compareRank: 1);
            var quarantined = Proxy("Quarantined", exposure: 8, compareRank: 2);
            var obscure = Proxy("Obscure", exposure: 32, compareRank: 3);
            var hidden = Proxy("Hidden", exposure: 16, compareRank: 4);
            var obsolete = Proxy("Obsolete", obsolete: true, compareRank: 5);
            var server = new FakeServer(visible, quarantined, obscure, hidden, obsolete);

            var names = Components(Search(server, null, null, 50, exact: false))
                .Select(item => item.GetProperty("name").GetString())
                .ToArray();

            Assert.Equal(new[] { "Visible", "Quarantined", "Obscure" }, names);
        }

        [Fact]
        public void Exact_name_preserves_native_and_third_party_duplicates()
        {
            var compiled = Proxy("Addition", kind: FakeProxyKind.CompiledObject, compareRank: 1);
            var userObject = Proxy("Addition", kind: FakeProxyKind.UserObject, compareRank: 2);
            var server = new FakeServer(compiled, userObject)
            {
                SearchResults = new object[] { userObject, compiled },
                SearchScores = new[] { 3.0, 2.0 }
            };

            var components = Components(Search(server, "addition", null, 50, exact: true));

            Assert.Equal(2, components.Length);
            Assert.Equal(new[] { "user_object", "compiled" }, components
                .Select(item => item.GetProperty("sourceKind").GetString()).ToArray());
            Assert.All(components, item => Assert.Equal("exact_name", item.GetProperty("matchSource").GetString()));
        }

        [Fact]
        public void Unknown_kind_fails_without_candidate_list()
        {
            var server = new FakeServer(Proxy("Unknown", kind: FakeProxyKind.Unsupported));

            var response = Search(server, null, null, 50, exact: false);

            Assert.False(response.Success);
            Assert.IsType<string>(response.Data);
            Assert.DoesNotContain("components", (string)response.Data!, StringComparison.OrdinalIgnoreCase);
        }

        [Fact]
        public void Search_and_catalog_never_instantiate_or_read_user_object_data()
        {
            var proxy = Proxy("User Tool", kind: FakeProxyKind.UserObject);
            var server = new FakeServer(proxy)
            {
                SearchResults = new object[] { proxy },
                SearchScores = new[] { 1.0 }
            };

            Assert.True(Search(server, null, null, 50, exact: false).Success);
            Assert.True(Search(server, "User Tool", null, 50, exact: false).Success);
            Assert.Equal(0, proxy.CreateInstanceCalls);
            Assert.Equal(0, proxy.DataReadCalls);
        }

        [Fact]
        public void Ordinary_counts_are_complete_and_exact()
        {
            var proxies = Enumerable.Range(1, 4)
                .Select(index => Proxy($"Item {index}", compareRank: index))
                .ToArray();
            var server = new FakeServer(proxies);

            var data = Data(Search(server, null, null, 2, exact: false));

            Assert.Equal(2, data.GetProperty("count").GetInt32());
            Assert.Equal(2, data.GetProperty("returnedCount").GetInt32());
            Assert.Equal(4, data.GetProperty("totalMatches").GetInt32());
            Assert.True(data.GetProperty("truncated").GetBoolean());
            Assert.Equal(2, data.GetProperty("components").GetArrayLength());
        }

        [Fact]
        public void Audit_branch_shape_and_source_path_remain_unchanged()
        {
            var visible = Proxy("Visible", exposure: 1);
            var obsolete = Proxy("Obsolete", obsolete: true);
            var hidden = Proxy("Hidden", exposure: 16);
            var quarantined = Proxy("Quarantined", exposure: 8);
            var server = new FakeServer(visible, obsolete, hidden, quarantined);

            var response = Audit(server, null, null, exact: false);
            var data = Data(response);

            Assert.True(response.Success);
            Assert.Equal(4, data.GetProperty("totalScanned").GetInt32());
            Assert.Equal(3, data.GetProperty("deprecatedCount").GetInt32());
            Assert.Equal(1, data.GetProperty("obsoleteCount").GetInt32());
            Assert.Equal(1, data.GetProperty("hiddenCount").GetInt32());
            foreach (var component in data.GetProperty("components").EnumerateArray())
            {
                Assert.False(component.TryGetProperty("sourceKind", out _));
                Assert.False(component.TryGetProperty("nativeScore", out _));
            }
            Assert.Equal(0, server.FindObjectsCalls);
        }

        private static ApiResponse Search(
            FakeServer server,
            string? search,
            string? category,
            int limit,
            bool exact)
        {
            var method = typeof(GrasshopperHandler).GetMethod(
                "SearchLibraryFromComponentServer",
                BindingFlags.Instance | BindingFlags.NonPublic);
            Assert.NotNull(method);
            return Assert.IsType<ApiResponse>(method!.Invoke(
                new GrasshopperHandler(runningAsRhinoInside: () => false),
                new object?[] { server, search, category, limit, exact }));
        }

        private static ApiResponse Audit(FakeServer server, string? search, string? category, bool exact)
        {
            var method = typeof(GrasshopperHandler).GetMethod(
                "SearchLibraryAuditUnchanged",
                BindingFlags.Instance | BindingFlags.NonPublic);
            Assert.NotNull(method);
            return Assert.IsType<ApiResponse>(method!.Invoke(
                new GrasshopperHandler(runningAsRhinoInside: () => false),
                new object?[] { server, search, category, exact }));
        }

        private static JsonElement Data(ApiResponse response) =>
            JsonSerializer.SerializeToElement(response.Data, JsonOptions);

        private static JsonElement[] Components(ApiResponse response) =>
            Data(response).GetProperty("components").EnumerateArray().ToArray();

        private static FakeProxy Proxy(
            string name,
            string? category = "Synthetic",
            string? subCategory = "Operators",
            string? guid = null,
            FakeProxyKind kind = FakeProxyKind.CompiledObject,
            bool obsolete = false,
            int exposure = 1,
            int compareRank = 0,
            bool compareThrows = false) =>
            new(
                name,
                guid == null ? Guid.NewGuid() : Guid.Parse(guid),
                kind,
                obsolete,
                exposure,
                compareRank,
                compareThrows,
                category,
                subCategory);

        private enum FakeProxyKind
        {
            CompiledObject,
            UserObject,
            Unsupported
        }

        private sealed class FakeDescription
        {
            public string Name { get; }
            public string? NickName { get; }
            public string? Description { get; }
            public string? Category { get; }
            public string? SubCategory { get; }
            public int Exposure { get; }

            public FakeDescription(
                string name,
                string? category,
                string? subCategory,
                int exposure)
            {
                Name = name;
                NickName = name + " Nick";
                Description = name + " description";
                Category = category;
                SubCategory = subCategory;
                Exposure = exposure;
            }
        }

        private sealed class FakeProxy
        {
            private readonly bool _compareThrows;

            public FakeDescription Desc { get; }
            public Guid Guid { get; }
            public Guid LibraryGuid { get; } = Guid.NewGuid();
            public FakeProxyKind Kind { get; }
            public bool Obsolete { get; }
            public string Location { get; } = "C:/synthetic/component.ghuser";
            public int CompareRank { get; }
            public int CreateInstanceCalls { get; private set; }
            public int DataReadCalls { get; private set; }

            public bool CompareThrows => _compareThrows;

            public object Data
            {
                get
                {
                    DataReadCalls++;
                    throw new InvalidOperationException("Discovery must not read user-object data.");
                }
            }

            public FakeProxy(
                string name,
                Guid guid,
                FakeProxyKind kind,
                bool obsolete,
                int exposure,
                int compareRank,
                bool compareThrows,
                string? category,
                string? subCategory)
            {
                Desc = new FakeDescription(name, category, subCategory, exposure);
                Guid = guid;
                Kind = kind;
                Obsolete = obsolete;
                CompareRank = compareRank;
                _compareThrows = compareThrows;
            }

            public object CreateInstance()
            {
                CreateInstanceCalls++;
                throw new InvalidOperationException("Discovery must not instantiate candidates.");
            }
        }

        private sealed class FakeServer
        {
            private readonly IReadOnlyList<object> _proxies;

            public static int CompareCalls { get; private set; }
            public IReadOnlyList<object> ObjectProxies => _proxies;
            public object[]? SearchResults { get; set; }
            public double[]? SearchScores { get; set; }
            public int? ReturnCount { get; set; }
            public bool ThrowOnFind { get; set; }
            public int FindObjectsCalls { get; private set; }
            public string[]? LastTerms { get; private set; }
            public int LastMaximumResults { get; private set; }

            public FakeServer(params FakeProxy[] proxies)
            {
                _proxies = proxies.Cast<object>().ToArray();
                SearchResults = _proxies.ToArray();
                SearchScores = Enumerable.Repeat(1.0, proxies.Length).ToArray();
                CompareCalls = 0;
            }

            public int FindObjects(
                string[] terms,
                int maximumResults,
                out object[] proxies,
                out double[] weights)
            {
                FindObjectsCalls++;
                LastTerms = terms;
                LastMaximumResults = maximumResults;
                if (ThrowOnFind)
                    throw new InvalidOperationException("Synthetic native search failure.");

                proxies = SearchResults!;
                weights = SearchScores!;
                return ReturnCount ?? proxies.Length;
            }

            public static int CompareProxies(object left, object right)
            {
                CompareCalls++;
                var leftProxy = Assert.IsType<FakeProxy>(left);
                var rightProxy = Assert.IsType<FakeProxy>(right);
                if (leftProxy.CompareThrows || rightProxy.CompareThrows)
                    throw new InvalidOperationException("Synthetic proxy comparison failure.");
                return leftProxy.CompareRank.CompareTo(rightProxy.CompareRank);
            }
        }
    }
}
