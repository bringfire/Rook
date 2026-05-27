namespace Rook.UI.Web
{
    internal sealed class WebViewHostPresentationIdleGate
    {
        private bool _pending;
        private long _generation;

        public bool TrySchedule(long generation)
        {
            if (_pending)
                return false;
            _pending = true;
            _generation = generation;
            return true;
        }

        public bool ShouldRun(long currentGeneration, bool disposed, bool desiredVisible)
        {
            if (!_pending)
                return false;
            _pending = false;
            return !disposed &&
                desiredVisible &&
                currentGeneration == _generation;
        }

        public void Clear()
        {
            _pending = false;
        }
    }
}
