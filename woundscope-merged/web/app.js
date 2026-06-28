// WoundScope — production UI logic
const DEC = {
  auto_accept:    { label: "Auto-Accept",     pill: "p-accept", dot: "dot-accept" },
  flag_for_review:{ label: "Flag for Review", pill: "p-review", dot: "dot-review" },
  reject:         { label: "Reject",          pill: "p-reject", dot: "dot-reject" },
};
const DEFAULTS = () => ({
  decisions: new Set(Object.keys(DEC)), facility: "all", status: "", minConf: 0, search: "",
});
const state = { all: [], summary: null, selected: null, showPHI: false, ...DEFAULTS() };
const $ = (s) => document.querySelector(s);

async function boot() {
  try {
    state.summary = await (await fetch("/api/summary")).json();
    state.all = await (await fetch("/api/results")).json();
  } catch (e) {
    $("#queue").innerHTML = `<div class="error">⚠ Can't reach the backend.<br>Run <code>python3.13 run.py all</code> then restart the server.</div>`;
    $("#live-count").textContent = "offline";
    return;
  }
  $("#live-count").textContent = `${state.all.length} patients live`;
  if (localStorage.getItem("ws_onboard_dismissed")) $("#onboard").style.display = "none";
  renderKpis(); renderSeg(); renderFacilities(); bindToolbar(); bindHelp(); render();
}

// ---- PHI (HIPAA minimum-necessary) ----
const maskName = (n) => state.showPHI ? n : n.split(/\s+/).map(p => (p[0]||"") + "•••").join(" ");
const maskId = (p) => state.showPHI ? p : p.replace(/\d/g, "•");

function renderKpis() {
  const s = state.summary;
  $("#kpis").innerHTML = `
    <div class="kpi"><div class="n">${s.total}</div><div class="l">Patients evaluated</div><div class="s">across ${s.facilities.length} facilities</div></div>
    <div class="kpi"><div class="n">${s.auto_accept}</div><div class="l"><span class="dot dot-accept"></span>Auto-Accept</div><div class="s">clean to bill</div></div>
    <div class="kpi"><div class="n">${s.flag_for_review}</div><div class="l"><span class="dot dot-review"></span>Flag for Review</div><div class="s">needs a human</div></div>
    <div class="kpi"><div class="n">${s.reject}</div><div class="l"><span class="dot dot-reject"></span>Reject</div><div class="s">not Part B billable</div></div>
    <div class="kpi"><div class="n">${s.part_b_pct}%</div><div class="l">Medicare Part B</div><div class="s">${s.part_b_count} of ${s.total} · ${s.billed} billed</div></div>`;
}
function renderSeg() {
  $("#decision-seg").innerHTML = Object.entries(DEC).map(([k,v]) =>
    `<button data-d="${k}" class="on" title="Toggle ${v.label}"><span class="dot ${v.dot}"></span>${v.label}</button>`).join("");
  document.querySelectorAll("#decision-seg button").forEach(b => b.onclick = () => {
    const d = b.dataset.d;
    state.decisions.has(d) ? state.decisions.delete(d) : state.decisions.add(d);
    b.classList.toggle("on", state.decisions.has(d)); render();
  });
}
function renderFacilities() {
  $("#facility").innerHTML = ['<option value="all">All facilities</option>']
    .concat(state.summary.facilities.map(f => `<option value="${f}">Facility ${f}</option>`)).join("");
}
function bindToolbar() {
  $("#search").oninput = e => { state.search = e.target.value.toLowerCase(); render(); };
  $("#facility").onchange = e => { state.facility = e.target.value; render(); };
  $("#status-filter").onchange = e => { state.status = e.target.value; render(); };
  $("#conf").oninput = e => { state.minConf = +e.target.value; $("#conf-val").textContent = state.minConf.toFixed(2); render(); };
  $("#export").onclick = exportCSV;
  $("#reset").onclick = resetFilters;
  $("#phi-toggle").onclick = togglePHI;
  $("#onboard-x").onclick = () => { $("#onboard").style.display = "none"; localStorage.setItem("ws_onboard_dismissed","1"); };
}
function bindHelp() {
  const ov = $("#overlay");
  $("#help-btn").onclick = () => ov.classList.add("show");
  $("#modal-x").onclick = () => ov.classList.remove("show");
  ov.onclick = (e) => { if (e.target === ov) ov.classList.remove("show"); };
  // patient modal close
  const pov = $("#patient-overlay");
  $("#pm-x").onclick = closePatient;
  pov.onclick = (e) => { if (e.target === pov) closePatient(); };
  document.addEventListener("keydown", e => {
    if (e.key !== "Escape") return;
    ov.classList.remove("show");
    if (pov.classList.contains("show")) closePatient();
  });
}
function togglePHI() {
  state.showPHI = !state.showPHI;
  $("#phi-state").textContent = state.showPHI ? "PHI Visible" : "PHI Masked";
  $("#phi-icon").textContent = state.showPHI ? "🔓" : "🔒";
  render();
  if (state.selected && $("#patient-overlay").classList.contains("show")) openPatient();
}
function resetFilters() {
  Object.assign(state, DEFAULTS());
  $("#search").value = ""; $("#facility").value = "all"; $("#status-filter").value = "";
  $("#conf").value = 0; $("#conf-val").textContent = "0.00";
  document.querySelectorAll("#decision-seg button").forEach(b => b.classList.add("on"));
  render();
}
const pill = (d) => `<span class="pill ${DEC[d].pill}"><span class="pdot"></span>${DEC[d].label}</span>`;

function filtered() {
  return state.all.filter(p =>
    state.decisions.has(p.decision) &&
    (state.facility === "all" || String(p.facility_id) === state.facility) &&
    (!state.status || (p.status || "open") === state.status) &&
    p.confidence >= state.minConf &&
    (!state.search || p.name.toLowerCase().includes(state.search) || p.patient_id.toLowerCase().includes(state.search)));
}

function render() {
  const rows = filtered();
  $("#queue-count").textContent = rows.length;
  if (!rows.length) { $("#queue").innerHTML = `<div class="error">No patients match the filters. <button class="reset" onclick="document.getElementById('reset').click()">Reset</button></div>`; return; }
  $("#queue").innerHTML = rows.map(p => `
    <div class="qrow ${state.selected===p.patient_id?"sel":""}" data-id="${p.patient_id}" tabindex="0" role="button">
      <div><div class="qname">${maskName(p.name)}</div><div class="qid mono">${maskId(p.patient_id)} · Fac ${p.facility_id}</div></div>
      <div>
        <div class="qmeta">${p.wound_type||"—"}${p.wound_stage?" · "+p.wound_stage:""}${p.wound_count>1?` <span class="wbadge">${p.wound_count} wounds</span>`:""}</div>
        <div class="confbar" title="confidence ${p.confidence.toFixed(2)}"><span style="width:${Math.round(p.confidence*100)}%"></span></div>
      </div>
      <div class="qend">${pill(p.decision)}${(p.status&&p.status!=="open")?`<div class="statustag">${p.status}</div>`:""}</div>
    </div>`).join("");
  document.querySelectorAll(".qrow").forEach(r => {
    const sel = () => { state.selected = r.dataset.id; render(); openPatient(); };
    r.onclick = sel;
    r.onkeydown = e => { if (e.key==="Enter"||e.key===" ") { e.preventDefault(); sel(); } };
  });
}

function closePatient() {
  $("#patient-overlay").classList.remove("show");
  state.selected = null; render();
}

const evRow = (cls, mark, t, d) => `<div class="ev ${cls}"><div class="mark">${mark}</div><div><div class="t">${t}</div><div class="d">${d}</div></div></div>`;
const measChip = (label, val) => `<div class="m ${val==null?"miss":""}"><div class="ml">${label}</div><div class="mv">${val==null?"missing":val+" cm"}</div></div>`;

function openPatient() {
  const p = state.all.find(x => x.patient_id === state.selected);
  if (!p) { closePatient(); return; }
  const reliable = !!p.wound_type && p.confidence >= 0.45;

  const log = [
    p.has_active_wound ? evRow("pass","✓","Active wound diagnosis","Active wound ICD-10 on record") : evRow("fail","✕","Active wound diagnosis","No active wound diagnosis"),
    p.has_active_mcb ? evRow("pass","✓","Active Medicare Part B","MCB coverage active") : evRow("fail","✕","Active Medicare Part B","No active Part B coverage"),
    reliable ? evRow("pass","✓","Wound reliably extracted",`${p.wound_type} · confidence ${p.confidence.toFixed(2)}`) : evRow("fail","✕","Wound reliably extracted",`Low confidence (${p.confidence.toFixed(2)}) or no type`),
    p.measurements_complete ? evRow("pass","✓","Complete measurements (L/W/D)","All three documented") : evRow("fail","✕","Complete measurements (L/W/D)","One or more missing"),
    p.drainage ? evRow("pass","✓","Drainage documented",p.drainage) : evRow("fail","✕","Drainage documented","Not documented"),
    p.confidence>=0.75 ? evRow("pass","✓","Auto-accept confidence threshold",`${p.confidence.toFixed(2)} ≥ 0.75`) : evRow("na","–","Auto-accept confidence threshold",`${p.confidence.toFixed(2)} < 0.75`),
  ].join("");

  const ev_e = Object.entries(p.evidence||{});
  const evidence = ev_e.length ? ev_e.slice(0,4).map(([k,s]) => `<div class="evi"><span class="evi-k">${k}</span><span class="evi-t">"${(s||"").slice(0,150)}"</span></div>`).join("") : "—";
  const prov = Object.entries(p.sources).length ? Object.entries(p.sources).map(([k,v]) => `<div>${k} ← ${v}</div>`).join("") : "—";
  const multi = (p.wound_count>1 && Array.isArray(p.wounds)) ?
    `<div class="sec"><h4>Wounds detected (${p.wound_count}) — bill separately</h4><div class="wounds">${p.wounds.map((w,i)=>`<div class="wound"><div class="wound-h">Wound ${i+1}${w.location?" · "+w.location:""}</div><div class="wound-d">${w.wound_type||"type —"} · ${w.length_cm??"—"}×${w.width_cm??"—"}×${w.depth_cm??"—"} cm${w.drainage_amount?" · "+(w.drainage_type||"")+" "+w.drainage_amount:""}</div></div>`).join("")}</div></div>` : "";
  const st = p.status || "open";
  const sbtn = (v,l) => `<button class="sbtn ${st===v?"active":""}" data-st="${v}">${l}</button>`;

  $("#pm-title").innerHTML = `
    <div class="pm-name">${maskName(p.name)}</div>
    <div class="pm-sub mono">${maskId(p.patient_id)} · Facility ${p.facility_id}${st!=="open"?` · <b>${st}</b>`:""}</div>
    <div class="pm-pill">${pill(p.decision)}</div>`;

  $("#pm-body").innerHTML = `
    <div class="sec"><h4>Eligibility evaluation log</h4><div class="evlog">${log}</div><div class="reason">${p.reasoning}</div></div>
    <div class="sec"><h4>Wound measurements</h4><div class="meas">${measChip("Length",p.length_cm)}${measChip("Width",p.width_cm)}${measChip("Depth",p.depth_cm)}</div></div>
    ${multi}
    <div class="sec"><h4>Biller action</h4><div class="status-row">${sbtn("open","Open")}${sbtn("billed","Mark billed")}${sbtn("dismissed","Dismiss")}</div></div>
    <details class="fold"><summary>Evidence — source text behind each value</summary><div class="body">${evidence}</div></details>
    <details class="fold"><summary>Provenance — source record per field</summary><div class="body prov">${prov}</div></details>`;

  $("#pm-body").querySelectorAll(".sbtn").forEach(b => b.onclick = () => setStatus(p.patient_id, b.dataset.st));
  $("#patient-overlay").classList.add("show");
}

async function setStatus(pid, status) {
  try {
    await fetch(`/api/patient/${pid}/status`, { method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({status}) });
    const p = state.all.find(x => x.patient_id === pid); if (p) p.status = status;
    state.summary = await (await fetch("/api/summary")).json();
    renderKpis(); render(); openPatient();
  } catch {}
}

function exportCSV() {
  const cols = ["patient_id","name","facility_id","decision","confidence","status","wound_type","wound_stage","wound_location","length_cm","width_cm","depth_cm","drainage","reasoning"];
  const esc = v => `"${String(v ?? "").replace(/"/g,'""')}"`;
  const lines = [cols.join(",")].concat(state.all.map(p => cols.map(c => esc(p[c])).join(",")));
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([lines.join("\n")], {type:"text/csv"}));
  a.download = "wound_billing_review.csv"; a.click();
}

boot();
