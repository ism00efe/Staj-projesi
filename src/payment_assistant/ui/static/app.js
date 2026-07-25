/* Ödeme Sistemleri Asistanı — vanilla JS client for POST /api/analyze.
   No framework, no build step. The page holds no state beyond the last response. */

(function () {
  "use strict";

  var form = document.getElementById("query-form");
  var questionEl = document.getElementById("question");
  var fileEl = document.getElementById("logfile");
  var fileStatusEl = document.getElementById("file-status");
  var submitBtn = document.getElementById("submit");
  var clearBtn = document.getElementById("clear");
  var placeholderEl = document.getElementById("placeholder");
  var kbStatusEl = document.getElementById("kb-status");
  var loadingEl = document.getElementById("loading");
  var resultsEl = document.getElementById("results");
  var answerEl = document.getElementById("answer");
  var sourcesEl = document.getElementById("sources");
  var sourcesCardEl = document.getElementById("sources-card");
  var sourcesTitleEl = document.getElementById("sources-title");
  var sourcesCountEl = document.getElementById("sources-count");
  var securityCardEl = document.getElementById("security-card");
  var securityEl = document.getElementById("security");
  var traceIdEl = document.getElementById("trace-id");

  // Server-supplied so the client checks against the limit this process actually
  // enforces rather than a copy that drifts from config.py. Null until /api/health
  // answers; the server re-checks regardless, so a missed client-side check is only a
  // worse error message, never a bypass.
  var maxUploadBytes = null;

  /* ------------------------------------------------------------- escaping */

  var ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

  // The answer is model output and titles/paths/excerpts are corpus content. Both are
  // untrusted for rendering purposes, so everything is escaped before it reaches
  // innerHTML — and escaping always happens BEFORE any markup we add ourselves.
  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
      return ESCAPES[ch];
    });
  }

  function linkifyCitations(text) {
    return esc(text).replace(/\[S(\d+)\]/g, function (_match, num) {
      return '<a class="cite" href="#src-S' + num + '" data-tag="S' + num + '">[S' + num + "]</a>";
    });
  }

  /* --------------------------------------------------------------- helpers */

  function show(el) { el.hidden = false; }
  function hide(el) { el.hidden = true; }

  function setBusy(busy) {
    submitBtn.disabled = busy;
    submitBtn.textContent = busy ? "Sorgulanıyor…" : "Sorgula";
    resultsEl.setAttribute("aria-busy", busy ? "true" : "false");
    if (busy) {
      hide(placeholderEl);
      hide(resultsEl);
      show(loadingEl);
    } else {
      hide(loadingEl);
    }
  }

  function showError(message) {
    answerEl.innerHTML = '<div class="notice notice--error">' + esc(message) + "</div>";
    hide(sourcesCardEl);
    hide(securityCardEl);
    traceIdEl.textContent = "—";
    show(resultsEl);
  }

  function readFileAsText(file) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () { resolve(reader.result); };
      reader.onerror = function () { reject(new Error("Dosya okunamadı.")); };
      reader.readAsText(file, "utf-8");
    });
  }

  /* -------------------------------------------------------------- rendering */

  function renderSources(sources) {
    if (!sources.length) {
      hide(sourcesCardEl);
      return;
    }
    show(sourcesCardEl);

    // Preserves the distinction the previous interface drew: an answer that cites
    // nothing still shows what was read, so the retrieval can be judged.
    var anyCited = sources.some(function (s) { return s.cited; });
    sourcesTitleEl.textContent = anyCited
      ? "Kullanılan Kaynaklar"
      : "Getirilen Kaynaklar (yanıtta atıf yapılmadı)";
    sourcesCountEl.textContent = sources.length + " kaynak";

    sourcesEl.innerHTML = sources.map(function (s) {
      var excerpt = s.excerpt
        ? '<p class="source__excerpt">' + esc(s.excerpt) + "</p>"
        : "";
      return (
        '<div class="source" id="src-' + esc(s.tag) + '">' +
          '<div class="source__head">' +
            '<span class="source__tag">[' + esc(s.tag) + "]</span>" +
            '<span class="source__title">' + esc(s.title) + "</span>" +
            '<span class="badge badge--' + esc(s.doc_type) + '">' + esc(s.doc_type) + "</span>" +
          "</div>" +
          '<p class="source__meta">' + esc(s.source_path) +
            " · Benzerlik: " + esc(Number(s.score).toFixed(2)) + "</p>" +
          excerpt +
        "</div>"
      );
    }).join("");
  }

  function renderSecurity(summary) {
    var parts = [];
    if (summary.blocked) {
      parts.push(
        '<div class="notice notice--warn">Bu istek güvenlik filtresi tarafından ' +
        "reddedildi. Lütfen sorunuzu farklı bir şekilde ifade edin.</div>"
      );
    }
    if (summary.redactions.length) {
      parts.push(
        '<p class="masked">Gönderilmeden önce maskelenen hassas veriler ' +
        "(toplam " + esc(summary.redaction_total) + "):<br>" +
        summary.redactions.map(function (r) {
          return '<span class="masked__item">' + esc(r.label) + " ×" + esc(r.count) + "</span>";
        }).join("") +
        "</p>"
      );
    }
    if (!parts.length) {
      hide(securityCardEl);
      return;
    }
    securityEl.innerHTML = parts.join("");
    show(securityCardEl);
  }

  function renderResult(data) {
    answerEl.innerHTML = linkifyCitations(data.answer || "(Boş yanıt)");
    renderSources(data.sources || []);
    renderSecurity(data.security_summary || { blocked: false, redactions: [], redaction_total: 0 });
    traceIdEl.textContent = data.trace_id || "—";
    show(resultsEl);
  }

  /* ------------------------------------------------------------ error copy */

  function messageForStatus(status, body, retryAfter) {
    if (status === 413) {
      return (body && body.error && body.error.message) || "Gönderilen içerik çok büyük.";
    }
    if (status === 429) {
      return retryAfter
        ? "Çok fazla istek gönderdiniz. " + retryAfter + " saniye sonra tekrar deneyin."
        : "Çok fazla istek gönderdiniz. Lütfen biraz sonra tekrar deneyin.";
    }
    if (status === 422) {
      return "İstek geçersiz. Lütfen girdilerinizi kontrol edip tekrar deneyin.";
    }
    if (body && body.error && body.error.message) {
      return body.error.message;
    }
    return "Beklenmeyen bir hata oluştu.";
  }

  /* -------------------------------------------------------------- submitting */

  async function submitQuery() {
    var question = questionEl.value.trim();
    var file = fileEl.files && fileEl.files[0];

    if (!question && !file) {
      showError("Lütfen bir soru yazın veya bir log dosyası seçin.");
      return;
    }

    var fileContent = null;
    if (file) {
      if (maxUploadBytes !== null && file.size > maxUploadBytes) {
        showError(
          "Seçilen dosya çok büyük (limit: " +
          Math.floor(maxUploadBytes / 1000000) + " MB)."
        );
        return;
      }
      try {
        fileContent = await readFileAsText(file);
      } catch (err) {
        showError("Dosya okunamadı. Lütfen başka bir dosya deneyin.");
        return;
      }
    }

    setBusy(true);
    try {
      // POST, never GET with a query string: a query string would be written to access
      // logs, proxy logs, and browser history.
      var response = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: question || null, file_content: fileContent })
      });

      var body = null;
      try { body = await response.json(); } catch (err) { body = null; }

      if (!response.ok) {
        showError(messageForStatus(response.status, body, response.headers.get("Retry-After")));
        return;
      }
      renderResult(body);
    } catch (err) {
      showError("Sunucuya ulaşılamadı. Bağlantınızı kontrol edip tekrar deneyin.");
    } finally {
      setBusy(false);
    }
  }

  /* ------------------------------------------------------------------ wiring */

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    submitQuery();
  });

  // Selecting a file never submits on its own — the user always triggers the request.
  fileEl.addEventListener("change", function () {
    var file = fileEl.files && fileEl.files[0];
    if (!file) {
      fileStatusEl.textContent = "Dosya seçilmedi.";
      fileStatusEl.className = "file__status";
      return;
    }
    if (maxUploadBytes !== null && file.size > maxUploadBytes) {
      fileStatusEl.textContent =
        "✕ " + file.name + " — çok büyük (limit: " +
        Math.floor(maxUploadBytes / 1000000) + " MB)";
      fileStatusEl.className = "file__status file__status--error";
      return;
    }
    fileStatusEl.textContent = "✓ " + file.name + " seçildi";
    fileStatusEl.className = "file__status file__status--set";
  });

  clearBtn.addEventListener("click", function () {
    form.reset();
    fileStatusEl.textContent = "Dosya seçilmedi.";
    fileStatusEl.className = "file__status";
    hide(resultsEl);
    hide(loadingEl);
    show(placeholderEl);
    questionEl.focus();
  });

  Array.prototype.forEach.call(document.querySelectorAll(".chip"), function (chip) {
    chip.addEventListener("click", function () {
      questionEl.value = chip.textContent.trim();
      questionEl.focus();
    });
  });

  // Clicking a [S#] link opens the source list and highlights the row it points at.
  answerEl.addEventListener("click", function (event) {
    var link = event.target.closest ? event.target.closest("a.cite") : null;
    if (!link) { return; }
    event.preventDefault();
    var target = document.getElementById("src-" + link.dataset.tag);
    if (!target) { return; }
    var details = sourcesCardEl.querySelector("details");
    if (details) { details.open = true; }
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    target.classList.remove("source--flash");
    void target.offsetWidth; // restart the animation if the same row is clicked twice
    target.classList.add("source--flash");
  });

  // Best-effort: the page stays fully usable if this fails.
  fetch("/api/health")
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (health) {
      if (!health) { return; }
      maxUploadBytes = health.max_upload_bytes;
      kbStatusEl.textContent = health.knowledge_base_size + " kaynak parçası indekslendi.";
    })
    .catch(function () { /* offline health check is not worth surfacing */ });
})();
