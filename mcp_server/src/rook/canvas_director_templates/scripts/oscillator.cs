using System;
using System.Globalization;
using System.Text;
using Grasshopper;
using Grasshopper.Kernel;

public class Script_Instance : GH_ScriptInstance
{
    private void RunScript(
        object Progress,
        object Amplitude,
        object Frequency,
        object Phase,
        object Bias,
        object Clamp,
        object Enabled,
        ref object Oscillator,
        ref object Value,
        ref object Wave,
        ref object ProgressOut,
        ref object AmplitudeOut,
        ref object FrequencyOut,
        ref object PhaseOut,
        ref object BiasOut,
        ref object EnabledOut,
        ref object Info)
    {
        double progress = ClampValue(ReadDouble(Progress, 0.0), 0.0, 1.0);
        double amplitude = ReadDouble(Amplitude, 1.0);
        double frequency = ReadDouble(Frequency, 1.0);
        double phase = ReadDouble(Phase, 0.0);
        double bias = ReadDouble(Bias, 0.0);
        bool clamp = ReadBool(Clamp, false);
        bool enabled = ReadBool(Enabled, true);

        double wave = enabled ? Math.Sin(2.0 * Math.PI * ((progress * frequency) + phase)) : 0.0;
        double value = enabled ? (bias + (wave * amplitude)) : bias;
        if (clamp)
            value = ClampValue(value, 0.0, 1.0);

        Oscillator = BuildOscillatorJson(progress, amplitude, frequency, phase, bias, clamp, enabled, wave, value);
        Value = value;
        Wave = wave;
        ProgressOut = progress;
        AmplitudeOut = amplitude;
        FrequencyOut = frequency;
        PhaseOut = phase;
        BiasOut = bias;
        EnabledOut = enabled;
        Info = $"Director Oscillator: progress={progress:0.###}; amplitude={amplitude:0.###}; frequency={frequency:0.###}; phase={phase:0.###}; bias={bias:0.###}; clamp={clamp}; enabled={enabled}; wave={wave:0.###}; value={value:0.###}.";
    }

    private static string BuildOscillatorJson(double progress, double amplitude, double frequency, double phase, double bias, bool clamp, bool enabled, double wave, double value)
    {
        var sb = new StringBuilder();
        sb.Append("{");
        sb.Append("\"metadata_kind\":\"director_oscillator_payload\",");
        sb.Append("\"schema_version\":1,");
        sb.Append("\"progress\":").Append(Num(progress)).Append(",");
        sb.Append("\"amplitude\":").Append(Num(amplitude)).Append(",");
        sb.Append("\"frequency\":").Append(Num(frequency)).Append(",");
        sb.Append("\"phase\":").Append(Num(phase)).Append(",");
        sb.Append("\"bias\":").Append(Num(bias)).Append(",");
        sb.Append("\"clamp\":").Append(clamp ? "true" : "false").Append(",");
        sb.Append("\"enabled\":").Append(enabled ? "true" : "false").Append(",");
        sb.Append("\"wave\":").Append(Num(wave)).Append(",");
        sb.Append("\"value\":").Append(Num(value));
        sb.Append("}");
        return sb.ToString();
    }

    private static double ReadDouble(object value, double fallback)
    {
        if (value == null) return fallback;
        try { return Convert.ToDouble(value, CultureInfo.InvariantCulture); }
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

    private static double ClampValue(double value, double min, double max)
    {
        if (value < min) return min;
        if (value > max) return max;
        return value;
    }

    private static string Num(double value)
    {
        return value.ToString("G17", CultureInfo.InvariantCulture);
    }
}
