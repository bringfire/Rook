using System;
using Rook.Services.Vision.Generation;
namespace Rook.Services.Vision.Fal.Models
{
    public sealed class FalModelOptions : ProviderOptions
    {
        public FalModelInput Input { get; }
        public string? SelectedOperation { get; }
        public FalModelOptions(FalModelInput input, string? selectedOperation = null)
        { Input = input ?? throw new ArgumentNullException(nameof(input)); SelectedOperation = selectedOperation ?? input.OperationId; }
    }
}
