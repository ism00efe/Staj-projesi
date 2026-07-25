using System.Runtime.InteropServices;
using Microsoft.VisualStudio.Shell;

namespace PaymentAssistant.ToolWindows
{
    /// <summary>
    /// Dockable tool window hosting the analysis result.
    ///
    /// A dedicated tool window rather than the Output window: results are structured
    /// (answer, source list, security summary) and the source list is interactive, none
    /// of which survives being flattened into a text pane. Visual Studio persists the
    /// window's docked position and reopens it across sessions.
    /// </summary>
    [Guid(WindowGuidString)]
    public sealed class ResultToolWindow : ToolWindowPane
    {
        public const string WindowGuidString = "ec725a02-cd24-4feb-b288-6edae64dc4aa";

        public ResultToolWindow() : base(null)
        {
            Caption = "Payment Assistant";

            // ToolWindowPane wraps this in the frame; it must be a WPF element.
            Content = new ResultToolWindowControl();
        }
    }
}
