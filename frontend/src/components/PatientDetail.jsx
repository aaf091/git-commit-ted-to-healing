import { useEffect, useState } from "react";
import { api } from "../api";
import { Badge, Confidence, Spinner } from "./ui";

// Detail page + evidence panel. Selecting a queue item loads the full record
// and EVERY flag attached to it, each with its evidence — the "why", not "AI says so".
// Each flag also carries a review workflow (resolve/dismiss/confirm) and an
// optional AI-drafted suggestion (deterministic evidence stays the source of truth).
export default function PatientDetail({ rowId, onChanged }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  function load() {
    if (!rowId) return;
    setLoading(true);
    api.record(rowId).then(setData).catch(() => setData(null)).finally(() => setLoading(false));
  }

  useEffect(load, [rowId]);

  if (!rowId)
    return (
      <div className="rounded-xl border border-slate-200 bg-white h-full flex items-center justify-center">
        <p className="text-sm text-slate-400">Select an issue to see the record + evidence</p>
      </div>
    );

  if (loading) return <div className="rounded-xl border border-slate-200 bg-white h-full"><Spinner /></div>;
  if (!data) return null;

  const r = data.record;
  const name = `${r.first_name || ""} ${r.last_name || ""}`.trim() || r.patient_id || rowId;
  const fields = Object.entries(r).filter(([k]) => !k.startsWith("_"));

  function afterChange() {
    load();          // refresh this record's flags
    onChanged?.();   // let parent refresh stats + queue
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white h-full flex flex-col overflow-hidden">
      <div className="p-4 border-b border-slate-100">
        <h2 className="text-base font-semibold text-slate-800">{name}</h2>
        <p className="text-xs text-slate-400 font-mono">{r._row_id} · {r.patient_id}</p>
      </div>

      <div className="overflow-y-auto flex-1 p-4 space-y-5">
        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-2">
            Why this was flagged ({data.flags.length})
          </h3>
          <div className="space-y-2">
            {data.flags.length === 0 && (
              <p className="text-sm text-slate-400">No issues on this record.</p>
            )}
            {data.flags.map((f) => (
              <FlagCard key={f.flag_id} flag={f} onChange={afterChange} />
            ))}
          </div>
        </section>

        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-2">
            Record (normalized)
          </h3>
          <div className="rounded-lg border border-slate-200 divide-y divide-slate-100">
            {fields.map(([k, v]) => (
              <div key={k} className="flex justify-between gap-4 px-3 py-1.5 text-sm">
                <span className="text-slate-400">{k}</span>
                <span className="font-medium text-slate-700 text-right truncate">
                  {String(v ?? "—")}
                </span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

const STATUS_TONE = {
  open: "slate",
  resolved: "revenue",
  dismissed: "low",
  confirmed: "compliance",
};

function FlagCard({ flag, onChange }) {
  const [busy, setBusy] = useState(false);
  const [ai, setAi] = useState(null);
  const [aiLoading, setAiLoading] = useState(false);
  const status = flag.status || "open";

  async function setStatus(next) {
    setBusy(true);
    try {
      await api.setStatus(flag.flag_id, next);
      onChange?.();
    } finally {
      setBusy(false);
    }
  }

  async function getSuggestion() {
    setAiLoading(true);
    try {
      setAi(await api.explain(flag.flag_id));
    } catch (e) {
      setAi({ explanation: "", suggested_action: "AI request failed.", source: "fallback" });
    } finally {
      setAiLoading(false);
    }
  }

  const resolved = status === "resolved" || status === "dismissed";

  return (
    <div className={`rounded-lg border p-3 ${resolved ? "border-slate-200 bg-slate-50/60 opacity-80" : "border-slate-200"}`}>
      <div className="flex items-center justify-between gap-2 mb-1">
        <span className="text-sm font-medium text-slate-800">{flag.label}</span>
        <div className="flex items-center gap-2">
          <Badge tone={flag.severity}>{flag.severity}</Badge>
          <Confidence value={flag.confidence} />
        </div>
      </div>
      <p className="text-xs text-slate-500 mb-2">{flag.explanation}</p>

      <div className="rounded-md bg-slate-50 p-2 grid grid-cols-2 gap-x-4 gap-y-1 mb-2">
        {flag.evidence.map((e, i) => (
          <div key={i} className="flex justify-between gap-2 text-xs">
            <span className="text-slate-400">{e.field}</span>
            <span className="font-medium text-slate-700 truncate">{String(e.value ?? "—")}</span>
          </div>
        ))}
      </div>

      {/* AI suggestion (clearly assistive; evidence above is the source of truth) */}
      {ai && (
        <div className="rounded-md border border-violet-200 bg-violet-50 p-2 mb-2 text-xs">
          <div className="flex items-center gap-1 font-semibold text-violet-700 mb-1">
            ✨ AI suggestion
            <span className="font-normal text-violet-400">
              ({ai.source === "llm" ? `${ai.model}` : "templated fallback"})
            </span>
          </div>
          {ai.explanation && <p className="text-slate-600 mb-1">{ai.explanation}</p>}
          <p className="text-slate-700"><b>Next:</b> {ai.suggested_action}</p>
        </div>
      )}

      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <Badge tone={STATUS_TONE[status]}>{status}</Badge>
          {flag.related_row_ids?.length > 0 && (
            <span className="text-xs text-slate-400">↔ {flag.related_row_ids.length} linked</span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={getSuggestion}
            disabled={aiLoading}
            className="text-xs rounded-md border border-violet-200 text-violet-700 px-2 py-1 hover:bg-violet-50 disabled:opacity-50"
          >
            {aiLoading ? "…" : ai ? "↻ AI" : "✨ Suggest"}
          </button>
          <ActionBtn label="Resolve" tone="emerald" disabled={busy} onClick={() => setStatus("resolved")} />
          <ActionBtn label="Dismiss" tone="slate" disabled={busy} onClick={() => setStatus("dismissed")} />
          {status !== "open" && (
            <ActionBtn label="Reopen" tone="amber" disabled={busy} onClick={() => setStatus("open")} />
          )}
        </div>
      </div>
    </div>
  );
}

function ActionBtn({ label, tone, onClick, disabled }) {
  const tones = {
    emerald: "border-emerald-200 text-emerald-700 hover:bg-emerald-50",
    slate: "border-slate-200 text-slate-600 hover:bg-slate-50",
    amber: "border-amber-200 text-amber-700 hover:bg-amber-50",
  };
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`text-xs rounded-md border px-2 py-1 disabled:opacity-50 ${tones[tone]}`}
    >
      {label}
    </button>
  );
}
