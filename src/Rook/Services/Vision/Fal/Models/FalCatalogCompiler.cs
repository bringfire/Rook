using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
namespace Rook.Services.Vision.Fal.Models
{
    public sealed class FalCatalogCompiler
    {
        public FalCatalogLoadResult Compile(string rootDirectory, IReadOnlyCollection<string> reservedModelIds)
        {
            if (reservedModelIds == null) throw new ArgumentNullException(nameof(reservedModelIds));
            var diagnostics = new List<FalCatalogDiagnostic>();
            var definitions = new List<FalModelDefinition>();
            string root = rootDirectory;
            string file = Path.Combine(rootDirectory, "catalog.json");
            try
            {
                root = Path.GetFullPath(rootDirectory);
                file = Path.Combine(root, "catalog.json");
                RejectReparsePoints(file);
                var manifest = Read(file);
                Closed(manifest, "/", "schema_version", "definitions");
                Version(manifest, "/");
                var names = Array(manifest, "definitions", "/", 64);
                var seenFiles = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                var modelIds = new HashSet<string>(reservedModelIds, StringComparer.Ordinal);
                var definitionIds = new HashSet<string>(StringComparer.Ordinal);
                for (int i = 0; i < names.Count; i++)
                {
                    string pointer = "/definitions/" + i;
                    string name = Text(names[i], pointer);
                    string definitionFile = ContainedFile(root, name, pointer);
                    if (!seenFiles.Add(definitionFile)) Fail(pointer, "Duplicate definition filename under Windows case-insensitive rules.");
                    try
                    {
                        RejectReparsePoints(definitionFile);
                        var json = Read(definitionFile);
                        ValidateDefinition(json);
                        string modelId = Text(json, "model_id", "/");
                        string definitionId = Text(json, "definition_id", "/");
                        if (!modelIds.Add(modelId)) Fail("/model_id", "Model ID collides with a configured or reserved legacy ID.");
                        if (!definitionIds.Add(definitionId)) Fail("/definition_id", "Duplicate definition ID.");
                        definitions.Add(new FalModelDefinition(json, definitionFile));
                    }
                    catch (AdmissionException ex) { diagnostics.Add(new FalCatalogDiagnostic(definitionFile, ex.Pointer, ex.Message)); }
                    catch (Exception ex) when (IsReadError(ex)) { diagnostics.Add(new FalCatalogDiagnostic(definitionFile, "/", ex.Message)); }
                }
            }
            catch (AdmissionException ex) { diagnostics.Add(new FalCatalogDiagnostic(file, ex.Pointer, ex.Message)); }
            catch (Exception ex) when (IsReadError(ex)) { diagnostics.Add(new FalCatalogDiagnostic(file, "/", ex.Message)); }
            return diagnostics.Count == 0
                ? new FalCatalogLoadResult(new FalCatalogSnapshot(root, definitions), System.Array.Empty<FalCatalogDiagnostic>())
                : new FalCatalogLoadResult(null, diagnostics.ToArray());
        }

        private static bool IsReadError(Exception ex) => ex is IOException || ex is UnauthorizedAccessException
            || ex is JsonException || ex is ArgumentException || ex is NotSupportedException;

        private static string ContainedFile(string root, string name, string pointer)
        {
            // Reject rooted, drive-relative, device/ADS and parent segments before normalization.
            string normalized = name.Replace('\\', '/');
            var segments = normalized.Split('/');
            if (normalized.StartsWith("/", StringComparison.Ordinal) || name.IndexOf(':') >= 0
                || segments.Any(s => s.Length == 0 || s == "." || s == ".." || s.EndsWith(".", StringComparison.Ordinal) || s.EndsWith(" ", StringComparison.Ordinal))
                || !normalized.EndsWith(".json", StringComparison.OrdinalIgnoreCase)
                || segments.Any(s => s.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0))
                Fail(pointer, "Definition must be a contained relative JSON filename without parent, rooted or device segments.");
            string full = Path.GetFullPath(Path.Combine(root, normalized.Replace('/', Path.DirectorySeparatorChar)));
            string prefix = root.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar) + Path.DirectorySeparatorChar;
            if (!full.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)) Fail(pointer, "Definition escapes catalog root.");
            return full;
        }

        private static void RejectReparsePoints(string path)
        {
            // Include ancestors of the root: a packaged root itself must not alias another location.
            for (string? current = Path.GetFullPath(path); current != null; current = Path.GetDirectoryName(current))
            {
                if ((File.Exists(current) || Directory.Exists(current)) && (File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                    Fail("/", "Reparse points are not permitted in catalog paths: " + current);
            }
        }

        private static JsonObject Read(string file)
        {
            const int limit = 1048576;
            using var stream = new FileStream(file, FileMode.Open, FileAccess.Read, FileShare.Read);
            if (stream.Length > limit) Fail("/", "JSON file exceeds 1048576 byte limit.");
            using var memory = new MemoryStream();
            var buffer = new byte[8192]; int read;
            while ((read = stream.Read(buffer, 0, Math.Min(buffer.Length, limit + 1 - (int)memory.Length))) != 0)
            {
                memory.Write(buffer, 0, read);
                if (memory.Length > limit) Fail("/", "JSON file exceeds 1048576 byte limit.");
            }
            // Duplicate members must be detected before JsonNode overwrites or rejects them.
            using var document = JsonDocument.Parse(memory.ToArray(), new JsonDocumentOptions { MaxDepth = 32 });
            UniqueMembers(document.RootElement, "/");
            return Object(JsonNode.Parse(document.RootElement.GetRawText()), "/");
        }

        private static void UniqueMembers(JsonElement element, string pointer)
        {
            if (element.ValueKind == JsonValueKind.Object)
            {
                var keys = new HashSet<string>(StringComparer.Ordinal);
                foreach (var property in element.EnumerateObject())
                {
                    string p = At(pointer, Escape(property.Name));
                    if (!keys.Add(property.Name)) Fail(p, "Duplicate JSON member.");
                    UniqueMembers(property.Value, p);
                }
            }
            else if (element.ValueKind == JsonValueKind.Array)
            {
                int i = 0; foreach (var child in element.EnumerateArray()) UniqueMembers(child, At(pointer, (i++).ToString(CultureInfo.InvariantCulture)));
            }
        }

        private static void ValidateDefinition(JsonObject json)
        {
            Closed(json, "/", "schema_version", "definition_id", "revision", "model_id", "display_name", "provider", "status", "operations");
            Version(json, "/");
            Id(Text(json, "definition_id", "/"), "/definition_id");
            Text(json, "revision", "/"); Id(Text(json, "model_id", "/"), "/model_id"); Text(json, "display_name", "/");
            OneOf(Text(json, "provider", "/"), "/provider", "fal");
            OneOf(Text(json, "status", "/"), "/status", "available", "experimental", "disabled");
            var operations = Array(json, "operations", "/", 16, true);
            var ids = new HashSet<string>(StringComparer.Ordinal);
            for (int i = 0; i < operations.Count; i++)
            {
                string p = "/operations/" + i;
                var operation = Object(operations[i], p);
                if (!ids.Add(Text(operation, "operation_id", p))) Fail(At(p, "operation_id"), "Duplicate operation ID.");
                ValidateOperation(operation, p);
            }
        }

        private static readonly string[] CommonFields = { "prompt", "resolution", "aspect_ratio", "duration_seconds", "seed" };
        private static void ValidateOperation(JsonObject operation, string p)
        {
            Closed(operation, p, "operation_id", "endpoint_id", "lifecycle_root", "invocation", "adapter", "fields", "media", "constraints", "constants", "result", "pricing", "evidence");
            string id = Text(operation, "operation_id", p);
            OneOf(id, At(p, "operation_id"), "text_to_image", "image_to_image", "text_to_video", "image_to_video", "first_last_frame_to_video");
            bool image = id.EndsWith("_image", StringComparison.Ordinal);
            string endpoint = Text(operation, "endpoint_id", p); Endpoint(endpoint, At(p, "endpoint_id"));
            string invocation = Text(operation, "invocation", p); OneOf(invocation, At(p, "invocation"), "sync", "queue");
            if (!image && invocation != "queue") Fail(At(p, "invocation"), "Video operations require queue invocation.");
            if (invocation == "queue")
            {
                string lifecycle = Text(operation, "lifecycle_root", p); Endpoint(lifecycle, At(p, "lifecycle_root"));
                if (endpoint != lifecycle && !endpoint.StartsWith(lifecycle + "/", StringComparison.Ordinal)) Fail(At(p, "lifecycle_root"), "Lifecycle root must be the endpoint or a complete segment ancestor.");
            }
            else if (operation.ContainsKey("lifecycle_root")) Fail(At(p, "lifecycle_root"), "Sync invocation cannot declare a lifecycle root.");
            var adapter = Object(operation["adapter"], At(p, "adapter")); Closed(adapter, At(p, "adapter"), "id", "version");
            OneOf(Text(adapter, "id", At(p, "adapter")), At(p, "adapter/id"), image ? "fal.image.declarative" : "fal.video.declarative");
            if (Integer(adapter["version"], At(p, "adapter/version")) != 1) Fail(At(p, "adapter/version"), "Supported adapter version is 1.");

            var fields = Array(operation, "fields", p, 128);
            var fieldMap = new Dictionary<string, JsonObject>(StringComparer.Ordinal);
            var writers = new List<string>();
            for (int i = 0; i < fields.Count; i++)
            {
                string fp = At(p, "fields/" + i); var field = Object(fields[i], fp);
                ValidateField(field, fp, writers);
                string qualified = Text(field, "scope", fp) + "." + Text(field, "key", fp);
                if (fieldMap.ContainsKey(qualified)) Fail(fp, "Duplicate field key.");
                fieldMap.Add(qualified, field);
            }
            var media = Array(operation, "media", p, 16);
            var roles = new Dictionary<string, JsonObject>(StringComparer.Ordinal);
            for (int i = 0; i < media.Count; i++)
            {
                string mp = At(p, "media/" + i); var role = Object(media[i], mp);
                ValidateMedia(role, mp, writers, image);
                if (roles.ContainsKey(Text(role, "role", mp))) Fail(mp, "Duplicate semantic media role.");
                roles.Add(Text(role, "role", mp), role);
            }
            ValidateRoles(id, roles, At(p, "media"));
            var constants = Array(operation, "constants", p, 128);
            for (int i = 0; i < constants.Count; i++)
            {
                string cp = At(p, "constants/" + i); var constant = Object(constants[i], cp);
                Closed(constant, cp, "pointer", "value"); AddWriter(Text(constant, "pointer", cp), At(cp, "pointer"), writers);
                Scalar(constant["value"], At(cp, "value"));
            }
            ValidateConstraints(Array(operation, "constraints", p, 256), fieldMap, roles, At(p, "constraints"));
            ValidateResult(Object(operation["result"], At(p, "result")), At(p, "result"), image);
            if (operation.ContainsKey("pricing")) ValidatePricing(Object(operation["pricing"], At(p, "pricing")), fieldMap, At(p, "pricing"));
            ValidateEvidence(Object(operation["evidence"], At(p, "evidence")), At(p, "evidence"));
        }

        private static void ValidateField(JsonObject field, string p, List<string> writers)
        {
            Closed(field, p, "key", "scope", "type", "required", "default", "label", "description", "ui", "min", "max", "step", "min_length", "max_length", "values", "payload");
            string key = Text(field, "key", p);
            if (!Regex.IsMatch(key, "^[a-z][a-z0-9_]*$")) Fail(At(p, "key"), "Field keys must be lowercase identifiers.");
            string scope = Text(field, "scope", p); OneOf(scope, At(p, "scope"), "request", "options");
            if (scope == "request" && !CommonFields.Contains(key)) Fail(At(p, "key"), "Unknown common request field.");
            if (scope == "options" && CommonFields.Contains(key)) Fail(At(p, "key"), "Options cannot shadow common request fields.");
            string type = Text(field, "type", p); OneOf(type, At(p, "type"), "boolean", "integer", "number", "string", "enum");
            // Canonical request names retain their public JSON types.
            if (scope == "request" && ((key == "seed" && type != "integer")
                || (key == "duration_seconds" && type != "integer" && type != "number")
                || (key == "prompt" && type != "string")
                || ((key == "resolution" || key == "aspect_ratio") && type != "enum"))) Fail(At(p, "type"), "Type conflicts with the canonical request field.");
            Text(field, "label", p);
            if (field.ContainsKey("description")) Text(field, "description", p, true);
            if (field.ContainsKey("required")) Boolean(field["required"], At(p, "required"));
            if (field.ContainsKey("ui"))
            {
                var ui = Object(field["ui"], At(p, "ui")); Closed(ui, At(p, "ui"), "group", "order", "hidden");
                if (ui.ContainsKey("group")) OneOf(Text(ui, "group", At(p, "ui")), At(p, "ui/group"), "basic", "advanced");
                if (ui.ContainsKey("order") && (Integer(ui["order"], At(p, "ui/order")) < -1000000 || Integer(ui["order"], At(p, "ui/order")) > 1000000)) Fail(At(p, "ui/order"), "UI order exceeds bounds.");
                if (ui.ContainsKey("hidden")) Boolean(ui["hidden"], At(p, "ui/hidden"));
            }
            bool numeric = type == "integer" || type == "number";
            foreach (string member in new[] { "min", "max", "step" })
            {
                if (field.ContainsKey(member))
                {
                    if (!numeric) Fail(At(p, member), "Only numeric controls have numeric bounds/step.");
                    UserNumber(field[member], type, At(p, member));
                }
            }
            if (numeric)
            {
                decimal min = UserNumber(field["min"], type, At(p, "min"));
                decimal max = UserNumber(field["max"], type, At(p, "max"));
                if (min > max) Fail(p, "Minimum exceeds maximum.");
                if (field.ContainsKey("step") && UserNumber(field["step"], type, At(p, "step")) <= 0) Fail(At(p, "step"), "Step must be positive and representable.");
            }
            foreach (string member in new[] { "min_length", "max_length" })
                if (field.ContainsKey(member) && (type != "string" || Integer(field[member], At(p, member)) < 0 || Integer(field[member], At(p, member)) > 1048576)) Fail(At(p, member), "String length must be between 0 and 1048576.");
            if (type == "string")
            {
                long max = Integer(field["max_length"], At(p, "max_length"));
                long min = field.ContainsKey("min_length") ? Integer(field["min_length"], At(p, "min_length")) : 0;
                if (max < min) Fail(p, "Minimum string length exceeds maximum.");
            }
            if (type == "enum")
            {
                var values = Array(field, "values", p, 256, true); var seen = new HashSet<string>(StringComparer.Ordinal);
                for (int i = 0; i < values.Count; i++)
                {
                    string vp = At(p, "values/" + i);
                    if (!seen.Add(Text(values[i], vp))) Fail(vp, "Duplicate enum value.");
                    ScalarMediaBoundary(values[i], vp);
                }
            }
            else if (field.ContainsKey("values")) Fail(At(p, "values"), "Only enum controls declare values.");
            if (field.ContainsKey("default")) FieldValue(field, field["default"], At(p, "default"));
            var payload = Object(field["payload"], At(p, "payload"));
            ValidateMapping(payload, At(p, "payload"), writers, false);
            string conversion = Text(payload, "conversion", At(p, "payload"));
            if (conversion == "integer_to_string" && type != "integer") Fail(At(p, "payload/conversion"), "integer_to_string requires integer field.");
            if (conversion == "enum_lookup")
            {
                if (type != "enum") Fail(At(p, "payload/conversion"), "enum_lookup requires enum field.");
                var lookup = Object(payload["lookup"], At(p, "payload/lookup"));
                var values = field["values"]!.AsArray().Select(v => v!.GetValue<string>()).ToArray();
                if (lookup.Count != values.Length || values.Any(v => !lookup.ContainsKey(v))) Fail(At(p, "payload/lookup"), "Lookup must map every enum value exactly once.");
                foreach (var entry in lookup) Scalar(entry.Value, At(p, "payload/lookup/" + Escape(entry.Key)));
            }
            else if (payload.ContainsKey("lookup")) Fail(At(p, "payload/lookup"), "Lookup is only valid for enum_lookup.");
        }

        private static void ValidateMapping(JsonObject mapping, string p, List<string> writers, bool media)
        {
            Closed(mapping, p, "pointer", "conversion", "lookup");
            AddWriter(Text(mapping, "pointer", p), At(p, "pointer"), writers);
            OneOf(Text(mapping, "conversion", p), At(p, "conversion"), media ? new[] { "identity", "ordered_array" } : new[] { "identity", "integer_to_string", "enum_lookup" });
            if (media && mapping.ContainsKey("lookup")) Fail(At(p, "lookup"), "Media cannot declare enum lookups.");
        }

        private static void ValidateMedia(JsonObject media, string p, List<string> writers, bool image)
        {
            Closed(media, p, "role", "min_count", "max_count", "ordered", "preparation", "transport", "max_bytes", "payload");
            string role = Text(media, "role", p); OneOf(role, At(p, "role"), "primary_image", "reference_image", "start_frame", "end_frame");
            long min = Integer(media["min_count"], At(p, "min_count")); long max = Integer(media["max_count"], At(p, "max_count"));
            bool ordered = Boolean(media["ordered"], At(p, "ordered"));
            if (min < 0 || max < 1 || max > 16 || min > max) Fail(p, "Media cardinality must satisfy 0 <= min <= max <= 16, max >= 1.");
            if (role != "reference_image" && (max != 1 || ordered)) Fail(p, "Single-image roles have max_count 1 and ordered false.");
            if (role == "reference_image" && !ordered) Fail(At(p, "ordered"), "Reference images are ordered.");
            OneOf(Text(media, "preparation", p), At(p, "preparation"), "validated_original");
            OneOf(Text(media, "transport", p), At(p, "transport"), image ? new[] { "fal_upload", "data_uri" } : new[] { "fal_upload" });
            if (media.ContainsKey("max_bytes") && (Integer(media["max_bytes"], At(p, "max_bytes")) <= 0 || Integer(media["max_bytes"], At(p, "max_bytes")) > 31457280)) Fail(At(p, "max_bytes"), "max_bytes must be 1..31457280 (30 MiB conservative Rook catalog ceiling); runtime/provider limits may be lower.");
            var payload = Object(media["payload"], At(p, "payload")); ValidateMapping(payload, At(p, "payload"), writers, true);
            if (Text(payload, "conversion", At(p, "payload")) != (role == "reference_image" ? "ordered_array" : "identity")) Fail(At(p, "payload/conversion"), "Media mapping conflicts with semantic role cardinality.");
        }

        private static void ValidateRoles(string id, Dictionary<string, JsonObject> roles, string p)
        {
            string[] required = id == "image_to_image" || id == "image_to_video" ? new[] { "primary_image" }
                : id == "first_last_frame_to_video" ? new[] { "start_frame", "end_frame" } : System.Array.Empty<string>();
            string[] allowed = id == "image_to_image" ? new[] { "primary_image", "reference_image" } : required;
            foreach (string role in required)
                if (!roles.TryGetValue(role, out var media) || Integer(media["min_count"], p) != 1) Fail(p, "Operation requires exactly one " + role + ".");
            if (roles.Keys.Any(role => !allowed.Contains(role))) Fail(p, "Media role is not supported by this operation.");
            if (roles.TryGetValue("reference_image", out var references) && Integer(references["min_count"], p) != 0) Fail(p, "Image editing references must be optional.");
        }

        private static void ValidateConstraints(JsonArray constraints, Dictionary<string, JsonObject> fields, Dictionary<string, JsonObject> roles, string p)
        {
            var seen = new HashSet<string>(StringComparer.Ordinal);
            var restrictions = new Dictionary<string, HashSet<string>>(StringComparer.Ordinal);
            for (int i = 0; i < constraints.Count; i++)
            {
                string cp = At(p, i.ToString(CultureInfo.InvariantCulture)); var constraint = Object(constraints[i], cp);
                Closed(constraint, cp, "kind", "field", "when", "values");
                string kind = Text(constraint, "kind", cp); OneOf(kind, At(cp, "kind"), "required_when", "allowed_when", "allowed_values", "omit_when");
                var field = Reference(fields, Text(constraint, "field", cp), At(cp, "field"));
                var when = Array(constraint, "when", cp, 128, true);
                var predicates = new Dictionary<string, HashSet<string>>(StringComparer.Ordinal);
                for (int j = 0; j < when.Count; j++)
                {
                    string wp = At(cp, "when/" + j); var condition = Object(when[j], wp);
                    string predicateKey; HashSet<string> operands;
                    if (condition.ContainsKey("role"))
                    {
                        Closed(condition, wp, "role", "present");
                        string role = Text(condition, "role", wp);
                        if (!roles.ContainsKey(role)) Fail(At(wp, "role"), "Condition references undeclared media role.");
                        predicateKey = "role:" + role;
                        operands = new HashSet<string> { Boolean(condition["present"], At(wp, "present")) ? "true" : "false" };
                    }
                    else
                    {
                        Closed(condition, wp, "field", "operator", "value", "values");
                        string name = Text(condition, "field", wp); var referenced = Reference(fields, name, At(wp, "field"));
                        string op = Text(condition, "operator", wp); OneOf(op, At(wp, "operator"), "eq", "in");
                        predicateKey = name;
                        if (op == "eq")
                        {
                            if (condition.ContainsKey("values")) Fail(At(wp, "values"), "eq uses value only.");
                            FieldValue(referenced, condition["value"], At(wp, "value"));
                            operands = new HashSet<string> { FalCanonicalJson.Hash(condition["value"]!) };
                        }
                        else
                        {
                            if (condition.ContainsKey("value")) Fail(At(wp, "value"), "in uses values only.");
                            operands = ValueSet(Array(condition, "values", wp, 256, true), referenced, At(wp, "values"));
                        }
                    }
                    if (predicates.TryGetValue(predicateKey, out var previous)) { previous.IntersectWith(operands); if (previous.Count == 0) Fail(wp, "Contradictory AND conditions."); }
                    else predicates.Add(predicateKey, operands);
                }
                if (!seen.Add(FalCanonicalJson.Hash(constraint))) Fail(cp, "Duplicate constraint.");
                if (kind == "allowed_values")
                {
                    var allowed = ValueSet(Array(constraint, "values", cp, 256, true), field, At(cp, "values"));
                    // Identical predicates impose simultaneous restrictions; their intersection must be nonempty.
                    string key = Text(constraint, "field", cp) + ":" + string.Join(";", predicates.OrderBy(k => k.Key, StringComparer.Ordinal).Select(k => k.Key + "=" + string.Join(",", k.Value.OrderBy(v => v, StringComparer.Ordinal))));
                    if (restrictions.TryGetValue(key, out var prior)) { prior.IntersectWith(allowed); if (prior.Count == 0) Fail(cp, "Contradictory allowed_values restrictions."); }
                    else restrictions.Add(key, allowed);
                }
                else if (constraint.ContainsKey("values")) Fail(At(cp, "values"), "Only allowed_values declares values.");
                if (kind == "omit_when" && field["required"]?.GetValue<bool>() == true) Fail(cp, "An unconditionally required field cannot be omitted.");
            }
            ValidateDefaultState(constraints, fields, roles, p);
        }

        // Admission checks only defaults whose conditions are determinable. Supplied
        // combinations and intersecting active restrictions remain request validation.
        private static void ValidateDefaultState(JsonArray constraints, Dictionary<string, JsonObject> fields, Dictionary<string, JsonObject> roles, string p)
        {
            foreach (var pair in fields)
            {
                var applicable = constraints.Select(c => c!.AsObject()).Where(c => c["field"]!.GetValue<string>() == pair.Key).ToArray();
                bool omitted = applicable.Any(c => c["kind"]!.GetValue<string>() == "omit_when" && DefaultGuard(c["when"]!.AsArray(), fields, roles) == true);
                if (omitted)
                {
                    if (applicable.Any(c => c["kind"]!.GetValue<string>() == "required_when" && DefaultGuard(c["when"]!.AsArray(), fields, roles) == true))
                        Fail(p, "Default-filled conditions simultaneously require and omit " + pair.Key + ".");
                    continue;
                }
                if (!pair.Value.ContainsKey("default")) continue; // Required caller input is legitimate.
                string hash = FalCanonicalJson.Hash(pair.Value["default"]!);
                foreach (var constraint in applicable)
                {
                    bool? active = DefaultGuard(constraint["when"]!.AsArray(), fields, roles);
                    string kind = constraint["kind"]!.GetValue<string>();
                    if (kind == "allowed_when" && active == false) Fail(p, "Default-filled state disallows " + pair.Key + ".");
                    if (kind == "allowed_values" && active == true && !constraint["values"]!.AsArray().Any(v => FalCanonicalJson.Hash(v!) == hash))
                        Fail(p, "Default-filled state violates allowed_values for " + pair.Key + ".");
                }
            }
        }

        private static bool? DefaultGuard(JsonArray conditions, Dictionary<string, JsonObject> fields, Dictionary<string, JsonObject> roles)
        {
            bool unknown = false;
            foreach (var node in conditions)
            {
                var condition = node!.AsObject(); bool? matches;
                if (condition.ContainsKey("role"))
                {
                    var media = roles[condition["role"]!.GetValue<string>()];
                    matches = Integer(media["min_count"], "/") > 0 ? condition["present"]!.GetValue<bool>() : (bool?)null;
                }
                else
                {
                    var field = fields[condition["field"]!.GetValue<string>()];
                    if (!field.ContainsKey("default")) matches = null;
                    else
                    {
                        string hash = FalCanonicalJson.Hash(field["default"]!);
                        matches = condition["operator"]!.GetValue<string>() == "eq"
                            ? hash == FalCanonicalJson.Hash(condition["value"]!)
                            : condition["values"]!.AsArray().Any(v => hash == FalCanonicalJson.Hash(v!));
                    }
                }
                if (matches == false) return false;
                if (matches == null) unknown = true;
            }
            return unknown ? (bool?)null : true;
        }

        private static HashSet<string> ValueSet(JsonArray values, JsonObject field, string p)
        {
            var set = new HashSet<string>(StringComparer.Ordinal);
            for (int i = 0; i < values.Count; i++)
            {
                FieldValue(field, values[i], At(p, i.ToString(CultureInfo.InvariantCulture)));
                if (!set.Add(FalCanonicalJson.Hash(values[i]!))) Fail(p, "Duplicate condition/restriction value.");
            }
            return set;
        }

        private static JsonObject Reference(Dictionary<string, JsonObject> fields, string name, string p)
        {
            if (!fields.TryGetValue(name, out var field)) { Fail(p, "Unknown qualified field reference; use request.<key> or options.<key>."); return null!; }
            return field;
        }

        private static void ValidateResult(JsonObject result, string p, bool image)
        {
            Closed(result, p, "role", "mime_family", "collection_pointer", "cardinality", "url_pointer", "mime_pointer");
            OneOf(Text(result, "role", p), At(p, "role"), image ? "generated_image" : "generated_video");
            OneOf(Text(result, "mime_family", p), At(p, "mime_family"), image ? "image" : "video");
            Pointer(Text(result, "url_pointer", p), At(p, "url_pointer"));
            if (result.ContainsKey("mime_pointer")) Pointer(Text(result, "mime_pointer", p), At(p, "mime_pointer"));
            if (result.ContainsKey("collection_pointer"))
            {
                string collection = Text(result, "collection_pointer", p);
                Pointer(collection, At(p, "collection_pointer"));
                if (HasArrayTraversalSegment(collection)) Fail(At(p, "collection_pointer"), "Collection pointers cannot traverse another array.");
                if (Integer(result["cardinality"], At(p, "cardinality")) != 1) Fail(At(p, "cardinality"), "Only result cardinality 1 is supported.");
                CheckedCollectionPointer(Text(result, "url_pointer", p), collection, At(p, "url_pointer"));
                if (result.ContainsKey("mime_pointer") && HasArrayTraversalSegment(Text(result, "mime_pointer", p)))
                    CheckedCollectionPointer(Text(result, "mime_pointer", p), collection, At(p, "mime_pointer"));
            }
            else
            {
                if (result.ContainsKey("cardinality")) Fail(At(p, "cardinality"), "Scalar-object results do not declare cardinality.");
                foreach (string member in new[] { "url_pointer", "mime_pointer" })
                    if (result.ContainsKey(member) && HasArrayTraversalSegment(Text(result, member, p)))
                        Fail(At(p, member), "Array traversal requires an explicit one-item collection declaration.");
            }
        }

        private static bool HasArrayTraversalSegment(string pointer) => pointer.Split('/').Skip(1).Any(IsArrayTraversalSegment);
        private static bool IsArrayTraversalSegment(string segment)
        {
            // Also reserve signed and append-like spellings rather than admitting
            // unsupported array operators as ambiguous numeric object properties.
            if (segment == "+" || segment == "-") return true;
            int start = segment.StartsWith("+", StringComparison.Ordinal) || segment.StartsWith("-", StringComparison.Ordinal) ? 1 : 0;
            return segment.Length > start && segment.Skip(start).All(c => c >= '0' && c <= '9');
        }
        private static void CheckedCollectionPointer(string pointer, string collection, string p)
        {
            string item = collection + "/0";
            if ((pointer != item && !pointer.StartsWith(item + "/", StringComparison.Ordinal))
                || pointer.Split('/').Skip(1).Count(IsArrayTraversalSegment) != 1)
                Fail(p, "Result pointer must traverse exactly the declared collection at index 0, with no other array traversal.");
        }

        private static void ValidatePricing(JsonObject pricing, Dictionary<string, JsonObject> fields, string p)
        {
            Closed(pricing, p, "strategy", "unit", "revision", "rates", "rounding", "source", "reviewed_on", "quantity_field", "dimensions", "max_megapixels");
            string strategy = Text(pricing, "strategy", p); OneOf(strategy, At(p, "strategy"), "fixed_per_output", "per_output_second", "per_output_megapixel");
            OneOf(Text(pricing, "unit", p), At(p, "unit"), strategy == "fixed_per_output" ? "output" : strategy == "per_output_second" ? "second" : "megapixel");
            Text(pricing, "revision", p); Url(Text(pricing, "source", p), At(p, "source")); Date(Text(pricing, "reviewed_on", p), At(p, "reviewed_on"));
            OneOf(Text(pricing, "rounding", p), At(p, "rounding"), "none", "ceil_unit");
            if (strategy == "per_output_second")
            {
                string name = Text(pricing, "quantity_field", p); var quantity = Reference(fields, name, At(p, "quantity_field"));
                if (name != "request.duration_seconds" || UserNumber(quantity["min"], Text(quantity, "type", p), At(p, "quantity_field")) <= 0) Fail(At(p, "quantity_field"), "Seconds pricing requires a positive duration_seconds control.");
            }
            else if (pricing.ContainsKey("quantity_field")) Fail(At(p, "quantity_field"), "quantity_field is only supported for per_output_second.");
            if (strategy == "per_output_megapixel")
            {
                bool dimensions = pricing.ContainsKey("dimensions"); bool max = pricing.ContainsKey("max_megapixels");
                if (dimensions == max) Fail(p, "Megapixel pricing requires exactly one dimension mapping or conservative max_megapixels.");
                if (max && ExactNumber(pricing["max_megapixels"], At(p, "max_megapixels")) <= 0) Fail(At(p, "max_megapixels"), "Megapixel bound must be positive.");
                if (dimensions)
                {
                    var map = Object(pricing["dimensions"], At(p, "dimensions")); Closed(map, At(p, "dimensions"), "field", "values");
                    var field = Reference(fields, Text(map, "field", At(p, "dimensions")), At(p, "dimensions/field"));
                    if (Text(field, "type", p) != "enum") Fail(At(p, "dimensions/field"), "Dimension mapping requires an enum control.");
                    var values = Object(map["values"], At(p, "dimensions/values"));
                    var choices = field["values"]!.AsArray().Select(v => v!.GetValue<string>()).ToArray();
                    if (values.Count != choices.Length || choices.Any(c => !values.ContainsKey(c))) Fail(At(p, "dimensions/values"), "Dimension mapping must cover each enum choice.");
                    foreach (var pair in values)
                    {
                        string dp = At(p, "dimensions/values/" + Escape(pair.Key)); var size = Object(pair.Value, dp); Closed(size, dp, "width", "height");
                        foreach (string dimension in new[] { "width", "height" }) if (Integer(size[dimension], At(dp, dimension)) < 1 || Integer(size[dimension], At(dp, dimension)) > 65536) Fail(At(dp, dimension), "Pixel dimensions must be between 1 and 65536.");
                    }
                }
            }
            else if (pricing.ContainsKey("dimensions") || pricing.ContainsKey("max_megapixels")) Fail(p, "Dimensions are only supported for megapixel pricing.");
            var rates = Array(pricing, "rates", p, 256, true);
            var rateKeys = new HashSet<string>(StringComparer.Ordinal);
            HashSet<string>? selectorKeys = null;
            for (int i = 0; i < rates.Count; i++)
            {
                string rp = At(p, "rates/" + i); var rate = Object(rates[i], rp); Closed(rate, rp, "selectors", "rate_usd");
                if (ExactNumber(rate["rate_usd"], At(rp, "rate_usd")) < 0) Fail(At(rp, "rate_usd"), "Pricing rate cannot be negative.");
                var selectors = Object(rate["selectors"], At(rp, "selectors"));
                var keys = new HashSet<string>(selectors.Select(s => s.Key), StringComparer.Ordinal);
                if (selectorKeys != null && !selectorKeys.SetEquals(keys)) Fail(At(rp, "selectors"), "All rates must use the same selector keys; wildcard overlap is unsupported.");
                selectorKeys = keys;
                foreach (var selector in selectors)
                {
                    string sp = At(rp, "selectors/" + Escape(selector.Key)); var field = Reference(fields, selector.Key, sp);
                    string type = Text(field, "type", sp);
                    if (type != "enum" && type != "boolean") Fail(sp, "Rate selectors must reference finite enum or boolean controls.");
                    FieldValue(field, selector.Value, sp);
                }
                if (!rateKeys.Add(FalCanonicalJson.Hash(selectors))) Fail(rp, "Duplicate pricing selector combination.");
            }
        }

        private static void ValidateEvidence(JsonObject evidence, string p)
        {
            Closed(evidence, p, "url", "reviewed_on", "qualification");
            Url(Text(evidence, "url", p), At(p, "url")); Date(Text(evidence, "reviewed_on", p), At(p, "reviewed_on"));
            OneOf(Text(evidence, "qualification", p), At(p, "qualification"), "synthetic", "unverified", "qualified");
        }

        private static void FieldValue(JsonObject field, JsonNode? value, string p)
        {
            string type = Text(field, "type", p);
            if (type == "boolean") { Boolean(value, p); return; }
            if (type == "integer" || type == "number")
            {
                decimal number = UserNumber(value, type, p);
                decimal min = UserNumber(field["min"], type, p); decimal max = UserNumber(field["max"], type, p);
                if (number < min || number > max) Fail(p, "Value is outside declared bounds.");
                if (field.ContainsKey("step") && (number - min) % UserNumber(field["step"], type, p) != 0) Fail(p, "Value is off the declared step, originating at min.");
                return;
            }
            string text = Text(value, p, true);
            if (field["scope"]!.GetValue<string>() != "request" || field["key"]!.GetValue<string>() != "prompt") ScalarMediaBoundary(value, p);
            if (type == "enum" && !field["values"]!.AsArray().Any(v => v!.GetValue<string>() == text)) Fail(p, "Value is not a declared enum choice.");
            if (type == "string" && (text.Length < (field.ContainsKey("min_length") ? Integer(field["min_length"], p) : 0) || text.Length > Integer(field["max_length"], p))) Fail(p, "Value violates string length bounds.");
        }

        private static decimal UserNumber(JsonNode? value, string type, string p)
        {
            decimal number = type == "integer" ? Integer(value, p) : ExactNumber(value, p);
            if (type == "integer")
            {
                if (decimal.Truncate(number) != number || number < -9007199254740991m || number > 9007199254740991m) Fail(p, "Integer must be in [-9007199254740991, 9007199254740991].");
            }
            else if (Math.Abs(number) > 1000000000m || decimal.Round(number, 6) != number) Fail(p, "Number must have absolute value <= 1000000000 and at most six fractional places after trailing-zero normalization.");
            return number;
        }
        private static decimal ExactNumber(JsonNode? value, string p)
        {
            if (!FalCanonicalJson.TryExactDecimal(value, out decimal number)) Fail(p, "Expected an exactly representable finite decimal JSON number (numeric strings and rounding are not supported).");
            return number;
        }
        private static long Integer(JsonNode? value, string p)
        {
            decimal number = ExactNumber(value, p);
            if (decimal.Truncate(number) != number || number < long.MinValue || number > long.MaxValue) Fail(p, "Expected Int64 integer.");
            return (long)number;
        }
        private static void Scalar(JsonNode? value, string p)
        {
            if (!(value is JsonValue scalar)) Fail(p, "Only non-null scalar literals are supported.");
            if (value!.GetValueKind() == JsonValueKind.Number) ExactNumber(value, p);
            ScalarMediaBoundary(value, p);
        }
        private static void ScalarMediaBoundary(JsonNode? value, string p)
        { if (!FalScalarLiteralPolicy.IsAllowed(value)) Fail(p, "Scalar values cannot contain standalone media source locators. Use semantic media roles and resolved preparation."); }
        private static JsonObject Object(JsonNode? node, string p)
        { if (!(node is JsonObject json)) { Fail(p, "Expected object."); return null!; } return json; }
        private static JsonArray Array(JsonObject json, string key, string p, int max, bool nonempty = false)
        {
            if (!(json[key] is JsonArray array)) { Fail(At(p, key), "Expected array."); return null!; }
            if (array.Count > max || (nonempty && array.Count == 0)) Fail(At(p, key), "Expected " + (nonempty ? "1" : "0") + ".." + max + " entries.");
            return array;
        }
        private static void Closed(JsonObject json, string p, params string[] allowed)
        { foreach (var member in json) if (!allowed.Contains(member.Key, StringComparer.Ordinal)) Fail(At(p, Escape(member.Key)), "Unknown member; vocabulary is closed and case-sensitive."); }
        private static string Text(JsonObject json, string key, string p, bool empty = false) => Text(json[key], At(p, key), empty);
        private static string Text(JsonNode? node, string p, bool empty = false)
        {
            if (!(node is JsonValue value) || value.GetValueKind() != JsonValueKind.String) { Fail(p, "Expected string."); return null!; }
            string text = value.GetValue<string>();
            if ((!empty && string.IsNullOrWhiteSpace(text)) || text.Any(char.IsControl)) Fail(p, "Expected plain text without control characters.");
            return text;
        }
        private static bool Boolean(JsonNode? node, string p)
        {
            if (!(node is JsonValue value) || (value.GetValueKind() != JsonValueKind.True && value.GetValueKind() != JsonValueKind.False)) { Fail(p, "Expected JSON boolean."); return false; }
            return value.GetValue<bool>();
        }
        private static void OneOf(string value, string p, params string[] allowed)
        { if (!allowed.Contains(value, StringComparer.Ordinal)) Fail(p, "Unsupported value; expected " + string.Join(", ", allowed) + "."); }
        private static void Version(JsonObject json, string p)
        { if (Integer(json["schema_version"], At(p, "schema_version")) != 1) Fail(At(p, "schema_version"), "Supported schema_version is 1."); }
        private static void Id(string value, string p)
        { if (value.Length > 200 || !Regex.IsMatch(value, "^[a-z0-9][a-z0-9_.-]*(/[a-z0-9][a-z0-9_.-]*)*$") || value.Split('/').Any(s => s == "." || s == "..")) Fail(p, "Expected a bounded stable lowercase identifier."); }
        private static void Endpoint(string value, string p)
        { Id(value, p); if (value.Split('/').Length < 2 || value.IndexOf('%') >= 0) Fail(p, "Expected exact fal endpoint ID with owner/model segments, never a URL."); }
        private static void Pointer(string value, string p)
        { if (!value.StartsWith("/", StringComparison.Ordinal) || Regex.IsMatch(value, "~(?![01])") || value.Split('/').Skip(1).Any(s => s.Length == 0)) Fail(p, "Expected non-root RFC 6901 JSON pointer with nonempty segments and valid ~0/~1 escapes."); }
        private static void AddWriter(string pointer, string p, List<string> writers)
        {
            Pointer(pointer, p);
            if (writers.Any(w => w == pointer || w.StartsWith(pointer + "/", StringComparison.Ordinal) || pointer.StartsWith(w + "/", StringComparison.Ordinal))) Fail(p, "Payload writers conflict at identical or parent/child destinations.");
            writers.Add(pointer);
        }
        private static void Url(string value, string p)
        { if (!Uri.TryCreate(value, UriKind.Absolute, out var uri) || uri.Scheme != "https" || uri.UserInfo.Length != 0) Fail(p, "Evidence/source must be an absolute HTTPS documentation URL without credentials."); }
        private static void Date(string value, string p)
        { if (!DateTime.TryParseExact(value, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out _)) Fail(p, "Expected a valid yyyy-MM-dd review date."); }
        private static string Escape(string value) => value.Replace("~", "~0").Replace("/", "~1");
        private static string At(string pointer, string member) => (pointer == "/" ? "" : pointer) + "/" + member;
        private static void Fail(string pointer, string message) => throw new AdmissionException(pointer, message);
        private sealed class AdmissionException : Exception
        { internal string Pointer { get; } internal AdmissionException(string pointer, string message) : base(message) { Pointer = pointer; } }
    }

    /// <summary>
    /// Shared lexical boundary for scalar controls and fixed payload literals. Task 2
    /// must apply this policy to every supplied option value before payload mapping.
    /// It does not validate field types, numeric bounds, or resolve/open any location.
    /// The request prompt alone is free text and bypasses this locator policy.
    /// </summary>
    public static class FalScalarLiteralPolicy
    {
        public static bool IsAllowed(JsonNode? value)
        {
            if (!(value is JsonValue scalar)) return false;
            var kind = scalar.GetValueKind();
            if (kind == JsonValueKind.Number || kind == JsonValueKind.True || kind == JsonValueKind.False) return true;
            if (kind != JsonValueKind.String) return false;
            string raw = scalar.GetValue<string>();
            if (raw.Any(char.IsControl)) return false;
            string text = raw.Trim();
            // URI schemes cover HTTP(S), data, file, blob, cloud storage and drive
            // prefixes. Separators reserve absolute/relative paths for media roles.
            if (Regex.IsMatch(text, "^[A-Za-z][A-Za-z0-9+.-]*:") || text.IndexOfAny(new[] { '/', '\\' }) >= 0
                || text == "." || text == ".." || text == "~") return false;
            // Bare filenames (including spaces and URL query/fragment suffixes)
            // are locations too. Ordinary enum labels, numeric ratios and prose
            // without locator syntax remain scalar values.
            return !Regex.IsMatch(text, "^[^<>:\"|?*]+\\.[A-Za-z][A-Za-z0-9]*(?:[?#].*)?$");
        }
    }
    public sealed class FalCatalogLoadResult
    {
        public FalCatalogSnapshot? Catalog { get; }
        public IReadOnlyList<FalCatalogDiagnostic> Diagnostics { get; }
        internal FalCatalogLoadResult(FalCatalogSnapshot? catalog, FalCatalogDiagnostic[] diagnostics)
        {
            if ((catalog != null) == (diagnostics.Length != 0)) throw new ArgumentException("Exactly one of catalog or diagnostics is required.");
            Catalog = catalog; Diagnostics = Array.AsReadOnly((FalCatalogDiagnostic[])diagnostics.Clone());
        }
    }
    public sealed class FalCatalogDiagnostic
    {
        public string File { get; }
        public string Pointer { get; }
        public string Message { get; }
        internal FalCatalogDiagnostic(string file, string pointer, string message) { File = file; Pointer = pointer; Message = message; }
    }
}
