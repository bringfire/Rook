using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text.Json;
using Rhino;
using Rhino.Geometry;
using Grasshopper;
using Grasshopper.Kernel;

public class Script_Instance : GH_ScriptInstance
{
    private const string DefaultActorSetRef = ".rook/director_planning/actor_sets/roof_uplift_vertical_test_chunk_001.json";
    private const string DefaultActorGroupingRef = ".rook/director_planning/actor_sets/roof_uplift_vertical_test_chunk_001_subsets/same_orientation_mullions_001_band_sets/same_orientation_mullions_001_bands_001.json";
    private const string DefaultSourceInstanceId = "a28cbdb5-51fa-46b2-b18b-ab880b54ded7";

    private CachedActorSet _cache;

    private void RunScript(
		object Actors,
		object Start,
		object Progress,
		object MaxH,
		object Spread,
		object FastPreview,
		ref object G,
		ref object H,
		ref object Info)
    {
        var frameTimer = Stopwatch.StartNew();
        var config = ResolveActorConfig(Actors);
        bool start = ReadBool(Start, true);
        double progress = Clamp(ReadDouble(Progress, 0.0), 0.0, 1.0);
        double effectiveProgress = start ? progress : 0.0;
        double maxH = ReadDouble(MaxH, 10000.0);
        double spread = Math.Max(1.0, ReadDouble(Spread, 16.0));
        bool fastPreview = ReadBool(FastPreview, true);

        G = null;
        H = null;
        Info = "";

        string cacheStatus;
        var cache = GetOrBuildCache(config, out cacheStatus);
        if (cache == null)
        {
            Info = cacheStatus;
            return;
        }

        double front = effectiveProgress * ((double)(cache.BandCount - 1) + spread);
        var geometry = new List<GeometryBase>(cache.ResolvedCount);
        var heights = new List<double>(cache.ResolvedCount);

        foreach (var member in cache.Members)
        {
            double bandT = Clamp((front - member.BandIndex) / spread, 0.0, 1.0);
            double dz = maxH * SmoothStep(bandT);
            heights.Add(dz);

            var xform = Transform.Translation(0.0, 0.0, dz);
            if (fastPreview && member.BaseMesh != null)
            {
                var mesh = member.BaseMesh.DuplicateMesh();
                mesh.Transform(xform);
                geometry.Add(mesh);
            }
            else
            {
                var brep = member.BaseBrep.DuplicateBrep();
                brep.Transform(xform);
                geometry.Add(brep);
            }
        }

        frameTimer.Stop();
        G = geometry;

        var sampleIds = new string[cache.Members.Count];
        for (int i = 0; i < cache.Members.Count; i++)
            sampleIds[i] = cache.Members[i].DefId;
        H = System.Text.Json.JsonSerializer.Serialize(new { ids = sampleIds, z = heights });

        Info = $"Director movement primitive v2: {geometry.Count}/{cache.SourceMemberCount} items; mode={(fastPreview ? "mesh-preview" : "brep-preview")}; start={start}; progress={progress:0.###}; effectiveProgress={effectiveProgress:0.###}; maxH={maxH:0.###}; spreadBands={spread:0.###}; frontBand={front:0.###}; bands={cache.BandCount}; missingIds={cache.MissingId}; nonBreps={cache.NonBrep}; cache={cacheStatus}; cacheBuildMs={cache.BuildMs:0.###}; frameMs={frameTimer.Elapsed.TotalMilliseconds:0.###}; actors={config.Source}; actorKey={config.CacheKey}; sourceTop={config.SourceInstanceId}; resolver=v2 metadata refs.";
    }

    private CachedActorSet GetOrBuildCache(ActorConfig config, out string status)
    {
        status = "reused";
        if (_cache != null && _cache.Key == config.CacheKey)
            return _cache;

        var doc = RhinoDoc.ActiveDoc;
        if (doc == null)
        {
            status = "No active Rhino document.";
            return null;
        }

        if (!File.Exists(config.ActorSetPath))
        {
            status = "Actor metadata file not found: " + config.ActorSetPath;
            return null;
        }

        if (!File.Exists(config.ActorGroupingPath))
        {
            status = "Actor grouping metadata file not found: " + config.ActorGroupingPath;
            return null;
        }

        if (!Guid.TryParse(config.SourceInstanceId, out var instanceGuid))
        {
            status = "Source occurrence instance id is invalid: " + config.SourceInstanceId;
            return null;
        }

        var inst = doc.Objects.FindId(instanceGuid) as Rhino.DocObjects.InstanceObject;
        if (inst == null)
        {
            status = "Source occurrence block instance was not found in the active document: " + config.SourceInstanceId;
            return null;
        }

        var idef = inst.InstanceDefinition;
        if (idef == null)
        {
            status = "Source occurrence block instance has no definition.";
            return null;
        }

        var defObjects = idef.GetObjects();
        if (defObjects == null || defObjects.Length == 0)
        {
            status = "Block definition has no direct objects.";
            return null;
        }

        var actorCandidates = LoadActorCandidates(config.ActorSetPath);
        var members = LoadBandMembers(config.ActorGroupingPath, actorCandidates);
        if (members.Count == 0)
        {
            status = "Band metadata contained no members.";
            return null;
        }

        var timer = Stopwatch.StartNew();
        var built = BuildCache(config.CacheKey, inst, defObjects, members);
        timer.Stop();
        if (built == null)
        {
            status = "Cache build failed.";
            return null;
        }

        built.BuildMs = timer.Elapsed.TotalMilliseconds;
        _cache = built;
        status = "built";
        return _cache;
    }

    private static CachedActorSet BuildCache(string key, Rhino.DocObjects.InstanceObject inst, Rhino.DocObjects.RhinoObject[] defObjects, List<MemberRef> members)
    {
        var objectsById = new Dictionary<Guid, Rhino.DocObjects.RhinoObject>();
        foreach (var obj in defObjects)
        {
            if (obj != null && !objectsById.ContainsKey(obj.Id))
                objectsById.Add(obj.Id, obj);
        }

        int bandCount = 0;
        foreach (var member in members)
            if (member.BandIndex + 1 > bandCount) bandCount = member.BandIndex + 1;

        var cache = new CachedActorSet
        {
            Key = key,
            BandCount = bandCount,
            SourceMemberCount = members.Count
        };

        foreach (var member in members)
        {
            Rhino.DocObjects.RhinoObject source = null;
            foreach (var id in member.CandidateIds)
            {
                if (objectsById.TryGetValue(id, out source))
                    break;
            }

            if (source == null)
            {
                cache.MissingId++;
                continue;
            }

            var brep = source.Geometry as Brep;
            if (brep == null)
            {
                cache.NonBrep++;
                continue;
            }

            var baseBrep = brep.DuplicateBrep();
            if (baseBrep == null)
            {
                cache.MissingId++;
                continue;
            }

            baseBrep.Transform(inst.InstanceXform);
            cache.Members.Add(new CachedMember
            {
                BandIndex = member.BandIndex,
                Ordinal = member.Ordinal,
                DefId = source.Id.ToString(),
                BaseBrep = baseBrep,
                BaseMesh = BuildPreviewMesh(baseBrep)
            });
        }

        cache.ResolvedCount = cache.Members.Count;
        return cache;
    }

    private static Mesh BuildPreviewMesh(Brep brep)
    {
        var parts = Mesh.CreateFromBrep(brep, MeshingParameters.FastRenderMesh);
        if (parts == null || parts.Length == 0)
            return null;

        var joined = new Mesh();
        foreach (var part in parts)
        {
            if (part != null)
                joined.Append(part);
        }

        if (joined.Vertices.Count == 0)
            return null;

        joined.Normals.ComputeNormals();
        joined.Compact();
        return joined;
    }

    private static ActorConfig ResolveActorConfig(object actors)
    {
        var config = DefaultConfig();
        string text = actors == null ? null : actors.ToString();
        if (string.IsNullOrWhiteSpace(text))
            return config;

        text = text.Trim();
        config.CacheKey = "actors:" + text;
        try
        {
            if (File.Exists(text))
            {
                ApplyActorConfigJson(config, File.ReadAllText(text), text);
                return config;
            }

            if (text.StartsWith("{") && text.EndsWith("}"))
                ApplyActorConfigJson(config, text, "inline-v2-runtime-payload");
        }
        catch (Exception ex)
        {
            config.Source = "defaults-invalid-actors-input:" + ex.GetType().Name;
        }

        return config;
    }

    private static ActorConfig DefaultConfig()
    {
        var config = new ActorConfig
        {
            ActorSetRef = DefaultActorSetRef,
            ActorGroupingRef = DefaultActorGroupingRef,
            SourceInstanceId = DefaultSourceInstanceId,
            Source = "defaults-v2-refs",
            CacheKey = "defaults-v2-refs"
        };
        string root = GetProjectRoot();
        config.ActorSetPath = ResolveMetadataRef(root, config.ActorSetRef);
        config.ActorGroupingPath = ResolveMetadataRef(root, config.ActorGroupingRef);
        return config;
    }

    private static void ApplyActorConfigJson(ActorConfig config, string json, string source)
    {
        using (var doc = JsonDocument.Parse(json))
        {
            var root = doc.RootElement;
            string actorRef = GetString(root, "actor_set_ref");
            string groupingRef = GetString(root, "actor_grouping_ref");
            string actorPath = GetString(root, "resolved_actor_set_path");
            string groupingPath = GetString(root, "resolved_actor_grouping_path");
            string payloadCacheKey = GetString(root, "cache_key");

            if (!string.IsNullOrWhiteSpace(actorRef))
            {
                config.ActorSetRef = actorRef;
                config.ActorSetPath = ResolveMetadataRef(GetProjectRoot(), actorRef);
            }
            if (!string.IsNullOrWhiteSpace(groupingRef))
            {
                config.ActorGroupingRef = groupingRef;
                config.ActorGroupingPath = ResolveMetadataRef(GetProjectRoot(), groupingRef);
            }
            if (!string.IsNullOrWhiteSpace(actorPath) && File.Exists(actorPath))
                config.ActorSetPath = actorPath;
            if (!string.IsNullOrWhiteSpace(groupingPath) && File.Exists(groupingPath))
                config.ActorGroupingPath = groupingPath;
            if (!string.IsNullOrWhiteSpace(payloadCacheKey))
                config.CacheKey = "actors:" + payloadCacheKey;

            JsonElement sourceOccurrence;
            if (root.TryGetProperty("source_occurrence", out sourceOccurrence) && sourceOccurrence.ValueKind == JsonValueKind.Object)
            {
                string sourceId = GetString(sourceOccurrence, "source_top_level_object_id");
                if (!string.IsNullOrWhiteSpace(sourceId))
                    config.SourceInstanceId = sourceId;
            }

            JsonElement takeContext;
            if (root.TryGetProperty("source_take_context", out takeContext) && takeContext.ValueKind == JsonValueKind.Object)
            {
                string sourceId = GetString(takeContext, "top_level_instance_id");
                if (!string.IsNullOrWhiteSpace(sourceId))
                    config.SourceInstanceId = sourceId;
            }
        }

        config.Source = source;
    }

    private static string GetProjectRoot()
    {
        var doc = RhinoDoc.ActiveDoc;
        if (doc == null || string.IsNullOrWhiteSpace(doc.Path))
            return null;
        return Path.GetDirectoryName(doc.Path);
    }

    private static string ResolveMetadataRef(string projectRoot, string metadataRef)
    {
        if (string.IsNullOrWhiteSpace(projectRoot) || string.IsNullOrWhiteSpace(metadataRef))
            return "";
        string normalized = metadataRef.Trim().Trim('"').Replace('\\', '/');
        if (!normalized.StartsWith(".rook/", StringComparison.Ordinal) || normalized.Contains("../") || normalized.Contains("/..") || Path.IsPathRooted(normalized))
            return "";
        return Path.GetFullPath(Path.Combine(projectRoot, normalized.Replace('/', Path.DirectorySeparatorChar)));
    }

    private static Dictionary<int, List<Guid>> LoadActorCandidates(string path)
    {
        var result = new Dictionary<int, List<Guid>>();
        if (!File.Exists(path)) return result;

        using (var doc = JsonDocument.Parse(File.ReadAllText(path)))
        {
            JsonElement members;
            if (!doc.RootElement.TryGetProperty("members", out members) || members.ValueKind != JsonValueKind.Array)
                return result;

            foreach (var member in members.EnumerateArray())
            {
                int ordinal = GetInt(member, "ordinal", -1);
                if (ordinal < 0) continue;
                var ids = new List<Guid>();

                JsonElement observedSelection;
                if (member.TryGetProperty("observed_selection", out observedSelection))
                    AddGuid(ids, GetString(observedSelection, "id"));

                JsonElement currentReference;
                if (member.TryGetProperty("current_reference", out currentReference))
                    AddGuid(ids, GetString(currentReference, "document_object_id"));

                JsonElement resolvedReference;
                if (member.TryGetProperty("resolved_reference", out resolvedReference))
                    AddGuid(ids, GetString(resolvedReference, "definition_object_id"));

                if (ids.Count > 0)
                    result[ordinal] = ids;
            }
        }

        return result;
    }

    private static List<MemberRef> LoadBandMembers(string path, Dictionary<int, List<Guid>> actorCandidates)
    {
        var result = new List<MemberRef>();
        using (var doc = JsonDocument.Parse(File.ReadAllText(path)))
        {
            JsonElement bands;
            if (!doc.RootElement.TryGetProperty("bands", out bands) || bands.ValueKind != JsonValueKind.Array)
                return result;

            foreach (var band in bands.EnumerateArray())
            {
                int bandIndex = GetInt(band, "sequence_index", result.Count);
                JsonElement members;
                if (!band.TryGetProperty("members", out members) || members.ValueKind != JsonValueKind.Array)
                    continue;

                foreach (var item in members.EnumerateArray())
                {
                    var member = new MemberRef();
                    member.BandIndex = bandIndex;
                    member.Ordinal = GetInt(item, "ordinal", -1);
                    AddGuid(member.CandidateIds, GetString(item, "observed_id"));

                    List<Guid> candidates;
                    if (member.Ordinal >= 0 && actorCandidates.TryGetValue(member.Ordinal, out candidates))
                    {
                        foreach (var id in candidates)
                            AddGuid(member.CandidateIds, id.ToString());
                    }

                    if (member.CandidateIds.Count > 0)
                        result.Add(member);
                }
            }
        }

        result.Sort((a, b) => a.BandIndex.CompareTo(b.BandIndex));
        return result;
    }

    private sealed class CachedActorSet
    {
        public string Key;
        public int BandCount;
        public int SourceMemberCount;
        public int ResolvedCount;
        public int MissingId;
        public int NonBrep;
        public double BuildMs;
        public readonly List<CachedMember> Members = new List<CachedMember>();
    }

    private sealed class CachedMember
    {
        public int BandIndex;
        public int Ordinal;
        public string DefId;
        public Brep BaseBrep;
        public Mesh BaseMesh;
    }

    private sealed class MemberRef
    {
        public int BandIndex;
        public int Ordinal;
        public readonly List<Guid> CandidateIds = new List<Guid>();
    }

    private sealed class ActorConfig
    {
        public string ActorSetRef;
        public string ActorGroupingRef;
        public string ActorSetPath;
        public string ActorGroupingPath;
        public string SourceInstanceId;
        public string Source;
        public string CacheKey;
    }

    private static string GetString(JsonElement element, string propertyName)
    {
        JsonElement value;
        if (element.TryGetProperty(propertyName, out value) && value.ValueKind == JsonValueKind.String)
            return value.GetString();
        return null;
    }

    private static int GetInt(JsonElement element, string propertyName, int fallback)
    {
        JsonElement value;
        if (element.TryGetProperty(propertyName, out value) && value.ValueKind == JsonValueKind.Number)
        {
            int parsed;
            if (value.TryGetInt32(out parsed)) return parsed;
        }
        return fallback;
    }

    private static void AddGuid(List<Guid> ids, string value)
    {
        if (string.IsNullOrWhiteSpace(value)) return;
        Guid id;
        if (!Guid.TryParse(value, out id)) return;
        if (!ids.Contains(id)) ids.Add(id);
    }

    private static double ReadDouble(object value, double fallback)
    {
        if (value == null) return fallback;
        try { return Convert.ToDouble(value); }
        catch { return fallback; }
    }

    private static bool ReadBool(object value, bool fallback)
    {
        if (value == null) return fallback;
        try { return Convert.ToBoolean(value); }
        catch { return fallback; }
    }

    private static double Clamp(double value, double min, double max)
    {
        if (value < min) return min;
        if (value > max) return max;
        return value;
    }

    private static double SmoothStep(double t)
    {
        t = Clamp(t, 0.0, 1.0);
        return t * t * (3.0 - 2.0 * t);
    }
}
