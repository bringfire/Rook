using System.Text.Json;
using MultiProviderSpike.Models;

var repoRoot = FindRepoRoot(AppContext.BaseDirectory);
string? artifactRoot;
if (args.Length > 0)
{
    artifactRoot = Path.GetFullPath(args[0]);
}
else
{
    var artifactsParent = Path.Combine(repoRoot, "docs", "rook_docs", "artifacts");
    if (!Directory.Exists(artifactsParent))
    {
        Console.Error.WriteLine($"Missing curated artifact root: {artifactsParent}. Pass an explicit artifact directory as the first argument.");
        return 2;
    }
    artifactRoot = Directory.GetDirectories(artifactsParent, "*-multi-provider-spike")
        .OrderByDescending(path => path)
        .FirstOrDefault();
}

if (string.IsNullOrWhiteSpace(artifactRoot) || !Directory.Exists(artifactRoot))
{
    Console.Error.WriteLine("Missing curated artifact directory. Pass it as the first argument.");
    return 2;
}

var options = new JsonSerializerOptions
{
    PropertyNameCaseInsensitive = true,
    WriteIndented = true,
};

var requiredProbeIds = new[] { "p2", "p3", "p4" };
foreach (var probeId in requiredProbeIds)
{
    var probeDir = Path.Combine(artifactRoot, probeId);
    if (!Directory.Exists(probeDir))
    {
        Console.Error.WriteLine($"Missing curated probe directory: {probeDir}");
        return 3;
    }

    int checkedCount = 0;
    bool hasSubmit = false;
    bool hasResultEvidence = false;  // fetch.json, fetch_head.json, or any status_*.json

    foreach (var file in Directory.GetFiles(probeDir, "*.json").OrderBy(path => path))
    {
        var fileName = Path.GetFileName(file);
        if (fileName.Equals("manifest.json", StringComparison.OrdinalIgnoreCase))
            continue;

        var json = File.ReadAllText(file);
        var envelope = JsonSerializer.Deserialize<CaptureEnvelope>(json, options);
        if (envelope is null)
        {
            Console.Error.WriteLine($"Could not deserialize {file}");
            return 4;
        }
        if (string.IsNullOrWhiteSpace(envelope.Stage))
        {
            Console.Error.WriteLine($"Capture stage missing in {file}");
            return 5;
        }

        var response = envelope.Response.Deserialize<CaptureHttpResponse>(options);
        if (response is null)
        {
            Console.Error.WriteLine($"Response wrapper did not match expected capture shape in {file}");
            return 6;
        }

        if (response.Body.ValueKind is JsonValueKind.Object)
        {
            var bodyShape = response.Body.Deserialize<ProviderBodyShape>(options);
            if (bodyShape is null)
            {
                Console.Error.WriteLine($"Could not deserialize provider body shape in {file}");
                return 7;
            }
            // Accept either a recognized success-result envelope OR a recognized
            // error envelope. Both prove the capture round-trips through a typed
            // shape; they are reported separately so the operator can tell at a
            // glance whether a probe captured a working contract or a failure.
            if (!bodyShape.IsRecognizedShape())
            {
                Console.Error.WriteLine(
                    $"Provider body did not expose any recognized lifecycle/result OR error signal in {file}");
                return 7;
            }
            if (bodyShape.HasErrorSignal() && !bodyShape.HasLifecycleOrResultSignal())
            {
                Console.WriteLine(
                    $"  note: {file} matches an ERROR envelope (detail field present); recorded as error evidence");
            }
        }

        var roundTrip = JsonSerializer.Serialize(envelope, options);
        if (string.IsNullOrWhiteSpace(roundTrip) || !roundTrip.Contains("\"response\""))
        {
            Console.Error.WriteLine($"Round-trip lost response payload in {file}");
            return 8;
        }

        checkedCount++;
        var stem = Path.GetFileNameWithoutExtension(fileName).ToLowerInvariant();
        if (stem == "submit") hasSubmit = true;
        if (stem == "fetch" || stem == "fetch_head" || stem.StartsWith("status_"))
            hasResultEvidence = true;
    }

    if (checkedCount == 0)
    {
        Console.Error.WriteLine($"Probe {probeId}: no JSON evidence files checked (only manifest.json or empty directory). Probe contract requires submit plus at least one result/status artifact.");
        return 9;
    }
    if (!hasSubmit)
    {
        Console.Error.WriteLine($"Probe {probeId}: missing submit.json. Required by contract.");
        return 10;
    }
    if (!hasResultEvidence)
    {
        Console.Error.WriteLine($"Probe {probeId}: missing fetch.json / fetch_head.json / status_*.json. Required by contract (need at least one result or polling artifact).");
        return 11;
    }
}

Console.WriteLine($"C# shape probe passed for {artifactRoot}");
return 0;

static string FindRepoRoot(string start)
{
    var dir = new DirectoryInfo(start);
    while (dir is not null)
    {
        if (Directory.Exists(Path.Combine(dir.FullName, ".git")))
            return dir.FullName;
        dir = dir.Parent;
    }
    throw new InvalidOperationException("Could not find repository root.");
}
