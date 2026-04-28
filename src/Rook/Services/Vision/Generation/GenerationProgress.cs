using System;

namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Optional progress signal exposed by providers that surface one.
    /// Veo emits operation-style progress; fal queue exposes
    /// <c>queue_position</c>; Replicate exposes streaming logs but no
    /// percentage. Providers populate the field they have signal for
    /// and leave the rest null.
    ///
    /// <para>Sealed class with read-only properties + bounded
    /// invariants:</para>
    /// <list type="bullet">
    ///   <item><see cref="PercentComplete"/>, when set, must be in
    ///         <c>[0, 100]</c>. Out-of-range values would flow into
    ///         UI/logging as valid progress.</item>
    ///   <item><see cref="QueuePosition"/>, when set, must be
    ///         non-negative.</item>
    /// </list>
    /// </summary>
    public sealed class GenerationProgress
    {
        public GenerationProgress(
            double? PercentComplete = null,
            int? QueuePosition = null,
            string? Message = null)
        {
            if (PercentComplete is { } pc && (pc < 0.0 || pc > 100.0))
                throw new ArgumentOutOfRangeException(
                    nameof(PercentComplete), pc,
                    "PercentComplete must be in [0, 100] when set.");
            if (QueuePosition is { } qp && qp < 0)
                throw new ArgumentOutOfRangeException(
                    nameof(QueuePosition), qp,
                    "QueuePosition must be non-negative when set.");

            this.PercentComplete = PercentComplete;
            this.QueuePosition = QueuePosition;
            this.Message = Message;
        }

        public double? PercentComplete { get; }
        public int? QueuePosition { get; }
        public string? Message { get; }
    }
}
