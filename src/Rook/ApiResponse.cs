namespace Rook
{
    /// <summary>
    /// Standard API response format.
    /// </summary>
    public class ApiResponse
    {
        public bool Success { get; set; }
        public object? Data { get; set; }

        /// <summary>
        /// Optional explicit HTTP status. When null, bridge executors
        /// fall back to the legacy mapping (Success=true → 200, else 400).
        /// Set by handlers that need typed status semantics on the native
        /// HTTP path (e.g. video routes mapping VideoErrorCode → 400/415/
        /// 500/503). The bridge dispatcher silently drops this field —
        /// it has no HTTP-status concept.
        /// </summary>
        public int? HttpStatus { get; set; }

        /// <summary>
        /// Optional Phase 2 route diagnostic payload. Bridge executors
        /// must opt in to serializing this field; it is intentionally not
        /// emitted by the shared legacy API response paths by default.
        /// </summary>
        public object? Diagnostic { get; set; }
    }
}
