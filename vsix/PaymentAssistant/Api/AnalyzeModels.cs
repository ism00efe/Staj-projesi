using System.Collections.Generic;
using System.Runtime.Serialization;

namespace PaymentAssistant.Api
{
    /// <summary>
    /// Request body for POST /api/analyze.
    ///
    /// Only text is ever sent. There is deliberately no file-path member: the API rejects
    /// unknown fields outright, and more importantly a path would be meaningless to a
    /// server that may not share this machine's filesystem.
    /// </summary>
    [DataContract]
    public sealed class AnalyzeRequest
    {
        [DataMember(Name = "query", EmitDefaultValue = true)]
        public string Query { get; set; }

        [DataMember(Name = "file_content", EmitDefaultValue = true)]
        public string FileContent { get; set; }
    }

    [DataContract]
    public sealed class SourceItem
    {
        [DataMember(Name = "tag")]
        public string Tag { get; set; }

        [DataMember(Name = "title")]
        public string Title { get; set; }

        [DataMember(Name = "doc_type")]
        public string DocType { get; set; }

        [DataMember(Name = "source_path")]
        public string SourcePath { get; set; }

        [DataMember(Name = "score")]
        public double Score { get; set; }

        [DataMember(Name = "document_id")]
        public string DocumentId { get; set; }

        [DataMember(Name = "cited")]
        public bool Cited { get; set; }

        [DataMember(Name = "excerpt")]
        public string Excerpt { get; set; }

        public string Display =>
            string.Format("[{0}] {1}  ({2}, benzerlik {3:0.00})", Tag, Title, DocType, Score);
    }

    [DataContract]
    public sealed class RedactionItem
    {
        [DataMember(Name = "label")]
        public string Label { get; set; }

        [DataMember(Name = "count")]
        public int Count { get; set; }
    }

    [DataContract]
    public sealed class SecuritySummary
    {
        [DataMember(Name = "blocked")]
        public bool Blocked { get; set; }

        [DataMember(Name = "redactions")]
        public List<RedactionItem> Redactions { get; set; }

        [DataMember(Name = "redaction_total")]
        public int RedactionTotal { get; set; }
    }

    [DataContract]
    public sealed class AnalyzeResponse
    {
        [DataMember(Name = "answer")]
        public string Answer { get; set; }

        [DataMember(Name = "sources")]
        public List<SourceItem> Sources { get; set; }

        [DataMember(Name = "security_summary")]
        public SecuritySummary SecuritySummary { get; set; }

        [DataMember(Name = "trace_id")]
        public string TraceId { get; set; }
    }

    [DataContract]
    public sealed class ErrorBody
    {
        [DataMember(Name = "code")]
        public string Code { get; set; }

        [DataMember(Name = "message")]
        public string Message { get; set; }
    }

    /// <summary>Error envelope; every non-2xx response from the API uses this shape.</summary>
    [DataContract]
    public sealed class ErrorResponse
    {
        [DataMember(Name = "error")]
        public ErrorBody Error { get; set; }

        [DataMember(Name = "trace_id")]
        public string TraceId { get; set; }
    }
}
