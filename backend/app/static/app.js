const rootPath = document.body.dataset.rootPath || "";
const apiBase = new URL(`${rootPath.replace(/\/$/, "")}/`, window.location.origin);
const STORAGE_KEY = "archiveDeckJobs";

const state = {
  jobs: loadJobs(),
  activeScope: "all",
  searchResults: null,
};

const elements = {
  uploadForm: document.getElementById("upload-form"),
  fileInput: document.getElementById("pdf-file"),
  uploadButton: document.getElementById("upload-button"),
  uploadHelper: document.getElementById("upload-helper"),
  dropzone: document.getElementById("dropzone"),
  jobsList: document.getElementById("jobs-list"),
  jobsEmpty: document.getElementById("jobs-empty"),
  searchForm: document.getElementById("search-form"),
  queryInput: document.getElementById("query-input"),
  topKSelect: document.getElementById("top-k-select"),
  scopeSelect: document.getElementById("scope-select"),
  searchButton: document.getElementById("search-button"),
  resultsEmpty: document.getElementById("results-empty"),
  resultsColumns: document.getElementById("results-columns"),
  textResults: document.getElementById("text-results"),
  captionResults: document.getElementById("caption-results"),
  signalDot: document.getElementById("signal-dot"),
  signalLabel: document.getElementById("signal-label"),
};

function loadJobs() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
  } catch {
    return [];
  }
}

function saveJobs() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state.jobs));
}

function apiUrl(path) {
  return new URL(path, apiBase).toString();
}

function setSignal(mode, label) {
  elements.signalDot.classList.remove("live", "error");
  if (mode === "live") {
    elements.signalDot.classList.add("live");
  }
  if (mode === "error") {
    elements.signalDot.classList.add("error");
  }
  elements.signalLabel.textContent = label;
}

function statusClass(status) {
  return ["pending", "running", "completed", "failed"].includes(status) ? status : "pending";
}

function jobStageFlags(status) {
  if (status === "completed") {
    return ["done", "done", "done"];
  }
  if (status === "running") {
    return ["done", "active", ""];
  }
  if (status === "failed") {
    return ["done", "active", ""];
  }
  return ["active", "", ""];
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function upsertJob(nextJob) {
  const index = state.jobs.findIndex((job) => job.job_id === nextJob.job_id);
  if (index === -1) {
    state.jobs.unshift(nextJob);
  } else {
    state.jobs[index] = { ...state.jobs[index], ...nextJob };
  }
  saveJobs();
}

function refreshScopeOptions() {
  const previous = elements.scopeSelect.value || "all";
  const filenames = [...new Set(state.jobs.map((job) => job.filename).filter(Boolean))];
  elements.scopeSelect.innerHTML = '<option value="all">All indexed documents</option>';
  for (const filename of filenames) {
    const option = document.createElement("option");
    option.value = filename;
    option.textContent = filename;
    elements.scopeSelect.appendChild(option);
  }
  elements.scopeSelect.value = filenames.includes(previous) || previous === "all" ? previous : "all";
}

function renderJobs() {
  const jobs = [...state.jobs];
  elements.jobsEmpty.hidden = jobs.length > 0;
  elements.jobsList.innerHTML = "";

  for (const job of jobs) {
    const status = statusClass(job.status || "pending");
    const [queued, processing, indexed] = jobStageFlags(status);
    const stats = job.stats || job.payload?.stats || {};
    const createdAt = job.created_at || job.createdAt || null;
    const metaLine = createdAt ? new Date(createdAt).toLocaleString() : "Waiting for first status refresh";

    const card = document.createElement("article");
    card.className = "job-card";
    card.innerHTML = `
      <div class="job-topline">
        <div>
          <p class="job-title">Document job</p>
          <p class="job-filename">${escapeHtml(job.filename || "unknown.pdf")}</p>
        </div>
        <span class="status-pill ${status}">${escapeHtml(status)}</span>
      </div>
      <p class="job-meta">job ${escapeHtml(job.job_id || job.id || "")} · ${escapeHtml(metaLine)}</p>
      <div class="job-progress">
        <div class="progress-step ${queued}">Queued in backend</div>
        <div class="progress-step ${processing}">Worker processing</div>
        <div class="progress-step ${indexed}">Indexed and queryable</div>
      </div>
      <div class="job-actions">
        <button class="mini-button" type="button" data-scope="${escapeHtml(job.filename || "")}">Focus search on this PDF</button>
      </div>
      <div class="job-stats">
        <div>
          <span class="stat-label">Pages</span>
          <span class="stat-value">${escapeHtml(stats.pages ?? "—")}</span>
        </div>
        <div>
          <span class="stat-label">Chunks indexed</span>
          <span class="stat-value">${escapeHtml(stats.chunks_indexed ?? "—")}</span>
        </div>
        <div>
          <span class="stat-label">Captions indexed</span>
          <span class="stat-value">${escapeHtml(stats.captions_indexed ?? "—")}</span>
        </div>
      </div>
      ${job.error_message ? `<p class="helper">Failure: ${escapeHtml(job.error_message)}</p>` : ""}
    `;

    card.querySelector("button")?.addEventListener("click", () => {
      elements.scopeSelect.value = job.filename || "all";
    });

    elements.jobsList.appendChild(card);
  }

  refreshScopeOptions();

  const hasError = jobs.some((job) => job.status === "failed");
  const isWorking = jobs.some((job) => job.status === "pending" || job.status === "running");
  if (hasError) {
    setSignal("error", "One or more jobs failed");
  } else if (isWorking) {
    setSignal("live", "Pipeline active");
  } else if (jobs.length > 0) {
    setSignal("live", "Indexes ready");
  } else {
    setSignal("idle", "Backend idle");
  }
}

function resultMetaChips(item) {
  const metadata = item.metadata || {};
  const chips = [];
  if (metadata.source_pdf) {
    chips.push(metadata.source_pdf);
  }
  if (metadata.filename && metadata.filename !== metadata.source_pdf) {
    chips.push(metadata.filename);
  }
  if (metadata.pages?.length) {
    chips.push(`pages ${metadata.pages.join(", ")}`);
  }
  if (metadata.page_number) {
    chips.push(`page ${metadata.page_number}`);
  }
  return chips
    .map((chip) => `<span class="metadata-chip">${escapeHtml(chip)}</span>`)
    .join("");
}

function filterByScope(items) {
  const scope = elements.scopeSelect.value;
  if (scope === "all") {
    return items;
  }
  return items.filter((item) => {
    const metadata = item.metadata || {};
    return metadata.source_pdf === scope || metadata.filename === scope;
  });
}

function renderResults() {
  if (!state.searchResults) {
    elements.resultsEmpty.hidden = false;
    elements.resultsColumns.hidden = true;
    elements.textResults.innerHTML = "";
    elements.captionResults.innerHTML = "";
    return;
  }

  const textChunks = filterByScope(state.searchResults.text_chunks || []);
  const captions = filterByScope(state.searchResults.captions || []);

  elements.resultsEmpty.hidden = false;
  if (textChunks.length === 0 && captions.length === 0) {
    elements.resultsEmpty.textContent = "No results matched the current scope. Try widening the scope or changing the query.";
    elements.resultsColumns.hidden = true;
    return;
  }

  elements.resultsEmpty.hidden = true;
  elements.resultsColumns.hidden = false;

  const renderStack = (container, items, label) => {
    container.innerHTML = "";
    if (items.length === 0) {
      container.innerHTML = `<div class="result-card"><p>No ${label} matched the current scope.</p></div>`;
      return;
    }

    for (const item of items) {
      const card = document.createElement("article");
      card.className = "result-card";
      card.innerHTML = `
        <div class="result-topline">
          <p class="result-title">${escapeHtml(label)}</p>
          <span class="result-score">score ${Number(item.score ?? 0).toFixed(4)}</span>
        </div>
        <div class="metadata-row">${resultMetaChips(item)}</div>
        <p>${escapeHtml(item.text || "")}</p>
      `;
      container.appendChild(card);
    }
  };

  renderStack(elements.textResults, textChunks, "Text chunk");
  renderStack(elements.captionResults, captions, "Caption");
}

async function refreshJob(jobId) {
  const response = await fetch(apiUrl(`jobs/${jobId}`));
  if (!response.ok) {
    throw new Error(`Failed to load job ${jobId}`);
  }
  const payload = await response.json();
  upsertJob({
    job_id: payload.id,
    document_id: payload.document_id,
    filename: payload.filename,
    status: payload.status,
    job_type: payload.job_type,
    payload: payload.payload || {},
    stats: payload.payload?.stats || {},
    attempt_count: payload.attempt_count,
    worker_name: payload.worker_name,
    error_message: payload.error_message,
    created_at: payload.created_at,
    started_at: payload.started_at,
    finished_at: payload.finished_at,
  });
}

async function pollJobs() {
  const activeJobs = state.jobs.filter((job) => ["pending", "running"].includes(job.status));
  if (activeJobs.length === 0) {
    renderJobs();
    return;
  }

  try {
    await Promise.all(activeJobs.map((job) => refreshJob(job.job_id)));
    renderJobs();
  } catch (error) {
    console.error(error);
    setSignal("error", "Polling error");
  } finally {
    window.setTimeout(pollJobs, 3000);
  }
}

async function handleUpload(event) {
  event.preventDefault();
  const file = elements.fileInput.files?.[0];
  if (!file) {
    elements.uploadHelper.textContent = "Choose a PDF before uploading.";
    return;
  }

  const formData = new FormData();
  formData.append("file", file);

  elements.uploadButton.disabled = true;
  elements.uploadButton.textContent = "Queueing...";
  elements.uploadHelper.textContent = `Uploading ${file.name}`;

  try {
    const response = await fetch(apiUrl("upload/"), {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || "Upload failed");
    }

    const payload = await response.json();
    upsertJob({
      job_id: payload.job_id,
      document_id: payload.document_id,
      filename: payload.filename,
      status: payload.status,
      createdAt: new Date().toISOString(),
    });

    elements.uploadForm.reset();
    elements.uploadHelper.textContent = `${file.name} uploaded and queued.`;
    renderJobs();
    window.setTimeout(() => refreshJob(payload.job_id).then(renderJobs).catch(console.error), 500);
    window.setTimeout(pollJobs, 800);
  } catch (error) {
    console.error(error);
    elements.uploadHelper.textContent = error.message;
    setSignal("error", "Upload failed");
  } finally {
    elements.uploadButton.disabled = false;
    elements.uploadButton.textContent = "Upload and queue";
  }
}

async function handleSearch(event) {
  event.preventDefault();
  const query = elements.queryInput.value.trim();
  if (!query) {
    return;
  }

  elements.searchButton.disabled = true;
  elements.searchButton.textContent = "Searching...";

  try {
    const response = await fetch(apiUrl("query/"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        query,
        top_k: Number(elements.topKSelect.value),
      }),
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || "Search failed");
    }

    state.searchResults = await response.json();
    renderResults();
    setSignal("live", "Search finished");
  } catch (error) {
    console.error(error);
    state.searchResults = null;
    renderResults();
    setSignal("error", error.message);
  } finally {
    elements.searchButton.disabled = false;
    elements.searchButton.textContent = "Run search";
  }
}

function bindDropzone() {
  const updateFileLabel = () => {
    const file = elements.fileInput.files?.[0];
    elements.uploadHelper.textContent = file ? `${file.name} ready for upload.` : "No file selected.";
  };

  elements.fileInput.addEventListener("change", updateFileLabel);

  ["dragenter", "dragover"].forEach((eventName) => {
    elements.dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      elements.dropzone.classList.add("dragover");
    });
  });

  ["dragleave", "drop"].forEach((eventName) => {
    elements.dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      elements.dropzone.classList.remove("dragover");
    });
  });

  elements.dropzone.addEventListener("drop", (event) => {
    const files = event.dataTransfer?.files;
    if (!files || files.length === 0) {
      return;
    }
    elements.fileInput.files = files;
    updateFileLabel();
  });
}

function bootstrap() {
  elements.uploadForm.addEventListener("submit", handleUpload);
  elements.searchForm.addEventListener("submit", handleSearch);
  elements.scopeSelect.addEventListener("change", renderResults);
  bindDropzone();
  renderJobs();
  renderResults();
  window.setTimeout(() => {
    state.jobs.forEach((job) => {
      if (job.job_id) {
        refreshJob(job.job_id).catch(console.error);
      }
    });
    renderJobs();
    pollJobs();
  }, 200);
}

bootstrap();
