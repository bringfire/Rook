namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Canonical lowercase lifecycle vocabulary across every provider.
    /// Phase 0 evidence:
    /// <list type="bullet">
    ///   <item>fal queue uses UPPERCASE <c>IN_QUEUE</c> /
    ///         <c>IN_PROGRESS</c> / <c>COMPLETED</c>.</item>
    ///   <item>Replicate uses lowercase <c>starting</c> /
    ///         <c>processing</c> / <c>succeeded</c>.</item>
    ///   <item>Veo uses operation-style states.</item>
    /// </list>
    ///
    /// <para>Provider adapters call
    /// <see cref="GenerationLifecycleStateNormalizer.Normalize"/> to
    /// map to this canonical set. The manager has a richer state
    /// vocabulary (e.g. <c>VideoJobState</c>'s
    /// <c>Submitting/Polling/Downloading/Saving</c>) that includes
    /// manager-only phases not visible to providers.</para>
    /// </summary>
    public enum GenerationLifecycleState
    {
        Pending = 0,
        Running = 1,
        Completed = 2,
        Failed = 3,
        Canceled = 4,
    }
}
