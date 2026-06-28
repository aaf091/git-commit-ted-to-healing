import { useEffect, useState } from "react";
import { api } from "../api";
import { Badge, Confidence, DECISION_LABEL, Spinner } from "./ui";

// Biller view: why this patient got this routing decision, with every field
// traceable back to the coverage / diagnosis / note / assessment it came from.
export default function PatientDetail({ rowId, onChanged }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [ai, setAi] = useState(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [busy, setBusy] = useState(false);

  function load() {
    if (!rowId) return;
    setLoading(true);
    setAi(null);
    api.patient(rowId).then(setData).catch(() => setData(null)).finally(() => setLoading(false));
  }
  useEffect(load, [rowId]);

  if (!rowId)
    return (
      <div className="rounded-xl border border-slate-200 bg-white h-full flex items-center justify-center">
        <p className="text-sm text-slate-400">Select a patient to see the routing decision + evidence</p>
      </div>
    );
  if (loading) return <div className="rounded-xl border border-slate-200 bg-white h-full"><Spinner /></div>;
  if (!data) return null;

  const d = data.decision;
  const w = d.wound || {};

  async function setStatus(status) {
    setBusy(true);
    try { await api.setStatus(rowId, status); load(); onChanged?.(); }
    finally { setBusy(false); }
  }
  async function getAI() {
    setAiLoading(true);
    try { setAi(await api.explain(rowId)); }
    catch { setAi({ narrative: "", next_action: "AI request failed.", source: "fallback" }); }
    finally { setAiLoading(false); }
  }

  const measRow = (k, label) => {
    const present = w[k] != null && w[k] !== "";
    return (
      <div className={`rounded-md border px-2 py-1.5 text-center ${present ? "border-slate-200" : "border-red-200 bg-red-50"}`}>
        <div className="text-[10px] uppercase tracking-wide text-slate-400">{label}</div>
        <div className={`text-sm font-semibold ${present ? "text-slate-800" : "text-red-400"}`}>
          {present ? w[k] : "missing"}
        </div>
      </div>
    );
  };

  return (
    <div className="rounded-xl border border-slate-200 bg-white h-full flex flex-col overflow-hidden">
      <div className="p-4 border-b border-slate-100">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-base font-semibold text-slate-800">{d.name}</h2>
          <Badge tone={d.decision}>{DECISION_LABEL[d.decision]}</Badge>
        </div>
        <p className="text-xs text-slate-400 font-mono">
          {d.patient_id} · facility {d.facility_id} · {d.gender} · DOB {d.birth_date}
        </p>
      </div>

      <div className="overflow-y-auto flex-1 p-4 space-y-5">
        {/* Decision + reasoning */}
        <section>
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Decision</h3>
            <Confidence value={d.confidence} />
          </div>
          <p className="text-sm text-slate-700 mb-2">{d.reasoning}</p>
          <div className="space-y-1">
            {d.reasons.map((r, i) => (
              <div key={i} className="flex items-start gap-2 text-xs">
                <span className={r.ok ? "text-emerald-600" : "text-red-500"}>{r.ok ? "✓" : "✗"}</span>
                <span className="text-slate-600">{r.text}</span>
              </div>
            ))}
          </div>
        </section>

        {/* AI narrative (assistive) */}
        <section>
          {ai ? (
            <div className="rounded-md border border-violet-200 bg-violet-50 p-2.5 text-xs">
              <div className="flex items-center gap-1 font-semibold text-violet-700 mb-1">
                ✨ AI summary for the biller
                <span className="font-normal text-violet-400">
                  ({ai.source === "llm" ? ai.model : "deterministic fallback"})
                </span>
              </div>
              {ai.narrative && <p className="text-slate-600 mb-1">{ai.narrative}</p>}
              <p className="text-slate-700"><b>Next:</b> {ai.next_action}</p>
            </div>
          ) : (
            <button
              onClick={getAI}
              disabled={aiLoading}
              className="text-xs rounded-md border border-violet-200 text-violet-700 px-2.5 py-1 hover:bg-violet-50 disabled:opacity-50"
            >
              {aiLoading ? "…" : "✨ Explain for biller"}
            </button>
          )}
        </section>

        {/* Multi-wound banner + list */}
        {d.wound_count > 1 && (
          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-2">
              {d.wound_count} wounds documented
            </h3>
            <p className="text-[11px] text-slate-400 mb-2">
              Routing on the best-documented wound; all wounds shown below.
            </p>
            <div className="space-y-1.5">
              {(d.wounds || []).map((w, i) => {
                const isPrimary =
                  w.location === d.wound.location && w.length_cm === d.wound.length_cm;
                return (
                  <div key={i}
                    className={`rounded-md border px-2.5 py-1.5 text-xs flex items-center justify-between ${
                      isPrimary ? "border-slate-300 bg-slate-50" : "border-slate-200"
                    }`}>
                    <span className="text-slate-700">
                      {isPrimary && <span className="text-emerald-600 mr-1">★</span>}
                      {w.wound_type || "unspecified"}{" "}
                      <span className="text-slate-400">@ {w.location || "site n/a"}</span>
                    </span>
                    <span className="tabular-nums text-slate-500">
                      {w.length_cm ?? "—"}×{w.width_cm ?? "—"}×{w.depth_cm ?? "—"}cm
                      {w.drainage_amount ? ` · ${w.drainage_amount}` : ""}
                    </span>
                  </div>
                );
              })}
            </div>
          </section>
        )}

        {/* Extracted wound (primary) */}
        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-2">
            {d.wound_count > 1 ? "Primary wound (routing basis)" : "Extracted wound"}
          </h3>
          <div className="grid grid-cols-3 gap-2 mb-2">
            {measRow("length_cm", "Length")}
            {measRow("width_cm", "Width")}
            {measRow("depth_cm", "Depth")}
          </div>
          <div className="rounded-lg border border-slate-200 divide-y divide-slate-100">
            <KV k="Wound type" v={w.wound_type} />
            <KV k="Stage" v={w.stage} />
            <KV k="Location" v={w.location} />
            <KV k="Drainage" v={[w.drainage_amount, w.drainage_type].filter(Boolean).join(" · ")} />
            <KV k="Wound source" v={d.wound_source} />
          </div>
        </section>

        {/* Source evidence — coverage, diagnoses, raw notes/assessments */}
        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-2">
            Source data (the proof)
          </h3>
          <div className="space-y-2 text-xs">
            <SrcBlock title="Coverage">
              {data.coverage.map((c, i) => (
                <div key={i} className="text-slate-600">
                  {c.payer_name} ({c.payer_code}) · {String(c.effective_from).slice(0, 10)} →{" "}
                  {c.effective_to ? String(c.effective_to).slice(0, 10) : "open"}
                </div>
              ))}
            </SrcBlock>
            <SrcBlock title="Diagnoses">
              {data.diagnoses.map((dx, i) => (
                <div key={i} className="text-slate-600">
                  <span className="font-mono">{dx.icd10_code}</span> {dx.icd10_description}{" "}
                  <Badge tone={dx.clinical_status === "active" ? "pass" : "slate"}>{dx.clinical_status}</Badge>
                </div>
              ))}
            </SrcBlock>
            <SrcBlock title={`Progress notes (${data.notes.length})`}>
              {data.notes.map((n, i) => (
                <div key={i} className="rounded bg-slate-50 p-2 text-slate-600 whitespace-pre-wrap">
                  <span className="text-slate-400">[{n.note_type}] </span>{n.note_text}
                </div>
              ))}
            </SrcBlock>
            <SrcBlock title={`Assessments (${data.assessments.length})`}>
              {data.assessments.map((a, i) => (
                <div key={i} className="text-slate-500">
                  {a.assessment_type} · {a.status} · {a.assessment_date}
                </div>
              ))}
            </SrcBlock>
          </div>
        </section>
      </div>

      {/* Actions */}
      <div className="p-3 border-t border-slate-100 flex items-center justify-between">
        <Badge tone={d.status}>{d.status}</Badge>
        <div className="flex gap-1.5">
          <Act label="Mark billed" tone="emerald" disabled={busy} onClick={() => setStatus("billed")} />
          <Act label="Dismiss" tone="slate" disabled={busy} onClick={() => setStatus("dismissed")} />
          {d.status !== "open" && <Act label="Reopen" tone="amber" disabled={busy} onClick={() => setStatus("open")} />}
        </div>
      </div>
    </div>
  );
}

function KV({ k, v }) {
  return (
    <div className="flex justify-between gap-4 px-3 py-1.5 text-sm">
      <span className="text-slate-400">{k}</span>
      <span className="font-medium text-slate-700 text-right">{v || "—"}</span>
    </div>
  );
}

function SrcBlock({ title, children }) {
  const has = Array.isArray(children) ? children.length > 0 : !!children;
  return (
    <div>
      <div className="font-medium text-slate-500 mb-1">{title}</div>
      {has ? <div className="space-y-1">{children}</div> : <div className="text-slate-300">none</div>}
    </div>
  );
}

function Act({ label, tone, onClick, disabled }) {
  const tones = {
    emerald: "border-emerald-200 text-emerald-700 hover:bg-emerald-50",
    slate: "border-slate-200 text-slate-600 hover:bg-slate-50",
    amber: "border-amber-200 text-amber-700 hover:bg-amber-50",
  };
  return (
    <button onClick={onClick} disabled={disabled}
      className={`text-xs rounded-md border px-2.5 py-1 disabled:opacity-50 ${tones[tone]}`}>
      {label}
    </button>
  );
}
