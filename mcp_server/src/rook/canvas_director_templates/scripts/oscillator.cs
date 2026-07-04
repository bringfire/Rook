using System;
using Grasshopper;
using Grasshopper.Kernel;

public class Script_Instance : GH_ScriptInstance
{
    private void RunScript(
		object LocalT,
		object Active,
		object Cycles,
		object Phase,
		object Mode,
		object Amplitude,
		object HoldMode,
		ref object Value,
		ref object RepeatT,
		ref object PingPongT,
		ref object Sine,
		ref object Sine01,
		ref object CycleIndex,
		ref object ActiveOut,
		ref object Done,
		ref object Info)
    {
        double localT = Clamp(ReadDouble(LocalT, 0.0), 0.0, 1.0);
        bool active = ReadBool(Active, true);
        double cycles = Math.Max(0.0, ReadDouble(Cycles, 1.0));
        double phase = ReadDouble(Phase, 0.0);
        string mode = NormalizeMode(ReadString(Mode, "PingPong"));
        double amplitude = ReadDouble(Amplitude, 1.0);
        string holdMode = NormalizeHoldMode(ReadString(HoldMode, "Zero"));

        double repeatT = 0.0;
        double pingPongT = 0.0;
        double sine = 0.0;
        double sine01 = 0.5;
        int cycleIndex = 0;
        bool done = localT >= 1.0;

        if (cycles > 0.0)
        {
            double cyclePositionRaw = localT * cycles + phase;
            cycleIndex = (int)Math.Floor(Math.Max(0.0, cyclePositionRaw));
            repeatT = PositiveFraction(cyclePositionRaw);
            pingPongT = 1.0 - Math.Abs((2.0 * repeatT) - 1.0);
            sine = Math.Sin(2.0 * Math.PI * repeatT);
            sine01 = 0.5 + (0.5 * sine);

            if (done && Math.Abs(repeatT) < 1e-9)
            {
                repeatT = 1.0;
                pingPongT = 0.0;
                sine = 0.0;
                sine01 = 0.5;
            }
        }

        double selected = SelectValue(mode, repeatT, pingPongT, sine, sine01);
        if (!active)
            selected = HoldValue(holdMode, mode);

        double value = selected * amplitude;

        Value = value;
        RepeatT = active ? repeatT : HoldValue(holdMode, "Repeat");
        PingPongT = active ? pingPongT : HoldValue(holdMode, "PingPong");
        Sine = active ? sine : 0.0;
        Sine01 = active ? sine01 : HoldValue(holdMode, "Sine01");
        CycleIndex = cycleIndex;
        ActiveOut = active;
        Done = done;
        Info = $"Director Oscillator: localT={localT:0.###}; active={active}; cycles={cycles:0.###}; phase={phase:0.###}; mode={mode}; amplitude={amplitude:0.###}; holdMode={holdMode}; value={value:0.###}; repeatT={repeatT:0.###}; pingPongT={pingPongT:0.###}; sine={sine:0.###}; sine01={sine01:0.###}; cycleIndex={cycleIndex}; done={done}.";
    }

    private static double SelectValue(string mode, double repeatT, double pingPongT, double sine, double sine01)
    {
        switch (mode)
        {
            case "Repeat": return repeatT;
            case "Sine": return sine;
            case "Sine01": return sine01;
            case "PingPong":
            default:
                return pingPongT;
        }
    }

    private static double HoldValue(string holdMode, string mode)
    {
        switch (holdMode)
        {
            case "Initial": return mode == "Sine01" ? 0.5 : 0.0;
            case "Final": return mode == "PingPong" ? 0.0 : 1.0;
            case "One": return 1.0;
            case "Zero":
            default:
                return 0.0;
        }
    }

    private static string NormalizeMode(string value)
    {
        if (string.IsNullOrWhiteSpace(value)) return "PingPong";
        string v = value.Trim().ToLowerInvariant();
        if (v == "repeat" || v == "loopt" || v == "cycle") return "Repeat";
        if (v == "sine" || v == "sin") return "Sine";
        if (v == "sine01" || v == "sin01" || v == "sin01t" || v == "sine 0-1") return "Sine01";
        return "PingPong";
    }

    private static string NormalizeHoldMode(string value)
    {
        if (string.IsNullOrWhiteSpace(value)) return "Zero";
        string v = value.Trim().ToLowerInvariant();
        if (v == "initial" || v == "start") return "Initial";
        if (v == "final" || v == "end") return "Final";
        if (v == "one" || v == "1") return "One";
        return "Zero";
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

    private static string ReadString(object value, string fallback)
    {
        if (value == null) return fallback;
        string s = value.ToString();
        return string.IsNullOrWhiteSpace(s) ? fallback : s;
    }

    private static double Clamp(double value, double min, double max)
    {
        if (value < min) return min;
        if (value > max) return max;
        return value;
    }

    private static double PositiveFraction(double value)
    {
        double f = value - Math.Floor(value);
        if (f < 0.0) f += 1.0;
        return f;
    }
}
