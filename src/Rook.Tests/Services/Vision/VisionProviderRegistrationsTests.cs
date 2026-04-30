using System;
using System.IO;
using System.Linq;
using Rook.Services.Vision;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision
{
    public class VisionProviderRegistrationsTests
    {
        [Fact]
        public void CreateCredentialMetadata_merges_gemini_owner_and_fal_from_image_and_video()
        {
            var metadata = VisionProviderRegistrations.CreateCredentialMetadata();

            var providers = metadata.EnumerateProviders().ToArray();

            Assert.Equal(new[] { "gemini", "fal" }, providers.Select(p => p.ProviderName));
            var gemini = Assert.Single(providers, p => p.ProviderName == "gemini");
            Assert.Contains(
                gemini.SecretRequirements,
                r => r.Key == GenerationSecretKeys.GeminiApiKey);

            var fal = Assert.Single(providers, p => p.ProviderName == "fal");
            Assert.Contains(
                fal.SecretRequirements,
                r => r.Key == GenerationSecretKeys.FalApiKey);

            Assert.DoesNotContain(providers, p => p.ProviderName == "veo");
            Assert.DoesNotContain(providers, p => p.ProviderName == "replicate");
            Assert.All(
                providers,
                p => Assert.DoesNotContain(
                    p.SecretRequirements,
                    r => r.Key == GenerationSecretKeys.ReplicateApiToken));
        }

        [Fact]
        public void CreateCredentialMetadata_normalizes_fal_secret_display_metadata()
        {
            var metadata = VisionProviderRegistrations.CreateCredentialMetadata();

            var fal = Assert.Single(metadata.EnumerateProviders(), p => p.ProviderName == "fal");
            var requirement = Assert.Single(
                fal.SecretRequirements,
                r => r.Key == GenerationSecretKeys.FalApiKey);

            Assert.Equal("fal.ai API key", requirement.DisplayName);
        }

        [Fact]
        public void CreateCredentialMetadata_does_not_construct_provider_registrations()
        {
            var source = File.ReadAllText(FindSourceFile());
            var methodBody = ExtractCreateCredentialMetadataBody(source);

            Assert.DoesNotContain("CreateImageRegistrations", methodBody);
            Assert.DoesNotContain("CreateVideoRegistrations", methodBody);
            Assert.DoesNotContain("new VeoProvider", methodBody);
            Assert.DoesNotContain("new FalVideoProvider", methodBody);
        }

        private static string FindSourceFile()
        {
            var dir = new DirectoryInfo(AppContext.BaseDirectory);
            while (dir is not null)
            {
                var candidate = Path.Combine(
                    dir.FullName,
                    "src", "Rook", "Services", "Vision", "VisionProviderRegistrations.cs");
                if (File.Exists(candidate))
                    return candidate;

                dir = dir.Parent;
            }

            throw new FileNotFoundException(
                "Could not locate src/Rook/Services/Vision/VisionProviderRegistrations.cs.");
        }

        private static string ExtractCreateCredentialMetadataBody(string source)
        {
            const string signature = "CreateCredentialMetadata";
            var signatureIndex = source.IndexOf(signature, StringComparison.Ordinal);
            if (signatureIndex < 0)
                throw new InvalidOperationException("CreateCredentialMetadata was not found.");

            var openBrace = source.IndexOf('{', signatureIndex);
            if (openBrace < 0)
                throw new InvalidOperationException("CreateCredentialMetadata body was not found.");

            var depth = 0;
            for (var i = openBrace; i < source.Length; i++)
            {
                if (source[i] == '{') depth++;
                if (source[i] == '}') depth--;
                if (depth == 0)
                    return source.Substring(openBrace, i - openBrace + 1);
            }

            throw new InvalidOperationException("CreateCredentialMetadata body was not closed.");
        }
    }
}
