using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

internal static class ClipAiLauncher
{
    [STAThread]
    private static void Main()
    {
        var applicationDirectory = AppDomain.CurrentDomain.BaseDirectory;
        var startupScript = Path.Combine(applicationDirectory, "run_clipai_silent.vbs");

        if (!File.Exists(startupScript))
        {
            MessageBox.Show(
                "The ClipAI startup script could not be found. Make sure the launcher remains alongside the ClipAI application files.",
                "ClipAI Could Not Start",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            return;
        }

        Process.Start(new ProcessStartInfo
        {
            FileName = "wscript.exe",
            Arguments = "\"" + startupScript + "\"",
            WorkingDirectory = applicationDirectory,
            UseShellExecute = false,
            CreateNoWindow = true,
            WindowStyle = ProcessWindowStyle.Hidden,
        });
    }
}
