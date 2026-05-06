using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Rook.UI.Chat;
using Rook.UI.Knowledge;
using Xunit;

namespace Rook.Tests.UI.Knowledge
{
    public class KnowledgeGraphBootstrapCoordinatorTests
    {
        [Fact]
        public async Task RequestBeforeWebViewReady_DelaysServiceCoordinatesUntilReady()
        {
            var scripts = new List<string>();
            var coordinator = new KnowledgeGraphBootstrapCoordinator(
                _ => Task.FromResult(new ChatServiceHealth
                {
                    ServiceAvailable = true,
                    BaseUri = new Uri("http://127.0.0.1:49152"),
                }),
                () => "nonce-1",
                scripts.Add,
                _ => { });

            await coordinator.RequestBootstrapAsync(CancellationToken.None);

            Assert.Empty(scripts);

            await coordinator.MarkWebViewReadyAsync(CancellationToken.None);

            var script = Assert.Single(scripts);
            Assert.Contains("window.__rookServiceHost = '127.0.0.1';", script);
            Assert.Contains("window.__rookServicePort = 49152;", script);
            Assert.Contains("window.__rookSessionNonce = 'nonce-1';", script);
            Assert.Contains("window.rookKnowledgeGraphBootstrap", script);
        }

        [Fact]
        public async Task RequestAfterWebViewReady_InjectsServiceCoordinates()
        {
            var scripts = new List<string>();
            var coordinator = new KnowledgeGraphBootstrapCoordinator(
                _ => Task.FromResult(new ChatServiceHealth
                {
                    ServiceAvailable = true,
                    BaseUri = new Uri("http://127.0.0.1:49153"),
                }),
                () => "nonce-2",
                scripts.Add,
                _ => { });

            await coordinator.MarkWebViewReadyAsync(CancellationToken.None);
            await coordinator.RequestBootstrapAsync(CancellationToken.None);

            Assert.Contains(scripts, script =>
                script.Contains("window.__rookServicePort = 49153;")
                && script.Contains("window.rookKnowledgeGraphBootstrap"));
        }

        [Fact]
        public async Task ServiceUnavailable_InjectsSpecificFailureMessage()
        {
            var scripts = new List<string>();
            var coordinator = new KnowledgeGraphBootstrapCoordinator(
                _ => Task.FromResult(new ChatServiceHealth
                {
                    ServiceAvailable = false,
                    ServiceMessage = "Chat service manifest missing",
                }),
                () => null,
                scripts.Add,
                _ => { });

            await coordinator.MarkWebViewReadyAsync(CancellationToken.None);

            var script = Assert.Single(scripts);
            Assert.Contains("window.rookKnowledgeGraphBootstrapFailed", script);
            Assert.Contains("Chat service manifest missing", script);
            Assert.DoesNotContain("__rookServicePort", script);
        }

        [Fact]
        public async Task FailedBootstrap_CanRetryWhenPanelIsShownAgain()
        {
            var calls = 0;
            var scripts = new List<string>();
            var coordinator = new KnowledgeGraphBootstrapCoordinator(
                _ =>
                {
                    calls++;
                    return Task.FromResult(calls == 1
                        ? new ChatServiceHealth
                        {
                            ServiceAvailable = false,
                            ServiceMessage = "Chat service unavailable",
                        }
                        : new ChatServiceHealth
                        {
                            ServiceAvailable = true,
                            BaseUri = new Uri("http://127.0.0.1:49154"),
                        });
                },
                () => "nonce-3",
                scripts.Add,
                _ => { });

            await coordinator.MarkWebViewReadyAsync(CancellationToken.None);
            await coordinator.RequestBootstrapAsync(CancellationToken.None);

            Assert.Equal(2, calls);
            Assert.Contains(scripts, script => script.Contains("window.rookKnowledgeGraphBootstrapFailed"));
            Assert.Contains(scripts, script => script.Contains("window.__rookServicePort = 49154;"));
        }
    }
}
