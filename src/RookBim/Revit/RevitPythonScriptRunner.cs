using System;
using System.IO;
using System.Text;
using Rhino.Runtime.Code;
using Rhino.Runtime.Code.Execution;
using Rhino.Runtime.Code.Languages;

namespace RookBim.Revit
{
    /// <summary>
    /// Runs the script wrapper in Rhino's Python 3 engine by calling the
    /// engine directly, on the calling thread, and returning only after the
    /// engine call has returned or thrown.
    ///
    /// This is the point of the design: the host observes the end of the
    /// script itself. It does not start a Rhino command and wait for a file;
    /// it calls <c>Code.Run</c> and gets a return or an exception.
    ///
    /// Uses no Revit types and no Rook core types, so it can be exercised in
    /// a plain Rhino without Revit.
    /// </summary>
    public static class RevitPythonScriptRunner
    {
        public const string ChannelInputName = "__rook__";
        private const string WrapperResourceName = "RookBim.run_transaction_wrapper.py";

        /// <summary>
        /// Returns null when the host saw the engine return normally, otherwise
        /// the engine's error text (for a script exception this includes the
        /// Python traceback). Never throws for a script or engine failure.
        /// </summary>
        public static string? Run(RevitScriptChannel channel)
        {
            if (channel == null)
            {
                throw new ArgumentNullException(nameof(channel));
            }

            try
            {
                var language = RhinoCode.Languages.QueryLatest(LanguageSpec.Python3);
                if (language == null)
                {
                    return "Rhino's Python 3 script engine is not available in this session.";
                }

                var code = language.CreateCode(ReadWrapperBody());
                var context = new RunContext(false, false)
                {
                    // Makes each input a global of the script.
                    AutoApplyParams = true
                };
                context.Inputs.Set(ChannelInputName, channel, false, false);
                code.Run(context);
                return null;
            }
            catch (Exception ex)
            {
                // ExecuteException carries the Python traceback in its message.
                var text = ex.Message;
                return string.IsNullOrWhiteSpace(text) ? ex.GetType().Name : text;
            }
        }

        internal static string ReadWrapperBody()
        {
            using (var stream = typeof(RevitPythonScriptRunner).Assembly
                .GetManifestResourceStream(WrapperResourceName))
            {
                if (stream == null)
                {
                    throw new InvalidOperationException(
                        "RookBim.dll is missing its embedded resource " + WrapperResourceName + ".");
                }

                using (var reader = new StreamReader(stream, Encoding.UTF8))
                {
                    return reader.ReadToEnd();
                }
            }
        }
    }
}
