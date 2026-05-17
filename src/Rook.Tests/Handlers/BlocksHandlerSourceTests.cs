using System;
using System.IO;
using Xunit;

namespace Rook.Tests.Handlers
{
    public class BlocksHandlerSourceTests
    {
        [Fact]
        public void BlockCreateRoute_IsNativeOwnedAndNotExposedByCompanion()
        {
            var nativeServer = ReadSourceFile("src", "RookNative", "RookServer.cpp");
            var companionBlocks = ReadSourceFile("src", "Rook", "Handlers", "BlocksHandler.cs");

            Assert.Contains("m_server->Post(\"/block/create\"", nativeServer);
            Assert.Contains("HandleBlockCreate(req, res);", nativeServer);
            Assert.DoesNotContain("public ApiResponse CreateBlock(", companionBlocks);
        }

        private static string ReadSourceFile(params string[] pathParts)
        {
            var dir = new DirectoryInfo(AppContext.BaseDirectory);
            while (dir != null)
            {
                var candidate = Path.Combine(dir.FullName, Path.Combine(pathParts));
                if (File.Exists(candidate))
                    return File.ReadAllText(candidate);
                dir = dir.Parent;
            }

            throw new FileNotFoundException(
                "Could not locate source file " + string.Join("/", pathParts));
        }
    }
}
