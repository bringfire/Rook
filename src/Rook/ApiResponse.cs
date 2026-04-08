namespace Rook
{
    /// <summary>
    /// Standard API response format.
    /// </summary>
    public class ApiResponse
    {
        public bool Success { get; set; }
        public object? Data { get; set; }
    }
}
