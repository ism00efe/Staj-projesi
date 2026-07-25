using System;
using System.ComponentModel.Design;
using System.IO;
using System.Threading.Tasks;
using EnvDTE;
using EnvDTE80;
using Microsoft.VisualStudio.Shell;
using Microsoft.VisualStudio.Shell.Interop;
using PaymentAssistant.Detection;
using Task = System.Threading.Tasks.Task;

namespace PaymentAssistant.Commands
{
    /// <summary>
    /// Solution Explorer context menu: "Analyze with Payment Assistant".
    ///
    /// Sends the contents of the selected .log/.json/.xml file. Unlike the editor
    /// command this is an explicit whole-file action — the user right-clicked that
    /// specific file and picked this command, so the intent is unambiguous. A
    /// confirmation still precedes transmission, because sending a whole log off the
    /// machine should never be one stray click away.
    /// </summary>
    internal sealed class AnalyzeFileCommand
    {
        public const int CommandId = 0x0101;
        public static readonly Guid CommandSet = PaymentAssistantPackage.CommandSetGuid;

        // Guards against a mis-click on a huge file; the server enforces its own cap and
        // would reject anything larger anyway (MAX_UPLOAD_BYTES, 2 MB by default).
        private const long MaxFileBytes = 2_000_000;

        private readonly AsyncPackage _package;

        private AnalyzeFileCommand(AsyncPackage package, OleMenuCommandService commandService)
        {
            _package = package;
            var menuCommandId = new CommandID(CommandSet, CommandId);
            var command = new OleMenuCommand(Execute, menuCommandId);
            command.BeforeQueryStatus += OnBeforeQueryStatus;
            commandService.AddCommand(command);
        }

        public static AnalyzeFileCommand Instance { get; private set; }

        public static async Task InitializeAsync(AsyncPackage package)
        {
            await ThreadHelper.JoinableTaskFactory.SwitchToMainThreadAsync(package.DisposalToken);
            var commandService =
                await package.GetServiceAsync(typeof(IMenuCommandService)) as OleMenuCommandService;
            if (commandService != null)
            {
                Instance = new AnalyzeFileCommand(package, commandService);
            }
        }

        /// <summary>
        /// Hide the command for file types it cannot help with, rather than showing it
        /// everywhere and failing after the click.
        /// </summary>
        private void OnBeforeQueryStatus(object sender, EventArgs e)
        {
            ThreadHelper.ThrowIfNotOnUIThread();

            if (!(sender is OleMenuCommand command))
            {
                return;
            }

            string path = GetSelectedFilePath();
            command.Visible = ErrorCodeScanner.IsScannableFile(path);
            command.Enabled = command.Visible;
        }

        private void Execute(object sender, EventArgs e)
        {
            ThreadHelper.ThrowIfNotOnUIThread();

            string path = GetSelectedFilePath();
            if (string.IsNullOrEmpty(path) || !File.Exists(path))
            {
                ShowMessage("Seçili dosya bulunamadı.", OLEMSGICON.OLEMSGICON_INFO);
                return;
            }

            var info = new FileInfo(path);
            if (info.Length > MaxFileBytes)
            {
                ShowMessage(
                    string.Format(
                        "'{0}' çok büyük ({1:N0} bayt). Sınır {2:N0} bayt.\n\n" +
                        "Dosyayı açıp ilgilendiğiniz satırları seçerek analiz edin.",
                        info.Name, info.Length, MaxFileBytes),
                    OLEMSGICON.OLEMSGICON_WARNING);
                return;
            }

            // Explicit confirmation: this transmits the entire file.
            int answer = VsShellUtilities.ShowMessageBox(
                ServiceProvider.GlobalProvider,
                string.Format(
                    "'{0}' dosyasının tamamı analiz için gönderilecek.\n\n" +
                    "Hassas veriler sunucuda maskelenir. Devam edilsin mi?",
                    info.Name),
                "Payment Assistant",
                OLEMSGICON.OLEMSGICON_QUERY,
                OLEMSGBUTTON.OLEMSGBUTTON_OKCANCEL,
                OLEMSGDEFBUTTON.OLEMSGDEFBUTTON_SECOND);

            const int idOk = 1;
            if (answer != idOk)
            {
                return;
            }

            string content;
            try
            {
                content = File.ReadAllText(path);
            }
            catch (Exception ex)
            {
                ShowMessage(
                    string.Format("Dosya okunamadı: {0}", ex.Message),
                    OLEMSGICON.OLEMSGICON_CRITICAL);
                return;
            }

            AnalysisRunner.Run(
                _package,
                info.Name,
                string.Format(
                    "'{0}' log dosyasını analiz et: hangi hata var, kök nedeni ne ve " +
                    "nasıl çözülür?",
                    info.Name),
                content);
        }

        private static string GetSelectedFilePath()
        {
            ThreadHelper.ThrowIfNotOnUIThread();

            var dte = (DTE2)Package.GetGlobalService(typeof(DTE));
            var selected = dte?.SelectedItems;
            if (selected == null || selected.Count != 1)
            {
                return null;
            }

            ProjectItem item = selected.Item(1)?.ProjectItem;
            if (item == null || item.FileCount < 1)
            {
                return null;
            }

            try
            {
                return item.FileNames[1];
            }
            catch (Exception)
            {
                // Virtual/solution-folder items have no backing file.
                return null;
            }
        }

        private static void ShowMessage(string message, OLEMSGICON icon)
        {
            ThreadHelper.ThrowIfNotOnUIThread();
            VsShellUtilities.ShowMessageBox(
                ServiceProvider.GlobalProvider,
                message,
                "Payment Assistant",
                icon,
                OLEMSGBUTTON.OLEMSGBUTTON_OK,
                OLEMSGDEFBUTTON.OLEMSGDEFBUTTON_FIRST);
        }
    }
}
