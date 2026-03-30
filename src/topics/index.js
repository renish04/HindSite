const API_BASE = "http://localhost:8000";

const loadingEl = document.getElementById("loading");
const topicsRootEl = document.getElementById("topicsRoot");
const emptyEl = document.getElementById("emptyState");
const statusBadgeEl = document.getElementById("statusBadge");
const errorBoxEl = document.getElementById("errorBox");
const autoBtn = document.getElementById("autoOrganizeBtn");
const retrainBtn = document.getElementById("retrainBtn");

function setError(msg) {
  if (!msg) {
    errorBoxEl.classList.add("hidden");
    errorBoxEl.textContent = "";
    return;
  }
  errorBoxEl.textContent = msg;
  errorBoxEl.classList.remove("hidden");
}

function setLoading(on) {
  loadingEl.classList.toggle("hidden", !on);
}

async function fetchStatus() {
  const res = await fetch(`${API_BASE}/topics/status`);
  const data = await res.json();
  if (data.is_trained) {
    statusBadgeEl.textContent = `${data.n_topics} topics discovered`;
    statusBadgeEl.style.background = "#dcfce7";
    statusBadgeEl.style.color = "#166534";
  } else {
    statusBadgeEl.textContent = "Model not trained";
    statusBadgeEl.style.background = "#fef3c7";
    statusBadgeEl.style.color = "#92400e";
  }
}

function pageCard(page) {
  const wrap = document.createElement("div");
  wrap.className = "page-card";
  wrap.addEventListener("click", () => chrome.tabs.create({ url: page.url }));

  const thumb = page.thumbnail_base64
    ? `<img class="thumb" src="data:image/jpeg;base64,${page.thumbnail_base64}" alt="thumbnail" />`
    : `<div class="thumb-placeholder">No thumbnail</div>`;

  wrap.innerHTML = `
    ${thumb}
    <div class="page-content">
      <p class="page-title">${(page.title || "Untitled").slice(0, 90)}</p>
      <div class="meta-row">
        <span>${page.domain || "-"}</span>
      </div>
    </div>
  `;
  return wrap;
}

function clusterSection(topic, idx) {
  const section = document.createElement("section");
  section.className = "cluster";

  const head = document.createElement("div");
  head.className = "cluster-head";
  head.innerHTML = `
    <div>
      <h3 class="cluster-title">${topic.topic_label}</h3>
      <div class="cluster-count">${topic.page_count} pages</div>
    </div>
    <div id="arrow-${idx}">▼</div>
  `;

  const body = document.createElement("div");
  body.className = "cluster-body";
  topic.pages.forEach((p) => body.appendChild(pageCard(p)));

  head.addEventListener("click", () => {
    const hidden = body.classList.toggle("hidden");
    document.getElementById(`arrow-${idx}`).textContent = hidden ? "▶" : "▼";
  });

  section.appendChild(head);
  section.appendChild(body);
  return section;
}

async function fetchClusters() {
  setLoading(true);
  setError(null);
  topicsRootEl.classList.add("hidden");
  emptyEl.classList.add("hidden");

  try {
    await fetchStatus();
    const res = await fetch(`${API_BASE}/topics/pages?include_thumbnails=true`);
    const data = await res.json();

    if (!Array.isArray(data) || data.length === 0) {
      emptyEl.classList.remove("hidden");
      return;
    }

    topicsRootEl.innerHTML = "";
    data.forEach((topic, idx) => topicsRootEl.appendChild(clusterSection(topic, idx)));
    topicsRootEl.classList.remove("hidden");
  } catch (e) {
    setError("Failed to load clusters. Ensure backend is running on localhost:8000.");
  } finally {
    setLoading(false);
  }
}

async function autoOrganize() {
  autoBtn.disabled = true;
  retrainBtn.disabled = true;
  setError(null);
  try {
    const res = await fetch(`${API_BASE}/topics/auto-organize`, { method: "POST" });
    const data = await res.json();
    if (!data.success) throw new Error(data.message || "Auto-organize failed");
    await fetchClusters();
  } catch (e) {
    setError(String(e.message || e));
  } finally {
    autoBtn.disabled = false;
    retrainBtn.disabled = false;
  }
}

async function retrain() {
  autoBtn.disabled = true;
  retrainBtn.disabled = true;
  setError(null);
  try {
    const res = await fetch(`${API_BASE}/topics/train`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ force_retrain: true }),
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.message || "Retrain failed");
    await fetchClusters();
  } catch (e) {
    setError(String(e.message || e));
  } finally {
    autoBtn.disabled = false;
    retrainBtn.disabled = false;
  }
}

autoBtn.addEventListener("click", autoOrganize);
retrainBtn.addEventListener("click", retrain);
fetchClusters();

