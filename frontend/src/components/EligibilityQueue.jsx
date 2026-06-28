import { useEffect, useState } from "react";
import { api } from "../api";
import { Badge, Confidence, DECISION_LABEL, Spinner } from "./ui";

// The routing work list — the heart of the demo. Defaults to flag_for_review
// (the items that actually need a human), filterable by decision/facility/status.
export default function EligibilityQueue({ onSelect, selectedId, refreshKey, facilities }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ decision: "", facility_id: "", status: "" });

  useEffect(() => {
    setLoading(true);
    api
      .eligibility(filters)
      .then((r) => setRows(r.rows))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, [filters, refreshKey]);

  const set = (k) => (e) => setFilters((f) => ({ ...f, [k]: e.target.value }));

  return (
    <div className="rounded-xl border border-slate-200 bg-white flex flex-col h-full">
      <div className="flex items-center justify-between p-4 border-b border-slate-100 gap-2 flex-wrap">
        <h2 className="text-sm font-semibold text-slate-700">
          Routing decisions <span className="text-slate-400 font-normal">({rows.length})</span>
        </h2>
        <div className="flex gap-2 items-center">
          <a
            href={api.exportUrl(filters.decision)}
            className="text-xs rounded-md border border-emerald-200 text-emerald-700 px-2 py-1 hover:bg-emerald-50"
            title="Download the biller worklist as CSV"
          >
            ⤓ Export
          </a>
          <Select value={filters.decision} onChange={set("decision")}
            options={[["", "All decisions"], ["auto_accept", "Auto-accept"], ["flag_for_review", "Flag for review"], ["reject", "Reject"]]} />
          <Select value={filters.facility_id} onChange={set("facility_id")}
            options={[["", "All facilities"], ...(facilities || []).map((f) => [String(f.id), f.name])]} />
          <Select value={filters.status} onChange={set("status")}
            options={[["", "Any status"], ["open", "Open"], ["billed", "Billed"], ["dismissed", "Dismissed"]]} />
        </div>
      </div>

      <div className="overflow-y-auto flex-1 divide-y divide-slate-100">
        {loading ? (
          <Spinner />
        ) : rows.length === 0 ? (
          <p className="text-sm text-slate-400 text-center py-10">No patients match.</p>
        ) : (
          rows.map((r) => (
            <button
              key={r.row_id}
              onClick={() => onSelect?.(r.row_id)}
              className={`w-full text-left px-4 py-3 hover:bg-slate-50 transition flex flex-col gap-1.5 ${
                selectedId === r.row_id ? "bg-sky-50" : ""
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-medium text-slate-800">
                  {r.name} <span className="text-slate-400 font-mono text-xs">{r.patient_id}</span>
                </span>
                <Badge tone={r.decision}>{DECISION_LABEL[r.decision]}</Badge>
              </div>
              <p className="text-xs text-slate-500 line-clamp-2">{r.reasoning}</p>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 text-xs text-slate-400">
                  <span>{r.wound?.wound_type || "no wound type"}</span>
                  {r.status !== "open" && <Badge tone={r.status}>{r.status}</Badge>}
                </div>
                <Confidence value={r.confidence} />
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  );
}

function Select({ value, onChange, options }) {
  return (
    <select
      value={value}
      onChange={onChange}
      className="text-xs rounded-md border border-slate-200 bg-white px-2 py-1 text-slate-600"
    >
      {options.map(([v, l]) => (
        <option key={v} value={v}>{l}</option>
      ))}
    </select>
  );
}
