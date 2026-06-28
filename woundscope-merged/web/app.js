// WoundScope frontend — ABI-style eligibility console.
const DEC = {
  auto_accept:   { label: "Auto-Accept",     pill: "p-accept", dot: "dot-accept" },
  flag_for_review:{ label: "Flag for Review", pill: "p-review", dot: "dot-review" },
  reject:        { label: "Reject",          pill: "p-reject", dot: "dot-reject" },
};

const state = {
  all: [], summary: null,
  decisions: new Set(["auto_accept", "flag_for_review", "reject"]),
  facility: "all", minConf: 0, search: "", selected: null,
  showPHI: false,            // HIPAA minimum-necessary: PHI masked by default
};

const $ = (s) => document.querySelector(s);

async function boot() {
  state.summary = await (await fetch("/api/summary")).json();
  state.all = await (await fetch("/api/results")).json();
  renderKpis(); renderChips(); renderFacilities();
  bindToolbar();
  render();
}

// ---- PHI handling (HIPAA) ----
function maskName(name) {
  if (state.showPHI) return name;
  // show initials only — minimum necessary
  return name.split(/\s+/).map(p => (p[0] || "") + "•••").join(" ");
}
function maskId(pid) {
  if (state.showPHI) return pid;
  return pid.replace(/\d/g, "•");
}

function renderKpis() {
  const s = state.summary;
  $("#kpis").innerHTML = `
    <div class="kpi"><div class="n">${s.total}</div><div class="l">Patients evaluated</div></div>
    <div class="kpi"><div class="n">${s.auto_accept}</div><div class="l"><span class="dot dot-accept"></span>Auto-Accept</div></div>
    <div class="kpi"><div class="n">${s.flag_for_review}</div><div class="l"><span class="dot dot-review"></span>Flag for Review</div></div>
    <div class="kpi"><div class="n">${s.reject}</div><div class="l"><span class="dot dot-reject"></span>Reject</div></div>`;
}

function renderChips() {
  $("#decision-chips").innerHTML = Object.entries(DEC).map(([k, v]) =>
    `<span class="chip" data-d="${k}"><span class="dot ${v.dot}"></span>${v.label}</span>`).join("");
  document.querySelectorAll(".chip").forEach(c => c.onclick = () => {
    const d = c.dataset.d;
    state.decisions.has(d) ? state.decisions.delete(d) : state.decisions.add(d);
    c.classList.toggle("off", !state.decisions.has(d));
    render();
  });
}

function renderFacilities() {
  const opts = ['<option value="all">All facilities</option>']
    .concat(state.summary.facilities.map(f => `<option value="${f}">Facility ${f}</option>`));
  $("#facility").innerHTML = opts.join("");
}

function bindToolbar() {
  $("#search").oninput = (e) => { state.search = e.target.value.toLowerCase(); render(); };
  $("#facility").onchange = (e) => { state.facility = e.target.value; render(); };
  $("#conf").oninput = (e) => {
    state.minConf = parseFloat(e.target.value);
    $("#conf-val").textContent = state.minConf.toFixed(2); render();
  };
  $("#export").onclick = exportCSV;
  $("#phi-toggle").onclick = () => {
    state.showPHI = !state.showPHI;
    $("#phi-state").textContent = state.showPHI ? "PHI Visible" : "PHI Masked";
    $("#phi-toggle").querySelector(".lock").textContent = state.showPHI ? "🔓" : "🔒";
    render(); renderDetail();
  };
}

function filtered() {
  return state.all.filter(p =>
    state.decisions.has(p.decision) &&
    (state.facility === "all" || String(p.facility_id) === state.facility) &&
    p.confidence >= state.minConf &&
    (!state.search || p.name.toLowerCase().includes(state.search)
      || p.patient_id.toLowerCase().includes(state.search)));
}

function pill(d) {
  return `<span class="pill ${DEC[d].pill}"><span class="pdot"></span>${DEC[d].label}</span>`;
}

function render() {
  const rows = filtered();
  $("#queue-count").textContent = rows.length;
  $("#queue").innerHTML = rows.map(p => `
    <div class="qrow ${state.selected === p.patient_id ? "sel" : ""}" data-id="${p.patient_id}">
      <div>
        <div class="qname">${maskName(p.name)}</div>
        <div class="qid">${maskId(p.patient_id)} · Fac ${p.facility_id}</div>
      </div>
      <div>
        <div class="qmeta">${p.wound_type || "—"}${p.wound_stage ? " · " + p.wound_stage : ""}${p.wound_count > 1 ? ` <span class="wbadge">${p.wound_count} wounds</span>` : ""}</div>
        <div class="confbar"><span style="width:${Math.round(p.confidence*100)}%"></span></div>
      </div>
      <div style="text-align:right">${pill(p.decision)}</div>
    </div>`).join("") || `<div class="detail-empty">No patients match the filters.</div>`;

  document.querySelectorAll(".qrow").forEach(r =>
    r.onclick = () => { state.selected = r.dataset.id; render(); renderDetail(); });
  if (state.selected && !rows.find(p => p.patient_id === state.selected)) {
    state.selected = null; renderDetail();
  }
}

function ev(stateCls, mark, title, detail) {
  return `<div class="ev ${stateCls}"><div class="mark">${mark}</div>
    <div><div class="t">${title}</div><div class="d">${detail}</div></div></div>`;
}

function renderDetail() {
  const p = state.all.find(x => x.patient_id === state.selected);
  const el = $("#detail");
  if (!p) { el.innerHTML = `<div class="detail-empty">Select a patient to see the eligibility evaluation log.</div>`; return; }

  const m = `${p.length_cm ?? "—"} × ${p.width_cm ?? "—"} × ${p.depth_cm ?? "—"} cm`;
  const reliablyExtracted = !!p.wound_type && p.confidence >= 0.45;

  const log = [
    p.has_active_wound ? ev("pass","✓","Active wound diagnosis","Active wound ICD-10 on record")
                       : ev("fail","✕","Active wound diagnosis","No active wound diagnosis"),
    p.has_active_mcb   ? ev("pass","✓","Active Medicare Part B","MCB coverage active")
                       : ev("fail","✕","Active Medicare Part B","No active Part B coverage"),
    reliablyExtracted  ? ev("pass","✓","Wound reliably extracted",`${p.wound_type} · confidence ${p.confidence.toFixed(2)}`)
                       : ev("fail","✕","Wound reliably extracted",`Low confidence (${p.confidence.toFixed(2)}) or no type`),
    p.measurements_complete ? ev("pass","✓","Complete measurements (L/W/D)",m)
                            : ev("fail","✕","Complete measurements (L/W/D)",`Incomplete: ${m}`),
    p.drainage ? ev("pass","✓","Drainage documented",p.drainage)
               : ev("fail","✕","Drainage documented","Not documented"),
    p.confidence >= 0.75 ? ev("pass","✓","Auto-accept confidence threshold",`${p.confidence.toFixed(2)} ≥ 0.75`)
                         : ev("na","–","Auto-accept confidence threshold",`${p.confidence.toFixed(2)} < 0.75`),
  ].join("");

  const prov = Object.entries(p.sources).length
    ? Object.entries(p.sources).map(([k,v]) => `<div>${k} ← ${v}</div>`).join("")
    : "<div>—</div>";

  // evidence: the actual source text behind each extracted field
  const ev_entries = Object.entries(p.evidence || {});
  const evidence = ev_entries.length
    ? ev_entries.slice(0, 4).map(([k, snip]) =>
        `<div class="evi"><span class="evi-k">${k}</span><span class="evi-t">"${(snip||"").slice(0,160)}"</span></div>`).join("")
    : `<div class="evi"><span class="evi-t">—</span></div>`;

  // multi-wound list
  const multi = (p.wound_count > 1 && Array.isArray(p.wounds))
    ? `<div class="section-label">Wounds detected (${p.wound_count}) — bill separately</div>
       <div class="wounds">${p.wounds.map((w,i) => `
         <div class="wound"><div class="wound-h">Wound ${i+1}${w.location ? " · " + w.location : ""}</div>
         <div class="wound-d">${w.wound_type || "type —"} · ${w.length_cm ?? "—"}×${w.width_cm ?? "—"}×${w.depth_cm ?? "—"} cm${w.drainage_amount ? " · " + (w.drainage_type||"") + " " + w.drainage_amount : ""}</div></div>`).join("")}</div>`
    : "";

  el.innerHTML = `
    <div class="d-head">
      <div>
        <div class="d-name">${maskName(p.name)}</div>
        <div class="d-sub">${maskId(p.patient_id)} · Facility ${p.facility_id}</div>
      </div>
      <div>${pill(p.decision)}</div>
    </div>

    <div class="section-label">Eligibility evaluation log</div>
    <div class="evlog">${log}</div>

    <div class="reason">${p.reasoning}</div>

    <div class="section-label">Extracted wound data</div>
    <div class="grid">
      <div class="kv"><span class="k">Type</span><span class="v">${p.wound_type||"—"}</span></div>
      <div class="kv"><span class="k">Stage</span><span class="v">${p.wound_stage||"—"}</span></div>
      <div class="kv"><span class="k">Location</span><span class="v">${p.wound_location||"—"}</span></div>
      <div class="kv"><span class="k">Measurements</span><span class="v">${m}</span></div>
      <div class="kv"><span class="k">Drainage</span><span class="v">${p.drainage||"—"}</span></div>
      <div class="kv"><span class="k">Confidence</span><span class="v">${p.confidence.toFixed(2)}</span></div>
    </div>

    ${multi}

    <div class="section-label">Evidence — source text behind each value</div>
    <div class="evidence">${evidence}</div>

    <div class="section-label">Provenance — source of each field</div>
    <div class="prov">${prov}</div>`;
}

function exportCSV() {
  const cols = ["patient_id","name","facility_id","decision","confidence","wound_type",
    "wound_stage","wound_location","length_cm","width_cm","depth_cm","drainage","reasoning"];
  const esc = (v) => `"${String(v ?? "").replace(/"/g,'""')}"`;
  const lines = [cols.join(",")].concat(
    state.all.map(p => cols.map(c => esc(p[c])).join(",")));
  const blob = new Blob([lines.join("\n")], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "wound_billing_review.csv"; a.click();
}

boot();
