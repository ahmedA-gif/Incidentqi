"use strict";

const icons = {
  pulse: '<path d="M3 12h4l3-7 4 14 3-7h4"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4"/>',
  server: '<rect x="3" y="4" width="18" height="7" rx="2"/><rect x="3" y="13" width="18" height="7" rx="2"/><path d="M7 7.5h.01M7 16.5h.01"/>',
  layers: '<path d="m12 3 9 5-9 5-9-5 9-5Zm-9 9 9 5 9-5M3 16l9 5 9-5"/>',
  play: '<path d="m8 5 11 7-11 7V5Z"/>',
  check: '<circle cx="12" cy="12" r="8"/><path d="m8 12 3 3 5-5"/>',
  alert: '<path d="M12 8v4m0 4h.01M10 4 3 17a2 2 0 0 0 2 3h14a2 2 0 0 0 2-3L14 4a2 2 0 0 0-4 0Z"/>',
};

const byId = (id) => document.getElementById(id);
const form = byId("investigation-form");
const scenario = byId("scenario");
const report = byId("report");
const run = byId("run");
const nvidia = byId("nvidia");
let config;

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function fillIcon(node, name) {
  node.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + icons[name] + '</svg>';
  return node;
}

function label(id) {
  return id.replace(/([a-z])([A-Z])|([A-Z])([A-Z][a-z])|([A-Za-z])(\d)/g, (_, a, b, c, d, e, f) =>
    [a || c || e, b || d || f].join(" "));
}

function serviceLabel(id) {
  return config.services.find((service) => service.id === id)?.label || label(id);
}

function status(value, display = value) {
  return element("span", display, "status " + value.toLowerCase().split(" ")[0]);
}

function showInventory(values, source) {
  const services = config.services.map(({ id, label }) => ({ label, value: values[id] || "unknown" }));
  const online = services.filter(({ value }) => value === "online").length;
  const impacted = services.filter(({ value }) => ["offline", "down", "unavailable", "degraded"].includes(value)).length;
  const metrics = [
    ["server", services.length, "Services"],
    ["check", online, "Online"],
    ["alert", impacted, "Impacted"],
  ];
  byId("metrics").replaceChildren(...metrics.map(([icon, count, title]) => {
    const card = element("div", undefined, "metric");
    const value = element("div");
    value.append(element("strong", count), element("small", title));
    card.append(fillIcon(element("span", undefined, "section-icon"), icon), value);
    return card;
  }));
  byId("inventory-source").textContent = source;
  byId("service-list").replaceChildren(...services.map(({ label, value }) => {
    const li = element("li");
    li.append(element("span", label), status(value));
    return li;
  }));
}

function setBadge(text) {
  byId("source-badge").replaceChildren(element("span", undefined, "connection-dot"), document.createTextNode(text));
}

function resetResult(message) {
  byId("report-content").replaceChildren(element("p", message, "panel-copy"));
  byId("result-source").textContent = "";
  byId("evidence-count").textContent = "Waiting for a diagnosis";
  byId("trace").replaceChildren();
  byId("evidence-list").replaceChildren();
}

function selectSource() {
  const sample = config.scenarios[scenario.value];
  const previousSample = Object.values(config.scenarios).some((entry) => entry.report === report.value);
  if (!report.value || previousSample) report.value = sample?.report || "";
  setBadge(sample ? "Simulated data" : "Project evidence");
  byId("uploads").hidden = Boolean(sample);
  showInventory(sample?.services || {}, sample ? "Simulation · " + sample.label : "Attach a status snapshot");
  byId("error").hidden = true;
  resetResult("Run the diagnosis to see findings for this source.");
}

function references(ids) {
  const group = element("div", undefined, "references");
  for (const id of ids) {
    const anchor = element("a", id, "reference");
    anchor.href = "#evidence-" + id;
    anchor.setAttribute("aria-label", "View evidence " + id);
    group.append(anchor);
  }
  return group;
}

function detailGroup(title) {
  const group = element("section", undefined, "report-group");
  group.append(element("h3", title));
  return group;
}

function renderCandidate(candidate) {
  const details = element("details", undefined, "candidate");
  const summary = element("summary", candidate.label + " ");
  summary.append(status(candidate.assessment));
  const list = element("dl");
  if (candidate.severity) list.append(element("dt", "Severity"), element("dd", label(candidate.severity)));
  if (candidate.affected.length) {
    list.append(element("dt", "Potential impact"), element("dd", candidate.affected.map(serviceLabel).join(", ")));
  }
  if (candidate.tests.length) list.append(element("dt", "Diagnostic tests"));
  for (const test of candidate.tests) {
    const row = element("dd", label(test.id) + " ");
    row.append(status(test.result));
    list.append(row);
  }
  details.append(summary, list, references(candidate.evidence));
  return details;
}

function renderReport(data) {
  const content = byId("report-content");
  const finding = element("div", undefined, "finding");
  const heading = data.primary ? (data.primary.root ? "Suspected root cause" : "Supported fault") : "Assessment";
  finding.append(element("span", heading, "finding-label"), element("h3", data.title), element("p", data.summary));
  if (data.primary) finding.append(references(data.primary.evidence));
  content.replaceChildren(finding);
  byId("result-source").textContent = data.status_source + " · " + data.intake_mode;

  if (data.model_note) {
    const intake = detailGroup("Model intake");
    intake.append(element("p", data.model_note, "panel-copy"));
    content.append(intake);
  }
  if (data.symptoms.length || data.services.length) {
    const signals = detailGroup("Matched entities");
    signals.append(element("p", [...data.services.map(serviceLabel), ...data.symptoms.map(label)].join(" · "), "panel-copy"));
    content.append(signals);
  }
  if (data.primary?.solutions.length) {
    const actions = detailGroup("Recommended actions");
    const list = element("ul");
    list.append(...data.primary.solutions.map((solution) => element("li", solution.text)));
    actions.append(list);
    content.append(actions);
  }
  if (data.next_checks.length) {
    const checks = detailGroup("Missing diagnostic checks");
    const list = element("ul");
    list.append(...data.next_checks.map((test) => element("li", test.procedure || label(test.id))));
    checks.append(list);
    content.append(checks);
  }
  if (data.candidates.length) {
    const candidates = detailGroup("Candidate faults");
    candidates.append(...data.candidates.map(renderCandidate));
    content.append(candidates);
  }
  if (data.project.filename) {
    const project = detailGroup("Project ZIP");
    const omitted = data.project.skipped ? " · " + data.project.skipped + " skipped entries" : "";
    project.append(element("p", data.project.filename + " · " + data.project.files + " files cataloged" + omitted, "panel-copy"));
    content.append(project);
  }

  showInventory(data.monitoring.services, data.status_source);
  byId("evidence-count").textContent = data.evidence.length + (data.evidence.length === 1 ? " evidence item" : " evidence items");
  byId("evidence-list").replaceChildren(...data.evidence.map((item) => {
    const li = element("li");
    li.id = "evidence-" + item.id;
    li.tabIndex = -1;
    li.append(element("strong", item.id + " · " + item.kind), element("p", item.text), element("small", item.source));
    return li;
  }));
  const trace = element("details");
  trace.append(element("summary", "Agent activity · " + data.trace.length));
  const items = element("ul");
  for (const step of data.trace) {
    const item = element("li");
    item.append(element("strong", step.agent), element("span", step.ms + " ms"), element("p", step.summary));
    items.append(item);
  }
  trace.append(items);
  byId("trace").replaceChildren(trace);
}

async function diagnose() {
  if (run.disabled) return;
  const payload = new FormData(form);
  for (const name of ["status", "project"]) {
    if (scenario.value !== "project" || !byId(name).files.length) payload.delete(name);
  }
  if (payload.get("project")?.size > config.project_limit_mb * 1024 * 1024) {
    byId("error").textContent = "Choose a project ZIP up to " + config.project_limit_mb + " MB.";
    byId("error").hidden = false;
    return;
  }
  payload.set("use_nvidia", String(nvidia.checked));
  run.disabled = true;
  scenario.disabled = true;
  byId("error").hidden = true;
  byId("result").setAttribute("aria-busy", "true");
  resetResult("The agents are checking faults, dependencies, and monitoring evidence…");
  run.lastChild.textContent = "Running…";
  try {
    const response = await fetch("/api/diagnose", { method: "POST", body: payload });
    const result = await response.json();
    if (!response.ok) {
      const detail = typeof result.detail === "string" ? result.detail : result.detail?.[0]?.msg;
      throw new Error(detail || "The diagnosis could not be completed.");
    }
    renderReport(result);
  } catch (error) {
    byId("error").textContent = error.message;
    byId("error").hidden = false;
    resetResult("The diagnosis did not finish. Review the message above and try again.");
  } finally {
    run.disabled = false;
    scenario.disabled = false;
    byId("result").setAttribute("aria-busy", "false");
    run.lastChild.textContent = "Run diagnosis";
  }
}

async function init() {
  document.querySelectorAll("[data-icon]").forEach((node) => fillIcon(node, node.dataset.icon));
  document.querySelectorAll(".sidebar nav a").forEach((link) => {
    link.addEventListener("click", () => {
      document.querySelector(".sidebar nav a.active")?.classList.remove("active");
      link.classList.add("active");
    });
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    diagnose();
  });
  scenario.addEventListener("change", selectSource);
  try {
    const response = await fetch("/api/config");
    if (!response.ok) throw new Error("Could not connect to the diagnostic API.");
    config = await response.json();
    byId("project-limit").textContent = "optional · up to " + config.project_limit_mb + " MB";
    for (const [id, sample] of Object.entries(config.scenarios)) {
      scenario.add(new Option("Demo · " + sample.label, id));
    }
    scenario.add(new Option("My project", "project"));
    scenario.disabled = false;
    run.disabled = false;
    nvidia.disabled = !config.nvidia;
    byId("model-hint").textContent = config.nvidia ? "Sends the incident report to NVIDIA." : "Set NVIDIA_API_KEY to enable.";
    byId("connection").textContent = "Ontology loaded";
    byId("ontology-footer").textContent = config.ontology + " · " + config.classes + " classes · " + config.faults + " faults · " + config.reasoner;
    selectSource();
    await diagnose();
  } catch (error) {
    byId("connection").textContent = "API unavailable";
    setBadge("Disconnected");
    resetResult(error.message);
    byId("result").setAttribute("aria-busy", "false");
  }
}

init();
