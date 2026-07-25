using System;
using System.Threading.Tasks;
using Microsoft.VisualStudio.Shell;
using Microsoft.VisualStudio.Shell.Interop;
// Supplies the awaiter for `await TaskScheduler.Default`, the JoinableTaskFactory idiom
// for hopping off the UI thread.
using Microsoft.VisualStudio.Threading;
using PaymentAssistant.Api;
using PaymentAssistant.Options;
using PaymentAssistant.ToolWindows;
using Task = System.Threading.Tasks.Task;

namespace PaymentAssistant.Commands
{
    /// <summary>
    /// Shared execution path for both commands: show the tool window, call the API off
    /// the UI thread, render the outcome.
    ///
    /// Both commands funnel through here so the threading and error handling exist once.
    /// </summary>
    internal static class AnalysisRunner
    {
        /// <summary>
        /// Start an analysis. Returns immediately; the tool window updates when it finishes.
        /// </summary>
        /// <param name="what">Short description of what is being analyzed, for the status line.</param>
        public static void Run(AsyncPackage package, string what, string query, string fileContent)
        {
            package.JoinableTaskFactory
                .RunAsync(() => RunAsync(package, what, query, fileContent))
                .FileAndForget("paymentassistant/analyze");
        }

        private static async Task RunAsync(
            AsyncPackage package, string what, string query, string fileContent)
        {
            await package.JoinableTaskFactory.SwitchToMainThreadAsync(package.DisposalToken);

            ResultToolWindowControl control = await ShowToolWindowAsync(package);
            if (control == null)
            {
                return;
            }

            control.ShowBusy(what);

            // Reading options touches the shell, so it happens while still on the UI thread.
            var options = (GeneralOptionsPage)package.GetDialogPage(typeof(GeneralOptionsPage));
            string baseUrl = options.ApiBaseUrl;

            try
            {
                var client = new PaymentAssistantClient(baseUrl);

                // Leave the UI thread for the network call. The service can take tens of
                // seconds (retrieval, re-ranking, then the LLM); awaiting that on the UI
                // thread would freeze the IDE.
                await TaskScheduler.Default;
                AnalyzeResponse response = await client
                    .AnalyzeAsync(query, fileContent, package.DisposalToken)
                    .ConfigureAwait(false);

                await package.JoinableTaskFactory.SwitchToMainThreadAsync(package.DisposalToken);
                control.ShowResult(response);
            }
            catch (OperationCanceledException)
            {
                // The IDE is shutting down; there is nothing left to show it in.
            }
            catch (PaymentAssistantApiException ex)
            {
                await package.JoinableTaskFactory.SwitchToMainThreadAsync(package.DisposalToken);
                control.ShowError(ex.Message, ex.TraceId);
            }
            catch (Exception ex)
            {
                await package.JoinableTaskFactory.SwitchToMainThreadAsync(package.DisposalToken);
                control.ShowError(
                    string.Format(
                        "Servise ulaşılamadı ({0}). Adres: {1}{2}{2}Tools > Options > " +
                        "Payment Assistant altından API adresini kontrol edin ve servisin " +
                        "çalıştığından emin olun.",
                        ex.Message, baseUrl, Environment.NewLine),
                    null);
            }
        }

        private static async Task<ResultToolWindowControl> ShowToolWindowAsync(AsyncPackage package)
        {
            ToolWindowPane window = await package.ShowToolWindowAsync(
                typeof(ResultToolWindow), id: 0, create: true, cancellationToken: package.DisposalToken);

            if (window?.Frame == null)
            {
                throw new InvalidOperationException(
                    "Payment Assistant sonuç penceresi oluşturulamadı.");
            }

            await package.JoinableTaskFactory.SwitchToMainThreadAsync(package.DisposalToken);
            ((IVsWindowFrame)window.Frame).Show();
            return window.Content as ResultToolWindowControl;
        }
    }
}
