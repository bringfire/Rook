namespace Rook.Services.Vision.Video.Framing
{
    public enum SourceFramingMode { Fit, Fill }
    internal static class SourceFramingModeExtensions
    {
        public static string Wire(this SourceFramingMode mode) => mode == SourceFramingMode.Fit ? "fit" : "fill";
    }
}
