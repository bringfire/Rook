using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Text;
using Rook.UI.Web;

namespace Rook.UI.Chat
{
    /// <summary>
    /// One unit of chat presentation. A closed union (see feedback on records vs
    /// invariants): content-kind items (<see cref="Text"/>, <see cref="Thought"/>,
    /// <see cref="Content"/>) carry the display generation they were produced under and
    /// are dropped once that generation is invalidated; <see cref="Control"/> items carry
    /// the request id they belong to and apply only while that request is active.
    /// </summary>
    internal abstract class PresentationItem
    {
        private PresentationItem() { }

        /// <summary>A streamed assistant text delta. Adjacent deltas of one generation merge within a drain.</summary>
        public sealed class Text : PresentationItem
        {
            public Text(int displayGeneration, string delta)
            {
                DisplayGeneration = displayGeneration;
                Delta = delta ?? string.Empty;
            }
            public int DisplayGeneration { get; }
            public string Delta { get; }
        }

        /// <summary>A reasoning-status update. Collapses to last-wins within a drain.</summary>
        public sealed class Thought : PresentationItem
        {
            public Thought(int displayGeneration, string status)
            {
                DisplayGeneration = displayGeneration;
                Status = status ?? string.Empty;
            }
            public int DisplayGeneration { get; }
            public string Status { get; }
        }

        /// <summary>Any other transcript/history operation (bubble, card, segment break, finalize, typing).</summary>
        public sealed class Content : PresentationItem
        {
            public Content(int displayGeneration, string name, Action apply, bool emitsScripts = true)
            {
                DisplayGeneration = displayGeneration;
                Name = name ?? throw new ArgumentNullException(nameof(name));
                Apply = apply ?? throw new ArgumentNullException(nameof(apply));
                EmitsScripts = emitsScripts;
            }
            public int DisplayGeneration { get; }
            public string Name { get; }
            public Action Apply { get; }
            public bool EmitsScripts { get; }
        }

        /// <summary>A control-state operation for one request (processing flag, status text, composer, settings).</summary>
        public sealed class Control : PresentationItem
        {
            public Control(int requestId, string name, Action apply, bool emitsScripts = true)
            {
                RequestId = requestId;
                Name = name ?? throw new ArgumentNullException(nameof(name));
                Apply = apply ?? throw new ArgumentNullException(nameof(apply));
                EmitsScripts = emitsScripts;
            }
            public int RequestId { get; }
            public string Name { get; }
            public Action Apply { get; }
            public bool EmitsScripts { get; }
        }
    }

    /// <summary>
    /// The single ordered projection of a chat turn onto the UI thread (plan §2).
    /// Items are pushed in event order from any thread; exactly one consumer drains them
    /// on the UI thread in that order. Drains are bounded by item count and time budget,
    /// merge adjacent text deltas (across thought updates, which are a side channel),
    /// collapse thought updates to last-wins, and pause while the surface's script
    /// backlog is above the pause threshold. Validity is checked at apply time:
    /// content-kind items must match the current display generation, control items the
    /// active request. Nothing here blocks, and nothing here reorders.
    /// </summary>
    internal sealed class PresentationQueue
    {
        public const int DefaultMaxItemsPerDrain = 64;
        public const int DefaultPauseThreshold = 16;
        public static readonly TimeSpan DefaultDrainBudget = TimeSpan.FromMilliseconds(8);

        private readonly object _gate = new();
        private readonly Queue<PresentationItem> _pending = new();
        private readonly List<PresentationItem> _carry = new();   // UI thread only
        private readonly Action<Action> _schedule;
        private readonly Func<int> _currentDisplayGeneration;
        private readonly Func<int> _activeRequestId;
        private readonly IScriptBackpressure? _backpressure;
        private readonly Action<string> _applyText;
        private readonly Action<string> _applyThought;
        private readonly int _maxItemsPerDrain;
        private readonly TimeSpan _drainBudget;
        private readonly int _pauseThreshold;
        private bool _drainScheduled;   // under _gate
        private bool _paused;           // UI thread only
        private int _drainCount;

        public PresentationQueue(
            Action<Action> schedule,
            Func<int> currentDisplayGeneration,
            Func<int> activeRequestId,
            IScriptBackpressure? backpressure,
            Action<string> applyText,
            Action<string> applyThought,
            int maxItemsPerDrain = DefaultMaxItemsPerDrain,
            TimeSpan? drainBudget = null,
            int pauseThreshold = DefaultPauseThreshold)
        {
            _schedule = schedule ?? throw new ArgumentNullException(nameof(schedule));
            _currentDisplayGeneration = currentDisplayGeneration ?? throw new ArgumentNullException(nameof(currentDisplayGeneration));
            _activeRequestId = activeRequestId ?? throw new ArgumentNullException(nameof(activeRequestId));
            _backpressure = backpressure;
            _applyText = applyText ?? throw new ArgumentNullException(nameof(applyText));
            _applyThought = applyThought ?? throw new ArgumentNullException(nameof(applyThought));
            if (maxItemsPerDrain < 1) throw new ArgumentOutOfRangeException(nameof(maxItemsPerDrain));
            if (pauseThreshold < 1) throw new ArgumentOutOfRangeException(nameof(pauseThreshold));
            _maxItemsPerDrain = maxItemsPerDrain;
            _drainBudget = drainBudget ?? DefaultDrainBudget;
            _pauseThreshold = pauseThreshold;
            if (_backpressure != null) _backpressure.BacklogDrained += OnBacklogDrained;
        }

        /// <summary>Number of items not yet applied (pending plus carried). Diagnostic.</summary>
        public int PendingCount
        {
            get { lock (_gate) return _pending.Count + _carry.Count; }
        }

        /// <summary>Number of drains that have run. Diagnostic.</summary>
        public int DrainCount => _drainCount;

        /// <summary>True while a drain is parked on script backpressure. Diagnostic.</summary>
        public bool IsPaused => _paused;

        /// <summary>Append one item in event order (any thread) and make sure a drain is scheduled.</summary>
        public void Push(PresentationItem item)
        {
            if (item == null) throw new ArgumentNullException(nameof(item));
            var schedule = false;
            lock (_gate)
            {
                _pending.Enqueue(item);
                if (!_drainScheduled && !_paused)
                {
                    _drainScheduled = true;
                    schedule = true;
                }
            }
            if (schedule) _schedule(Drain);
        }

        /// <summary>
        /// Drop pending content-kind items whose generation is no longer current
        /// (Clear / close). Control items are never dropped here. UI thread.
        /// </summary>
        public void Discard()
        {
            var generation = _currentDisplayGeneration();
            lock (_gate)
            {
                if (_pending.Count > 0)
                {
                    var kept = new List<PresentationItem>(_pending.Count);
                    foreach (var item in _pending)
                        if (!IsStaleContent(item, generation)) kept.Add(item);
                    _pending.Clear();
                    foreach (var item in kept) _pending.Enqueue(item);
                }
            }
            _carry.RemoveAll(item => IsStaleContent(item, generation));
        }

        private static bool IsStaleContent(PresentationItem item, int generation) => item switch
        {
            PresentationItem.Text t => t.DisplayGeneration != generation,
            PresentationItem.Thought t => t.DisplayGeneration != generation,
            PresentationItem.Content c => c.DisplayGeneration != generation,
            _ => false,
        };

        private void OnBacklogDrained()
        {
            lock (_gate)
            {
                if (!_paused) return;
                _paused = false;
            }
            ScheduleDrainIfPending();
        }

        private void ScheduleDrainIfPending()
        {
            var schedule = false;
            lock (_gate)
            {
                if (!_drainScheduled && !_paused && (_pending.Count > 0 || _carry.Count > 0))
                {
                    _drainScheduled = true;
                    schedule = true;
                }
            }
            if (schedule) _schedule(Drain);
        }

        // ─── Drain (UI thread) ───────────────────────────────────────

        private abstract class Op
        {
            private Op() { }
            public sealed class MergedText : Op
            {
                public MergedText(int generation, string delta) { Generation = generation; Builder = new StringBuilder(delta); }
                public int Generation { get; }
                public StringBuilder Builder { get; }
            }
            public sealed class Thought : Op
            {
                public Thought(PresentationItem.Thought item) => Item = item;
                public PresentationItem.Thought Item { get; }
            }
            public sealed class Single : Op
            {
                public Single(PresentationItem item) => Item = item;
                public PresentationItem Item { get; }
            }
            public sealed class Carried : Op
            {
                // A merged text that must be re-queued unmerged is impossible to
                // reconstruct exactly; carry the original items instead.
                public Carried(List<PresentationItem> items) => Items = items;
                public List<PresentationItem> Items { get; }
            }
        }

        private void Drain()
        {
            _drainCount++;
            var batch = new List<PresentationItem>(_maxItemsPerDrain);
            lock (_gate)
            {
                _drainScheduled = false;
                batch.AddRange(_carry);
                _carry.Clear();
                while (batch.Count < _maxItemsPerDrain && _pending.Count > 0)
                    batch.Add(_pending.Dequeue());
            }
            if (batch.Count == 0) return;

            // Merge: adjacent Text of one generation (Thought items in between do not
            // break a run); Thought collapses to the latest; everything else is single.
            var ops = new List<(Op op, List<PresentationItem> source)>();
            var lastTextIndex = -1;
            foreach (var item in batch)
            {
                switch (item)
                {
                    case PresentationItem.Text text:
                        if (lastTextIndex >= 0 &&
                            ops[lastTextIndex].op is Op.MergedText merged &&
                            merged.Generation == text.DisplayGeneration &&
                            OnlyThoughtsSince(ops, lastTextIndex))
                        {
                            merged.Builder.Append(text.Delta);
                            ops[lastTextIndex].source.Add(text);
                        }
                        else
                        {
                            ops.Add((new Op.MergedText(text.DisplayGeneration, text.Delta), new List<PresentationItem> { text }));
                            lastTextIndex = ops.Count - 1;
                        }
                        break;
                    case PresentationItem.Thought thought:
                        for (var i = ops.Count - 1; i >= 0; i--)
                        {
                            if (ops[i].op is Op.Thought)
                            {
                                ops.RemoveAt(i);
                                if (lastTextIndex > i) lastTextIndex--;
                            }
                        }
                        ops.Add((new Op.Thought(thought), new List<PresentationItem> { thought }));
                        break;
                    default:
                        ops.Add((new Op.Single(item), new List<PresentationItem> { item }));
                        lastTextIndex = -1;
                        break;
                }
            }

            var generation = _currentDisplayGeneration();
            var request = _activeRequestId();
            var watch = Stopwatch.StartNew();
            for (var i = 0; i < ops.Count; i++)
            {
                var (op, source) = ops[i];
                var emitsScripts = op switch
                {
                    Op.MergedText => true,
                    Op.Thought => false,
                    Op.Single s => s.Item switch
                    {
                        PresentationItem.Content c => c.EmitsScripts,
                        PresentationItem.Control c => c.EmitsScripts,
                        _ => true,
                    },
                    _ => true,
                };
                if (emitsScripts && _backpressure != null && _backpressure.Backlog >= _pauseThreshold)
                {
                    CarryFrom(ops, i);
                    lock (_gate) _paused = true;
                    return;
                }
                switch (op)
                {
                    case Op.MergedText text:
                        if (text.Generation == generation) _applyText(text.Builder.ToString());
                        break;
                    case Op.Thought thought:
                        if (thought.Item.DisplayGeneration == generation) _applyThought(thought.Item.Status);
                        break;
                    case Op.Single single:
                        switch (single.Item)
                        {
                            case PresentationItem.Content content:
                                if (content.DisplayGeneration == generation) content.Apply();
                                break;
                            case PresentationItem.Control control:
                                if (control.RequestId == request) control.Apply();
                                break;
                        }
                        break;
                }
                if (i + 1 < ops.Count && watch.Elapsed >= _drainBudget)
                {
                    CarryFrom(ops, i + 1);
                    ScheduleDrainIfPending();
                    return;
                }
            }
            ScheduleDrainIfPending();
        }

        private static bool OnlyThoughtsSince(List<(Op op, List<PresentationItem> source)> ops, int index)
        {
            for (var i = index + 1; i < ops.Count; i++)
                if (ops[i].op is not Op.Thought) return false;
            return true;
        }

        private void CarryFrom(List<(Op op, List<PresentationItem> source)> ops, int start)
        {
            // Carry the original items (not merged ops) so a later drain re-merges
            // identically and ordering is untouched.
            for (var i = start; i < ops.Count; i++)
                _carry.AddRange(ops[i].source);
        }
    }
}
