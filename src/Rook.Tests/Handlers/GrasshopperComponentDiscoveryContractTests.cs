using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
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
            var countDisagreement = new FakeServer(proxy)
            {
                SearchResults = new object[] { proxy },
                SearchScores = new[] { 1.0 },
                ReturnCount = 0
            };

            Assert.False(Search(nonfinite, "Series", null, 50, exact: false).Success);
            Assert.False(Search(misaligned, "Series", null, 50, exact: false).Success);
            Assert.False(Search(countDisagreement, "Series", null, 50, exact: false).Success);
            Assert.Equal(1, nonfinite.FindObjectsCalls);
            Assert.Equal(1, misaligned.FindObjectsCalls);
            Assert.Equal(1, countDisagreement.FindObjectsCalls);
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
        public void Raw_integer_exposure_fails_strict_projection()
        {
            var server = new FakeServer(Proxy(
                "Integer Exposure",
                exposureProjection: FakeExposureProjection.RawInteger));

            var response = Search(server, null, null, 50, exact: false);

            Assert.False(response.Success);
            Assert.Contains("Exposure", Assert.IsType<string>(response.Data), StringComparison.Ordinal);
        }

        [Theory]
        [InlineData(FakeExposureProjection.Null)]
        [InlineData(FakeExposureProjection.WrongType)]
        [InlineData(FakeExposureProjection.Throwing)]
        public void Invalid_proxy_exposure_fails_strict_projection(
            FakeExposureProjection exposureProjection)
        {
            var proxy = Proxy(
                "Invalid Exposure",
                exposureProjection: exposureProjection);
            var server = new FakeServer(proxy);

            var response = Search(server, null, null, 50, exact: false);

            Assert.False(response.Success);
            Assert.Contains("Exposure", Assert.IsType<string>(response.Data), StringComparison.Ordinal);
            Assert.Equal(1, proxy.ExposureReads);
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
            var visible = Proxy("Visible", guid: "00000000-0000-0000-0000-000000000001", exposure: 1);
            var obsolete = Proxy("Obsolete", guid: "00000000-0000-0000-0000-000000000002", obsolete: true);
            var hidden = Proxy("Hidden", guid: "00000000-0000-0000-0000-000000000003", exposure: 16);
            var quarantined = Proxy("Quarantined", guid: "00000000-0000-0000-0000-000000000004", exposure: 8);
            var server = new FakeServer(visible, obsolete, hidden, quarantined);

            var response = Audit(server, null, null, exact: false);
            var data = Data(response);

            Assert.True(response.Success);
            Assert.Equal(
                new[] { "totalScanned", "deprecatedCount", "obsoleteCount", "hiddenCount", "components" },
                data.EnumerateObject().Select(property => property.Name).ToArray());
            Assert.Equal(4, data.GetProperty("totalScanned").GetInt32());
            Assert.Equal(3, data.GetProperty("deprecatedCount").GetInt32());
            Assert.Equal(1, data.GetProperty("obsoleteCount").GetInt32());
            Assert.Equal(1, data.GetProperty("hiddenCount").GetInt32());
            var components = data.GetProperty("components").EnumerateArray().ToArray();
            Assert.Equal(new[] { "Obsolete", "Hidden", "Quarantined" }, components
                .Select(component => component.GetProperty("name").GetString()).ToArray());
            AssertAuditComponent(
                components[0],
                "Obsolete",
                "00000000-0000-0000-0000-000000000002",
                obsolete: true,
                exposure: 1,
                exposureLabel: "primary");
            AssertAuditComponent(
                components[1],
                "Hidden",
                "00000000-0000-0000-0000-000000000003",
                obsolete: false,
                exposure: 16,
                exposureLabel: "hidden");
            AssertAuditComponent(
                components[2],
                "Quarantined",
                "00000000-0000-0000-0000-000000000004",
                obsolete: false,
                exposure: 8,
                exposureLabel: "quarantine");
            Assert.Equal(0, server.FindObjectsCalls);
        }

        [Theory]
        [InlineData("{}")]
        [InlineData("{\"names\":[\"Series\"],\"guids\":[\"00000000-0000-0000-0000-000000000001\"]}")]
        [InlineData("{\"names\":[]}")]
        [InlineData("{\"names\":\"Series\"}")]
        [InlineData("{\"names\":[1]}")]
        public void Batch_metadata_refuses_invalid_selector_family_before_proxy_access(string body)
        {
            var server = new FakeServer(Proxy("Series"));

            var response = Batch(server, body);

            Assert.False(response.Success);
            Assert.Equal(0, server.ObjectProxiesReads);
            Assert.Equal(0, server.FindObjectsCalls);
        }

        [Fact]
        public void Name_batch_preserves_order_case_duplicates_and_local_ambiguity()
        {
            const string uniqueGuid = "10000000-0000-0000-0000-000000000001";
            var unique = Proxy(
                "Unique",
                guid: uniqueGuid,
                libraryGuid: "20000000-0000-0000-0000-000000000001",
                componentFactory: () => new FakeComponent(Guid.Parse(uniqueGuid)));
            var duplicateOne = Proxy("Duplicate", guid: "30000000-0000-0000-0000-000000000001");
            var duplicateTwo = Proxy("Duplicate", guid: "30000000-0000-0000-0000-000000000002");
            var hiddenDuplicate = Proxy(
                "Duplicate",
                guid: "30000000-0000-0000-0000-000000000003",
                exposure: 16);
            var server = new FakeServer(unique, duplicateTwo, hiddenDuplicate, duplicateOne);
            server.AddAssembly(unique.LibraryGuid, AssemblyInfo());

            var response = Batch(
                server,
                "{\"names\":[\"uNiQuE\",\"Missing\",\"Duplicate\",\"uNiQuE\"]}");

            Assert.True(response.Success);
            var data = Data(response);
            Assert.Equal(4, data.GetProperty("count").GetInt32());
            Assert.Equal(2, data.GetProperty("errors").GetInt32());
            var results = Results(response);
            Assert.Equal(
                new[] { "uNiQuE", "Missing", "Duplicate", "uNiQuE" },
                results.Select(ResultSelectorValue).ToArray());
            Assert.Equal(
                new[] { "success", "not_found", "ambiguous_name", "success" },
                results.Select(item => item.GetProperty("status").GetString()).ToArray());
            Assert.Equal(
                new[]
                {
                    "30000000-0000-0000-0000-000000000001",
                    "30000000-0000-0000-0000-000000000002"
                },
                results[2].GetProperty("candidates").EnumerateArray()
                    .Select(item => item.GetProperty("guid").GetString()).ToArray());
            Assert.Equal(2, unique.CreateInstanceCalls);
            Assert.Equal(0, duplicateOne.CreateInstanceCalls);
            Assert.Equal(0, duplicateTwo.CreateInstanceCalls);
            Assert.Equal(0, hiddenDuplicate.CreateInstanceCalls);
            Assert.Equal(1, server.ObjectProxiesReads);
            Assert.Equal(0, server.FindObjectsCalls);
        }

        [Fact]
        public void Guid_batch_correlates_invalid_missing_success_and_duplicates()
        {
            const string guid = "40000000-0000-0000-0000-000000000001";
            var proxy = Proxy(
                "Selected",
                guid: guid,
                exposure: 16,
                libraryGuid: "40000000-0000-0000-0000-000000000002",
                componentFactory: () => new FakeComponent(Guid.Parse(guid)));
            var server = new FakeServer(proxy);
            server.AddAssembly(proxy.LibraryGuid, AssemblyInfo());

            var response = Batch(
                server,
                "{\"guids\":[\"not-a-guid\",\"40000000-0000-0000-0000-000000000099\",\"40000000-0000-0000-0000-000000000001\",\"40000000-0000-0000-0000-000000000001\"]}");

            Assert.True(response.Success);
            var results = Results(response);
            Assert.Equal(
                new[] { "invalid_guid", "not_found", "success", "success" },
                results.Select(item => item.GetProperty("status").GetString()).ToArray());
            Assert.Equal("not-a-guid", ResultSelectorValue(results[0]));
            Assert.False(results[0].TryGetProperty("guid", out _));
            Assert.Equal(
                "40000000-0000-0000-0000-000000000099",
                results[1].GetProperty("guid").GetString());
            Assert.All(results.Skip(2), item => Assert.Equal(guid, item.GetProperty("guid").GetString()));
            Assert.Equal(2, proxy.CreateInstanceCalls);
            Assert.Equal(1, server.ObjectProxiesReads);
        }

        [Fact]
        public void Unsupported_proxy_kind_is_a_correlated_projection_failure()
        {
            const string guid = "50000000-0000-0000-0000-000000000001";
            var proxy = Proxy("Unsupported", guid: guid, kind: FakeProxyKind.Unsupported);
            var server = new FakeServer(proxy);

            var response = Batch(server, $"{{\"guids\":[\"{guid}\"]}}");

            Assert.True(response.Success);
            var result = Assert.Single(Results(response));
            Assert.Equal("projection_failure", result.GetProperty("status").GetString());
            Assert.Equal("proxy_projection_failed", result.GetProperty("error").GetString());
            Assert.Equal(guid, result.GetProperty("guid").GetString());
            Assert.False(result.TryGetProperty("sourceKind", out _));
            Assert.Equal(0, proxy.CreateInstanceCalls);
        }

        [Fact]
        public void Compiled_metadata_uses_selected_library_and_exact_implementation_sources()
        {
            const string guid = "60000000-0000-0000-0000-000000000001";
            const string libraryGuid = "60000000-0000-0000-0000-000000000002";
            var parameters = new FakeParamsServer(
                new object[] { new FakeParam { Name = "Input", NickName = "I", TypeName = "Number", Description = "in" } },
                new object[] { new FakeParam { Name = "Output", NickName = "O", TypeName = "Number", Description = "out" } });
            var proxy = Proxy(
                "Compiled",
                guid: guid,
                libraryGuid: libraryGuid,
                componentFactory: () => new FakeComponent(Guid.Parse(guid), parameters));
            var server = new FakeServer(proxy);
            var assemblyInfo = AssemblyInfo();
            server.AddAssembly(Guid.Parse(libraryGuid), assemblyInfo);

            var result = Assert.Single(Results(Batch(server, $"{{\"guids\":[\"{guid.ToUpperInvariant()}\"]}}")));

            Assert.Equal("success", result.GetProperty("status").GetString());
            Assert.Equal(guid, result.GetProperty("guid").GetString());
            Assert.Equal("compiled", result.GetProperty("sourceKind").GetString());
            Assert.Equal(
                new[]
                {
                    "selector", "status", "guid", "name", "nickName", "description",
                    "category", "subCategory", "sourceKind", "provenance", "implementation", "params"
                },
                result.EnumerateObject().Select(property => property.Name).ToArray());
            var provenance = result.GetProperty("provenance");
            Assert.Equal(
                new[]
                {
                    "libraryGuid", "libraryName", "libraryVersion", "assemblyFullName",
                    "assemblyVersion", "assemblyLocation"
                },
                provenance.EnumerateObject().Select(property => property.Name).ToArray());
            Assert.Equal(libraryGuid, provenance.GetProperty("libraryGuid").GetString());
            Assert.Equal(assemblyInfo.Name, provenance.GetProperty("libraryName").GetString());
            Assert.Equal(assemblyInfo.Version, provenance.GetProperty("libraryVersion").GetString());
            Assert.Equal(assemblyInfo.Assembly!.FullName, provenance.GetProperty("assemblyFullName").GetString());
            Assert.Equal(assemblyInfo.AssemblyVersion, provenance.GetProperty("assemblyVersion").GetString());
            Assert.Equal(assemblyInfo.Location, provenance.GetProperty("assemblyLocation").GetString());
            var implementation = result.GetProperty("implementation");
            Assert.Equal(
                new[]
                {
                    "baseGuid", "componentGuid", "runtimeType", "runtimeAssemblyName",
                    "runtimeAssemblyVersion", "runtimeAssemblyLocation"
                },
                implementation.EnumerateObject().Select(property => property.Name).ToArray());
            Assert.Equal(JsonValueKind.Null, implementation.GetProperty("baseGuid").ValueKind);
            Assert.Equal(guid, implementation.GetProperty("componentGuid").GetString());
            Assert.Equal(typeof(FakeComponent).FullName, implementation.GetProperty("runtimeType").GetString());
            Assert.NotEqual(typeof(FakeComponent).Name, implementation.GetProperty("runtimeType").GetString());
            Assert.Equal(typeof(FakeComponent).Assembly.GetName().Name, implementation.GetProperty("runtimeAssemblyName").GetString());
            Assert.Equal(typeof(FakeComponent).Assembly.GetName().Version!.ToString(), implementation.GetProperty("runtimeAssemblyVersion").GetString());
            Assert.Equal(typeof(FakeComponent).Assembly.Location, implementation.GetProperty("runtimeAssemblyLocation").GetString());
            var projectedParams = result.GetProperty("params");
            Assert.Equal("Input", projectedParams.GetProperty("inputs")[0].GetProperty("name").GetString());
            Assert.Equal("Output", projectedParams.GetProperty("outputs")[0].GetProperty("name").GetString());
            Assert.Equal(1, server.FindAssemblyCalls);
        }

        [Fact]
        public void Missing_compiled_provenance_retains_proxy_and_stops_before_instantiation()
        {
            const string guid = "70000000-0000-0000-0000-000000000001";
            var proxy = Proxy("Compiled", guid: guid, componentFactory: () => new FakeComponent(Guid.Parse(guid)));

            var result = Assert.Single(Results(Batch(new FakeServer(proxy), $"{{\"guids\":[\"{guid}\"]}}")));

            Assert.Equal("projection_failure", result.GetProperty("status").GetString());
            Assert.Equal("provenance_projection_failed", result.GetProperty("error").GetString());
            Assert.Equal("Compiled", result.GetProperty("name").GetString());
            Assert.Equal("compiled", result.GetProperty("sourceKind").GetString());
            Assert.False(result.TryGetProperty("provenance", out _));
            Assert.False(result.TryGetProperty("implementation", out _));
            Assert.False(result.TryGetProperty("params", out _));
            Assert.Equal(0, proxy.CreateInstanceCalls);
        }

        [Fact]
        public void Unique_name_and_guid_return_the_same_metadata_shape_after_selector()
        {
            const string guid = "75000000-0000-0000-0000-000000000001";
            var proxy = Proxy(
                "Shared Shape",
                guid: guid,
                libraryGuid: "75000000-0000-0000-0000-000000000002",
                componentFactory: () => new FakeComponent(Guid.Parse(guid)));
            var server = new FakeServer(proxy);
            server.AddAssembly(proxy.LibraryGuid, AssemblyInfo());

            var byName = Assert.Single(Results(Batch(server, "{\"names\":[\"Shared Shape\"]}")));
            var byGuid = Assert.Single(Results(Batch(server, $"{{\"guids\":[\"{guid}\"]}}")));

            Assert.Equal("name", byName.GetProperty("selector").GetProperty("kind").GetString());
            Assert.Equal("guid", byGuid.GetProperty("selector").GetProperty("kind").GetString());
            Assert.Equal(
                byName.EnumerateObject().Skip(1).Select(property => (property.Name, property.Value.GetRawText())).ToArray(),
                byGuid.EnumerateObject().Skip(1).Select(property => (property.Name, property.Value.GetRawText())).ToArray());
        }

        [Theory]
        [InlineData(false)]
        [InlineData(true)]
        public void User_object_provenance_uses_exact_path_and_paired_content_fields(bool nullData)
        {
            const string guid = "80000000-0000-0000-0000-000000000001";
            const string baseGuid = "80000000-0000-0000-0000-000000000002";
            const string path = "C:\\synthetic\\user.ghuser";
            var proxy = Proxy(
                "User",
                guid: guid,
                kind: FakeProxyKind.UserObject,
                location: path,
                componentFactory: () => new FakeComponent(Guid.Parse(guid)));
            var data = nullData ? null : new byte[] { 1, 2, 3 };

            var result = Assert.Single(Results(Batch(
                new FakeServer(proxy),
                $"{{\"guids\":[\"{guid}\"]}}",
                actualPath => new FakeUserObject
                {
                    Path = actualPath,
                    BaseGuid = Guid.Parse(baseGuid),
                    Data = data
                })));

            Assert.Equal("success", result.GetProperty("status").GetString());
            var provenance = result.GetProperty("provenance");
            Assert.Equal(
                new[] { "path", "contentByteLength", "contentSha256" },
                provenance.EnumerateObject().Select(property => property.Name).ToArray());
            Assert.Equal(path, provenance.GetProperty("path").GetString());
            if (nullData)
            {
                Assert.Equal(JsonValueKind.Null, provenance.GetProperty("contentByteLength").ValueKind);
                Assert.Equal(JsonValueKind.Null, provenance.GetProperty("contentSha256").ValueKind);
            }
            else
            {
                Assert.Equal(3, provenance.GetProperty("contentByteLength").GetInt64());
                using var sha = SHA256.Create();
                Assert.Equal(
                    BitConverter.ToString(sha.ComputeHash(new byte[] { 1, 2, 3 })).Replace("-", ""),
                    provenance.GetProperty("contentSha256").GetString());
            }
            Assert.Equal(baseGuid, result.GetProperty("implementation").GetProperty("baseGuid").GetString());
        }

        [Theory]
        [InlineData("different_path")]
        [InlineData("invalid_path")]
        [InlineData("construction")]
        [InlineData("unexpected_data")]
        [InlineData("throwing_data")]
        public void User_object_provenance_failures_retain_proxy_and_stop_later_phases(string failure)
        {
            const string guid = "90000000-0000-0000-0000-000000000001";
            const string path = "C:\\synthetic\\user.ghuser";
            var proxy = Proxy(
                "User",
                guid: guid,
                kind: FakeProxyKind.UserObject,
                location: path,
                componentFactory: () => new FakeComponent(Guid.Parse(guid)));

            object Factory(string actualPath) => failure switch
            {
                "different_path" => new FakeUserObject { Path = "C:\\synthetic\\other.ghuser", BaseGuid = Guid.NewGuid(), Data = null },
                "invalid_path" => new FakeUserObject { Path = "\0", BaseGuid = Guid.NewGuid(), Data = null },
                "construction" => throw new InvalidOperationException("Synthetic construction failure."),
                "unexpected_data" => new FakeUserObject { Path = actualPath, BaseGuid = Guid.NewGuid(), Data = "bytes" },
                _ => new ThrowingDataUserObject { Path = actualPath, BaseGuid = Guid.NewGuid() }
            };

            var result = Assert.Single(Results(Batch(
                new FakeServer(proxy),
                $"{{\"guids\":[\"{guid}\"]}}",
                Factory)));

            Assert.Equal("projection_failure", result.GetProperty("status").GetString());
            Assert.Equal("provenance_projection_failed", result.GetProperty("error").GetString());
            Assert.Equal("User", result.GetProperty("name").GetString());
            Assert.Equal("user_object", result.GetProperty("sourceKind").GetString());
            Assert.False(result.TryGetProperty("provenance", out _));
            Assert.False(result.TryGetProperty("implementation", out _));
            Assert.Equal(0, proxy.CreateInstanceCalls);
        }

        [Fact]
        public void Instantiation_and_implementation_failures_preserve_completed_prefixes()
        {
            const string instantiationGuid = "a0000000-0000-0000-0000-000000000001";
            const string implementationGuid = "a0000000-0000-0000-0000-000000000002";
            var instantiation = Proxy(
                "Instantiation",
                guid: instantiationGuid,
                libraryGuid: "a0000000-0000-0000-0000-000000000011",
                componentFactory: () => throw new InvalidOperationException("synthetic"));
            var implementation = Proxy(
                "Implementation",
                guid: implementationGuid,
                libraryGuid: "a0000000-0000-0000-0000-000000000012",
                componentFactory: () => new MissingComponentGuidComponent());
            var server = new FakeServer(instantiation, implementation);
            server.AddAssembly(instantiation.LibraryGuid, AssemblyInfo());
            server.AddAssembly(implementation.LibraryGuid, AssemblyInfo());

            var results = Results(Batch(
                server,
                $"{{\"guids\":[\"{instantiationGuid}\",\"{implementationGuid}\"]}}"));

            Assert.Equal("instantiation_failure", results[0].GetProperty("status").GetString());
            Assert.Equal("component_instantiation_failed", results[0].GetProperty("error").GetString());
            Assert.True(results[0].TryGetProperty("provenance", out _));
            Assert.False(results[0].TryGetProperty("implementation", out _));
            Assert.Equal("projection_failure", results[1].GetProperty("status").GetString());
            Assert.Equal("implementation_projection_failed", results[1].GetProperty("error").GetString());
            Assert.True(results[1].TryGetProperty("provenance", out _));
            Assert.False(results[1].TryGetProperty("implementation", out _));
            Assert.False(results[1].TryGetProperty("params", out _));
        }

        [Fact]
        public void Params_null_including_existing_caught_exception_remains_success()
        {
            const string nullGuid = "b0000000-0000-0000-0000-000000000001";
            const string throwingGuid = "b0000000-0000-0000-0000-000000000002";
            var nullParams = Proxy(
                "Null Params",
                guid: nullGuid,
                libraryGuid: "b0000000-0000-0000-0000-000000000011",
                componentFactory: () => new FakeComponent(Guid.Parse(nullGuid)));
            var throwingParams = Proxy(
                "Throwing Params",
                guid: throwingGuid,
                libraryGuid: "b0000000-0000-0000-0000-000000000012",
                componentFactory: () => new ThrowingParamsComponent(Guid.Parse(throwingGuid)));
            var server = new FakeServer(nullParams, throwingParams);
            server.AddAssembly(nullParams.LibraryGuid, AssemblyInfo());
            server.AddAssembly(throwingParams.LibraryGuid, AssemblyInfo());

            var results = Results(Batch(
                server,
                $"{{\"guids\":[\"{nullGuid}\",\"{throwingGuid}\"]}}"));

            Assert.All(results, result => Assert.Equal("success", result.GetProperty("status").GetString()));
            Assert.All(results, result => Assert.Equal(JsonValueKind.Null, result.GetProperty("params").ValueKind));
        }

        [Fact]
        public void An_admitted_all_failure_batch_is_still_complete()
        {
            var response = Batch(
                new FakeServer(),
                "{\"guids\":[\"bad\",\"c0000000-0000-0000-0000-000000000001\"]}");

            Assert.True(response.Success);
            var data = Data(response);
            Assert.Equal(2, data.GetProperty("count").GetInt32());
            Assert.Equal(2, data.GetProperty("errors").GetInt32());
            Assert.Equal(2, data.GetProperty("results").GetArrayLength());
        }

        [Theory]
        [InlineData("throwing")]
        [InlineData("null")]
        [InlineData("wrong_type")]
        public void User_object_BaseGuid_failure_belongs_to_implementation_and_preserves_provenance(
            string failure)
        {
            const string guid = "d0000000-0000-0000-0000-000000000001";
            const string path = "C:\\synthetic\\base-guid.ghuser";
            var proxy = Proxy(
                "Base Guid",
                guid: guid,
                kind: FakeProxyKind.UserObject,
                location: path,
                componentFactory: () => new FakeComponent(Guid.Parse(guid)));

            object Factory(string actualPath) => failure switch
            {
                "throwing" => new ThrowingBaseGuidUserObject { Path = actualPath, Data = new byte[] { 4, 5 } },
                "null" => new FlexibleBaseGuidUserObject { Path = actualPath, BaseGuid = null, Data = new byte[] { 4, 5 } },
                _ => new FlexibleBaseGuidUserObject { Path = actualPath, BaseGuid = "not-a-guid", Data = new byte[] { 4, 5 } }
            };

            var result = Assert.Single(Results(Batch(
                new FakeServer(proxy),
                $"{{\"guids\":[\"{guid}\"]}}",
                Factory)));

            Assert.Equal("projection_failure", result.GetProperty("status").GetString());
            Assert.Equal("implementation_projection_failed", result.GetProperty("error").GetString());
            var provenance = result.GetProperty("provenance");
            Assert.Equal(path, provenance.GetProperty("path").GetString());
            Assert.Equal(2, provenance.GetProperty("contentByteLength").GetInt64());
            Assert.Equal(
                "2FA1B377BF67309F65E5E7BC9D924345CA648DEC4E601A398A9CB497DCBA3765",
                provenance.GetProperty("contentSha256").GetString());
            Assert.False(result.TryGetProperty("implementation", out _));
            Assert.False(result.TryGetProperty("params", out _));
            Assert.Equal(1, proxy.CreateInstanceCalls);
        }

        [Fact]
        public void Malformed_proxy_failure_is_selector_local_and_mixed_batch_outcomes_survive()
        {
            const string goodGuid = "e0000000-0000-0000-0000-000000000001";
            var good = Proxy(
                "Good",
                guid: goodGuid,
                libraryGuid: "e0000000-0000-0000-0000-000000000002",
                componentFactory: () => new FakeComponent(Guid.Parse(goodGuid)));
            var malformed = new ThrowingGuidProxy("Affected");
            var server = new FakeServer(good, malformed);
            server.AddAssembly(good.LibraryGuid, AssemblyInfo());

            var response = Batch(server, "{\"names\":[\"Good\",\"Affected\",\"Good\"]}");

            Assert.True(response.Success);
            var results = Results(response);
            Assert.Equal(
                new[] { "success", "projection_failure", "success" },
                results.Select(result => result.GetProperty("status").GetString()).ToArray());
            Assert.Equal("proxy_projection_failed", results[1].GetProperty("error").GetString());
            Assert.Equal(
                new[] { "Good", "Affected", "Good" },
                results.Select(ResultSelectorValue).ToArray());
            Assert.Equal(2, good.CreateInstanceCalls);
            Assert.Equal(1, server.ObjectProxiesReads);
            Assert.Equal(0, server.FindObjectsCalls);
        }

        [Fact]
        public void Guid_resolution_preserves_exact_match_but_never_guesses_not_found_after_incomplete_scan()
        {
            const string goodGuid = "f0000000-0000-0000-0000-000000000001";
            const string missingGuid = "f0000000-0000-0000-0000-000000000099";
            var good = Proxy(
                "Good Guid",
                guid: goodGuid,
                libraryGuid: "f0000000-0000-0000-0000-000000000002",
                componentFactory: () => new FakeComponent(Guid.Parse(goodGuid)));
            var server = new FakeServer(new ThrowingGuidProxy("Unknown Guid"), good);
            server.AddAssembly(good.LibraryGuid, AssemblyInfo());

            var results = Results(Batch(
                server,
                $"{{\"guids\":[\"{goodGuid}\",\"{missingGuid}\"]}}"));

            Assert.Equal("success", results[0].GetProperty("status").GetString());
            Assert.Equal("projection_failure", results[1].GetProperty("status").GetString());
            Assert.Equal("proxy_projection_failed", results[1].GetProperty("error").GetString());
            Assert.Equal(missingGuid, results[1].GetProperty("guid").GetString());
            Assert.Equal(1, good.CreateInstanceCalls);
            Assert.Equal(1, server.ObjectProxiesReads);
        }

        [Fact]
        public void Name_resolution_does_not_read_exposure_after_obsolete_already_excludes_proxy()
        {
            const string guid = "f1000000-0000-0000-0000-000000000001";
            var selected = Proxy(
                "Eligible",
                guid: guid,
                libraryGuid: "f1000000-0000-0000-0000-000000000002",
                componentFactory: () => new FakeComponent(Guid.Parse(guid)));
            var excluded = new ObsoleteThrowingExposureProxy("Eligible");
            var server = new FakeServer(excluded, selected);
            server.AddAssembly(selected.LibraryGuid, AssemblyInfo());

            var result = Assert.Single(Results(Batch(server, "{\"names\":[\"Eligible\"]}")));

            Assert.Equal("success", result.GetProperty("status").GetString());
            Assert.Equal(guid, result.GetProperty("guid").GetString());
            Assert.Equal(1, selected.CreateInstanceCalls);
            Assert.Equal(0, excluded.ExposureReads);
        }

        private static void AssertAuditComponent(
            JsonElement component,
            string name,
            string guid,
            bool obsolete,
            int exposure,
            string exposureLabel)
        {
            Assert.Equal(
                new[]
                {
                    "name", "nickName", "category", "subCategory", "guid", "obsolete",
                    "exposure", "exposureLabel"
                },
                component.EnumerateObject().Select(property => property.Name).ToArray());
            Assert.Equal(name, component.GetProperty("name").GetString());
            Assert.Equal(name + " Nick", component.GetProperty("nickName").GetString());
            Assert.Equal("Synthetic", component.GetProperty("category").GetString());
            Assert.Equal("Operators", component.GetProperty("subCategory").GetString());
            Assert.Equal(guid, component.GetProperty("guid").GetString());
            Assert.Equal(obsolete, component.GetProperty("obsolete").GetBoolean());
            Assert.Equal(exposure, component.GetProperty("exposure").GetInt32());
            Assert.Equal(exposureLabel, component.GetProperty("exposureLabel").GetString());
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

        private static JsonElement[] Results(ApiResponse response) =>
            Data(response).GetProperty("results").EnumerateArray().ToArray();

        private static string? ResultSelectorValue(JsonElement result) =>
            result.GetProperty("selector").GetProperty("value").GetString();

        private static ApiResponse Batch(
            FakeServer server,
            string body,
            Func<string, object>? userObjectFactory = null)
        {
            var method = typeof(GrasshopperHandler).GetMethod(
                "HandleBatchComponentInfoFromServer",
                BindingFlags.Instance | BindingFlags.NonPublic);
            Assert.NotNull(method);
            return Assert.IsType<ApiResponse>(method!.Invoke(
                new GrasshopperHandler(runningAsRhinoInside: () => false),
                new object?[] { server, body, userObjectFactory }));
        }

        private static FakeAssemblyInfo AssemblyInfo() => new()
        {
            Name = "Synthetic Library",
            Version = "1.2.3",
            Assembly = typeof(FakeComponent).Assembly,
            AssemblyVersion = "1.2.3.4",
            Location = "C:/synthetic/Synthetic.gha"
        };

        private static FakeProxy Proxy(
            string name,
            string? category = "Synthetic",
            string? subCategory = "Operators",
            string? guid = null,
            FakeProxyKind kind = FakeProxyKind.CompiledObject,
            bool obsolete = false,
            int exposure = 1,
            int compareRank = 0,
            bool compareThrows = false,
            FakeExposureProjection exposureProjection = FakeExposureProjection.Enum,
            string? libraryGuid = null,
            string location = "C:/synthetic/component.ghuser",
            Func<object?>? componentFactory = null) =>
            new(
                name,
                guid == null ? Guid.NewGuid() : Guid.Parse(guid),
                kind,
                obsolete,
                exposure,
                compareRank,
                compareThrows,
                category,
                subCategory,
                exposureProjection,
                libraryGuid == null ? Guid.NewGuid() : Guid.Parse(libraryGuid),
                location,
                componentFactory);

        private enum FakeProxyKind
        {
            CompiledObject,
            UserObject,
            Unsupported
        }

        [Flags]
        private enum FakeExposure
        {
            Primary = 1,
            Secondary = 2,
            Tertiary = 4,
            Quarantine = 8,
            Hidden = 16,
            Obscure = 32
        }

        public enum FakeExposureProjection
        {
            Enum,
            RawInteger,
            Null,
            WrongType,
            Throwing
        }

        private sealed class FakeDescription
        {
            public string Name { get; }
            public string? NickName { get; }
            public string? Description { get; }
            public string? Category { get; }
            public string? SubCategory { get; }

            public FakeDescription(
                string name,
                string? category,
                string? subCategory)
            {
                Name = name;
                NickName = name + " Nick";
                Description = name + " description";
                Category = category;
                SubCategory = subCategory;
            }
        }

        private sealed class FakeProxy
        {
            private readonly bool _compareThrows;
            private readonly object? _exposure;
            private readonly bool _throwOnExposure;

            public object Desc { get; }
            public Guid Guid { get; }
            public Guid LibraryGuid { get; }
            public FakeProxyKind Kind { get; }
            public bool Obsolete { get; }
            public string Location { get; }
            public int CompareRank { get; }
            public int CreateInstanceCalls { get; private set; }
            public int DataReadCalls { get; private set; }
            public int ExposureReads { get; private set; }

            public bool CompareThrows => _compareThrows;

            public object? Exposure
            {
                get
                {
                    ExposureReads++;
                    if (_throwOnExposure)
                        throw new InvalidOperationException("Synthetic Exposure getter failure.");
                    return _exposure;
                }
            }

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
                string? subCategory,
                FakeExposureProjection exposureProjection,
                Guid libraryGuid,
                string location,
                Func<object?>? componentFactory)
            {
                Desc = new FakeDescription(name, category, subCategory);
                _exposure = exposureProjection switch
                {
                    FakeExposureProjection.Enum => (FakeExposure)exposure,
                    FakeExposureProjection.RawInteger => exposure,
                    FakeExposureProjection.Null => null,
                    FakeExposureProjection.WrongType => "primary",
                    FakeExposureProjection.Throwing => null,
                    _ => throw new ArgumentOutOfRangeException(nameof(exposureProjection))
                };
                _throwOnExposure = exposureProjection == FakeExposureProjection.Throwing;
                Guid = guid;
                LibraryGuid = libraryGuid;
                Kind = kind;
                Obsolete = obsolete;
                Location = location;
                CompareRank = compareRank;
                _compareThrows = compareThrows;
                ComponentFactory = componentFactory;
            }

            public Func<object?>? ComponentFactory { get; set; }

            public object? CreateInstance()
            {
                CreateInstanceCalls++;
                if (ComponentFactory == null)
                    throw new InvalidOperationException("Discovery must not instantiate candidates.");
                return ComponentFactory();
            }
        }

        private sealed class FakeServer
        {
            private readonly IReadOnlyList<object> _proxies;
            private readonly Dictionary<Guid, object?> _assemblies = new();

            public static int CompareCalls { get; private set; }
            public IReadOnlyList<object> ObjectProxies
            {
                get
                {
                    ObjectProxiesReads++;
                    return _proxies;
                }
            }
            public object[]? SearchResults { get; set; }
            public double[]? SearchScores { get; set; }
            public int? ReturnCount { get; set; }
            public bool ThrowOnFind { get; set; }
            public int FindObjectsCalls { get; private set; }
            public int ObjectProxiesReads { get; private set; }
            public int FindAssemblyCalls { get; private set; }
            public string[]? LastTerms { get; private set; }
            public int LastMaximumResults { get; private set; }

            public FakeServer(params object[] proxies)
            {
                _proxies = proxies;
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

            public void AddAssembly(Guid libraryGuid, object? assemblyInfo) =>
                _assemblies[libraryGuid] = assemblyInfo;

            public object? FindAssembly(Guid libraryGuid)
            {
                FindAssemblyCalls++;
                return _assemblies.TryGetValue(libraryGuid, out var assemblyInfo)
                    ? assemblyInfo
                    : null;
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

        private sealed class FakeAssemblyInfo
        {
            public string? Name { get; init; }
            public string? Version { get; init; }
            public Assembly? Assembly { get; init; }
            public string? AssemblyVersion { get; init; }
            public string? Location { get; init; }
        }

        private sealed class FakeUserObject
        {
            public string Path { get; init; } = null!;
            public Guid BaseGuid { get; init; }
            public object? Data { get; init; }
        }

        private sealed class ThrowingDataUserObject
        {
            public string Path { get; init; } = null!;
            public Guid BaseGuid { get; init; }
            public object Data => throw new InvalidOperationException("Synthetic Data getter failure.");
        }

        private sealed class FlexibleBaseGuidUserObject
        {
            public string Path { get; init; } = null!;
            public object? BaseGuid { get; init; }
            public object? Data { get; init; }
        }

        private sealed class ThrowingBaseGuidUserObject
        {
            public string Path { get; init; } = null!;
            public object BaseGuid => throw new InvalidOperationException("Synthetic BaseGuid getter failure.");
            public object? Data { get; init; }
        }

        private sealed class ThrowingGuidProxy
        {
            public object Desc { get; }
            public Guid Guid => throw new InvalidOperationException("Synthetic Guid getter failure.");
            public Guid LibraryGuid { get; } = Guid.NewGuid();
            public FakeProxyKind Kind { get; } = FakeProxyKind.CompiledObject;
            public bool Obsolete { get; } = false;
            public FakeExposure Exposure { get; } = FakeExposure.Primary;
            public string Location { get; } = "C:/synthetic/malformed.ghuser";

            public ThrowingGuidProxy(string name)
            {
                Desc = new FakeDescription(name, "Synthetic", "Operators");
            }

            public object CreateInstance() =>
                throw new InvalidOperationException("Malformed proxy must not be instantiated.");
        }

        private sealed class ObsoleteThrowingExposureProxy
        {
            public FakeDescription Desc { get; }
            public Guid Guid { get; } = Guid.NewGuid();
            public bool Obsolete { get; } = true;
            public int ExposureReads { get; private set; }
            public FakeExposure Exposure
            {
                get
                {
                    ExposureReads++;
                    throw new InvalidOperationException("Synthetic Exposure getter failure.");
                }
            }

            public ObsoleteThrowingExposureProxy(string name)
            {
                Desc = new FakeDescription(name, "Synthetic", "Operators");
            }
        }

        private sealed class FakeComponent
        {
            public Guid ComponentGuid { get; }
            public object? Params { get; }

            public FakeComponent(Guid componentGuid, object? parameters = null)
            {
                ComponentGuid = componentGuid;
                Params = parameters;
            }
        }

        private sealed class MissingComponentGuidComponent
        {
            public object? Params => null;
        }

        private sealed class ThrowingParamsComponent
        {
            public Guid ComponentGuid { get; }
            public object Params => throw new InvalidOperationException("Synthetic Params getter failure.");

            public ThrowingParamsComponent(Guid componentGuid)
            {
                ComponentGuid = componentGuid;
            }
        }

        private sealed class FakeParamsServer
        {
            public IReadOnlyList<object> Input { get; }
            public IReadOnlyList<object> Output { get; }

            public FakeParamsServer(IReadOnlyList<object> input, IReadOnlyList<object> output)
            {
                Input = input;
                Output = output;
            }
        }

        private sealed class FakeParam
        {
            public string Name { get; init; } = null!;
            public string NickName { get; init; } = null!;
            public string TypeName { get; init; } = null!;
            public string Access { get; init; } = "item";
            public bool Optional { get; init; }
            public string Description { get; init; } = null!;
            public bool Hidden { get; init; }
            public int SourceCount { get; init; }
            public IReadOnlyList<object> Recipients { get; init; } = Array.Empty<object>();
        }
    }
}
