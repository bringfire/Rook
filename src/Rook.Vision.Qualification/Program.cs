using System;

namespace Rook.Vision.Qualification
{
    internal static class Program
    {
        private static int Main(string[] args)
        {
            try
            {
                if (args.Length != 5 || args[0] != "validate-catalog")
                    throw new ArgumentException("Usage: validate-catalog --root <catalog-directory> --report <json-path>");
                string? root = null, report = null;
                for (int i = 1; i < args.Length; i += 2)
                {
                    if (args[i] == "--root" && root == null) root = args[i + 1];
                    else if (args[i] == "--report" && report == null) report = args[i + 1];
                    else throw new ArgumentException("Unknown or repeated argument: " + args[i]);
                }
                if (string.IsNullOrWhiteSpace(root) || string.IsNullOrWhiteSpace(report))
                    throw new ArgumentException("Both --root and --report are required.");
                return CatalogQualification.Validate(root!, report!);
            }
            catch (Exception ex) { Console.Error.WriteLine(ex.Message); return 1; }
        }
    }
}
