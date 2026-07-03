using System.Text.Json;
using Rook;

namespace Rook.Services.Vision.CanvasDirector
{
    internal sealed class CanvasDirectorHandler
    {
        private readonly ICanvasDirectorExtractor extractor;

        public CanvasDirectorHandler()
            : this(new CanvasDirectorExtractor())
        {
        }

        internal CanvasDirectorHandler(ICanvasDirectorExtractor extractor)
        {
            this.extractor = extractor;
        }

        public ApiResponse Dispatch(string? requestJson)
        {
            try
            {
                var request = CanvasDirectorExtractRequest.Parse(requestJson);
                if (string.IsNullOrWhiteSpace(request.Op))
                {
                    throw new CanvasDirectorException(
                        "invalid_input",
                        "CanvasDirector request missing required 'op' discriminator.",
                        400);
                }

                if (request.Op != "extract")
                {
                    throw new CanvasDirectorException(
                        "invalid_input",
                        $"Unknown CanvasDirector op '{request.Op}'.",
                        400);
                }

                var envelope = extractor.Extract(request);
                return new ApiResponse
                {
                    Success = true,
                    Data = envelope,
                    HttpStatus = 200,
                };
            }
            catch (JsonException ex)
            {
                return Fail("invalid_input", $"Invalid CanvasDirector request JSON: {ex.Message}", 400);
            }
            catch (CanvasDirectorException ex)
            {
                return Fail(ex.Code, ex.Message, ex.HttpStatus);
            }
        }

        private static ApiResponse Fail(string code, string message, int httpStatus)
        {
            return new ApiResponse
            {
                Success = false,
                Data = new { code, message },
                HttpStatus = httpStatus,
            };
        }
    }
}
