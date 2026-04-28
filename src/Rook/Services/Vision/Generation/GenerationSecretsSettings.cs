using System.Collections.Generic;

namespace Rook.Services.Vision.Generation
{
    public sealed class GenerationSecretsSettings
    {
        public Dictionary<string, GenerationSecretEntry> Secrets { get; set; }
            = new Dictionary<string, GenerationSecretEntry>();
    }

    public sealed class GenerationSecretEntry
    {
        public string? EncryptedValue { get; set; }
        public string? Preview { get; set; }
    }
}
