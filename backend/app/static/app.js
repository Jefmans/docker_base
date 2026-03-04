const rootPath = document.body.dataset.rootPath || "";
const apiBase = new URL(`${rootPath.replace(/\/$/, "")}/`, window.location.origin);

const state = {
  projects: [],
  projectsLoaded: false,
  documents: [],
  searchResults: null,
  answerResult: null,
  answerRun: null,
  answerTree: null,
  libraryTimer: null,
  answerPollTimer: null,
  answerPollDelay: 2500,
  lastAnswerStage: null,
};

const elements = {
  uploadForm: document.getElementById("upload-form"),
  fileInput: document.getElementById("pdf-file"),
  projectInput: document.getElementById("project-input"),
  projectOptions: document.getElementById("project-options"),
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
  answerForm: document.getElementById("answer-form"),
  answerQueryInput: document.getElementById("answer-query-input"),
  answerButton: document.getElementById("answer-button"),
  answerHelper: document.getElementById("answer-helper"),
  answerEmpty: document.getElementById("answer-empty"),
  answerOutput: document.getElementById("answer-output"),
  answerTree: document.getElementById("answer-tree"),
  resultsEmpty: document.getElementById("results-empty"),
  resultsColumns: document.getElementById("results-columns"),
  textResults: document.getElementById("text-results"),
  captionResults: document.getElementById("caption-results"),
  signalDot: document.getElementById("signal-dot"),
  signalLabel: document.getElementById("signal-label"),
};

function apiUrl(path) {
  return new URL(path, apiBase).toString();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
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

function currentScope() {
  const value = elements.scopeSelect.value || "all";
  if (value === "all") {
    return { mode: "all" };
  }

  const [mode, id] = value.split(":", 2);
  if (mode === "project") {
    return { mode, project_id: id };
  }
  if (mode === "document") {
    return { mode, document_id: id };
  }
  return { mode: "all" };
}

function setScopeValue(mode, id) {
  if (mode === "all" || !id) {
    elements.scopeSelect.value = "all";
    return;
  }
  elements.scopeSelect.value = `${mode}:${id}`;
}

function humanScopeLabel(scope) {
  if (!scope || scope.mode === "all") {
    return "All indexed documents";
  }
  if (scope.mode === "project") {
    const project = state.projects.find((item) => item.id === scope.project_id);
    return project ? `Project: ${project.name}` : "Selected project";
  }
  if (scope.mode === "document") {
    const doc = findDocumentById(scope.document_id);
    return doc ? `PDF: ${doc.display_name}` : "Selected PDF";
  }
  return "Scoped selection";
}

function findDocumentById(documentId) {
  return state.documents.find((doc) => doc.id === documentId) || null;
}

function findDocumentByFilename(filename) {
  return state.documents.find((doc) => doc.filename === filename) || null;
}

function displayFilename(filename) {
  const doc = findDocumentByFilename(filename);
  if (doc) {
    return doc.display_name;
  }
  if (!filename || !filename.includes("_")) {
    return filename || "";
  }
  return filename.split("_", 2)[1];
}

function refreshProjectOptions() {
  const previousScope = elements.scopeSelect.value || "all";
  const previousProjectInput = elements.projectInput.value;

  elements.projectOptions.innerHTML = "";
  for (const project of state.projects) {
    const option = document.createElement("option");
    option.value = project.name;
    elements.projectOptions.appendChild(option);
  }

  elements.scopeSelect.innerHTML = "";

  const allOption = document.createElement("option");
  allOption.value = "all";
  allOption.textContent = "All indexed documents";
  elements.scopeSelect.appendChild(allOption);

  if (state.projects.length > 0) {
    const projectGroup = document.createElement("optgroup");
    projectGroup.label = "Projects";
    for (const project of state.projects) {
      const option = document.createElement("option");
      option.value = `project:${project.id}`;
      option.textContent = `${project.name} (${project.document_count} pdf${project.document_count === 1 ? "" : "s"})`;
      projectGroup.appendChild(option);
    }
    elements.scopeSelect.appendChild(projectGroup);
  }

  if (state.documents.length > 0) {
    const documentGroup = document.createElement("optgroup");
    documentGroup.label = "Documents";
    for (const doc of state.documents) {
      const option = document.createElement("option");
      option.value = `document:${doc.id}`;
      option.textContent = doc.display_name;
      documentGroup.appendChild(option);
    }
    elements.scopeSelect.appendChild(documentGroup);
  }

  const availableValues = [...elements.scopeSelect.options].map((option) => option.value);
  elements.scopeSelect.value = availableValues.includes(previousScope) ? previousScope : "all";
  elements.projectInput.value = previousProjectInput;
}

function renderJobs() {
  const docs = [...state.documents];
  elements.jobsEmpty.hidden = docs.length > 0;
  elements.jobsList.innerHTML = "";

  for (const doc of docs) {
    const latestJob = doc.latest_job || null;
    const status = statusClass(latestJob?.status || "pending");
    const [queued, processing, indexed] = jobStageFlags(status);
    const stats = latestJob?.payload?.stats || {};
    const createdAt = doc.created_at || latestJob?.created_at || null;
    const metaLine = createdAt ? new Date(createdAt).toLocaleString() : "No timestamps yet";
    const details = [doc.title, doc.year, doc.type].filter(Boolean).join(" | ") || "Metadata will appear here after processing completes.";
    const projectLabel = doc.project_name || "Unassigned";
    const projectClass = doc.project_name ? "" : "unassigned";
    const isQueryable = status === "completed";
    const isBusy = ["pending", "running"].includes(status);

    const card = document.createElement("article");
    card.className = "job-card";
    card.innerHTML = `
      <div class="job-topline">
        <div>
          <p class="job-title">${escapeHtml(doc.display_name)}</p>
          <div class="job-subline">
            <span class="project-chip ${projectClass}">${escapeHtml(projectLabel)}</span>
            <span class="job-filename">${escapeHtml(doc.filename)}</span>
          </div>
        </div>
        <span class="status-pill ${status}">${escapeHtml(status)}</span>
      </div>
      <p class="job-meta">document ${escapeHtml(doc.id)} | ${escapeHtml(metaLine)}</p>
      <p class="helper">${escapeHtml(details)}</p>
      <div class="job-progress">
        <div class="progress-step ${queued}">Queued in backend</div>
        <div class="progress-step ${processing}">Worker processing</div>
        <div class="progress-step ${indexed}">Indexed and queryable</div>
      </div>
      <div class="job-actions">
        <button class="mini-button query-button" type="button" ${isQueryable ? "" : "disabled"}>Query this PDF</button>
        <button class="mini-button answer-button" type="button" ${isQueryable ? "" : "disabled"}>Build answer</button>
        <button class="mini-button danger-button delete-button" type="button" ${isBusy ? "disabled" : ""}>Delete PDF</button>
      </div>
      <form class="project-form">
        <input type="text" name="project_name" list="project-options" value="${escapeHtml(doc.project_name || "")}" placeholder="Assign to a project or leave blank">
        <button class="mini-button" type="submit">Save project</button>
      </form>
      <div class="job-stats">
        <div>
          <span class="stat-label">Pages</span>
          <span class="stat-value">${escapeHtml(stats.pages ?? "-")}</span>
        </div>
        <div>
          <span class="stat-label">Chunks indexed</span>
          <span class="stat-value">${escapeHtml(stats.chunks_indexed ?? "-")}</span>
        </div>
        <div>
          <span class="stat-label">Captions indexed</span>
          <span class="stat-value">${escapeHtml(stats.captions_indexed ?? "-")}</span>
        </div>
      </div>
      ${latestJob?.error_message ? `<p class="helper">Failure: ${escapeHtml(latestJob.error_message)}</p>` : ""}
    `;

    card.querySelector(".query-button")?.addEventListener("click", () => {
      setScopeValue("document", doc.id);
      if (elements.queryInput.value.trim()) {
        runSearch().catch(console.error);
      } else {
        elements.queryInput.focus();
      }
    });

    card.querySelector(".answer-button")?.addEventListener("click", () => {
      setScopeValue("document", doc.id);
      if (!elements.answerQueryInput.value.trim() && elements.queryInput.value.trim()) {
        elements.answerQueryInput.value = elements.queryInput.value.trim();
      }
      elements.answerQueryInput.focus();
    });

    card.querySelector(".delete-button")?.addEventListener("click", () => {
      handleDeleteDocument(doc);
    });

    card.querySelector(".project-form")?.addEventListener("submit", (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const input = form.querySelector('input[name="project_name"]');
      updateDocumentProject(doc.id, input.value);
    });

    elements.jobsList.appendChild(card);
  }

  refreshProjectOptions();

  const hasError = docs.some((doc) => doc.latest_job?.status === "failed");
  const isWorking = docs.some((doc) => ["pending", "running"].includes(doc.latest_job?.status));
  if (hasError) {
    setSignal("error", "One or more documents failed");
  } else if (isWorking) {
    setSignal("live", "Pipeline active");
  } else if (docs.length > 0) {
    setSignal("live", "Library ready");
  } else {
    setSignal("idle", "Backend idle");
  }
}

function resultMetaChips(item) {
  const metadata = item.metadata || {};
  const chips = [];
  if (metadata.source_pdf) {
    chips.push(displayFilename(metadata.source_pdf));
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

function renderResults() {
  if (!state.searchResults) {
    elements.resultsEmpty.hidden = false;
    elements.resultsColumns.hidden = true;
    elements.textResults.innerHTML = "";
    elements.captionResults.innerHTML = "";
    elements.resultsEmpty.textContent = "Search results will appear here once at least one document completes processing and you run a query.";
    return;
  }

  const textChunks = state.searchResults.text_chunks || [];
  const captions = state.searchResults.captions || [];

  if (textChunks.length === 0 && captions.length === 0) {
    elements.resultsEmpty.hidden = false;
    elements.resultsColumns.hidden = true;
    elements.textResults.innerHTML = "";
    elements.captionResults.innerHTML = "";
    elements.resultsEmpty.textContent = "No results matched the current query and scope.";
    return;
  }

  elements.resultsEmpty.hidden = true;
  elements.resultsColumns.hidden = false;

  const renderStack = (container, items, label) => {
    container.innerHTML = "";
    if (items.length === 0) {
      container.innerHTML = `<div class="result-card"><p>No ${label.toLowerCase()} matched the current query.</p></div>`;
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

function renderAnswer() {
  if (!state.answerResult && !state.answerRun) {
    elements.answerEmpty.hidden = false;
    elements.answerOutput.hidden = true;
    elements.answerOutput.innerHTML = "";
    elements.answerTree.hidden = true;
    elements.answerTree.innerHTML = "";
    return;
  }

  if (state.answerRun && state.answerRun.status !== "completed") {
    const scope = state.answerRun.scope || { mode: "all" };
    elements.answerEmpty.hidden = true;
    elements.answerOutput.hidden = false;
    elements.answerOutput.innerHTML = `
      <article class="answer-card">
        <div class="answer-header">
          <div>
            <h3 class="answer-title">${escapeHtml(state.answerRun.query || "Building answer")}</h3>
            <p class="helper">The research tree is running in the backend. This view will update automatically.</p>
          </div>
          <div class="answer-meta">
            <span class="metadata-chip">${escapeHtml(humanScopeLabel(scope))}</span>
            <span class="metadata-chip">status ${escapeHtml(state.answerRun.status || "pending")}</span>
            <span class="metadata-chip">stage ${escapeHtml(state.answerRun.stage || "Queued")}</span>
            <span class="metadata-chip">session ${escapeHtml(state.answerRun.session_id || "")}</span>
          </div>
        </div>
      </article>
    `;
    renderAnswerTree();
    return;
  }

  const outline = state.answerResult.outline || [];
  const scope = state.answerResult.scope || { mode: "all" };
  const article = state.answerResult.article || "";

  elements.answerEmpty.hidden = true;
  elements.answerOutput.hidden = false;
  elements.answerOutput.innerHTML = `
    <article class="answer-card">
      <div class="answer-header">
        <div>
          <h3 class="answer-title">${escapeHtml(state.answerResult.title || "Untitled answer")}</h3>
          <p class="helper">${escapeHtml(state.answerResult.abstract || "No abstract generated.")}</p>
        </div>
        <div class="answer-meta">
          <span class="metadata-chip">${escapeHtml(humanScopeLabel(scope))}</span>
          <span class="metadata-chip">${escapeHtml(state.answerRun?.stage || "Completed")}</span>
          <span class="metadata-chip">session ${escapeHtml(state.answerResult.session_id || "")}</span>
        </div>
      </div>
      ${
        outline.length > 0
          ? `<div class="outline-list">${outline
              .map((section) => `<span class="outline-chip">${escapeHtml(section.heading || "Section")}</span>`)
              .join("")}</div>`
          : ""
      }
      <pre class="answer-article">${escapeHtml(article)}</pre>
    </article>
  `;
  renderAnswerTree();
}

function summarizeNode(node) {
  if (node.content) {
    return node.content.slice(0, 220);
  }
  if (node.summary) {
    return node.summary.slice(0, 220);
  }
  if (node.questions?.length) {
    return `${node.questions.length} question${node.questions.length === 1 ? "" : "s"} attached`;
  }
  return "Waiting for content.";
}

function classifyTreeNode(node) {
  if (node.is_final || node.content) {
    return { label: "written", className: "done" };
  }
  if ((node.questions?.length || 0) > 0 || (node.chunks?.length || 0) > 0 || (node.subnodes?.length || 0) > 0) {
    return { label: "active", className: "live" };
  }
  return { label: "pending", className: "pending" };
}

function renderTreeNode(node) {
  const status = classifyTreeNode(node);
  const questionCount = node.questions?.length || 0;
  const chunkCount = node.chunks?.length || 0;
  const children = node.subnodes || [];
  const questionBlock =
    questionCount > 0
      ? `
        <details class="tree-question-block" ${questionCount <= 3 ? "open" : ""}>
          <summary>Questions (${escapeHtml(questionCount)})</summary>
          <ul class="tree-question-list">
            ${node.questions
              .map((question) => `<li class="tree-question-item">${escapeHtml(question)}</li>`)
              .join("")}
          </ul>
        </details>
      `
      : "";

  return `
    <li class="tree-node">
      <article class="tree-node-body">
        <div class="tree-node-header">
          <p class="tree-node-title">${escapeHtml(node.display_rank ? `${node.display_rank} ${node.title}` : node.title || "Untitled node")}</p>
          <div class="tree-node-meta">
            <span class="tree-badge ${status.className}">${escapeHtml(status.label)}</span>
            <span class="tree-badge">q ${escapeHtml(questionCount)}</span>
            <span class="tree-badge">chunks ${escapeHtml(chunkCount)}</span>
            <span class="tree-badge">depth ${escapeHtml(node.level ?? "-")}</span>
          </div>
        </div>
        <p class="tree-node-snippet">${escapeHtml(summarizeNode(node))}</p>
        ${questionBlock}
        ${
          children.length > 0
            ? `<ul class="tree-children">${children.map((child) => renderTreeNode(child)).join("")}</ul>`
            : ""
        }
      </article>
    </li>
  `;
}

function renderAnswerTree() {
  if (!state.answerTree?.root_node) {
    elements.answerTree.hidden = true;
    elements.answerTree.innerHTML = "";
    return;
  }

  const scope = state.answerTree.scope || state.answerResult?.scope || state.answerRun?.scope || { mode: "all" };
  const root = state.answerTree.root_node;
  const topNodes = root.subnodes || [];
  elements.answerTree.hidden = false;
  elements.answerTree.innerHTML = `
    <article class="tree-card">
      <div class="tree-topline">
        <div>
          <p class="eyebrow">Research Tree</p>
          <h3 class="tree-title">${escapeHtml(root.title || state.answerTree.query || "Research tree")}</h3>
        </div>
        <div class="answer-meta">
          <span class="metadata-chip">${escapeHtml(humanScopeLabel(scope))}</span>
          ${
            state.answerRun?.stage
              ? `<span class="metadata-chip">stage ${escapeHtml(state.answerRun.stage)}</span>`
              : ""
          }
        </div>
      </div>
      <ul class="tree-list">
        ${
          topNodes.length > 0
            ? topNodes.map((node) => renderTreeNode(node)).join("")
            : renderTreeNode(root)
        }
      </ul>
    </article>
  `;
}

function resetAnswerPollingState() {
  state.answerPollDelay = 2500;
  state.lastAnswerStage = null;
}

function nextAnswerPollDelay(payload) {
  const stage = payload?.stage || "";
  if (payload?.status !== "running") {
    resetAnswerPollingState();
    return 2500;
  }
  if (!stage || stage !== state.lastAnswerStage) {
    state.lastAnswerStage = stage;
    state.answerPollDelay = 2500;
    return state.answerPollDelay;
  }
  state.answerPollDelay = Math.min(state.answerPollDelay + 1500, 12000);
  return state.answerPollDelay;
}

async function refreshAnswerTree(sessionId) {
  try {
    const payload = await fetchJson(`agent/tree/${sessionId}`);
    state.answerTree = payload;
    renderAnswerTree();
  } catch (error) {
    if (!/not found/i.test(error.message || "")) {
      console.error(error);
    }
  }
}

function scheduleAnswerPoll(sessionId, delayMs = state.answerPollDelay) {
  if (state.answerPollTimer) {
    window.clearTimeout(state.answerPollTimer);
  }
  state.answerPollTimer = window.setTimeout(() => {
    pollAnswerRun(sessionId).catch(console.error);
  }, delayMs);
}

async function pollAnswerRun(sessionId) {
  try {
    const [payload] = await Promise.all([
      fetchJson(`agent/answer_runs/${sessionId}`),
      refreshAnswerTree(sessionId),
    ]);
    state.answerRun = payload;
    if (payload.status === "completed" && payload.result) {
      state.answerResult = payload.result;
      await refreshAnswerTree(sessionId);
      renderAnswer();
      elements.answerHelper.textContent = "Structured answer generated successfully.";
      setSignal("live", "Answer built");
      return;
    }

    if (payload.status === "failed") {
      state.answerResult = null;
      renderAnswer();
      elements.answerHelper.textContent = payload.error || "Answer generation failed";
      setSignal("error", payload.error || "Answer generation failed");
      return;
    }

    renderAnswer();
    scheduleAnswerPoll(sessionId, nextAnswerPollDelay(payload));
  } catch (error) {
    console.error(error);
    elements.answerHelper.textContent = error.message;
    setSignal("error", error.message);
  }
}

async function fetchJson(path, options = {}) {
  const response = await fetch(apiUrl(path), options);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `Request failed for ${path}`);
  }
  return response.json();
}

async function loadLibrary(options = {}) {
  const { includeProjects = false } = options;
  try {
    let documentPayload;
    if (includeProjects || !state.projectsLoaded) {
      const [projectPayload, docsPayload] = await Promise.all([
        fetchJson("projects/"),
        fetchJson("documents/"),
      ]);
      state.projects = projectPayload.projects || [];
      state.projectsLoaded = true;
      documentPayload = docsPayload;
    } else {
      documentPayload = await fetchJson("documents/");
    }
    state.documents = documentPayload.documents || [];
    renderJobs();
  } catch (error) {
    console.error(error);
    setSignal("error", "Failed to load library");
  } finally {
    scheduleLibraryRefresh();
  }
}

function scheduleLibraryRefresh() {
  if (state.libraryTimer) {
    window.clearTimeout(state.libraryTimer);
  }
  const hasActiveJobs = state.documents.some((document) =>
    ["pending", "running"].includes(document.latest_job?.status)
  );
  const delayMs = hasActiveJobs ? 8000 : 45000;
  state.libraryTimer = window.setTimeout(() => {
    loadLibrary({ includeProjects: false }).catch(console.error);
  }, delayMs);
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
  const projectName = elements.projectInput.value.trim();
  if (projectName) {
    formData.append("project_name", projectName);
  }

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
    elements.uploadForm.reset();
    elements.uploadHelper.textContent = `${payload.display_name || file.name} uploaded and queued.`;
    await loadLibrary({ includeProjects: true });
    setScopeValue("document", payload.document_id);
  } catch (error) {
    console.error(error);
    elements.uploadHelper.textContent = error.message;
    setSignal("error", "Upload failed");
  } finally {
    elements.uploadButton.disabled = false;
    elements.uploadButton.textContent = "Upload and queue";
  }
}

async function updateDocumentProject(documentId, projectName) {
  try {
    await fetchJson(`documents/${documentId}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        project_name: projectName,
      }),
    });
    await loadLibrary({ includeProjects: true });
    setSignal("live", "Project updated");
  } catch (error) {
    console.error(error);
    setSignal("error", error.message);
  }
}

async function handleDeleteDocument(document) {
  const confirmed = window.confirm(`Delete ${document.display_name}? This removes the PDF, derived images, and indexed search data.`);
  if (!confirmed) {
    return;
  }

  try {
    await fetchJson(`documents/${document.id}`, {
      method: "DELETE",
    });

    const scope = currentScope();
    if (scope.mode === "document" && scope.document_id === document.id) {
      setScopeValue("all");
    }
    state.searchResults = null;
    if (state.answerResult?.scope?.mode === "document" && state.answerResult.scope.document_id === document.id) {
      state.answerResult = null;
    }
    if (state.answerRun?.scope?.mode === "document" && state.answerRun.scope.document_id === document.id) {
      state.answerRun = null;
      state.answerTree = null;
    }
    renderAnswer();
    if (state.answerPollTimer) {
      window.clearTimeout(state.answerPollTimer);
      state.answerPollTimer = null;
    }
    renderResults();
    await loadLibrary({ includeProjects: true });
    setSignal("live", "Document deleted");
  } catch (error) {
    console.error(error);
    setSignal("error", error.message);
  }
}

async function runSearch() {
  const query = elements.queryInput.value.trim();
  if (!query) {
    return;
  }

  const scope = currentScope();
  const payload = {
    query,
    top_k: Number(elements.topKSelect.value),
  };
  if (scope.mode === "document") {
    payload.document_id = scope.document_id;
  }
  if (scope.mode === "project") {
    payload.project_id = scope.project_id;
  }

  elements.searchButton.disabled = true;
  elements.searchButton.textContent = "Searching...";

  try {
    state.searchResults = await fetchJson("query/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
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

async function runBuildAnswer() {
  const query = elements.answerQueryInput.value.trim();
  if (!query) {
    return;
  }

  const scope = currentScope();
  const payload = {
    query,
    top_k: Number(elements.topKSelect.value),
  };
  if (scope.mode === "document") {
    payload.document_id = scope.document_id;
  }
  if (scope.mode === "project") {
    payload.project_id = scope.project_id;
  }

  elements.answerButton.disabled = true;
  elements.answerButton.textContent = "Building...";
  elements.answerHelper.textContent = `Running research tree over ${humanScopeLabel(scope)}. This can take a while.`;

  try {
    const startPayload = await fetchJson("agent/answer_runs", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
    state.answerResult = null;
    state.answerRun = startPayload;
    state.answerTree = null;
    resetAnswerPollingState();
    renderAnswer();
    setSignal("live", "Answer queued");
    refreshAnswerTree(startPayload.session_id).catch(console.error);
    scheduleAnswerPoll(startPayload.session_id, 1000);
  } catch (error) {
    console.error(error);
    state.answerResult = null;
    state.answerRun = null;
    state.answerTree = null;
    renderAnswer();
    elements.answerHelper.textContent = error.message;
    setSignal("error", error.message);
  } finally {
    elements.answerButton.disabled = false;
    elements.answerButton.textContent = "Build answer";
  }
}

async function handleSearch(event) {
  event.preventDefault();
  await runSearch();
}

async function handleBuildAnswer(event) {
  event.preventDefault();
  await runBuildAnswer();
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
  elements.answerForm.addEventListener("submit", handleBuildAnswer);
  elements.scopeSelect.addEventListener("change", () => {
    if (elements.queryInput.value.trim()) {
      runSearch().catch(console.error);
    }
  });
  bindDropzone();
  renderResults();
  renderAnswer();
  loadLibrary({ includeProjects: true }).catch(console.error);
}

bootstrap();
