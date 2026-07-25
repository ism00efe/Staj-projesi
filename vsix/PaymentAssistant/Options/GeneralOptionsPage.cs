using System.ComponentModel;
using Microsoft.VisualStudio.Shell;

namespace PaymentAssistant.Options
{
    /// <summary>
    /// Tools &gt; Options &gt; Payment Assistant &gt; General.
    ///
    /// <see cref="DialogPage"/> persists its public properties in the user's settings
    /// store automatically, so there is no save/load code to write or get wrong.
    /// </summary>
    public sealed class GeneralOptionsPage : DialogPage
    {
        private string _apiBaseUrl = "http://127.0.0.1:7860";

        [Category("Payment Assistant")]
        [DisplayName("API base URL")]
        [Description(
            "Base address of the Payment Assistant service, e.g. http://127.0.0.1:7860. " +
            "The extension appends /api/analyze to this.")]
        public string ApiBaseUrl
        {
            get => _apiBaseUrl;
            set => _apiBaseUrl = value;
        }
    }
}
