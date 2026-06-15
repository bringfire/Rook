using System;
using System.Diagnostics;
using System.IO;
using Eto.Forms;
using Eto.Drawing;

namespace Rook.UI.Chat
{
    /// <summary>
    /// Settings dialog showing CLI status and project configuration.
    /// </summary>
    public class SettingsDialog : Dialog
    {
        private readonly ClaudeCodeWrapper? _wrapper;

        // Status labels
        private Label _cliStatusLabel = null!;
        private Label _mcpStatusLabel = null!;

        // Working directory controls
        private DropDown _workingDirMode = null!;
        private TextBox _customDirPath = null!;
        private Button _browseButton = null!;
        private Label _effectiveDirLabel = null!;

        // Buttons
        private Button _closeButton = null!;
        private Button _refreshButton = null!;
        private Button _applyButton = null!;

        // Track if custom directory was set
        private string? _pendingCustomDir;

        /// <summary>
        /// Create settings dialog with optional wrapper reference for directory control.
        /// </summary>
        public SettingsDialog(ClaudeCodeWrapper? wrapper = null)
        {
            _wrapper = wrapper;
            Title = "Rook Chat Settings";
            MinimumSize = new Size(550, 380);
            Padding = new Padding(15);
            Resizable = false;

            InitializeComponents();
            LayoutControls();
            AttachEvents();
            LoadCurrentSettings();
            RefreshStatus();
        }

        private void InitializeComponents()
        {
            // Status labels
            _cliStatusLabel = new Label
            {
                Text = "Checking...",
                TextColor = Colors.Gray
            };

            _mcpStatusLabel = new Label
            {
                Text = "Checking...",
                TextColor = Colors.Gray
            };

            // Working directory mode dropdown
            _workingDirMode = new DropDown
            {
                Width = 200
            };
            _workingDirMode.Items.Add("Follow Rhino Document (Auto)");
            _workingDirMode.Items.Add("Custom Folder");
            _workingDirMode.SelectedIndex = 0;

            // Custom directory path
            _customDirPath = new TextBox
            {
                Width = 300,
                PlaceholderText = "Select a folder...",
                Enabled = false
            };

            _browseButton = new Button
            {
                Text = "Browse...",
                Width = 80,
                Enabled = false
            };

            // Effective directory label
            _effectiveDirLabel = new Label
            {
                Text = "...",
                TextColor = Colors.Gray
            };

            // Buttons
            _closeButton = new Button { Text = "Close" };
            _refreshButton = new Button { Text = "Refresh" };
            _applyButton = new Button { Text = "Apply", Enabled = false };
        }

        private void LayoutControls()
        {
            Content = new TableLayout
            {
                Spacing = new Size(10, 8),
                Rows =
                {
                    // Header
                    new TableRow(new Label
                    {
                        Text = "Rook Integration",
                        Font = new Font(SystemFont.Bold, 14)
                    }),

                    // Spacer
                    new TableRow(new Label { Text = " " }),

                    // CLI Status
                    new TableRow(new TableLayout
                    {
                        Spacing = new Size(10, 0),
                        Rows =
                        {
                            new TableRow(
                                new TableCell(new Label { Text = "CLI:", Font = new Font(SystemFont.Bold), Width = 100 }),
                                new TableCell(_cliStatusLabel, true)
                            )
                        }
                    }),

                    // MCP Status
                    new TableRow(new TableLayout
                    {
                        Spacing = new Size(10, 0),
                        Rows =
                        {
                            new TableRow(
                                new TableCell(new Label { Text = "MCP Server:", Font = new Font(SystemFont.Bold), Width = 100 }),
                                new TableCell(_mcpStatusLabel, true)
                            )
                        }
                    }),

                    // Divider
                    new TableRow(new Label { Text = " " }),
                    new TableRow(new Label
                    {
                        Text = "Project Directory",
                        Font = new Font(SystemFont.Bold, 12)
                    }),

                    // Working directory mode
                    new TableRow(new TableLayout
                    {
                        Spacing = new Size(10, 0),
                        Rows =
                        {
                            new TableRow(
                                new TableCell(new Label { Text = "Mode:", Width = 100 }),
                                new TableCell(_workingDirMode, true)
                            )
                        }
                    }),

                    // Custom path row
                    new TableRow(new TableLayout
                    {
                        Spacing = new Size(5, 0),
                        Rows =
                        {
                            new TableRow(
                                new TableCell(new Label { Text = " ", Width = 100 }),
                                new TableCell(_customDirPath, true),
                                _browseButton
                            )
                        }
                    }),

                    // Effective directory
                    new TableRow(new TableLayout
                    {
                        Spacing = new Size(10, 0),
                        Rows =
                        {
                            new TableRow(
                                new TableCell(new Label { Text = "Active:", Width = 100 }),
                                new TableCell(_effectiveDirLabel, true)
                            )
                        }
                    }),

                    // Help text
                    new TableRow(new Label { Text = " " }),
                    new TableRow(new Label
                    {
                        Text = "The project directory is where Rook looks for CLAUDE.md\nand stores session context. Follow Rhino Document uses the\nfolder containing your .3dm file.",
                        TextColor = Colors.Gray
                    }),

                    // Spacer (grows)
                    new TableRow(new Label { Text = " " }) { ScaleHeight = true },

                    // Auth help
                    new TableRow(new Label
                    {
                        Text = "Authentication: Run 'claude' in a terminal to sign in.",
                        TextColor = Colors.Gray
                    }),

                    // Buttons
                    new TableRow(new TableLayout
                    {
                        Spacing = new Size(10, 0),
                        Rows =
                        {
                            new TableRow(_refreshButton, null, _applyButton, _closeButton)
                        }
                    })
                }
            };

            DefaultButton = _closeButton;
            AbortButton = _closeButton;
        }

        private void AttachEvents()
        {
            _closeButton.Click += (s, e) => Close();
            _refreshButton.Click += (s, e) => RefreshStatus();
            _applyButton.Click += OnApplyClicked;

            _workingDirMode.SelectedIndexChanged += (s, e) =>
            {
                var isCustom = _workingDirMode.SelectedIndex == 1;
                _customDirPath.Enabled = isCustom;
                _browseButton.Enabled = isCustom;
                _applyButton.Enabled = true;
                UpdateEffectiveDirectory();
            };

            _browseButton.Click += (s, e) =>
            {
                using var dialog = new SelectFolderDialog
                {
                    Title = "Select Project Directory"
                };

                // Set initial directory
                if (!string.IsNullOrEmpty(_customDirPath.Text) && Directory.Exists(_customDirPath.Text))
                {
                    dialog.Directory = _customDirPath.Text;
                }

                if (dialog.ShowDialog(this) == DialogResult.Ok)
                {
                    _customDirPath.Text = dialog.Directory;
                    _pendingCustomDir = dialog.Directory;
                    _applyButton.Enabled = true;
                    UpdateEffectiveDirectory();
                }
            };

            _customDirPath.TextChanged += (s, e) =>
            {
                _applyButton.Enabled = true;
                UpdateEffectiveDirectory();
            };
        }

        private void LoadCurrentSettings()
        {
            if (_wrapper != null)
            {
                // Check if wrapper has a custom directory set
                // For now, default to auto mode
                _workingDirMode.SelectedIndex = 0;
            }
        }

        private void OnApplyClicked(object? sender, EventArgs e)
        {
            if (_wrapper == null)
            {
                MessageBox.Show("Cannot apply settings - no connection to chat panel.",
                    "Error", MessageBoxType.Warning);
                return;
            }

            try
            {
                if (_workingDirMode.SelectedIndex == 0)
                {
                    // Auto mode - clear custom directory
                    _wrapper.SetWorkingDirectory(null);
                }
                else
                {
                    // Custom mode
                    var customPath = _customDirPath.Text?.Trim();
                    if (string.IsNullOrEmpty(customPath))
                    {
                        MessageBox.Show("Please select a folder.", "Error", MessageBoxType.Warning);
                        return;
                    }

                    if (!Directory.Exists(customPath))
                    {
                        MessageBox.Show($"Directory not found: {customPath}", "Error", MessageBoxType.Warning);
                        return;
                    }

                    _wrapper.SetWorkingDirectory(customPath);
                }

                _applyButton.Enabled = false;
                UpdateEffectiveDirectory();

                // Show success briefly
                var originalText = _effectiveDirLabel.Text;
                var originalColor = _effectiveDirLabel.TextColor;
                _effectiveDirLabel.Text = "Settings applied!";
                _effectiveDirLabel.TextColor = Colors.Green;

                Application.Instance.AsyncInvoke(() =>
                {
                    System.Threading.Thread.Sleep(1000);
                    Application.Instance.Invoke(() =>
                    {
                        UpdateEffectiveDirectory();
                    });
                });
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Error applying settings: {ex.Message}", "Error", MessageBoxType.Error);
            }
        }

        private void UpdateEffectiveDirectory()
        {
            string effectiveDir;
            Color color;

            if (_workingDirMode.SelectedIndex == 0)
            {
                // Auto mode - show what would be used
                try
                {
                    var doc = Rhino.RhinoDoc.ActiveDoc;
                    if (doc != null && !string.IsNullOrEmpty(doc.Path))
                    {
                        effectiveDir = Path.GetDirectoryName(doc.Path) ?? "Unknown";
                        color = Colors.Green;
                    }
                    else
                    {
                        effectiveDir = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments) + " (unsaved doc)";
                        color = Colors.Orange;
                    }
                }
                catch
                {
                    effectiveDir = "Unable to determine";
                    color = Colors.Red;
                }
            }
            else
            {
                // Custom mode
                var customPath = _customDirPath.Text?.Trim();
                if (string.IsNullOrEmpty(customPath))
                {
                    effectiveDir = "(not set)";
                    color = Colors.Orange;
                }
                else if (Directory.Exists(customPath))
                {
                    effectiveDir = customPath;
                    color = Colors.Green;
                }
                else
                {
                    effectiveDir = $"{customPath} (not found)";
                    color = Colors.Red;
                }
            }

            _effectiveDirLabel.Text = effectiveDir;
            _effectiveDirLabel.TextColor = color;
        }

        private void RefreshStatus()
        {
            // Check CLI
            var cliVersion = GetClaudeCliVersion();
            if (cliVersion != null)
            {
                _cliStatusLabel.Text = $"v{cliVersion}";
                _cliStatusLabel.TextColor = Colors.Green;
            }
            else
            {
                _cliStatusLabel.Text = "Not found — PowerShell: irm https://claude.ai/install.ps1 | iex";
                _cliStatusLabel.TextColor = Colors.Red;
            }

            // Check MCP server registration
            var mcpStatus = CheckMcpServer();
            _mcpStatusLabel.Text = mcpStatus.message;
            _mcpStatusLabel.TextColor = mcpStatus.ok ? Colors.Green : Colors.Orange;

            // Update effective directory display
            UpdateEffectiveDirectory();
        }

        private string? GetClaudeCliVersion()
        {
            try
            {
                var psi = new ProcessStartInfo
                {
                    FileName = "claude",
                    Arguments = "--version",
                    UseShellExecute = false,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    CreateNoWindow = true
                };

                using var process = Process.Start(psi);
                if (process == null) return null;

                var output = process.StandardOutput.ReadToEnd().Trim();
                process.WaitForExit(5000);

                if (process.ExitCode == 0 && !string.IsNullOrEmpty(output))
                {
                    return output;
                }
                return null;
            }
            catch
            {
                return null;
            }
        }

        private (bool ok, string message) CheckMcpServer()
        {
            // First, check if user-level MCP config exists and contains rook
            try
            {
                var userMcpConfig = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
                    ".claude.json");

                if (File.Exists(userMcpConfig))
                {
                    var configContent = File.ReadAllText(userMcpConfig);
                    if (configContent.Contains("rook"))
                    {
                        // Config exists, now try to check if connected via CLI
                        try
                        {
                            var psi = new ProcessStartInfo
                            {
                                FileName = "claude",
                                Arguments = "mcp list",
                                UseShellExecute = false,
                                RedirectStandardOutput = true,
                                RedirectStandardError = true,
                                CreateNoWindow = true
                            };

                            using var process = Process.Start(psi);
                            if (process != null)
                            {
                                var output = process.StandardOutput.ReadToEnd();
                                process.WaitForExit(10000);

                                if (output.Contains("rook") && output.Contains("Connected"))
                                {
                                    return (true, "Connected");
                                }
                            }
                        }
                        catch
                        {
                            // CLI check failed, but config exists
                        }

                        return (true, "Registered");
                    }
                }
            }
            catch
            {
                // Config check failed
            }

            // Fallback: try CLI directly
            try
            {
                var psi = new ProcessStartInfo
                {
                    FileName = "claude",
                    Arguments = "mcp list",
                    UseShellExecute = false,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    CreateNoWindow = true
                };

                using var process = Process.Start(psi);
                if (process == null) return (false, "Could not check");

                var output = process.StandardOutput.ReadToEnd();
                process.WaitForExit(10000);

                if (output.Contains("rook"))
                {
                    if (output.Contains("Connected"))
                    {
                        return (true, "Connected");
                    }
                    return (true, "Registered");
                }
                return (false, "Not registered - run installer");
            }
            catch
            {
                return (false, "Could not check");
            }
        }
    }
}
