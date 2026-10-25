using System;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using Rook.Services.Vision;
using Rook.Services.Vision.Fal.Models;
using Rook.Services.Vision.Image;
using Xunit;

namespace Rook.Tests.Services.Vision.Fal
{
    public class FalCatalogCompilerTests
    {
        [Fact]
        public void Complete_synthetic_definition_resolves_exact_binding()
        {
            using var files = new CatalogFiles();
            var result = files.Compile();
            Assert.Empty(result.Diagnostics);
            var binding = result.Catalog!.GetOperation("synthetic/image", "text_to_image");
            Assert.Equal("fal-ai/synthetic/render", binding.EndpointId);
            Assert.Equal("fal.image.declarative", binding.AdapterId);
            Assert.Equal(1, binding.AdapterVersion);
            Assert.Equal("revision-1", binding.Revision);
            Assert.Equal(64, binding.DefinitionHash.Length);
            Assert.False(result.Catalog.TryGetOperation("synthetic/image", "guessed_suffix", out _));
            Assert.Throws<System.Collections.Generic.KeyNotFoundException>(() => result.Catalog.GetOperation("synthetic/image", "guessed_suffix"));
        }

        [Theory]
        [InlineData("/host", "\"https://evil.example\"")]
        [InlineData("/schema_version", "2")]
        [InlineData("/provider", "\"other\"")]
        [InlineData("/status", "\"unknown\"")]
        [InlineData("/operations/0/adapter/id", "\"arbitrary.dll\"")]
        [InlineData("/operations/0/adapter/version", "2")]
        [InlineData("/operations/0/endpoint_id", "\"https://fal.run/evil\"")]
        [InlineData("/operations/0/endpoint_id", "\"fal-ai/../evil\"")]
        [InlineData("/operations/0/lifecycle_root", "\"fal-ai/other\"")]
        [InlineData("/operations/0/fields/0/extra", "true")]
        [InlineData("/operations/0/fields/0/payload/conversion", "\"eval\"")]
        [InlineData("/operations/0/fields/0/default", "null")]
        [InlineData("/operations/0/fields/1/default", "\"true\"")]
        [InlineData("/operations/0/fields/2/default", "9")]
        [InlineData("/operations/0/fields/3/default", "9007199254740993")]
        [InlineData("/operations/0/fields/3/min", "-9007199254740992")]
        [InlineData("/operations/0/fields/3/step", "0")]
        [InlineData("/operations/0/fields/4/default", "0.1234567890123456789012345678")]
        [InlineData("/operations/0/fields/4/min", "-1000000001")]
        [InlineData("/operations/0/fields/4/max", "1000000001")]
        [InlineData("/operations/0/fields/4/step", "0.0000001")]
        [InlineData("/operations/0/fields/4/default", "0.15")]
        [InlineData("/operations/0/fields/5/default", "\"unknown\"")]
        [InlineData("/operations/0/constraints/0/when/0/value", "false")]
        [InlineData("/operations/0/constraints/0/field", "\"missing\"")]
        [InlineData("/operations/0/constants/0/pointer", "\"/prompt/child\"")]
        [InlineData("/operations/0/constants/0/pointer", "\"/prompt\"")]
        [InlineData("/operations/0/result/cardinality", "2")]
        [InlineData("/operations/0/result/url_pointer", "\"/images/~2/url\"")]
        [InlineData("/operations/0/result/mime_family", "\"video\"")]
        [InlineData("/operations/0/pricing/rates/0/rate_usd", "-1")]
        [InlineData("/operations/0/evidence/url", "\"file:///c:/secret\"")]
        [InlineData("/operations/0/evidence/reviewed_on", "\"yesterday\"")]
        public void Closed_vocabulary_rejects_invalid_values(string pointer, string json)
        {
            using var files = new CatalogFiles();
            files.Set(pointer, JsonNode.Parse(json));
            AssertInvalid(files.Compile());
        }

        [Fact]
        public void Duplicate_members_are_rejected_before_node_conversion_and_keys_are_case_sensitive()
        {
            using var files = new CatalogFiles();
            files.WriteDefinition(CatalogFiles.ImageJson.Replace("\"schema_version\":1", "\"schema_version\":1,\"schema_version\":1"));
            AssertInvalid(files.Compile());
            files.WriteDefinition(CatalogFiles.ImageJson.Replace("\"display_name\":", "\"Display_Name\":"));
            AssertInvalid(files.Compile());
        }

        [Fact]
        public void Duplicate_operations_fields_and_writers_are_rejected()
        {
            foreach (var target in new[] { "operations", "fields", "constants" })
            {
                using var files = new CatalogFiles();
                var array = target == "operations" ? files.Definition["operations"]!.AsArray() : files.Operation[target]!.AsArray();
                array.Add(array[0]!.DeepClone());
                files.Save();
                AssertInvalid(files.Compile());
            }
        }

        [Theory]
        [InlineData("../escape.json")]
        [InlineData("C:/escape.json")]
        [InlineData("\\\\server\\share\\escape.json")]
        [InlineData("/escape.json")]
        [InlineData("sub/../image.json")]
        [InlineData("image.json:stream")]
        public void Manifest_rejects_escape_paths(string path)
        {
            using var files = new CatalogFiles();
            files.Manifest(path);
            AssertInvalid(files.Compile());
        }

        [Fact]
        public void Duplicate_Windows_filenames_and_reserved_or_cross_modality_ids_fail_atomically()
        {
            using var files = new CatalogFiles();
            files.Manifest("image.json", "IMAGE.JSON");
            AssertInvalid(files.Compile());
            files.Manifest("image.json");
            AssertInvalid(files.Compile("synthetic/image"));
            var video = JsonNode.Parse(CatalogFiles.VideoJson)!;
            video["model_id"] = "synthetic/image";
            File.WriteAllText(Path.Combine(files.Root, "video.json"), video.ToJsonString());
            files.Manifest("image.json", "video.json");
            AssertInvalid(files.Compile());
        }

        [Fact]
        public void Queue_requires_explicit_segment_ancestor_lifecycle_root()
        {
            using var files = new CatalogFiles(CatalogFiles.VideoJson);
            Assert.Empty(files.Compile().Diagnostics);
            files.Operation.Remove("lifecycle_root"); files.Save();
            AssertInvalid(files.Compile());
            files.Set("/operations/0/lifecycle_root", JsonValue.Create("fal-ai/synthetic"));
            Assert.Empty(files.Compile().Diagnostics);
            files.Set("/operations/0/lifecycle_root", JsonValue.Create("fal-ai/synth"));
            AssertInvalid(files.Compile());
        }

        [Fact]
        public void Required_media_roles_cardinality_and_preparation_are_checked()
        {
            using var files = new CatalogFiles(CatalogFiles.VideoJson);
            files.Operation["media"]!.AsArray().Clear(); files.Save();
            AssertInvalid(files.Compile());
            files.WriteDefinition(CatalogFiles.VideoJson);
            files.Set("/operations/0/media/0/max_count", JsonValue.Create(2));
            AssertInvalid(files.Compile());
            files.WriteDefinition(CatalogFiles.VideoJson);
            files.Set("/operations/0/media/0/preparation", JsonValue.Create("shell"));
            AssertInvalid(files.Compile());
        }

        [Fact]
        public void Numeric_boundary_values_are_exact_and_pricing_retains_precision()
        {
            using var files = new CatalogFiles();
            files.Set("/operations/0/fields/3/default", JsonNode.Parse("9007199254740991"));
            files.Set("/operations/0/fields/4/default", JsonNode.Parse("0.1000000"));
            files.Set("/operations/0/pricing/rates/0/rate_usd", JsonNode.Parse("0.1234567890123456789012345678"));
            Assert.Empty(files.Compile().Diagnostics);
            files.Set("/operations/0/fields/4/default", JsonNode.Parse("1e100"));
            AssertInvalid(files.Compile());
        }

        [Fact]
        public void Admission_size_and_depth_bounds_are_enforced()
        {
            using var files = new CatalogFiles();
            files.Manifest(Enumerable.Range(0, 65).Select(i => i + ".json").ToArray());
            AssertInvalid(files.Compile(), "64");
            files.Manifest("image.json");
            var operations = files.Definition["operations"]!.AsArray();
            while (operations.Count <= 16) operations.Add(operations[0]!.DeepClone());
            files.Save(); AssertInvalid(files.Compile(), "16");
            files.WriteDefinition(CatalogFiles.ImageJson);
            var fields = files.Operation["fields"]!.AsArray();
            while (fields.Count <= 128) fields.Add(fields[0]!.DeepClone());
            files.Save(); AssertInvalid(files.Compile(), "128");
            files.WriteDefinition(CatalogFiles.ImageJson);
            var constraints = files.Operation["constraints"]!.AsArray();
            while (constraints.Count <= 256) constraints.Add(constraints[0]!.DeepClone());
            files.Save(); AssertInvalid(files.Compile(), "256");
            files.WriteDefinition(new string(' ', 1048577) + CatalogFiles.ImageJson);
            AssertInvalid(files.Compile(), "1048576");
            files.WriteDefinition("{\"nested\":" + new string('[', 33) + "0" + new string(']', 33) + "}");
            AssertInvalid(files.Compile());
        }

        [Fact]
        public void Missing_pricing_is_unavailable_and_invalid_catalog_keeps_legacy_factory_usable()
        {
            using var files = new CatalogFiles();
            files.Operation.Remove("pricing"); files.Save();
            Assert.Null(files.Compile().Catalog!.GetOperation("synthetic/image", "text_to_image").Pricing);
            files.Set("/host", JsonValue.Create("evil")); AssertInvalid(files.Compile());
            var registry = new DefaultImageProviderRegistry(VisionProviderRegistrations.CreateImageRegistrations(() => null, () => null, () => null));
            Assert.True(registry.TryResolve("black-forest-labs/flux-schnell", out _));
        }

        [Theory]
        [InlineData("/operations/0/adapter/assembly")]
        [InlineData("/operations/0/fields/0/ui/script")]
        [InlineData("/operations/0/fields/0/payload/expression")]
        [InlineData("/operations/0/constraints/0/expression")]
        [InlineData("/operations/0/constraints/0/when/0/function")]
        [InlineData("/operations/0/constants/0/host")]
        [InlineData("/operations/0/result/headers")]
        [InlineData("/operations/0/pricing/credential")]
        [InlineData("/operations/0/pricing/rates/0/host")]
        [InlineData("/operations/0/evidence/code")]
        public void Every_nested_object_rejects_unrecognized_members(string pointer)
        {
            using var files = new CatalogFiles(); files.Set(pointer, JsonValue.Create("untrusted")); AssertInvalid(files.Compile());
        }

        [Theory]
        [InlineData("integer", "9007199254740993")]
        [InlineData("number", "0.1234567890123456789012345678")]
        [InlineData("number", "1000000001")]
        public void Numeric_condition_operands_obey_control_precision(string type, string operand)
        {
            using var files = new CatalogFiles();
            var condition = files.Operation["constraints"]![0]!["when"]![0]!;
            condition["field"] = type == "integer" ? "request.seed" : "options.strength";
            condition["value"] = JsonNode.Parse(operand); files.Save(); AssertInvalid(files.Compile());
        }

        [Fact]
        public void Integral_metadata_spellings_are_resolved_without_later_conversion_failures()
        {
            using var files = new CatalogFiles(CatalogFiles.VideoJson);
            files.Set("/operations/0/adapter/version", JsonNode.Parse("1.0"));
            files.Set("/operations/0/media/0/min_count", JsonNode.Parse("1e0"));
            var binding = files.Compile().Catalog!.GetOperation("synthetic/video", "first_last_frame_to_video");
            Assert.Equal(1, binding.AdapterVersion); Assert.Equal(1, binding.Media[0].MinCount);
        }

        [Fact]
        public void All_constraint_kinds_membership_and_role_conditions_are_admitted()
        {
            using var files = new CatalogFiles(CatalogFiles.VideoJson);
            files.Operation["constraints"] = JsonNode.Parse("""
            [
              {"kind":"required_when","field":"request.duration_seconds","when":[{"role":"start_frame","present":true}]},
              {"kind":"allowed_when","field":"request.duration_seconds","when":[{"role":"end_frame","present":true}]},
              {"kind":"allowed_values","field":"request.duration_seconds","values":[5,10],"when":[{"field":"request.duration_seconds","operator":"in","values":[5,10]}]}
            ]
            """);
            files.Save(); Assert.Empty(files.Compile().Diagnostics);
            files.Set("/operations/0/constraints/0/when/0/role", JsonValue.Create("undeclared")); AssertInvalid(files.Compile());
        }

        [Fact]
        public void Megapixel_pricing_requires_complete_declared_dimensions_or_positive_bound()
        {
            using var files = new CatalogFiles();
            files.Set("/operations/0/pricing/strategy", JsonValue.Create("per_output_megapixel"));
            files.Set("/operations/0/pricing/unit", JsonValue.Create("megapixel"));
            AssertInvalid(files.Compile());
            files.Set("/operations/0/pricing/dimensions", JsonNode.Parse("""
            {"field":"request.resolution","values":{"small":{"width":512,"height":512},"large":{"width":1024,"height":1024}}}
            """));
            Assert.Empty(files.Compile().Diagnostics);
            files.Set("/operations/0/pricing/dimensions/values/small/width", JsonValue.Create(0)); AssertInvalid(files.Compile());
            files.Operation["pricing"]!.AsObject().Remove("dimensions");
            files.Set("/operations/0/pricing/max_megapixels", JsonValue.Create(2)); Assert.Empty(files.Compile().Diagnostics);
            files.Set("/operations/0/pricing/max_megapixels", JsonValue.Create(0)); AssertInvalid(files.Compile());
        }

        [Fact]
        public void Rate_tables_validate_finite_selectors_and_unambiguous_combinations()
        {
            using var files = new CatalogFiles();
            files.Set("/operations/0/pricing/rates", JsonNode.Parse("""
            [{"selectors":{"request.resolution":"small","options.audio":false},"rate_usd":0.01},{"selectors":{"request.resolution":"large","options.audio":false},"rate_usd":0.02}]
            """));
            Assert.Empty(files.Compile().Diagnostics);
            files.Set("/operations/0/pricing/rates/1/selectors/request.resolution", JsonValue.Create("unknown")); AssertInvalid(files.Compile());
        }

        [Fact]
        public void Editing_supports_optional_ordered_references_and_rejects_parent_writer_overlap()
        {
            using var files = new CatalogFiles();
            files.Set("/operations/0/operation_id", JsonValue.Create("image_to_image"));
            files.Set("/operations/0/media", JsonNode.Parse("""
            [{"role":"primary_image","min_count":1,"max_count":1,"ordered":false,"preparation":"validated_original","transport":"fal_upload","max_bytes":1000,"payload":{"pointer":"/input/image","conversion":"identity"}},
            {"role":"reference_image","min_count":0,"max_count":3,"ordered":true,"preparation":"validated_original","transport":"fal_upload","payload":{"pointer":"/references","conversion":"ordered_array"}}]
            """));
            Assert.Empty(files.Compile().Diagnostics);
            files.Set("/operations/0/constants/0/pointer", JsonValue.Create("/input")); AssertInvalid(files.Compile());
        }

        [Fact]
        public void Boundary_sized_valid_catalogs_are_not_rejected()
        {
            using var files = new CatalogFiles();
            // A definition of exactly one MiB is admitted; one byte over is tested separately.
            var bytes = System.Text.Encoding.UTF8.GetByteCount(CatalogFiles.ImageJson);
            files.WriteDefinition(CatalogFiles.ImageJson + new string(' ', 1048576 - bytes));
            Assert.Empty(files.Compile().Diagnostics);
            files.Manifest(Enumerable.Range(0, 64).Select(i => "model-" + i + ".json").ToArray());
            for (int i = 0; i < 64; i++)
            {
                var definition = JsonNode.Parse(CatalogFiles.ImageJson)!;
                definition["definition_id"] = "definition-" + i; definition["model_id"] = "synthetic/" + i;
                File.WriteAllText(Path.Combine(files.Root, "model-" + i + ".json"), definition.ToJsonString());
            }
            Assert.Equal(64, files.Compile().Catalog!.Definitions.Count);
        }

        [Fact]
        public void Default_filled_restrictions_are_checked_without_rejecting_optional_user_combinations()
        {
            using var files = new CatalogFiles();
            files.Set("/operations/0/constraints", JsonNode.Parse("""
            [{"kind":"allowed_values","field":"request.resolution","values":["large"],"when":[{"field":"options.audio","operator":"eq","value":false}]}]
            """));
            AssertInvalid(files.Compile());
            files.Set("/operations/0/constraints/0/when/0/value", JsonValue.Create(true));
            Assert.Empty(files.Compile().Diagnostics); // Caller combinations are Task 2 validation.
        }

        [Fact]
        public void Contradictory_guard_and_identical_guard_empty_intersection_are_rejected()
        {
            using var files = new CatalogFiles();
            var conditions = files.Operation["constraints"]![0]!["when"]!.AsArray();
            conditions.Add(JsonNode.Parse("""{"field":"request.resolution","operator":"eq","value":"large"}"""));
            files.Save(); AssertInvalid(files.Compile());
            files.Set("/operations/0/constraints", JsonNode.Parse("""
            [{"kind":"allowed_values","field":"request.resolution","values":["small"],"when":[{"field":"options.audio","operator":"eq","value":true}]},
             {"kind":"allowed_values","field":"request.resolution","values":["large"],"when":[{"field":"options.audio","operator":"eq","value":true}]}]
            """));
            AssertInvalid(files.Compile());
        }

        [Fact]
        public void Common_fields_are_closed_and_negative_prompt_remains_an_option()
        {
            using var files = new CatalogFiles();
            files.Set("/operations/0/fields/0/key", JsonValue.Create("negative_prompt")); AssertInvalid(files.Compile());
            files.Set("/operations/0/fields/0/scope", JsonValue.Create("options")); Assert.Empty(files.Compile().Diagnostics);
        }

        [Theory]
        [InlineData("text_to_video", false)]
        [InlineData("image_to_video", true)]
        public void Other_video_operations_use_explicit_media_bindings(string operation, bool primary)
        {
            using var files = new CatalogFiles(CatalogFiles.VideoJson);
            files.Set("/operations/0/operation_id", JsonValue.Create(operation));
            var media = files.Operation["media"]!.AsArray();
            if (primary) { media.RemoveAt(1); media[0]!["role"] = "primary_image"; }
            else media.Clear();
            files.Save(); Assert.Empty(files.Compile().Diagnostics);
            files.Set("/operations/0/invocation", JsonValue.Create("sync")); AssertInvalid(files.Compile());
        }

        [Fact]
        public void Maximal_fields_and_constraints_are_admitted_and_media_caps_only_tighten()
        {
            using var files = new CatalogFiles();
            var fields = files.Operation["fields"]!.AsArray();
            while (fields.Count < 128)
            {
                int i = fields.Count; var field = fields[1]!.DeepClone();
                field["key"] = "control_" + i; field["payload"]!["pointer"] = "/control_" + i; fields.Add(field);
            }
            var constraints = files.Operation["constraints"]!.AsArray(); constraints.Clear();
            for (int i = 0; i < 256; i++) constraints.Add(new JsonObject { ["kind"] = "omit_when", ["field"] = "options.audio", ["when"] = new JsonArray(new JsonObject { ["field"] = "request.seed", ["operator"] = "eq", ["value"] = i }) });
            files.Save(); Assert.Empty(files.Compile().Diagnostics);
            files.WriteDefinition(CatalogFiles.VideoJson);
            files.Set("/operations/0/media/0/max_bytes", JsonValue.Create(31457280)); Assert.Empty(files.Compile().Diagnostics);
            files.Set("/operations/0/media/0/max_bytes", JsonValue.Create(31457281)); AssertInvalid(files.Compile());
        }

        [Fact]
        public void Disabled_unpriced_operation_and_partial_pricing_tables_are_catalog_metadata()
        {
            using var files = new CatalogFiles();
            files.Set("/status", JsonValue.Create("disabled"));
            files.Operation.Remove("pricing"); files.Save();
            var definition = Assert.Single(files.Compile().Catalog!.Definitions);
            Assert.Equal("disabled", definition.Status); Assert.Null(definition.Operations[0].Pricing);
            files.Set("/operations/0/pricing", null); AssertInvalid(files.Compile());
        }

        [Fact]
        public void Format_document_examples_compile_through_the_public_catalog_boundary()
        {
            var directory = new DirectoryInfo(AppContext.BaseDirectory);
            while (directory != null && !File.Exists(Path.Combine(directory.FullName, "docs", "vision", "fal-model-definition-v1.md"))) directory = directory.Parent;
            Assert.NotNull(directory);
            var text = File.ReadAllText(Path.Combine(directory!.FullName, "docs", "vision", "fal-model-definition-v1.md"));
            var blocks = System.Text.RegularExpressions.Regex.Matches(text, "```json\\s*([\\s\\S]*?)```");
            Assert.Equal(3, blocks.Count);
            using var files = new CatalogFiles();
            foreach (System.Text.RegularExpressions.Match block in blocks)
            {
                var json = JsonNode.Parse(block.Groups[1].Value)!.AsObject();
                if (json.ContainsKey("definition_id")) { files.WriteDefinition(json.ToJsonString()); files.Manifest("image.json"); }
                else File.WriteAllText(Path.Combine(files.Root, "catalog.json"), json.ToJsonString());
                Assert.Empty(files.Compile().Diagnostics);
            }
        }

        internal static void AssertInvalid(FalCatalogLoadResult result, string? message = null)
        {
            Assert.Null(result.Catalog); Assert.NotEmpty(result.Diagnostics);
            Assert.All(result.Diagnostics, d => { Assert.NotEmpty(d.File); Assert.NotEmpty(d.Pointer); });
            if (message != null) Assert.Contains(result.Diagnostics, d => d.Message.Contains(message));
        }
    }

    internal sealed class CatalogFiles : IDisposable
    {
        internal string Root { get; } = Path.Combine(Path.GetTempPath(), "rook-catalog-" + Guid.NewGuid().ToString("N"));
        internal JsonObject Definition { get; private set; } = null!;
        internal JsonObject Operation => Definition["operations"]![0]!.AsObject();
        internal CatalogFiles(string? definition = null) { Directory.CreateDirectory(Root); WriteDefinition(definition ?? ImageJson); Manifest("image.json"); }
        internal void Manifest(params string[] names) => File.WriteAllText(Path.Combine(Root, "catalog.json"), new JsonObject { ["schema_version"] = 1, ["definitions"] = new JsonArray(names.Select(n => (JsonNode?)JsonValue.Create(n)).ToArray()) }.ToJsonString());
        internal void WriteDefinition(string json) { File.WriteAllText(Path.Combine(Root, "image.json"), json); try { Definition = JsonNode.Parse(json)!.AsObject(); } catch (System.Text.Json.JsonException) { } }
        internal void Save() => File.WriteAllText(Path.Combine(Root, "image.json"), Definition.ToJsonString());
        internal FalCatalogLoadResult Compile(params string[] reserved) => new FalCatalogCompiler().Compile(Root, reserved);
        internal void Set(string pointer, JsonNode? value) { var segments = pointer.TrimStart('/').Split('/'); JsonNode node = Definition; foreach (var s in segments.Take(segments.Length - 1)) node = node is JsonArray a ? a[int.Parse(s)]! : node[s]!; if (node is JsonArray array) array[int.Parse(segments.Last())] = value; else node[segments.Last()] = value; Save(); }
        public void Dispose() { if (Directory.Exists(Root)) Directory.Delete(Root, true); }

        internal const string ImageJson = """
        {"schema_version":1,"definition_id":"synthetic-image","revision":"revision-1","model_id":"synthetic/image","display_name":"Synthetic image","provider":"fal","status":"experimental","operations":[{
          "operation_id":"text_to_image","endpoint_id":"fal-ai/synthetic/render","invocation":"sync","adapter":{"id":"fal.image.declarative","version":1},
          "fields":[
            {"key":"prompt","scope":"request","type":"string","required":true,"max_length":1000,"label":"Prompt","description":"Plain text","ui":{"group":"basic","order":0},"payload":{"pointer":"/prompt","conversion":"identity"}},
            {"key":"audio","scope":"options","type":"boolean","default":false,"label":"Audio","payload":{"pointer":"/audio","conversion":"identity"}},
            {"key":"count","scope":"options","type":"integer","min":1,"max":3,"default":1,"label":"Count","payload":{"pointer":"/count","conversion":"integer_to_string"}},
            {"key":"seed","scope":"request","type":"integer","min":-9007199254740991,"max":9007199254740991,"step":1,"default":0,"label":"Seed","payload":{"pointer":"/seed","conversion":"identity"}},
            {"key":"strength","scope":"options","type":"number","min":0,"max":1,"step":0.1,"default":0.1,"label":"Strength","payload":{"pointer":"/strength","conversion":"identity"}},
            {"key":"resolution","scope":"request","type":"enum","values":["small","large"],"default":"small","label":"Resolution","payload":{"pointer":"/size","conversion":"enum_lookup","lookup":{"small":"S","large":"L"}}}
          ],"media":[],"constraints":[{"kind":"omit_when","field":"options.audio","when":[{"field":"request.resolution","operator":"eq","value":"small"}]}],
          "constants":[{"pointer":"/num_images","value":1}],"result":{"role":"generated_image","mime_family":"image","collection_pointer":"/images","cardinality":1,"url_pointer":"/url","mime_pointer":"/content_type"},
          "pricing":{"strategy":"fixed_per_output","unit":"output","revision":"price-1","rates":[{"selectors":{},"rate_usd":0.01}],"rounding":"none","source":"https://fal.ai/models/synthetic","reviewed_on":"2026-10-25"},
          "evidence":{"url":"https://fal.ai/models/synthetic","reviewed_on":"2026-10-25","qualification":"synthetic"}
        }]}
        """;
        internal const string VideoJson = """
        {"schema_version":1,"definition_id":"synthetic-video","revision":"revision-1","model_id":"synthetic/video","display_name":"Synthetic video","provider":"fal","status":"experimental","operations":[{
          "operation_id":"first_last_frame_to_video","endpoint_id":"fal-ai/synthetic/video/frames","lifecycle_root":"fal-ai/synthetic","invocation":"queue","adapter":{"id":"fal.video.declarative","version":1},
          "fields":[{"key":"duration_seconds","scope":"request","type":"integer","min":1,"max":10,"default":5,"label":"Seconds","payload":{"pointer":"/duration","conversion":"integer_to_string"}}],
          "media":[{"role":"start_frame","min_count":1,"max_count":1,"ordered":false,"preparation":"validated_original","transport":"fal_upload","payload":{"pointer":"/first_frame","conversion":"identity"}},{"role":"end_frame","min_count":1,"max_count":1,"ordered":false,"preparation":"validated_original","transport":"fal_upload","payload":{"pointer":"/last_frame","conversion":"identity"}}],
          "constraints":[],"constants":[],"result":{"role":"generated_video","mime_family":"video","url_pointer":"/video/url"},
          "pricing":{"strategy":"per_output_second","unit":"second","quantity_field":"request.duration_seconds","revision":"price-1","rates":[{"selectors":{},"rate_usd":0.1}],"rounding":"none","source":"https://fal.ai/models/synthetic","reviewed_on":"2026-10-25"},
          "evidence":{"url":"https://fal.ai/models/synthetic","reviewed_on":"2026-10-25","qualification":"synthetic"}
        }]}
        """;
    }
}
