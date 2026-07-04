using System;
using System.Globalization;
using System.Text;
using Grasshopper;
using Grasshopper.Kernel;

public class Script_Instance : GH_ScriptInstance
{
    private void RunScript(
        object Frame,
        object FPS,
        object Duration,
        object Loop,
        object Reset,
        ref object Clock,
        ref object FrameOut,
        ref object T,
        ref object Seconds,
        ref object FrameCount,
        ref object FPSOut,
        ref object Info)
    {
        int fps = Math.Max(1, ReadInt(FPS, 24));
        double durationSeconds = Math.Max(0.0, ReadDouble(Duration, 10.0));
        int frameCount = SafeFrameCount(durationSeconds, fps);
        bool loop = ReadBool(Loop, false);
        bool reset = ReadBool(Reset, false);
        int frame = reset ? 0 : ReadInt(Frame, 0);

        if (loop)
            frame = PositiveModulo(frame, frameCount);
        else
            frame = Clamp(frame, 0, frameCount);

        double t = frameCount <= 0 ? 0.0 : Clamp((double)frame / (double)frameCount, 0.0, 1.0);
        double seconds = frame / (double)fps;

        Clock = BuildClockJson(frame, fps, durationSeconds, frameCount, t, seconds, loop, reset);
        FrameOut = frame;
        T = t;
        Seconds = seconds;
        FrameCount = frameCount;
        FPSOut = fps;
        Info = $"Director Clock: frame={frame}; fps={fps}; duration={durationSeconds:0.###}s; frameCount={frameCount}; t={t:0.###}; seconds={seconds:0.###}; loop={loop}; reset={reset}.";
    }

    private static string BuildClockJson(int frame, int fps, double durationSeconds, int frameCount, double t, double seconds, bool loop, bool reset)
    {
        var sb = new StringBuilder();
        sb.Append("{");
        sb.Append("\"metadata_kind\":\"director_clock_payload\",");
        sb.Append("\"schema_version\":1,");
        sb.Append("\"frame\":").Append(frame.ToString(CultureInfo.InvariantCulture)).Append(",");
        sb.Append("\"fps\":").Append(fps.ToString(CultureInfo.InvariantCulture)).Append(",");
        sb.Append("\"duration_seconds\":").Append(Num(durationSeconds)).Append(",");
        sb.Append("\"frame_count\":").Append(frameCount.ToString(CultureInfo.InvariantCulture)).Append(",");
        sb.Append("\"t\":").Append(Num(t)).Append(",");
        sb.Append("\"seconds\":").Append(Num(seconds)).Append(",");
        sb.Append("\"loop\":").Append(loop ? "true" : "false").Append(",");
        sb.Append("\"reset\":").Append(reset ? "true" : "false");
        sb.Append("}");
        return sb.ToString();
    }

    private static int ReadInt(object value, int fallback)
    {
        if (value == null) return fallback;
        try
        {
            double parsed = Convert.ToDouble(value, CultureInfo.InvariantCulture);
            if (!IsFinite(parsed)) return fallback;
            return Convert.ToInt32(Math.Round(parsed));
        }
        catch { return fallback; }
    }

    private static double ReadDouble(object value, double fallback)
    {
        if (value == null) return fallback;
        try
        {
            double parsed = Convert.ToDouble(value, CultureInfo.InvariantCulture);
            return IsFinite(parsed) ? parsed : fallback;
        }
        catch { return fallback; }
    }

    private static bool ReadBool(object value, bool fallback)
    {
        if (value == null) return fallback;
        try { return Convert.ToBoolean(value, CultureInfo.InvariantCulture); }
        catch
        {
            string text = value.ToString();
            if (string.IsNullOrWhiteSpace(text)) return fallback;
            text = text.Trim().ToLowerInvariant();
            if (text == "true" || text == "yes" || text == "1") return true;
            if (text == "false" || text == "no" || text == "0") return false;
            return fallback;
        }
    }

    private static int PositiveModulo(int value, int divisor)
    {
        if (divisor <= 0) return 0;
        int result = value % divisor;
        return result < 0 ? result + divisor : result;
    }

    private static int Clamp(int value, int min, int max)
    {
        if (value < min) return min;
        if (value > max) return max;
        return value;
    }

    private static double Clamp(double value, double min, double max)
    {
        if (!IsFinite(value)) return min;
        if (value < min) return min;
        if (value > max) return max;
        return value;
    }

    private static int SafeFrameCount(double durationSeconds, int fps)
    {
        double frames = durationSeconds * fps;
        if (!IsFinite(frames)) return 1;
        if (frames > int.MaxValue) return int.MaxValue;
        return Math.Max(1, (int)Math.Round(frames));
    }

    private static string Num(double value)
    {
        if (!IsFinite(value))
            value = 0.0;
        return value.ToString("G17", CultureInfo.InvariantCulture);
    }

    private static bool IsFinite(double value)
    {
        return !double.IsNaN(value) && !double.IsInfinity(value);
    }
}
