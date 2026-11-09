using System;
namespace Rook.Services.Vision.Fal
{
    /// <summary>Transient prepared transport value supplied by the bounded media service.</summary>
    public sealed class FalPreparedMedia
    {
        public string Role { get; }
        public int Ordinal { get; }
        public string TransportValue { get; }
        public FalPreparedMedia(string role, int ordinal, string transportValue)
        {
            if (string.IsNullOrWhiteSpace(role)) throw new ArgumentException("A semantic role is required.", nameof(role));
            if (ordinal < 0) throw new ArgumentOutOfRangeException(nameof(ordinal));
            if (string.IsNullOrWhiteSpace(transportValue)) throw new ArgumentException("A prepared value is required.", nameof(transportValue));
            Role = role; Ordinal = ordinal; TransportValue = transportValue;
        }
    }
}
