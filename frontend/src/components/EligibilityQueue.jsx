import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { DecisionPill, ConfidenceBar, DECISION_LABEL, Badge, Spinner, maskName, maskId } from "./ui";

// The routing work list — the heart of the demo. Search by name/ID, filter by
// decision (pills), facility, and a minimum-confidence slider.
export default function EligibilityQueue({ onSelect, selectedId, refreshKey, facilities, masked }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [decision, setDecision] = useState("");
  const [facilityId, setFacilityId] = useState("");
  const [minConf, setMinConf] = useState(0);
  const [q, setQ] = useState("");

  useEffect(() => {
    setLoading(true);
    api
      .eligibility({ decision, facility_id: facilityId, min_confidence: minConf })
      .then((r) => setRows(r.rows))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, [decision, facilityId, minConf, refreshKey]);

  // Search is client-side over name + patient ID (always on the real values, so
  // a biller can find a patient even while PHI is masked on screen).
  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return rows;
    return rows.filter(
      (r) =>
        String(r.name || "").toLowerCase().includes(needle) ||
        String(r.patient_id || "").toLowerCase().includes(needle)
    );
  }, [rows, q]);

  const toggleDecision = (key) => setDecision((d) => (d === key ? "" : key));

  return (
    <div className="flex flex-col h-full gap-3">
      {/* Toolbar */}
      <div className="flex items-center gap-2 flex-wrap">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search patient name or ID…"
          className="flex-1 min-w-[180px] text-sm rounded-lg border border-line bg-surface px-3 py-2 text-ink placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent"
        />
        {["auto_accept", "flag_for_review", "reject"].map((key) => (
          <FilterPill key={key} active={decision === key} onClick={() => toggleDecision(key)}>
            {DECISION_LABEL[key]}
          </FilterPill>
        ))}
        <select
          value={facilityId}
          onChange={(e) => setFacilityId(e.target.value)}
          className="text-sm rounded-lg border border-line bg-surface px-2.5 py-2 text-slate-600"
        >
          <option value="">All facilities</option>
          {(facilities || []).map((f) => (
            <option key={f.id} value={String(f.id)}>{f.name}</option>
          ))}
        </select>
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <span className="whitespace-nowrap">Min confidence</span>
          <span className="tabular-nums text-slate-700 w-8">{minConf}</span>
          <input
            type="range"
            min="0"
            max="100"
            step="1"
            value={minConf}
            onChange={(e) => setMinConf(Number(e.target.value))}
            className="w-28 accent-accent"
          />
        </div>
      </div>

      {/* List */}
      <div className="rounded-xl border border-line bg-surface flex flex-col flex-1 min-h-0">
        <div className="px-4 py-2.5 border-b border-slate-100 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
          {filtered.length} Patients
        </div>
        <div className="overflow-y-auto flex-1 divide-y divide-slate-100">
          {loading ? (
            <Spinner />
          ) : filtered.length === 0 ? (
            <p className="text-sm text-slate-400 text-center py-10">No patients match.</p>
          ) : (
            filtered.map((r) => (
              <button
                key={r.row_id}
                onClick={() => onSelect?.(r.row_id)}
                className={`w-full text-left px-4 py-3 hover:bg-soft transition flex items-center gap-4 ${
                  selectedId === r.row_id ? "bg-soft" : ""
                }`}
              >
                {/* Identity */}
                <div className="w-40 shrink-0">
                  <div className="text-sm font-semibold text-ink truncate">{maskName(r.name, masked)}</div>
                  <div className="text-[11px] font-mono text-slate-400">
                    {maskId(r.patient_id, masked)} · Fac {r.facility_id}
                  </div>
                </div>
                {/* Wound + confidence */}
                <div className="flex-1 min-w-0">
                  <div className="text-xs text-slate-500 truncate mb-1.5">
                    {r.wound?.wound_type || "no wound type"}
                    {r.wound?.stage ? ` · ${r.wound.stage}` : ""}
                    {r.wound_count > 1 ? ` · ${r.wound_count} wounds` : ""}
                  </div>
                  <ConfidenceBar value={r.confidence} />
                </div>
                {/* Decision */}
                <div className="shrink-0 flex items-center gap-1.5">
                  {r.status !== "open" && <Badge tone={r.status}>{r.status}</Badge>}
                  <DecisionPill decision={r.decision} />
                </div>
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function FilterPill({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      className={`text-sm rounded-full px-3.5 py-2 border transition whitespace-nowrap ${
        active
          ? "bg-accent text-white border-accent"
          : "bg-surface text-slate-600 border-line hover:bg-soft"
      }`}
    >
      {children}
    </button>
  );
}
