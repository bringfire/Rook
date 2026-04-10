using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Eto.Drawing;
using Eto.Forms;

namespace Rook.UI.Chat
{
    /// <summary>
    /// Result of the persona picker dialog.
    /// </summary>
    public class PersonaPickerResult
    {
        public bool IsClaudeCode { get; set; }
        public string Persona { get; set; } = "";
        public string Label { get; set; } = "";
        public Color Color { get; set; } = Color.FromArgb(0x1d, 0x9b, 0xf0);
    }

    /// <summary>
    /// Dialog for selecting an agent persona or Claude Code.
    /// </summary>
    public class PersonaPicker : Dialog<PersonaPickerResult?>
    {
        private readonly ListBox _listBox;
        private readonly Dictionary<string, PersonaInfo> _personaMap = new Dictionary<string, PersonaInfo>();

        public PersonaPicker()
        {
            Title = "New Chat Tab";
            MinimumSize = new Size(300, 400);
            Padding = new Padding(10);

            _listBox = new ListBox();

            var okButton = new Button { Text = "Open" };
            okButton.Click += (s, e) => Close(GetSelectedResult());

            var cancelButton = new Button { Text = "Cancel" };
            cancelButton.Click += (s, e) => Close(null);

            _listBox.MouseDoubleClick += (s, e) =>
            {
                var result = GetSelectedResult();
                if (result != null) Close(result);
            };

            Content = new TableLayout
            {
                Spacing = new Size(5, 5),
                Rows =
                {
                    new TableRow(_listBox) { ScaleHeight = true },
                    new TableRow(new TableLayout
                    {
                        Spacing = new Size(5, 0),
                        Rows = { new TableRow(null, okButton, cancelButton) }
                    })
                }
            };

            // Load personas in background
            LoadPersonas();
        }

        private async void LoadPersonas()
        {
            // Add Claude Code first (always available)
            _listBox.Items.Add(new ListItem
            {
                Text = "Claude Code (CLI)",
                Key = "claude-code"
            });

            // Try to load agent personas from the chat server
            try
            {
                using var client = new AgentChatClient();
                var health = await client.GetHealthAsync(startIfNeeded: true);
                if (health.ServiceAvailable)
                {
                    var nonce = ChatServiceManager.Instance.SessionNonce;
                    if (!string.IsNullOrEmpty(nonce))
                        client.SetSessionNonce(nonce);
                    var personas = await client.GetPersonasAsync();
                    foreach (var p in personas)
                    {
                        _personaMap[p.Persona] = p;
                        _listBox.Items.Add(new ListItem
                        {
                            Text = $"{p.Label} — {p.Description}",
                            Key = p.Persona
                        });
                    }
                }
                else
                {
                    _listBox.Items.Add(new ListItem
                    {
                        Text = $"(Chat service unavailable — {health.ServiceMessage})",
                        Key = "unavailable"
                    });
                }
            }
            catch (Exception)
            {
                // IMPORTANT: This catch must remain broad (catch Exception) because
                // this is an async void method called from the constructor.
                // Any unhandled exception would crash the host (Rhino).
                _listBox.Items.Add(new ListItem
                {
                    Text = "(Failed to connect to agent server)",
                    Key = "unavailable"
                });
            }

            _listBox.SelectedIndex = 0;
        }

        private PersonaPickerResult? GetSelectedResult()
        {
            if (_listBox.SelectedIndex < 0) return null;

            var item = _listBox.Items[_listBox.SelectedIndex] as ListItem;
            if (item == null || item.Key == "unavailable") return null;

            if (item.Key == "claude-code")
            {
                return new PersonaPickerResult
                {
                    IsClaudeCode = true,
                    Label = "Claude Code",
                    Color = Color.FromArgb(0x0e, 0x63, 0x9c)
                };
            }

            // Use the persona's actual color from the server
            var label = item.Text.Split(new[] { '\u2014' })[0].Trim();
            var color = Color.FromArgb(0x1d, 0x9b, 0xf0); // default blue

            if (_personaMap.TryGetValue(item.Key, out var info))
            {
                label = info.Label;
                color = ParseHexColor(info.Color);
            }

            return new PersonaPickerResult
            {
                IsClaudeCode = false,
                Persona = item.Key,
                Label = label,
                Color = color
            };
        }

        private static Color ParseHexColor(string hex)
        {
            if (string.IsNullOrEmpty(hex)) return Color.FromArgb(0x1d, 0x9b, 0xf0);
            hex = hex.TrimStart('#');
            if (hex.Length != 6) return Color.FromArgb(0x1d, 0x9b, 0xf0);
            try
            {
                var r = Convert.ToInt32(hex.Substring(0, 2), 16);
                var g = Convert.ToInt32(hex.Substring(2, 2), 16);
                var b = Convert.ToInt32(hex.Substring(4, 2), 16);
                return Color.FromArgb(r, g, b);
            }
            catch
            {
                return Color.FromArgb(0x1d, 0x9b, 0xf0);
            }
        }
    }
}
