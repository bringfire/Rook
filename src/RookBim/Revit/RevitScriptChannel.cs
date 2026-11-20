using System;
using System.Text;

namespace RookBim.Revit
{
    /// <summary>
    /// The object a script run talks to the host through. The host creates
    /// it, hands it to the Python wrapper as the single input <c>__rook__</c>,
    /// and reads it after its own call into the script engine has returned.
    ///
    /// Everything crosses here by method call on a live host object: the
    /// caller's code goes in as a string, output and the result come back as
    /// strings. There are no temporary files and no Rhino command, so nothing
    /// outside this call can be mistaken for its outcome.
    ///
    /// Deliberately a plain class: Rhino's script engine converts collection
    /// inputs (dictionaries, lists) to Python types, but passes an ordinary
    /// object through as itself. Host handles are typed <c>object</c> so this
    /// file needs no Revit types.
    /// </summary>
    public sealed class RevitScriptChannel
    {
        public const int StreamLimit = 20000;
        public const int ResultLimit = 50000;
        public const int ResultDepthLimit = 32;
        public const int TracebackLimit = 20000;
        public const int ErrorLimit = 2000;

        private readonly StringBuilder output = new StringBuilder();
        private readonly StringBuilder stderr = new StringBuilder();

        public RevitScriptChannel(
            string code,
            object? document,
            object? uiDocument,
            object? uiApplication,
            object? application)
        {
            Code = code ?? string.Empty;
            Document = document;
            UIDocument = uiDocument;
            UIApplication = uiApplication;
            Application = application;
        }

        // ---- read by the wrapper -------------------------------------------

        /// <summary>The caller's script source.</summary>
        public string Code { get; }

        public object? Document { get; }

        public object? UIDocument { get; }

        public object? UIApplication { get; }

        public object? Application { get; }

        /// <summary>False only for host-less tests, where the Revit namespaces do not exist.</summary>
        public bool BindRevitNamespaces { get; set; } = true;

        public int MaxResultLength
        {
            get { return ResultLimit; }
        }

        public int MaxResultDepth
        {
            get { return ResultDepthLimit; }
        }

        public int MaxTracebackLength
        {
            get { return TracebackLimit; }
        }

        public int MaxErrorLength
        {
            get { return ErrorLimit; }
        }

        // ---- called by the wrapper -----------------------------------------

        public void SetStage(string stage)
        {
            Stage = string.IsNullOrWhiteSpace(stage) ? "none" : stage;
        }

        /// <summary>Bounded as it arrives: a script cannot grow host memory by printing.</summary>
        public void WriteOutput(string text)
        {
            OutputTruncated |= Append(output, text);
        }

        public void WriteError(string text)
        {
            StderrTruncated |= Append(stderr, text);
        }

        /// <summary>The script ran to its end. Either argument may be null.</summary>
        public void Complete(string? resultJson, string? resultOmittedReason)
        {
            ResultJson = resultJson;
            ResultOmittedReason = resultOmittedReason;
            Completed = true;
        }

        /// <summary>The script, or the wrapper around it, raised.</summary>
        public void Fail(string? error, string? traceback)
        {
            ScriptError = string.IsNullOrWhiteSpace(error) ? "The script failed without a message." : error;
            ScriptTraceback = traceback;
            Completed = false;
        }

        // ---- read by the host after the engine call returned ----------------

        public string Stage { get; private set; } = "none";

        public bool Completed { get; private set; }

        public string? ScriptError { get; private set; }

        public string? ScriptTraceback { get; private set; }

        public string? ResultJson { get; private set; }

        public string? ResultOmittedReason { get; private set; }

        public string Output
        {
            get { return output.ToString(); }
        }

        public bool OutputTruncated { get; private set; }

        public string Stderr
        {
            get { return stderr.ToString(); }
        }

        public bool StderrTruncated { get; private set; }

        /// <summary>Returns true when text had to be cut.</summary>
        private static bool Append(StringBuilder buffer, string? text)
        {
            if (string.IsNullOrEmpty(text))
            {
                return false;
            }

            var room = StreamLimit - buffer.Length;
            if (room <= 0)
            {
                return true;
            }

            if (text!.Length <= room)
            {
                buffer.Append(text);
                return false;
            }

            buffer.Append(text, 0, room);
            return true;
        }
    }
}
