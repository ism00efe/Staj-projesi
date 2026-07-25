using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Windows.Controls;
using System.Windows.Input;
using EnvDTE;
using EnvDTE80;
using Microsoft.VisualStudio.Shell;
using PaymentAssistant.Api;

namespace PaymentAssistant.ToolWindows
{
    /// <summary>
    /// Renders one analysis result. Pure presentation — it never calls the API itself.
    /// </summary>
    public partial class ResultToolWindowControl : UserControl
    {
        public ResultToolWindowControl()
        {
            InitializeComponent();
        }

        /// <summary>Show that a request is in flight.</summary>
        public void ShowBusy(string what)
        {
            StatusText.Text = string.Format("Analiz ediliyor: {0}", what);
            AnswerText.Text = string.Empty;
            SourcesList.ItemsSource = null;
            SecurityText.Text = "—";
            TraceText.Text = string.Empty;
        }

        /// <summary>Show a failure. The message is already user-facing and in Turkish.</summary>
        public void ShowError(string message, string traceId)
        {
            StatusText.Text = "Analiz başarısız.";
            AnswerText.Text = message;
            SourcesList.ItemsSource = null;
            SecurityText.Text = "—";
            TraceText.Text = string.IsNullOrEmpty(traceId)
                ? string.Empty
                : string.Format("İzleme kimliği: {0}", traceId);
        }

        /// <summary>Show a completed analysis.</summary>
        public void ShowResult(AnalyzeResponse response)
        {
            StatusText.Text = "Analiz tamamlandı.";
            AnswerText.Text = response.Answer ?? string.Empty;

            List<SourceItem> sources = response.Sources ?? new List<SourceItem>();
            SourcesList.ItemsSource = sources;

            // Mirrors the web UI: an answer that cited nothing still shows what was read,
            // but says so plainly rather than implying the sources were used.
            SourcesHeader.Text = sources.Any(s => s.Cited)
                ? "Kullanılan Kaynaklar"
                : "Getirilen Kaynaklar (yanıtta atıf yapılmadı)";

            SecurityText.Text = DescribeSecurity(response.SecuritySummary);
            TraceText.Text = string.Format("İzleme kimliği: {0}", response.TraceId);
        }

        private static string DescribeSecurity(SecuritySummary summary)
        {
            if (summary == null)
            {
                return "—";
            }

            var parts = new List<string>();
            if (summary.Blocked)
            {
                parts.Add("Bu istek güvenlik filtresi tarafından reddedildi.");
            }

            if (summary.Redactions != null && summary.Redactions.Count > 0)
            {
                string masked = string.Join(
                    ", ", summary.Redactions.Select(r => string.Format("{0} ×{1}", r.Label, r.Count)));
                parts.Add(string.Format(
                    "Gönderilmeden önce maskelenen hassas veriler ({0}): {1}",
                    summary.RedactionTotal, masked));
            }

            return parts.Count > 0
                ? string.Join(Environment.NewLine, parts)
                : "Maskelenecek hassas veri bulunmadı.";
        }

        /// <summary>
        /// Open the clicked source in the editor, when the path resolves to a real file.
        ///
        /// Source paths come from the server's knowledge base and often do not exist on
        /// this machine, so a miss is expected and reported in the status line rather than
        /// raised as an error.
        /// </summary>
        private void OnSourceDoubleClick(object sender, MouseButtonEventArgs e)
        {
            ThreadHelper.ThrowIfNotOnUIThread();

            if (!(SourcesList.SelectedItem is SourceItem source)
                || string.IsNullOrWhiteSpace(source.SourcePath))
            {
                return;
            }

            try
            {
                if (!File.Exists(source.SourcePath))
                {
                    StatusText.Text = string.Format(
                        "Kaynak dosya bu makinede bulunamadı: {0}", source.SourcePath);
                    return;
                }

                var dte = (DTE2)Package.GetGlobalService(typeof(DTE));
                dte?.ItemOperations.OpenFile(source.SourcePath);
            }
            catch (Exception ex)
            {
                StatusText.Text = string.Format("Dosya açılamadı: {0}", ex.Message);
            }
        }
    }
}
