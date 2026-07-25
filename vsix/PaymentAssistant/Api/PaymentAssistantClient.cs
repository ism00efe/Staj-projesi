using System;
using System.IO;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Runtime.Serialization.Json;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace PaymentAssistant.Api
{
    /// <summary>Raised when the API answers with a non-success status.</summary>
    public sealed class PaymentAssistantApiException : Exception
    {
        public PaymentAssistantApiException(string message, string traceId)
            : base(message)
        {
            TraceId = traceId;
        }

        /// <summary>The server-side trace id, when the response carried one.</summary>
        public string TraceId { get; }
    }

    /// <summary>
    /// Thin async client for POST /api/analyze.
    ///
    /// JSON is handled with the in-box <see cref="DataContractJsonSerializer"/> rather than
    /// Json.NET on purpose: Visual Studio loads its own Json.NET into the same process, and
    /// an extension carrying a different version is a classic source of assembly-binding
    /// failures that only appear at runtime, in someone else's IDE. The DTOs here are
    /// simple enough that the framework serializer costs nothing.
    /// </summary>
    public sealed class PaymentAssistantClient
    {
        // One HttpClient for the lifetime of the process. Creating one per request
        // exhausts sockets under repeated use (each disposed client leaves its connection
        // in TIME_WAIT), which is the standard HttpClient pitfall.
        private static readonly HttpClient Http = CreateHttpClient();

        private readonly string _baseUrl;

        public PaymentAssistantClient(string baseUrl)
        {
            if (string.IsNullOrWhiteSpace(baseUrl))
            {
                throw new ArgumentException(
                    "API adresi boş olamaz. Tools > Options > Payment Assistant altından ayarlayın.",
                    nameof(baseUrl));
            }

            _baseUrl = baseUrl.TrimEnd('/');
        }

        private static HttpClient CreateHttpClient()
        {
            var client = new HttpClient
            {
                // Generous: a cold server loads an embedding model and a cross-encoder
                // re-ranker before it can answer the first request.
                Timeout = TimeSpan.FromMinutes(3),
            };
            client.DefaultRequestHeaders.Accept.Add(
                new MediaTypeWithQualityHeaderValue("application/json"));
            return client;
        }

        /// <summary>
        /// Send a question and/or log text for analysis.
        /// </summary>
        public async Task<AnalyzeResponse> AnalyzeAsync(
            string query, string fileContent, CancellationToken cancellationToken)
        {
            var request = new AnalyzeRequest { Query = query, FileContent = fileContent };
            using (var content = new StringContent(
                Serialize(request), Encoding.UTF8, "application/json"))
            using (HttpResponseMessage response = await Http
                .PostAsync(_baseUrl + "/api/analyze", content, cancellationToken)
                .ConfigureAwait(false))
            {
                string body = await response.Content.ReadAsStringAsync().ConfigureAwait(false);
                if (!response.IsSuccessStatusCode)
                {
                    throw BuildApiException(response, body);
                }

                return Deserialize<AnalyzeResponse>(body);
            }
        }

        private static PaymentAssistantApiException BuildApiException(
            HttpResponseMessage response, string body)
        {
            // The server sends a Turkish, user-facing message in a known envelope. Prefer
            // it over anything invented here — it already states the actual limit or cause.
            try
            {
                ErrorResponse error = Deserialize<ErrorResponse>(body);
                if (!string.IsNullOrEmpty(error?.Error?.Message))
                {
                    return new PaymentAssistantApiException(error.Error.Message, error.TraceId);
                }
            }
            catch (Exception)
            {
                // Not our envelope — fall through to a status-based message rather than
                // surfacing a parse error the user cannot act on.
            }

            return new PaymentAssistantApiException(
                string.Format(
                    "Sunucu isteği reddetti (HTTP {0}). API adresini kontrol edin.",
                    (int)response.StatusCode),
                null);
        }

        private static string Serialize<T>(T value)
        {
            var serializer = new DataContractJsonSerializer(typeof(T));
            using (var stream = new MemoryStream())
            {
                serializer.WriteObject(stream, value);
                return Encoding.UTF8.GetString(stream.ToArray());
            }
        }

        private static T Deserialize<T>(string json)
        {
            var serializer = new DataContractJsonSerializer(typeof(T));
            using (var stream = new MemoryStream(Encoding.UTF8.GetBytes(json)))
            {
                return (T)serializer.ReadObject(stream);
            }
        }
    }
}
