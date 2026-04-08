// Polyfill for C# 9 'init' accessors when targeting .NET Framework 4.8.
// This type is built-in on .NET 5+ but missing from net48.
#if !NET5_0_OR_GREATER
namespace System.Runtime.CompilerServices
{
    internal static class IsExternalInit { }
}
#endif
