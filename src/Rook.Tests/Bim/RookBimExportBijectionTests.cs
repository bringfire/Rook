using System.Collections.Generic;
using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim
{
    public class RookBimExportBijectionTests
    {
        [Fact]
        public void Verify_ElementOnlyKeysOneObjectEach_Ok()
        {
            var result = BimExportBijection.Verify(
                new string?[] { "a", "b", "c" },
                new HashSet<string> { "a", "b", "c" });

            Assert.True(result.Ok);
            Assert.Empty(result.Discrepancies);
        }

        [Fact]
        public void Verify_RoomKeyIncludedAndObjectPresent_Ok()
        {
            // A room that emitted a geometry object: its key is in the expected (union) set and
            // an object stamped with that key is present.
            var result = BimExportBijection.Verify(
                new string?[] { "wall-1", "room-1" },
                new HashSet<string> { "wall-1", "room-1" });

            Assert.True(result.Ok);
            Assert.Empty(result.Discrepancies);
        }

        [Fact]
        public void Verify_MultipleObjectsPerKey_Ok()
        {
            // Regression guard for multi-solid elements: one element emits one object per Brep, all
            // sharing the same revit.uniqueId. Multiple objects per key is VALID, not a duplicate.
            var result = BimExportBijection.Verify(
                new string?[] { "window-1", "window-1", "window-1" },
                new HashSet<string> { "window-1" });

            Assert.True(result.Ok);
            Assert.Empty(result.Discrepancies);
        }

        [Fact]
        public void Verify_ObjectKeyNotInExpected_NotOk()
        {
            var result = BimExportBijection.Verify(
                new string?[] { "a", "ghost" },
                new HashSet<string> { "a" });

            Assert.False(result.Ok);
            Assert.Contains(result.Discrepancies, d => d.Contains("ghost") && d.Contains("no exported record"));
        }

        [Fact]
        public void Verify_ExpectedKeyWithNoObject_NotOk()
        {
            var result = BimExportBijection.Verify(
                new string?[] { "a" },
                new HashSet<string> { "a", "orphan" });

            Assert.False(result.Ok);
            Assert.Contains(result.Discrepancies, d => d.Contains("orphan") && d.Contains("no .3dm object"));
        }

        [Fact]
        public void Verify_NullOrEmptyObjectKey_NotOk()
        {
            var resultNull = BimExportBijection.Verify(
                new string?[] { "a", null },
                new HashSet<string> { "a" });

            Assert.False(resultNull.Ok);
            Assert.Contains(resultNull.Discrepancies, d => d.Contains("no revit.uniqueId user string"));

            var resultEmpty = BimExportBijection.Verify(
                new string?[] { "a", "" },
                new HashSet<string> { "a" });

            Assert.False(resultEmpty.Ok);
            Assert.Contains(resultEmpty.Discrepancies, d => d.Contains("no revit.uniqueId user string"));
        }
    }
}
