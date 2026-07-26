using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Windows;
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
            DurationText.Visibility = Visibility.Collapsed;
            SourceDetailPanel.Visibility = Visibility.Collapsed;
        }

        /// <summary>Show a failure. The message is already user-facing and in Turkish.</summary>
        public void ShowError(string message, string traceId, TimeSpan? elapsed = null)
        {
            StatusText.Text = "Analiz başarısız.";
            AnswerText.Text = message;
            SourcesList.ItemsSource = null;
            SecurityText.Text = "—";
            SourceDetailPanel.Visibility = Visibility.Collapsed;
            // Shown on failure too: a timeout is the most common slow-path complaint, and
            // "it failed after 180 s" is a very different report from "it failed at once".
            ShowDuration(elapsed);
            TraceText.Text = string.IsNullOrEmpty(traceId)
                ? string.Empty
                : string.Format("İzleme kimliği: {0}", traceId);
        }

        /// <summary>Show a completed analysis.</summary>
        public void ShowResult(AnalyzeResponse response, TimeSpan? elapsed = null)
        {
            StatusText.Text = "Analiz tamamlandı.";
            AnswerText.Text = response.Answer ?? string.Empty;
            ShowDuration(elapsed);
            SourceDetailPanel.Visibility = Visibility.Collapsed;

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

        /// <summary>
        /// Report how long the round trip took.
        ///
        /// Measured client-side, so it covers the whole call as the user experiences it —
        /// network plus retrieval, re-ranking and generation — not just server time.
        /// </summary>
        private void ShowDuration(TimeSpan? elapsed)
        {
            if (elapsed == null)
            {
                DurationText.Visibility = Visibility.Collapsed;
                return;
            }

            DurationText.Text = string.Format(
                CultureInfo.CurrentCulture, "Yanıt süresi: {0:0.0} sn", elapsed.Value.TotalSeconds);
            DurationText.Visibility = Visibility.Visible;
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
        /// Show the selected source's metadata and excerpt.
        ///
        /// `source_path` identifies a document inside the server's knowledge base, not a
        /// file on this machine — for the synthetic corpus nothing at that path exists
        /// locally, and even against a real corpus the server may be on another host. So
        /// selecting a source shows what we already have (title, type, relevance, and the
        /// excerpt the API returned) instead of attempting an open that is expected to
        /// fail. Opening is offered only in the case where it can actually work: the path
        /// resolves to a real local file, via double-click.
        /// </summary>
        private void OnSourceSelectionChanged(object sender, SelectionChangedEventArgs e)
        {
            if (!(SourcesList.SelectedItem is SourceItem source))
            {
                SourceDetailPanel.Visibility = Visibility.Collapsed;
                return;
            }

            SourceDetailTitle.Text = string.Format("[{0}] {1}", source.Tag, source.Title);
            SourceDetailMeta.Text = string.Format(
                CultureInfo.CurrentCulture,
                "Tür: {0}  ·  Benzerlik: {1:0.00}  ·  Kaynak: {2}",
                source.DocType, source.Score, source.SourcePath);

            SourceDetailExcerpt.Text = string.IsNullOrWhiteSpace(source.Excerpt)
                ? "(Bu kaynak için önizleme metni yok.)"
                : source.Excerpt;

            SourceDetailHint.Text = CanOpenLocally(source)
                ? "Dosyayı düzenleyicide açmak için çift tıklayın."
                : "Bu belge bilgi tabanında saklanıyor; bu makinede bir dosyası yok. "
                  + "Yukarıdaki alıntı, yanıtın dayandığı bölümdür.";

            SourceDetailPanel.Visibility = Visibility.Visible;
        }

        /// <summary>
        /// Open the source in the editor — only when it is genuinely a local file.
        /// </summary>
        private void OnSourceDoubleClick(object sender, MouseButtonEventArgs e)
        {
            ThreadHelper.ThrowIfNotOnUIThread();

            if (!(SourcesList.SelectedItem is SourceItem source) || !CanOpenLocally(source))
            {
                // Not an error: the detail panel already explains why there is no file.
                return;
            }

            try
            {
                var dte = (DTE2)Package.GetGlobalService(typeof(DTE));
                dte?.ItemOperations.OpenFile(source.SourcePath);
            }
            catch (Exception ex)
            {
                StatusText.Text = string.Format("Dosya açılamadı: {0}", ex.Message);
            }
        }

        /// <summary>True only for an absolute path that exists on this machine.</summary>
        private static bool CanOpenLocally(SourceItem source)
        {
            if (string.IsNullOrWhiteSpace(source?.SourcePath))
            {
                return false;
            }

            try
            {
                // Corpus paths are bare names like "runbook_rc51.md". Resolving a relative
                // path here would silently probe the IDE's working directory, which is
                // both meaningless and a small information-disclosure footgun.
                return Path.IsPathRooted(source.SourcePath) && File.Exists(source.SourcePath);
            }
            catch (ArgumentException)
            {
                return false;  // characters that are illegal in a path
            }
        }
    }
}
