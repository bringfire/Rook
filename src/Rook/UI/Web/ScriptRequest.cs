using System;

namespace Rook.UI.Web
{
    /// <summary>
    /// Validity of a script posted to a <see cref="RookWebSurface"/>. A closed union:
    /// <see cref="Content"/> scripts belong to a display generation and are dropped once
    /// that generation has been invalidated (Clear, close); <see cref="Control"/> scripts
    /// mirror control state for the active request and are never dropped for display
    /// reasons — they were already request-filtered by the presentation queue.
    /// </summary>
    public abstract class ScriptValidity
    {
        private ScriptValidity() { }

        public sealed class Content : ScriptValidity
        {
            public Content(int displayGeneration) => DisplayGeneration = displayGeneration;
            public int DisplayGeneration { get; }
        }

        public sealed class Control : ScriptValidity
        {
            public static readonly Control Instance = new();
            private Control() { }
        }
    }

    /// <summary>
    /// One script to run in the WebView, tagged with its validity. Immutable.
    /// </summary>
    public sealed class ScriptRequest
    {
        public ScriptRequest(ScriptValidity validity, string script)
        {
            Validity = validity ?? throw new ArgumentNullException(nameof(validity));
            Script = script ?? throw new ArgumentNullException(nameof(script));
        }

        public ScriptValidity Validity { get; }
        public string Script { get; }

        public static ScriptRequest ForContent(int displayGeneration, string script)
            => new(new ScriptValidity.Content(displayGeneration), script);

        public static ScriptRequest ForControl(string script)
            => new(ScriptValidity.Control.Instance, script);

        /// <summary>True when this script is still valid for the given display generation.</summary>
        public bool IsValidFor(int displayGeneration)
            => Validity is not ScriptValidity.Content content || content.DisplayGeneration == displayGeneration;
    }

    /// <summary>
    /// Script admission backpressure exposed by a surface to its presentation producer.
    /// <see cref="Backlog"/> counts queued plus in-flight scripts; <see cref="BacklogDrained"/>
    /// fires on the UI thread when the backlog falls below the surface's resume threshold.
    /// </summary>
    public interface IScriptBackpressure
    {
        int Backlog { get; }
        event Action? BacklogDrained;
    }
}
