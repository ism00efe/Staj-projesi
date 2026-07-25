using System;
using System.Collections.Generic;
using System.ComponentModel.Design;
using System.Linq;
using System.Threading.Tasks;
using EnvDTE;
using EnvDTE80;
using Microsoft.VisualStudio.Shell;
using PaymentAssistant.Detection;
using PaymentAssistant.Dialogs;
using Task = System.Threading.Tasks.Task;

namespace PaymentAssistant.Commands
{
    /// <summary>
    /// Editor context menu: "Analyze with Payment Assistant".
    ///
    /// Behaviour, in order:
    ///   1. Text is selected  -> send exactly that selection.
    ///   2. Nothing selected, and the document is .log/.json/.xml -> scan it for error
    ///      codes and let the user tick which ones to send. Only the ticked lines go.
    ///   3. Otherwise -> explain what to do; send nothing.
    ///
    /// The whole document is never transmitted implicitly. Every byte that leaves the
    /// machine was either selected by the user or ticked in the dialog.
    /// </summary>
    internal sealed class AnalyzeSelectionCommand
    {
        public const int CommandId = 0x0100;
        public static readonly Guid CommandSet = PaymentAssistantPackage.CommandSetGuid;

        private readonly AsyncPackage _package;

        private AnalyzeSelectionCommand(AsyncPackage package, OleMenuCommandService commandService)
        {
            _package = package;
            var menuCommandId = new CommandID(CommandSet, CommandId);
            commandService.AddCommand(new MenuCommand(Execute, menuCommandId));
        }

        public static AnalyzeSelectionCommand Instance { get; private set; }

        public static async Task InitializeAsync(AsyncPackage package)
        {
            await ThreadHelper.JoinableTaskFactory.SwitchToMainThreadAsync(
                package.DisposalToken);
            var commandService =
                await package.GetServiceAsync(typeof(IMenuCommandService)) as OleMenuCommandService;
            if (commandService != null)
            {
                Instance = new AnalyzeSelectionCommand(package, commandService);
            }
        }

        private void Execute(object sender, EventArgs e)
        {
            ThreadHelper.ThrowIfNotOnUIThread();

            var dte = (DTE2)Package.GetGlobalService(typeof(DTE));
            Document document = dte?.ActiveDocument;
            if (document == null)
            {
                ShowInfo("Önce bir dosya açın.");
                return;
            }

            string selection = GetSelectedText(document);
            if (!string.IsNullOrWhiteSpace(selection))
            {
                AnalysisRunner.Run(
                    _package,
                    string.Format("{0} (seçim)", document.Name),
                    BuildQuestion(document.Name),
                    selection);
                return;
            }

            if (!ErrorCodeScanner.IsScannableFile(document.FullName))
            {
                ShowInfo(
                    "Analiz edilecek metni seçin.\n\n" +
                    "Seçim yapılmadığında yalnızca .log, .json ve .xml dosyaları " +
                    "otomatik olarak hata kodu için taranır.");
                return;
            }

            AnalyzeFoundCodes(document);
        }

        private void AnalyzeFoundCodes(Document document)
        {
            ThreadHelper.ThrowIfNotOnUIThread();

            string text = GetDocumentText(document);
            IReadOnlyList<ErrorCodeOccurrence> occurrences = ErrorCodeScanner.Scan(text);
            if (occurrences.Count == 0)
            {
                // Deliberately does NOT fall back to sending the whole file: an implicit
                // upload of an entire log is exactly what must never happen silently.
                ShowInfo(
                    "Bu dosyada tanınan bir hata kodu (RC-.., ERR-.., errorCode) " +
                    "bulunamadı.\n\nAnaliz etmek istediğiniz satırları seçip tekrar deneyin.");
                return;
            }

            var dialog = new ErrorCodePickerDialog(occurrences);
            if (dialog.ShowModal() != true)
            {
                return; // user cancelled — nothing is sent
            }

            IReadOnlyList<ErrorCodeOccurrence> selected = dialog.SelectedOccurrences;
            if (selected.Count == 0)
            {
                ShowInfo("Hiçbir hata kodu seçilmedi, istek gönderilmedi.");
                return;
            }

            AnalysisRunner.Run(
                _package,
                string.Format("{0} ({1} satır)", document.Name, selected.Count),
                BuildQuestion(document.Name),
                ErrorCodeScanner.BuildPayload(selected));
        }

        private static string BuildQuestion(string documentName)
        {
            return string.Format(
                "'{0}' dosyasındaki bu log satırlarında ne olduğunu açıkla ve nasıl " +
                "çözüleceğini adım adım anlat.",
                documentName);
        }

        private static string GetSelectedText(Document document)
        {
            ThreadHelper.ThrowIfNotOnUIThread();
            return (document.Selection as TextSelection)?.Text;
        }

        private static string GetDocumentText(Document document)
        {
            ThreadHelper.ThrowIfNotOnUIThread();

            var textDocument = document.Object("TextDocument") as TextDocument;
            if (textDocument == null)
            {
                return string.Empty;
            }

            EditPoint start = textDocument.StartPoint.CreateEditPoint();
            return start.GetText(textDocument.EndPoint);
        }

        private static void ShowInfo(string message)
        {
            ThreadHelper.ThrowIfNotOnUIThread();
            VsShellUtilities.ShowMessageBox(
                ServiceProvider.GlobalProvider,
                message,
                "Payment Assistant",
                Microsoft.VisualStudio.Shell.Interop.OLEMSGICON.OLEMSGICON_INFO,
                Microsoft.VisualStudio.Shell.Interop.OLEMSGBUTTON.OLEMSGBUTTON_OK,
                Microsoft.VisualStudio.Shell.Interop.OLEMSGDEFBUTTON.OLEMSGDEFBUTTON_FIRST);
        }
    }
}
