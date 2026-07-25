using System;
using System.Runtime.InteropServices;
using System.Threading;
using Microsoft.VisualStudio.Shell;
using PaymentAssistant.Commands;
using PaymentAssistant.Options;
using PaymentAssistant.ToolWindows;
using Task = System.Threading.Tasks.Task;

namespace PaymentAssistant
{
    /// <summary>
    /// Extension entry point.
    ///
    /// An <see cref="AsyncPackage"/> so loading never blocks the IDE's UI thread. It is
    /// loaded on demand — when one of its commands is invoked or its tool window is
    /// restored — rather than at startup, since an extension that idles most of the time
    /// should not cost every solution load.
    /// </summary>
    [PackageRegistration(UseManagedResourcesOnly = true, AllowsBackgroundLoading = true)]
    [Guid(PackageGuidString)]
    [ProvideMenuResource("Menus.ctmenu", 1)]

    // Registering the tool window is what lets Visual Studio recreate it on restart: the
    // shell remembers the window was open and loads this package to rebuild it.
    [ProvideToolWindow(typeof(ResultToolWindow), Style = VsDockStyle.Tabbed,
        Window = "{34E76E81-EE4A-11D0-AE2E-00A0C90FFFC3}")]  // dock beside the Output window

    [ProvideOptionPage(typeof(GeneralOptionsPage), "Payment Assistant", "General",
        categoryResourceID: 0, pageNameResourceID: 0, supportsAutomation: true)]
    public sealed class PaymentAssistantPackage : AsyncPackage
    {
        public const string PackageGuidString = "c425ce3c-df4b-4157-9076-a912b5e79f5c";

        /// <summary>
        /// The command set both commands live in. Must match the guidPaymentAssistantCmdSet
        /// symbol in PaymentAssistantPackage.vsct — if these drift, the menu items appear
        /// but clicking them does nothing.
        /// </summary>
        public static readonly Guid CommandSetGuid =
            new Guid("d33cab5c-15f8-4cc0-a92f-45e827fbf23c");

        protected override async Task InitializeAsync(
            CancellationToken cancellationToken, IProgress<ServiceProgressData> progress)
        {
            await base.InitializeAsync(cancellationToken, progress);

            await AnalyzeSelectionCommand.InitializeAsync(this);
            await AnalyzeFileCommand.InitializeAsync(this);
        }
    }
}
