using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Linq;
using System.Windows;
using Microsoft.VisualStudio.PlatformUI;
using PaymentAssistant.Detection;

namespace PaymentAssistant.Dialogs
{
    /// <summary>One row in the picker: an occurrence plus its checkbox state.</summary>
    public sealed class SelectableOccurrence : INotifyPropertyChanged
    {
        private bool _isSelected = true;

        public SelectableOccurrence(ErrorCodeOccurrence occurrence)
        {
            Occurrence = occurrence;
        }

        public ErrorCodeOccurrence Occurrence { get; }

        /// <summary>Trimmed line text, so a long log line does not stretch the dialog.</summary>
        public string Preview
        {
            get
            {
                string line = (Occurrence.LineText ?? string.Empty).Trim();
                return line.Length <= 160 ? line : line.Substring(0, 160) + "…";
            }
        }

        public bool IsSelected
        {
            get => _isSelected;
            set
            {
                if (_isSelected == value)
                {
                    return;
                }

                _isSelected = value;
                PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nameof(IsSelected)));
            }
        }

        public event PropertyChangedEventHandler PropertyChanged;
    }

    /// <summary>
    /// Lets the user choose which detected error-code lines are transmitted.
    ///
    /// This dialog is the consent step for the no-selection path: without it, invoking
    /// the command on a log file would ship the whole document to a server. Cancelling
    /// sends nothing.
    /// </summary>
    public partial class ErrorCodePickerDialog : DialogWindow
    {
        private readonly ObservableCollection<SelectableOccurrence> _rows;

        public ErrorCodePickerDialog(IReadOnlyList<ErrorCodeOccurrence> occurrences)
        {
            if (occurrences == null)
            {
                throw new ArgumentNullException(nameof(occurrences));
            }

            InitializeComponent();

            _rows = new ObservableCollection<SelectableOccurrence>(
                occurrences.Select(o => new SelectableOccurrence(o)));
            OccurrenceList.ItemsSource = _rows;
        }

        /// <summary>The occurrences still ticked when the user pressed Gönder.</summary>
        public IReadOnlyList<ErrorCodeOccurrence> SelectedOccurrences { get; private set; } =
            new List<ErrorCodeOccurrence>();

        private void OnSelectAll(object sender, RoutedEventArgs e) => SetAll(true);

        private void OnSelectNone(object sender, RoutedEventArgs e) => SetAll(false);

        private void SetAll(bool selected)
        {
            foreach (SelectableOccurrence row in _rows)
            {
                row.IsSelected = selected;
            }
        }

        private void OnSend(object sender, RoutedEventArgs e)
        {
            SelectedOccurrences = _rows
                .Where(r => r.IsSelected)
                .Select(r => r.Occurrence)
                .ToList();
            DialogResult = true;
            Close();
        }

        private void OnCancel(object sender, RoutedEventArgs e)
        {
            DialogResult = false;
            Close();
        }
    }
}
