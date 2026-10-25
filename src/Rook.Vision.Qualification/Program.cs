using System;
using System.Collections.Generic;
namespace Rook.Vision.Qualification
{
    internal static class Program
    {
        private static int Main(string[] args)
        {
            try
            {
                if (args.Length < 1 || args.Length % 2 != 1) throw new ArgumentException("Expected a verb and named argument pairs.");
                var values = new Dictionary<string, string>(StringComparer.Ordinal);
                for (int i = 1; i < args.Length; i += 2) values.Add(args[i], args[i + 1]);
                string Need(string name) => values.TryGetValue(name, out var value) && !string.IsNullOrWhiteSpace(value) ? value : throw new ArgumentException("Required " + name);
                if (args[0] == "validate-catalog" && values.Count == 2) return CatalogQualification.Validate(Need("--root"), Need("--report"));
                if (args[0] == "verify-cases" && values.Count == 3) return ConfiguredEndpointQualification.VerifyAsync(Need("--catalog"), Need("--cases"), Need("--report")).GetAwaiter().GetResult();
                if (args[0] == "freeze-runtime" && values.Count == 4) return RuntimeFreezeManifest.Capture(Need("--repo"), Need("--plugin-root"), Need("--mcp-root"), Need("--out"));
                throw new ArgumentException("Usage: validate-catalog --root ROOT --report JSON | verify-cases --catalog ROOT --cases JSON --report JSON | freeze-runtime --repo ROOT --plugin-root PATH --mcp-root PATH --out JSON");
            }
            catch (Exception ex) { Console.Error.WriteLine(ex.Message); return 1; }
        }
    }
}
