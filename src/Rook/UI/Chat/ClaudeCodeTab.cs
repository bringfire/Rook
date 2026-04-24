using System;
using System.Text;
using System.Threading.Tasks;
using Eto.Drawing;
using Eto.Forms;

namespace Rook.UI.Chat
{
    /// <summary>
    /// Chat tab backed by a persistent Claude Code subprocess.
    /// Creates a <see cref="ClaudeCodeWrapper"/> on construction and kills it on close.
    /// </summary>
    public class ClaudeCodeTab : ChatTab
    {
        private readonly ClaudeCodeWrapper _wrapper;
        private readonly StringBuilder _streamingContent;

        public ClaudeCodeTab(uint documentSerialNumber = 0)
            : base("Claude Code", Color.FromArgb(0x0e, 0x63, 0x9c))
        {
            _streamingContent = new StringBuilder();
            _wrapper = new ClaudeCodeWrapper(documentSerialNumber);

            // Wire streaming text updates
            _wrapper.OnStreamingUpdate += content => Application.Instance.Invoke(() =>
            {
                ShowTypingIndicator(false);
                UpdateStreamingChat(content);
                SetStatus("Receiving...", Colors.Blue);
            });

            // Wire message completion
            _wrapper.OnMessageComplete += () => Application.Instance.Invoke(() =>
            {
                FinalizeStreaming();
                _streamingContent.Clear();
                SetProcessing(false);
                SetStatus("Ready", Colors.Green);
            });

            // Wire errors
            _wrapper.OnError += error => Application.Instance.Invoke(() =>
            {
                ShowTypingIndicator(false);
                AddMessageToChat("error", error);
                SetProcessing(false);
                SetStatus("Error", Colors.Red);
            });

            // Wire tool execution (render images inline)
            _wrapper.OnToolExecuted += (name, result) => Application.Instance.Invoke(() =>
            {
                if (result.Length > 1000 && !result.Contains("{"))
                {
                    AddImageToChat(result);
                }
            });

            // Wire process readiness
            _wrapper.OnReady += () => Application.Instance.Invoke(() =>
            {
                SetStatus("Ready", Colors.Green);
                AddMessageToChat("system", "Claude Code connected");
            });

            // Wire unexpected process death
            _wrapper.OnProcessDied += reason => Application.Instance.Invoke(() =>
            {
                SetStatus("Disconnected", Colors.Red);
                AddMessageToChat("error", $"Process exited: {reason}. Click Send to reconnect.");
            });
        }

        /// <summary>
        /// Launch the persistent Claude Code subprocess.
        /// Call this after the tab has been added to the UI.
        /// </summary>
        public async Task InitializeAsync()
        {
            SetStatus("Connecting...", Colors.Blue);
            await Task.Run(() => _wrapper.StartPersistentProcess());
            if (!_wrapper.IsRunning)
            {
                SetStatus("Claude Code unavailable", Colors.Red);
            }
        }

        protected override async Task OnSendMessage(string message)
        {
            if (!_wrapper.IsRunning)
            {
                SetStatus("Reconnecting...", Colors.Blue);
                await Task.Run(() => _wrapper.StartPersistentProcess());
            }

            _streamingContent.Clear();
            _wrapper.WriteMessage(message);
        }

        protected override void OnStopRequested()
        {
            _wrapper.CancelCurrentRequest();
        }

        protected override void OnClearRequested()
        {
            _wrapper.ClearConversation();
        }

        public override void OnTabClosed()
        {
            if (!CloseWebSurface())
                return;

            _wrapper.Dispose();
        }
    }
}
