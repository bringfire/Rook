using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video.Framing
{
    internal sealed record VideoStillImageInfo(string MimeType, int Width, int Height, int Orientation = 1, int BitDepth = 8, int Planes = 4)
    {
        public int OrientedWidth => Orientation >= 5 ? Height : Width;
        public int OrientedHeight => Orientation >= 5 ? Width : Height;
    }
    internal sealed record VideoStillInspectionResult(VideoStillImageInfo? Info, GenerationError? Error);
    internal sealed record VideoFramingLayout(int CanvasWidth, int CanvasHeight, int ScaledWidth, int ScaledHeight, int OffsetX, int OffsetY, bool Upscaled);
    internal sealed record VideoFramingGeometryResult(VideoFramingLayout? Layout, GenerationError? Error);
    internal sealed record VideoFramingRecipe(SourceFramingMode Mode, VideoStillImageInfo Source,
        VideoFramingLayout Layout, string RendererSha256, string Encoding = "png", int? Quantizer = null)
    {
        public const string ProfileRevision = "video-source-framing-v1";
        public JsonObject Canonical() => new() {
            ["profile"] = ProfileRevision, ["renderer_sha256"] = RendererSha256, ["mode"] = Mode.Wire(),
            ["stored_width"] = Source.Width, ["stored_height"] = Source.Height,
            ["oriented_width"] = Source.OrientedWidth, ["oriented_height"] = Source.OrientedHeight,
            ["orientation"] = Source.Orientation, ["native_bit_depth"] = Source.BitDepth, ["native_planes"] = Source.Planes,
            ["canvas_width"] = Layout.CanvasWidth, ["canvas_height"] = Layout.CanvasHeight,
            ["scaled_width"] = Layout.ScaledWidth, ["scaled_height"] = Layout.ScaledHeight,
            ["offset_x"] = Layout.OffsetX, ["offset_y"] = Layout.OffsetY, ["matte"] = "black",
            ["color_policy"] = "ffmpeg-native-srgb-rgba8-no-icc", ["resampling"] = "lanczos",
            ["encoding"] = Encoding, ["quantizer"] = Quantizer, ["threads"] = 1,
            ["renderer_commit_limit_bytes"] = VideoPreparationLimits.RendererCommitBytes,
            ["renderer_notification_bytes"] = 480L * 1024 * 1024
        };
    }
}
