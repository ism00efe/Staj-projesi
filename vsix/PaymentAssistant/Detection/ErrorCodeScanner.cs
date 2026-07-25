using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;

namespace PaymentAssistant.Detection
{
    /// <summary>
    /// One error code found at a specific line of a document.
    /// </summary>
    public sealed class ErrorCodeOccurrence
    {
        public ErrorCodeOccurrence(string code, int lineNumber, string lineText)
        {
            Code = code;
            LineNumber = lineNumber;
            LineText = lineText;
        }

        /// <summary>The matched code, e.g. "RC-05".</summary>
        public string Code { get; }

        /// <summary>1-based line number, matching what the editor shows.</summary>
        public int LineNumber { get; }

        /// <summary>The full line the code was found on. This is what gets transmitted.</summary>
        public string LineText { get; }

        /// <summary>Label shown next to the checkbox in the picker dialog.</summary>
        public string Display => string.Format("{0}  (satır {1})", Code, LineNumber);
    }

    /// <summary>
    /// Finds payment error codes in log/JSON/XML text.
    ///
    /// Deliberately free of any Visual Studio dependency: this is the only part of the
    /// extension with real logic rather than shell plumbing, so keeping it a plain static
    /// class means it can be unit tested without an IDE.
    /// </summary>
    public static class ErrorCodeScanner
    {
        // Document types worth scanning. Anything else falls back to "use the selection",
        // because scanning arbitrary source files produces noise, not error codes.
        private static readonly string[] ScannableExtensions = { ".log", ".json", ".xml" };

        private static readonly Regex[] Patterns =
        {
            // Response codes: RC-05, RC-51, ...
            new Regex(@"\bRC-\d{2}\b", RegexOptions.Compiled | RegexOptions.IgnoreCase),

            // Application error codes: ERR-TIMEOUT, ERR_3DS, ...
            new Regex(@"\bERR-\w+\b", RegexOptions.Compiled | RegexOptions.IgnoreCase),

            // JSON/XML fields named errorCode — capture the value rather than the field
            // name, since the value is what identifies the failure.
            new Regex(
                "\"?errorCode\"?\\s*[:=]\\s*\"?(?<value>[A-Za-z0-9_\\-]+)\"?",
                RegexOptions.Compiled | RegexOptions.IgnoreCase),
        };

        /// <summary>
        /// True when a document is one this extension knows how to scan.
        /// </summary>
        public static bool IsScannableFile(string filePath)
        {
            if (string.IsNullOrEmpty(filePath))
            {
                return false;
            }

            string extension = System.IO.Path.GetExtension(filePath);
            return ScannableExtensions.Any(
                candidate => string.Equals(candidate, extension, StringComparison.OrdinalIgnoreCase));
        }

        /// <summary>
        /// Scan text and return every error code occurrence, in document order.
        ///
        /// The same code appearing on several lines yields several occurrences: the user
        /// picks lines to send, so collapsing them would hide which context is going out.
        /// A code appearing twice on one line is reported once.
        /// </summary>
        public static IReadOnlyList<ErrorCodeOccurrence> Scan(string text)
        {
            var found = new List<ErrorCodeOccurrence>();
            if (string.IsNullOrEmpty(text))
            {
                return found;
            }

            string[] lines = text.Split(new[] { "\r\n", "\n", "\r" }, StringSplitOptions.None);
            for (int i = 0; i < lines.Length; i++)
            {
                var seenOnThisLine = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                foreach (Regex pattern in Patterns)
                {
                    foreach (Match match in pattern.Matches(lines[i]))
                    {
                        Group valueGroup = match.Groups["value"];
                        string code = valueGroup.Success ? valueGroup.Value : match.Value;
                        if (seenOnThisLine.Add(code))
                        {
                            found.Add(new ErrorCodeOccurrence(code, i + 1, lines[i]));
                        }
                    }
                }
            }

            return found;
        }

        /// <summary>
        /// Build the text to transmit from the occurrences the user ticked.
        ///
        /// Only the selected lines leave the machine — never the whole document. Lines are
        /// de-duplicated (two codes on one line must not send it twice) and emitted in
        /// document order so the log still reads chronologically on the other side.
        /// </summary>
        public static string BuildPayload(IEnumerable<ErrorCodeOccurrence> selected)
        {
            if (selected == null)
            {
                return string.Empty;
            }

            var builder = new StringBuilder();
            var emittedLines = new HashSet<int>();
            foreach (ErrorCodeOccurrence occurrence in selected.OrderBy(o => o.LineNumber))
            {
                if (emittedLines.Add(occurrence.LineNumber))
                {
                    builder.AppendLine(occurrence.LineText);
                }
            }

            return builder.ToString().TrimEnd();
        }
    }
}
