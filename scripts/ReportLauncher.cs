using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

internal static class ReportLauncher
{
    [STAThread]
    private static int Main(string[] args)
    {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string launcher = Path.Combine(root, "Start.cmd");
        if (args.Length == 1 && args[0] == "--check")
            return File.Exists(launcher) && File.Exists(Path.Combine(root, "engine", "__main__.py")) ? 0 : 1;
        try
        {
            var start = new ProcessStartInfo(launcher);
            start.WorkingDirectory = root;
            start.UseShellExecute = true;
            Process.Start(start);
            return 0;
        }
        catch (Exception error)
        {
            MessageBox.Show(error.Message, "Iran Smart Invest", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}
