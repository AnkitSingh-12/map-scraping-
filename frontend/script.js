const form = document.getElementById("search-form");
const queryInput = document.getElementById("query");
const maxInput = document.getElementById("max");
const enrichInput = document.getElementById("enrich");
const goBtn = document.getElementById("go");

const statusCard = document.getElementById("status-card");
const spinner = document.getElementById("spinner");
const parsedLine = document.getElementById("parsed-line");
const logEl = document.getElementById("log");

const resultsCard = document.getElementById("results-card");
const countEl = document.getElementById("count");
const tbody = document.querySelector("#results-table tbody");
const errorCard = document.getElementById("error-card");

let currentResults = [];
let evtSource = null;

document.querySelectorAll(".chip").forEach((c) =>
  c.addEventListener("click", () => {
    queryInput.value = c.textContent;
    form.requestSubmit();
  })
);

document.querySelectorAll(".exp").forEach((b) =>
  b.addEventListener("click", () => exportResults(b.dataset.fmt))
);

form.addEventListener("submit", (e) => {
  e.preventDefault();
  startSearch();
});

function show(el) { el.classList.remove("hidden"); }
function hide(el) { el.classList.add("hidden"); }
function appendLog(msg) {
  logEl.textContent += msg + "\n";
  logEl.scrollTop = logEl.scrollHeight;
}

function startSearch() {
  const query = queryInput.value.trim();
  if (!query) return;

  if (evtSource) evtSource.close();
  currentResults = [];
  tbody.innerHTML = "";
  logEl.textContent = "";
  hide(resultsCard);
  hide(errorCard);
  show(statusCard);
  spinner.style.display = "block";
  parsedLine.textContent = "Starting…";
  goBtn.disabled = true;

  const params = new URLSearchParams({
    query,
    max_results: maxInput.value || "20",
    enrich: enrichInput.checked ? "true" : "false",
  });

  evtSource = new EventSource(`/api/stream?${params.toString()}`);

  evtSource.addEventListener("log", (e) => {
    const { message } = JSON.parse(e.data);
    appendLog(message);
    if (message.startsWith("Category:")) parsedLine.textContent = message;
  });

  evtSource.addEventListener("result", (e) => {
    const data = JSON.parse(e.data);
    currentResults = data.results || [];
    renderResults(data);
  });

  evtSource.addEventListener("error", (e) => {
    let msg = "An error occurred during scraping.";
    try { msg = JSON.parse(e.data); } catch (_) {}
    errorCard.textContent = "⚠ " + msg;
    show(errorCard);
  });

  evtSource.addEventListener("done", () => {
    evtSource.close();
    spinner.style.display = "none";
    parsedLine.textContent = "Finished.";
    goBtn.disabled = false;
  });

  evtSource.onerror = () => {
    // Network drop / server closed unexpectedly.
    if (goBtn.disabled) {
      goBtn.disabled = false;
      spinner.style.display = "none";
    }
  };
}

function cell(value, isLink) {
  if (!value) return '<td class="muted-cell">—</td>';
  if (isLink) {
    const href = value.startsWith("http") ? value : "https://" + value;
    let label = value.replace(/^https?:\/\//, "").replace(/\/$/, "");
    if (label.length > 32) label = label.slice(0, 32) + "…";
    return `<td><a href="${href}" target="_blank" rel="noopener">${label}</a></td>`;
  }
  return `<td>${escapeHtml(value)}</td>`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

function renderResults(data) {
  countEl.textContent = data.count;
  tbody.innerHTML = "";
  (data.results || []).forEach((c, i) => {
    const tr = document.createElement("tr");
    tr.innerHTML =
      `<td>${i + 1}</td>` +
      cell(c.name) +
      cell(c.website, true) +
      (c.phone ? `<td><a href="tel:${c.phone}">${escapeHtml(c.phone)}</a></td>` : '<td class="muted-cell">—</td>') +
      (c.email ? `<td><a href="mailto:${c.email}">${escapeHtml(c.email)}</a></td>` : '<td class="muted-cell">—</td>') +
      cell(c.address) +
      (c.maps_url ? `<td><a href="${c.maps_url}" target="_blank" rel="noopener">📍</a></td>` : '<td class="muted-cell">—</td>');
    tbody.appendChild(tr);
  });
  show(resultsCard);
}

async function exportResults(fmt) {
  if (!currentResults.length) {
    alert("No results to export yet.");
    return;
  }
  const res = await fetch(`/api/export/${fmt}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(currentResults),
  });
  if (!res.ok) {
    alert("Export failed.");
    return;
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `companies.${fmt === "xlsx" ? "xlsx" : fmt}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
