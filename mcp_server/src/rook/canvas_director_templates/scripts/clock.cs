using System;
using Grasshopper;
using Grasshopper.Kernel;

public class Script_Instance : GH_ScriptInstance
{
    private int _frame = 0;
    private bool _hasFrame = false;
    private bool _wasPlaying = false;
    private int _lastFrameIn = 0;
    private bool _hasLastFrameIn = false;

    private void RunScript(
		object FrameIn,
		object FPS,
		object Dur,
		object Play,
		object Reset,
		ref object Frame,
		ref object Time,
		ref object T,
		ref object Done,
		ref object Playing,
		ref object Info)
    {
        int duration = Math.Max(1, ReadInt(Dur, 240));
        double fps = Math.Max(0.001, ReadDouble(FPS, 24.0));
        bool reset = ReadBool(Reset, false);
        bool play = ReadBool(Play, false);
        bool hasFrameIn = TryReadInt(FrameIn, out int frameIn);
        frameIn = Clamp(frameIn, 0, duration);
        bool frameInputChanged = hasFrameIn && (!_hasLastFrameIn || frameIn != _lastFrameIn);

        if (reset)
        {
            _frame = 0;
            _hasFrame = true;
            _wasPlaying = false;
        }
        else if (!play)
        {
            if (frameInputChanged)
            {
                _frame = frameIn;
                _hasFrame = true;
            }
            else if (!_hasFrame)
            {
                _frame = hasFrameIn ? frameIn : 0;
                _hasFrame = true;
            }

            _wasPlaying = false;
        }
        else
        {
            if (!_wasPlaying && (frameInputChanged || !_hasFrame))
            {
                _frame = hasFrameIn ? frameIn : (_hasFrame ? _frame : 0);
                _hasFrame = true;
            }
        }

        int frame = _frame;
        frame = Clamp(frame, 0, duration);

        double time = frame / fps;
        double globalT = Clamp((double)frame / (double)duration, 0.0, 1.0);
        bool done = frame >= duration;
        bool playing = play && !reset && !done;

        Frame = frame;
        Time = time;
        T = globalT;
        Done = done;
        Playing = playing;
        Info = $"Director Clock: frame={frame}/{duration}; time={time:0.###}s; fps={fps:0.###}; globalT={globalT:0.###}; playing={playing}; done={done}; mode={(playing ? "scheduled playback" : "scrub/hold")}; FrameIn={(hasFrameIn ? frameIn.ToString() : "none")}.";

        if (hasFrameIn)
        {
            _lastFrameIn = frameIn;
            _hasLastFrameIn = true;
        }
        else
        {
            _hasLastFrameIn = false;
        }

        if (playing)
        {
            _frame = Clamp(frame + 1, 0, duration);
            _hasFrame = true;
            _wasPlaying = true;
            ScheduleNext(fps);
        }
        else
        {
            _frame = frame;
            _hasFrame = true;
            _wasPlaying = false;
        }
    }

    private static int ReadInt(object value, int fallback)
    {
        if (value == null) return fallback;
        try { return Convert.ToInt32(Math.Round(Convert.ToDouble(value))); }
        catch { return fallback; }
    }

    private static bool TryReadInt(object value, out int result)
    {
        result = 0;
        if (value == null) return false;
        try
        {
            result = Convert.ToInt32(Math.Round(Convert.ToDouble(value)));
            return true;
        }
        catch
        {
            return false;
        }
    }

    private static double ReadDouble(object value, double fallback)
    {
        if (value == null) return fallback;
        try { return Convert.ToDouble(value); }
        catch { return fallback; }
    }

    private static bool ReadBool(object value, bool fallback)
    {
        if (value == null) return fallback;
        try { return Convert.ToBoolean(value); }
        catch { return fallback; }
    }

    private static int Clamp(int value, int min, int max)
    {
        if (value < min) return min;
        if (value > max) return max;
        return value;
    }

    private static double Clamp(double value, double min, double max)
    {
        if (value < min) return min;
        if (value > max) return max;
        return value;
    }

    private void ScheduleNext(double fps)
    {
        var doc = GrasshopperDocument;
        if (doc == null || Component == null) return;

        int delay = Math.Max(1, (int)Math.Round(1000.0 / Math.Max(0.001, fps)));
        doc.ScheduleSolution(delay, d =>
        {
            if (Component != null)
            {
                Component.ExpireSolution(false);
            }
        });
    }
}
