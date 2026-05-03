using System;
using System.IO;
using System.Linq;
using Rook.Services.Vision;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Xunit;

namespace Rook.Tests.Services.Vision
{
    public class VisionProviderRegistrationsTests
    {
        [Fact]
        public void CreateCredentialMetadata_merges_gemini_fal_and_replicate()
        {
            var metadata = VisionProviderRegistrations.CreateCredentialMetadata();

            var providers = metadata.EnumerateProviders().ToArray();

            Assert.Equal(new[] { "gemini", "fal", "replicate" }, providers.Select(p => p.ProviderName));
            Assert.Contains(
                Assert.Single(providers, p => p.ProviderName == "gemini").SecretRequirements,
                r => r.Key == GenerationSecretKeys.GeminiApiKey);
            Assert.Contains(
                Assert.Single(providers, p => p.ProviderName == "fal").SecretRequirements,
                r => r.Key == GenerationSecretKeys.FalApiKey);

            var replicate = Assert.Single(providers, p => p.ProviderName == "replicate");
            var requirement = Assert.Single(replicate.SecretRequirements);
            Assert.Equal(GenerationSecretKeys.ReplicateApiToken, requirement.Key);
            Assert.Equal("Replicate API token", requirement.DisplayName);
            Assert.True(requirement.IsRequired);
            Assert.True(requirement.IsSensitive);

            Assert.DoesNotContain(providers, p => p.ProviderName == "veo");
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
            var methodBody = ExtractMethodBody(source, "CreateCredentialMetadata");

            Assert.DoesNotContain("CreateImageRegistrations", methodBody);
            Assert.DoesNotContain("CreateVideoRegistrations", methodBody);
            Assert.DoesNotContain("new VeoProvider", methodBody);
            Assert.DoesNotContain("new FalVideoProvider", methodBody);
            Assert.DoesNotContain("new ReplicateImageProvider", methodBody);
        }

        [Fact]
        public void CreateImageRegistrations_default_composition_includes_replicate()
        {
            var registrations = VisionProviderRegistrations.CreateImageRegistrations(
                () => null,
                () => null,
                () => null);
            var registry = new DefaultImageProviderRegistry(registrations);

            Assert.True(registry.TryResolve("black-forest-labs/flux-schnell", out var resolved));
            Assert.Equal("replicate", resolved.ProviderName);
            Assert.Equal(ImageSubmissionMode.AsyncImageJob, resolved.SubmissionMode);
            Assert.True(registry.TryResolveProviderByName("replicate", out _));
        }

        [Fact]
        public void CreateImageRegistrations_default_registry_includes_replicate_descriptor()
        {
            var registrations = VisionProviderRegistrations.CreateImageRegistrations(
                () => null,
                () => null,
                () => null);
            var registry = new DefaultImageProviderRegistry(registrations);

            var descriptors = registry.EnumerateAllModels();

            Assert.Contains(descriptors, d => d.ProviderName == "replicate");
            Assert.Contains(
                descriptors,
                d => d.ModelId == "black-forest-labs/flux-schnell");
            Assert.True(registry.TryResolveProviderByName("replicate", out _));
            Assert.True(registry.TryResolve("black-forest-labs/flux-schnell", out _));
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

        private static string ExtractMethodBody(string source, string methodName)
        {
            var signatureIndex = source.IndexOf(methodName, StringComparison.Ordinal);
            if (signatureIndex < 0)
                throw new InvalidOperationException($"{methodName} was not found.");

            var openBrace = source.IndexOf('{', signatureIndex);
            if (openBrace < 0)
                throw new InvalidOperationException($"{methodName} body was not found.");

            var depth = 0;
            for (var i = openBrace; i < source.Length; i++)
            {
                if (source[i] == '{') depth++;
                if (source[i] == '}') depth--;
                if (depth == 0)
                    return source.Substring(openBrace, i - openBrace + 1);
            }

            throw new InvalidOperationException($"{methodName} body was not closed.");
        }
    }
}
