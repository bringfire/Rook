using System.Collections.Generic;
using System.Linq;
using Rook.UI.Chat;
using Xunit;

namespace Rook.Tests.UI.Chat
{
    public class ModelOverrideOptionHelpersTests
    {
        private static ModelOverrideOption Opt(string id, string elig, string? name = null,
            string? state = null, int? ctx = null)
            => new ModelOverrideOption
            {
                Id = id, DisplayName = name ?? "", Eligibility = elig,
                MetadataState = state, ContextLength = ctx,
            };

        [Fact]
        public void EligibleOptions_keeps_only_eligible()
        {
            var opts = new List<ModelOverrideOption>
            {
                Opt("a", "eligible"),
                Opt("b", "ineligible"),
                Opt("c", "eligible"),
            };
            var eligible = AgentChatTab.EligibleOptions(opts);
            Assert.Equal(new[] { "a", "c" }, eligible.Select(o => o.Id).ToArray());
        }

        [Fact]
        public void BuildOptionLabel_uses_display_name_then_falls_back_to_id()
        {
            Assert.Equal("Claude Sonnet 4.6",
                AgentChatTab.BuildOptionLabel(Opt("openrouter/anthropic/claude-sonnet-4.6", "eligible", "Claude Sonnet 4.6")));
            Assert.Equal("anthropic/x",
                AgentChatTab.BuildOptionLabel(Opt("anthropic/x", "eligible")));
        }

        [Fact]
        public void BuildSelectionDetail_includes_ctx_and_stale_note()
        {
            var detail = AgentChatTab.BuildSelectionDetail(
                Opt("x", "eligible", "X", state: "stale", ctx: 200000));
            Assert.Contains("200000", detail);
            Assert.Contains("stale", detail);
        }

        [Fact]
        public void BuildRowText_appends_detail_when_present_else_label_only()
        {
            // No detail (role/local-style: no ctx, not stale) -> label only.
            Assert.Equal("anthropic/x",
                AgentChatTab.BuildRowText(Opt("anthropic/x", "eligible")));
            // Detail present -> label then detail.
            var withDetail = AgentChatTab.BuildRowText(
                Opt("id", "eligible", "Name", state: "stale", ctx: 1000));
            Assert.StartsWith("Name", withDetail);
            Assert.Contains("stale", withDetail);
        }
    }
}
