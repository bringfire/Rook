using System;
using System.IO;
using Xunit;

namespace Rook.Tests.UI.Vision
{
    public class VisionQueueUiSourceTests
    {
        [Fact]
        public void QueueMarkup_ExposesStatusFilterButtonsWithActiveDefault()
        {
            var html = ReadSourceFile(
                "src",
                "Rook",
                "UI",
                "Vision",
                "Resources",
                "index.html");

            Assert.Contains("id=\"video-queue-filters\"", html);
            Assert.Contains("data-queue-filter=\"active\"", html);
            Assert.Contains("data-queue-filter=\"complete\"", html);
            Assert.Contains("data-queue-filter=\"error\"", html);
            Assert.Contains("data-queue-filter=\"all\"", html);
            Assert.Contains("aria-pressed=\"true\">Active", html);
        }

        [Fact]
        public void QueueStyles_KeepQueueListScrollBoundedInsidePanel()
        {
            var css = ReadSourceFile(
                "src",
                "Rook",
                "UI",
                "Vision",
                "Resources",
                "styles.css");

            var panelRule = ExtractCssRule(css, ".video-queue-panel {");
            var listRule = ExtractCssRule(css, ".video-queue-list {");

            Assert.Contains("min-height: 0;", panelRule);
            Assert.Contains("max-height:", listRule);
            Assert.Contains("overflow-y: auto;", listRule);
        }

        [Fact]
        public void QueueStyles_FilterBarIsResponsiveAndKeyboardFocusable()
        {
            var css = ReadSourceFile(
                "src",
                "Rook",
                "UI",
                "Vision",
                "Resources",
                "styles.css");

            var filterRule = ExtractCssRule(css, ".video-queue-filters");
            var focusRule = ExtractCssRule(css, ".video-queue-filter:focus-visible");

            Assert.Contains("repeat(auto-fit, minmax(", filterRule);
            Assert.Contains("outline:", focusRule);
        }

        [Fact]
        public void QueueStyles_HasFallbackBeforeColorMixSummaryColors()
        {
            var css = ReadSourceFile(
                "src",
                "Rook",
                "UI",
                "Vision",
                "Resources",
                "styles.css");

            var summaryRule = ExtractCssRule(css, ".video-queue-filter-summary");

            Assert.Contains("border: 1px solid var(--accent-amber);", summaryRule);
            Assert.Contains("background: var(--paper-tone);", summaryRule);
            Assert.Contains("color-mix", summaryRule);
            Assert.True(
                summaryRule.IndexOf("border: 1px solid var(--accent-amber);", StringComparison.Ordinal)
                < summaryRule.IndexOf("border: 1px solid color-mix", StringComparison.Ordinal));
            Assert.True(
                summaryRule.IndexOf("background: var(--paper-tone);", StringComparison.Ordinal)
                < summaryRule.IndexOf("background: color-mix", StringComparison.Ordinal));
        }

        [Fact]
        public void QueueScript_FiltersRenderedJobsBySelectedStatus()
        {
            var js = ReadSourceFile(
                "src",
                "Rook",
                "UI",
                "Vision",
                "Resources",
                "app.js");

            Assert.Contains("let queueFilter = \"active\";", js);
            Assert.Contains("const FAILED_STATES = new Set([\"error\", \"cancelled\", \"interrupted\"]);", js);
            Assert.Contains("ve.queueFilterButtons", js);
            Assert.Contains("function setQueueFilter(filter)", js);
            Assert.Contains("function filterQueueEntries(entries)", js);
            Assert.Contains("case \"active\":", js);
            Assert.Contains("IN_FLIGHT_STATES.has(j.state)", js);
            Assert.Contains("case \"complete\":", js);
            Assert.Contains("case \"error\":", js);
            Assert.Contains("return entries.filter(j => FAILED_STATES.has(j.state));", js);
        }

        [Fact]
        public void QueueScript_SummarizesHiddenFailedJobsOutsideFailedView()
        {
            var js = ReadSourceFile(
                "src",
                "Rook",
                "UI",
                "Vision",
                "Resources",
                "app.js");

            Assert.Contains("function renderQueueFilterSummary(entries)", js);
            Assert.Contains("queueFilter === \"error\"", js);
            Assert.Contains("queueFilter === \"all\"", js);
            Assert.Contains("failed job", js);
        }

        [Fact]
        public void QueueScript_ExpandsErrorDetailsInFailedAndAllViews()
        {
            var js = ReadSourceFile(
                "src",
                "Rook",
                "UI",
                "Vision",
                "Resources",
                "app.js");

            Assert.Contains("filter-error", js);
            Assert.Contains("filter-all", js);
        }

        [Fact]
        public void QueueStyles_UnclampsErrorDetailsInFailedAndAllViews()
        {
            var css = ReadSourceFile(
                "src",
                "Rook",
                "UI",
                "Vision",
                "Resources",
                "styles.css");

            var filterErrorRule = ExtractCssRule(
                css,
                ".video-queue-list.filter-error .video-queue-row-error");
            var filterAllRule = ExtractCssRule(
                css,
                ".video-queue-list.filter-all .video-queue-row-error");

            Assert.Contains("max-height: none;", filterErrorRule);
            Assert.Contains("overflow: visible;", filterErrorRule);
            Assert.Contains("max-height: none;", filterAllRule);
            Assert.Contains("overflow: visible;", filterAllRule);
        }

        private static string ExtractCssRule(string source, string selector)
        {
            var selectorStart = source.LastIndexOf(selector, StringComparison.Ordinal);
            if (selectorStart < 0)
                throw new InvalidOperationException("Selector not found: " + selector);

            var bodyStart = source.IndexOf('{', selectorStart);
            if (bodyStart < 0)
                throw new InvalidOperationException("Selector body not found: " + selector);

            var bodyEnd = source.IndexOf('}', bodyStart);
            if (bodyEnd < 0)
                throw new InvalidOperationException("Selector body did not close: " + selector);

            return source.Substring(selectorStart, bodyEnd - selectorStart + 1);
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
