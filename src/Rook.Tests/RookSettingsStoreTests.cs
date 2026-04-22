using System;
using System.IO;
using System.Text.Json;
using Xunit;

namespace Rook.Tests
{
    public class RookSettingsStoreTests : IDisposable
    {
        private readonly string _testDir;
        private readonly string _testFile;
        private readonly RookSettingsStore _store;

        public RookSettingsStoreTests()
        {
            _testDir = Path.Combine(Path.GetTempPath(), $"rook-settings-test-{Guid.NewGuid():N}");
            _testFile = Path.Combine(_testDir, "settings.json");
            _store = new RookSettingsStore(_testFile);
        }

        public void Dispose()
        {
            if (Directory.Exists(_testDir))
                Directory.Delete(_testDir, recursive: true);
        }

        public class TestSection
        {
            public string? Name { get; set; }
            public int Count { get; set; }
        }

        // ─── locked contract: file-missing semantics ──────────────────────

        [Fact]
        public void LoadSection_FileMissing_ReturnsNull()
        {
            Assert.Null(_store.LoadSection<TestSection>("anything"));
        }

        [Fact]
        public void SectionExists_FileMissing_ReturnsFalse()
        {
            Assert.False(_store.SectionExists("anything"));
        }

        // ─── locked contract: round-trip ──────────────────────────────────

        [Fact]
        public void RoundTrip_SaveThenLoad_ReturnsEqualValue()
        {
            var input = new TestSection { Name = "hello", Count = 42 };

            _store.SaveSection("test", input);
            var loaded = _store.LoadSection<TestSection>("test");

            Assert.NotNull(loaded);
            Assert.Equal("hello", loaded!.Name);
            Assert.Equal(42, loaded.Count);
        }

        [Fact]
        public void SectionExists_AfterSave_ReturnsTrue()
        {
            _store.SaveSection("test", new TestSection { Name = "x" });
            Assert.True(_store.SectionExists("test"));
        }

        // ─── locked contract: section-missing in present file ────────────

        [Fact]
        public void LoadSection_SectionMissingInPresentFile_ReturnsNull()
        {
            _store.SaveSection("alpha", new TestSection { Name = "a" });

            Assert.Null(_store.LoadSection<TestSection>("beta"));
        }

        // ─── locked contract: siblings preserved ─────────────────────────

        [Fact]
        public void SaveSection_PreservesOtherSections()
        {
            _store.SaveSection("alpha", new TestSection { Name = "a", Count = 1 });
            _store.SaveSection("beta", new TestSection { Name = "b", Count = 2 });

            var alpha = _store.LoadSection<TestSection>("alpha");
            Assert.NotNull(alpha);
            Assert.Equal("a", alpha!.Name);
            Assert.Equal(1, alpha.Count);
        }

        // ─── locked contract: malformed file → throws, no overwrite ──────

        [Fact]
        public void LoadSection_MalformedFile_ThrowsAndDoesNotOverwrite()
        {
            Directory.CreateDirectory(_testDir);
            File.WriteAllText(_testFile, "{ this is not json");
            string original = File.ReadAllText(_testFile);

            Assert.ThrowsAny<JsonException>(() => _store.LoadSection<TestSection>("anything"));

            Assert.Equal(original, File.ReadAllText(_testFile));
        }

        [Fact]
        public void SectionExists_MalformedFile_Throws()
        {
            Directory.CreateDirectory(_testDir);
            File.WriteAllText(_testFile, "{ broken");

            Assert.ThrowsAny<JsonException>(() => _store.SectionExists("anything"));
        }

        [Fact]
        public void LoadSection_RootIsJsonArray_ThrowsAndDoesNotOverwrite()
        {
            Directory.CreateDirectory(_testDir);
            File.WriteAllText(_testFile, "[1, 2, 3]");
            string original = File.ReadAllText(_testFile);

            Assert.Throws<InvalidDataException>(() => _store.LoadSection<TestSection>("anything"));

            Assert.Equal(original, File.ReadAllText(_testFile));
        }

        // ─── locked contract: malformed section payload → throws ─────────

        [Fact]
        public void LoadSection_SectionPayloadNotDeserializable_Throws()
        {
            Directory.CreateDirectory(_testDir);
            File.WriteAllText(_testFile,
                "{\"schemaVersion\":1,\"sections\":{\"test\":\"not-an-object\"}}");

            Assert.ThrowsAny<JsonException>(() => _store.LoadSection<TestSection>("test"));
        }

        // ─── argument validation ─────────────────────────────────────────

        [Fact]
        public void SaveSection_NullValue_Throws()
        {
            Assert.Throws<ArgumentNullException>(
                () => _store.SaveSection<TestSection>("test", null!));
        }

        [Theory]
        [InlineData(null)]
        [InlineData("")]
        [InlineData("   ")]
        public void SaveSection_InvalidSectionName_Throws(string? sectionName)
        {
            Assert.Throws<ArgumentException>(
                () => _store.SaveSection(sectionName!, new TestSection()));
        }

        [Theory]
        [InlineData(null)]
        [InlineData("")]
        [InlineData("   ")]
        public void LoadSection_InvalidSectionName_Throws(string? sectionName)
        {
            Assert.Throws<ArgumentException>(
                () => _store.LoadSection<TestSection>(sectionName!));
        }

        [Theory]
        [InlineData(null)]
        [InlineData("")]
        [InlineData("   ")]
        public void SectionExists_InvalidSectionName_Throws(string? sectionName)
        {
            Assert.Throws<ArgumentException>(() => _store.SectionExists(sectionName!));
        }

        // ─── write strategy: success-path temp cleanup ───────────────────

        [Fact]
        public void SaveSection_TempFileNotPresentAfterSuccess()
        {
            _store.SaveSection("test", new TestSection { Name = "x" });

            string tmpPath = _testFile + ".tmp";
            Assert.False(File.Exists(tmpPath));
        }

        // ─── lazy directory creation ─────────────────────────────────────

        [Fact]
        public void SaveSection_CreatesDirectoryLazily()
        {
            Assert.False(Directory.Exists(_testDir));

            _store.SaveSection("test", new TestSection { Name = "x" });

            Assert.True(File.Exists(_testFile));
        }

        // ─── RookPaths smoke ─────────────────────────────────────────────

        [Fact]
        public void RookPaths_SettingsFile_IsUnderSettingsRoot()
        {
            Assert.StartsWith(RookPaths.SettingsRoot, RookPaths.SettingsFile);
            Assert.EndsWith("settings.json", RookPaths.SettingsFile);
        }
    }
}
