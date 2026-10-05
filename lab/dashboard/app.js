"use strict";
const el = (id) => document.getElementById(id);
const escape = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const human = (value) => String(value || "Unknown").replace(/[_-]/g, " ").replace(/^./, (c) => c.toUpperCase());
const duration = (ms) => ms == null ? "—" : ms < 1000 ? `${Math.round(ms)} ms` : ms < 60000 ? `${(ms / 1000).toFixed(1)}s` : ms < 3600000 ? `${Math.floor(ms / 60000)}m ${Math.floor(ms / 1000) % 60}s` : `${Math.floor(ms / 3600000)}h ${Math.floor(ms / 60000) % 60}m`;
const verdict = (value) => value === true ? "Passed" : value === false ? "Failed" : "Not recorded";
const badge = (state) => `<span class="badge ${escape(state)}">${escape(human(state))}</span>`;
const rendered = new Map();
function replace(id, html) {
  if (rendered.get(id) === html) return;
  const active = el(id).contains(document.activeElement) ? document.activeElement : null;
  const key = active?.dataset.trial ? "trial" : "campaign", value = active?.dataset[key];
  el(id).innerHTML = html;
  rendered.set(id, html);
  if (value) el(id).querySelector(`[data-${key}="${CSS.escape(value)}"]`)?.focus({preventScroll:true});
}
let campaigns = [], selected = new URLSearchParams(location.search).get("campaign"), current = null, selectedTrial = null, loading = false;

function campaignName(id) {
  return id.replace(/-\d{8}(?:T\d+)?$/, "").replace(/^varied-/, "").replace(/-/g, " ").replace(/^./, (c) => c.toUpperCase());
}

function renderCampaigns() {
  el("campaign-count").textContent = campaigns.length;
  replace("campaigns", campaigns.map((c) => `<button class="campaign" data-campaign="${escape(c.id)}" aria-current="${c.id === selected}"><strong>${escape(campaignName(c.id))}</strong><small>${escape(human(c.state))} · ${c.completed}/${c.total} complete</small></button>`).join("") || '<p class="muted">No campaigns found.</p>');
}

function renderSummary() {
  const c = current, percent = c.total ? Math.round(c.completed / c.total * 100) : 0;
  el("title").textContent = campaignName(c.id);
  el("subtitle").textContent = `${c.id} · ${c.jobs} worker limit · ${human(c.measurement_purpose)}`;
  el("campaign-state").className = `badge ${c.state}`;
  el("campaign-state").textContent = human(c.state);
  el("completion").textContent = `${c.completed} of ${c.total} trials complete`;
  el("percent").textContent = `${percent}%`;
  el("progress").setAttribute("aria-valuenow", percent);
  el("passed-bar").style.width = `${c.total ? c.passed / c.total * 100 : 0}%`;
  el("failed-bar").style.width = `${c.total ? c.failed / c.total * 100 : 0}%`;
  el("cancelled-bar").style.width = `${c.total ? Math.max(0, c.completed - c.passed - c.failed) / c.total * 100 : 0}%`;
  for (const key of ["accepted", "rejected"]) el(key).textContent = c[key];
  el("acceptance-unknown").textContent = c.acceptance_unknown;
  el("elapsed").textContent = duration(c.elapsed_ms);
  const quiet = c.trials.filter((t) => t.status === "quiet").length;
  el("campaign-note").textContent = c.state === "prepared" ? `Prepared and waiting to start. ${c.total} trials are ready; opening this dashboard does not start them.` : `${c.trials.filter((t) => t.status === "queued").length} queued · ${quiet} quiet · ${c.jobs} workers configured. Elapsed time includes provider waiting.${c.state === "quiet" ? " No recent activity; process status is unconfirmed." : ""}`;
  const oldFamily = el("family-filter").value;
  replace("family-filter", '<option value="all">All task types</option>' + [...new Set(c.trials.map((t) => t.family).filter(Boolean))].sort().map((f) => `<option value="${escape(f)}">${escape(human(f))}</option>`).join(""));
  el("family-filter").value = [...el("family-filter").options].some((o) => o.value === oldFamily) ? oldFamily : "all";
  renderTasks();
  if (el("detail").open) renderDetail();
}

function renderTasks() {
  if (!current) return;
  const search = el("search").value.toLowerCase(), status = el("status-filter").value, family = el("family-filter").value;
  const trials = current.trials.filter((t) => (status === "all" || t.status === status) && (family === "all" || t.family === family) && `${t.fixture} ${t.run_id} ${t.workflow}`.toLowerCase().includes(search));
  el("task-count").textContent = `${trials.length} of ${current.total} trials`;
  replace("task-map", trials.map((t) => `<button class="tile ${escape(t.status)}" data-trial="${escape(t.run_id)}" aria-pressed="${t.run_id === selectedTrial}" aria-label="${escape(`${t.run_id}: ${t.fixture}, ${human(t.status)}`)}" title="${escape(`${t.run_id} · ${t.fixture} · ${human(t.status)}`)}">${escape(t.run_id.replace(/^trial-0*/, ""))}</button>`).join(""));
  replace("trials", trials.map((t) => `<tr><td><button class="task-link" data-trial="${escape(t.run_id)}">${escape(human(t.fixture))}</button><small>${escape(t.run_id)} · ${escape(human(t.family))} · ${escape(human(t.language))}</small></td><td>${escape(t.workflow)}</td><td>${escape(verdict(t.task_success))}</td><td>${badge(t.status)}</td><td>${t.phase ? escape(human(t.phase)) : "—"}</td><td class="number">${duration(t.elapsed_ms)}</td></tr>`).join(""));
  el("empty").hidden = trials.length !== 0;
}

function renderDetail() {
  const t = current?.trials.find((trial) => trial.run_id === selectedTrial);
  if (!t) { el("detail").close(); return; }
  const items = [["Workflow", t.workflow], ["Task acceptance", verdict(t.task_success)], ["Workflow completion", human(t.workflow_status)], ["Process stop", human(t.stop_status)], ["Evaluation", human(t.evaluation_status)], ["Task type", `${human(t.family)} · ${human(t.language)}`], [t.elapsed_basis === "worker" ? "Elapsed (includes setup)" : "Host elapsed", duration(t.elapsed_ms)], ["Provider queue wait", duration(t.queue_wait_ms)], ["Public tests", verdict(t.public_test_success)], ["Private tests", verdict(t.hidden_test_success)], ["Input tokens", t.usage.input_tokens ?? "Unknown"], ["Output tokens", t.usage.output_tokens ?? "Unknown"]];
  el("detail-content").innerHTML = `<h2 id="detail-title">${escape(human(t.fixture))}</h2><p class="muted">${escape(t.run_id)} ${t.repetition != null ? `· Repetition ${escape(t.repetition)}` : ""}</p>${badge(t.status)}<dl class="detail-grid">${items.map(([label, value]) => `<div><dt>${label}</dt><dd>${escape(value)}</dd></div>`).join("")}</dl><h2>Phase history</h2><ol class="phase-list">${t.phases.map((p) => `<li><span>${escape(human(p.name))}<small>${escape(human(p.status))}</small></span><span class="number">${duration(p.elapsed_ms)}</span></li>`).join("") || '<li class="muted">No phases recorded yet.</li>'}</ol>${t.failure_classification ? `<p class="failure-note">${escape(human(t.failure_classification))}</p>` : ""}<p class="note">Queue wait is shown only when a completed timing audit exists. A dash means the value has not been recorded.</p>`;
}

async function get(path) {
  const response = await fetch(path, { cache: "no-store", signal: AbortSignal.timeout(12000) });
  if (!response.ok) throw new Error(`Observer returned HTTP ${response.status}`);
  return response.json();
}

async function refresh() {
  if (loading) return;
  loading = true;
  try {
    const data = await get("/api/campaigns");
    campaigns = data.campaigns;
    if (!campaigns.some((c) => c.id === selected)) selected = campaigns[0]?.id;
    renderCampaigns();
    if (selected) {
      const id = selected, detail = await get(`/api/campaigns/${encodeURIComponent(id)}`);
      if (id !== selected) return;
      current = detail;
      renderSummary();
      document.querySelector(".overview").hidden = false;
      document.querySelector(".tasks").hidden = false;
    } else {
      current = null;
      el("detail").close();
      document.querySelector(".overview").hidden = true;
      document.querySelector(".tasks").hidden = true;
      el("title").textContent = "No campaigns yet";
      el("subtitle").textContent = "Prepared campaigns will appear here automatically.";
      el("campaign-state").textContent = "Waiting";
    }
    el("error").hidden = true;
    el("connection").textContent = `Updated ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`;
    el("connection").className = "connected";
  } catch (error) {
    el("error").textContent = `Cannot refresh the observer. ${current ? "Showing the last received snapshot. " : ""}${error.message}. Retrying automatically.`;
    el("error").hidden = false;
    el("connection").textContent = "Connection interrupted";
    el("connection").className = "";
  } finally { loading = false; }
}

el("campaigns").addEventListener("click", (event) => {
  const button = event.target.closest("[data-campaign]");
  if (!button || loading) return;
  selected = button.dataset.campaign;
  selectedTrial = null;
  el("search").value = "";
  el("status-filter").value = "all";
  el("family-filter").value = "all";
  history.replaceState(null, "", `?campaign=${encodeURIComponent(selected)}`);
  refresh();
});
document.querySelector(".tasks").addEventListener("click", (event) => {
  const button = event.target.closest("[data-trial]");
  if (!button) return;
  selectedTrial = button.dataset.trial;
  renderDetail();
  el("detail").showModal();
});
for (const id of ["search", "status-filter", "family-filter"]) el(id).addEventListener("input", renderTasks);
el("close-detail").addEventListener("click", () => el("detail").close());
refresh();
setInterval(refresh, 5000);
