using System;
using System.Collections.Generic;
using Rook.UI.Chat;
using Xunit;

namespace Rook.Tests.UI.Chat
{
    public sealed class AgentChatImageAdmissionTests
    {
        [Fact]
        public void Up_to_eight_images_are_admitted_without_decoding_them()
        {
            var images = new List<ChatImageInput>();
            for (var i = 0; i < 8; i++)
                images.Add(new ChatImageInput($"p{i}.png", "image/png", "AAAA"));

            AgentChatClient.ValidateImageAdmission(images, encodedBodyBytes: 1024);
        }

        [Fact]
        public void Ninth_image_refuses_before_HTTP()
        {
            var images = new List<ChatImageInput>();
            for (var i = 0; i < 9; i++)
                images.Add(new ChatImageInput($"p{i}.png", "image/png", "AAAA"));

            var error = Assert.Throws<ArgumentException>(
                () => AgentChatClient.ValidateImageAdmission(images, encodedBodyBytes: 1024));

            Assert.Contains("8", error.Message);
        }

        [Fact]
        public void Encoded_HTTP_body_over_48_MiB_refuses_before_HTTP()
        {
            var images = new[] { new ChatImageInput("p.png", "image/png", "AAAA") };

            var error = Assert.Throws<ArgumentException>(
                () => AgentChatClient.ValidateImageAdmission(images, AgentChatClient.MaxEncodedHttpBodyBytes + 1));

            Assert.Contains("oversized", error.Message, StringComparison.OrdinalIgnoreCase);
        }

        [Theory]
        [InlineData("image/png")]
        [InlineData("image/jpeg")]
        [InlineData("image/webp")]
        public void Closed_image_MIME_set_is_admitted(string mimeType)
        {
            AgentChatClient.ValidateImageAdmission(
                new[] { new ChatImageInput("image.bin", mimeType, "AAAA") },
                encodedBodyBytes: 1024);
        }

        [Fact]
        public void Unknown_image_MIME_refuses_before_HTTP()
        {
            Assert.Throws<ArgumentException>(() => AgentChatClient.ValidateImageAdmission(
                new[] { new ChatImageInput("image.gif", "image/gif", "AAAA") },
                encodedBodyBytes: 1024));
        }
    }
}
