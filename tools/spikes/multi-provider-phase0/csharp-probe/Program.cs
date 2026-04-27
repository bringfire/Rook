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

    foreach (var file in Directory.GetFiles(probeDir, "*.json").OrderBy(path => path))
    {
        if (Path.GetFileName(file).Equals("manifest.json", StringComparison.OrdinalIgnoreCase))
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
            if (bodyShape is null || !bodyShape.HasLifecycleOrResultSignal())
            {
                Console.Error.WriteLine($"Provider body did not expose lifecycle/result signals in {file}");
                return 7;
            }
        }

        var roundTrip = JsonSerializer.Serialize(envelope, options);
        if (string.IsNullOrWhiteSpace(roundTrip) || !roundTrip.Contains("\"response\""))
        {
            Console.Error.WriteLine($"Round-trip lost response payload in {file}");
            return 8;
        }
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
