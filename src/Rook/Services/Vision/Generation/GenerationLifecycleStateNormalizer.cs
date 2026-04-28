using System;

namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Maps a provider-specific lifecycle state string to a canonical
    /// <see cref="GenerationLifecycleState"/>. Case-insensitive; the
    /// raw value is preserved upstream for evidence/audit (Phase 0
    /// noted that fal queue uses UPPERCASE while Replicate uses
    /// lowercase, and the original case is observable in
    /// notes / ledger metadata).
    ///
    /// <para>Synonyms are explicit per provider: a provider whose
    /// state name is not in the table must extend this normalizer
    /// rather than silently fall through. <see cref="TryNormalize"/>
    /// returns false on unknown values; <see cref="Normalize"/>
    /// throws to make a missing mapping fail loudly during
    /// integration.</para>
    /// </summary>
    public static class GenerationLifecycleStateNormalizer
    {
        public static bool TryNormalize(string raw, out GenerationLifecycleState state)
        {
            if (string.IsNullOrWhiteSpace(raw))
            {
                state = default;
                return false;
            }

            // Lowercase + trim once; comparisons below assume both.
            var normalized = raw.Trim().ToLowerInvariant();

            switch (normalized)
            {
                // Pending: not yet started compute
                case "pending":
                case "queued":
                case "in_queue":
                case "starting":
                case "submitted":
                    state = GenerationLifecycleState.Pending;
                    return true;

                // Running: actively executing
                case "running":
                case "processing":
                case "in_progress":
                case "active":
                    state = GenerationLifecycleState.Running;
                    return true;

                // Completed: terminal success at the lifecycle level.
                // Note: for fal queue, COMPLETED is terminal-not-success;
                // success/failure discrimination happens at fetch step.
                // The lifecycle state here only encodes terminal-reached.
                case "completed":
                case "succeeded":
                case "success":
                case "done":
                case "finished":
                    state = GenerationLifecycleState.Completed;
                    return true;

                // Failed: terminal failure
                case "failed":
                case "error":
                case "errored":
                    state = GenerationLifecycleState.Failed;
                    return true;

                // Canceled: terminal user-initiated stop. Both English
                // spellings observed; we accept both.
                case "canceled":
                case "cancelled":
                    state = GenerationLifecycleState.Canceled;
                    return true;

                default:
                    state = default;
                    return false;
            }
        }

        public static GenerationLifecycleState Normalize(string raw)
        {
            if (TryNormalize(raw, out var state))
                return state;

            throw new ArgumentException(
                $"Unknown lifecycle state '{raw}'. Add the synonym to " +
                $"{nameof(GenerationLifecycleStateNormalizer)} explicitly " +
                "rather than relying on a fall-through default.",
                nameof(raw));
        }
    }
}
