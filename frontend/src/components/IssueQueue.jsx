import { useEffect, useState } from "react";
import { api } from "../api";
import { Badge, Confidence, Spinner } from "./ui";

// The prioritized review queue — the heart of the demo.
// Sorted server-side by severity then confidence. Filter by severity/category/type.
export default function IssueQueue({ onSelect, selectedRowId, refreshKey }) {
  const [flags, setFlags] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ severity: "", category: "", type: "", status: "open" });

  useEffect(() => {
    setLoading(true);
    api
      .flags(filters)
      .then((r) => setFlags(r.flags))
      .catch(() => setFlags([]))
      .finally(() => setLoading(false));
  }, [filters, refreshKey]);

  const set = (k) => (e) => setFilters((f) => ({ ...f, [k]: e.target.value }));

  return (
    <div className="rounded-xl border border-slate-200 bg-white flex flex-col h-full">
      <div className="flex items-center justify-between p-4 border-b border-slate-100">
        <h2 className="text-sm font-semibold text-slate-700">
          Issue queue{" "}
          <span className="text-slate-400 font-normal">({flags.length})</span>
        </h2>
        <div className="flex gap-2 items-center">
          <a
            href={api.exportUrl(filters.status)}
            className="text-xs rounded-md border border-emerald-200 text-emerald-700 px-2 py-1 hover:bg-emerald-50"
            title="Download the current worklist as CSV"
          >
            ⤓ Export CSV
          </a>
          <Select value={filters.severity} onChange={set("severity")}
            options={[["", "All severity"], ["high", "High"], ["medium", "Medium"], ["low", "Low"]]} />
          <Select value={filters.category} onChange={set("category")}
            options={[["", "All categories"], ["revenue", "Revenue"], ["compliance", "Compliance"], ["duplicate", "Duplicate"], ["data_quality", "Data quality"]]} />
          <Select value={filters.type} onChange={set("type")}
            options={[["", "All types"], ["rule", "Rule"], ["duplicate", "Duplicate"]]} />
          <Select value={filters.status} onChange={set("status")}
            options={[["open", "Open"], ["resolved", "Resolved"], ["dismissed", "Dismissed"], ["confirmed", "Confirmed"], ["", "All statuses"]]} />
        </div>
      </div>

      <div className="overflow-y-auto flex-1 divide-y divide-slate-100">
        {loading ? (
          <Spinner />
        ) : flags.length === 0 ? (
          <p className="text-sm text-slate-400 text-center py-10">No issues match.</p>
        ) : (
          flags.map((f) => (
            <button
              key={f.flag_id}
              onClick={() => onSelect?.(f.row_id)}
              className={`w-full text-left px-4 py-3 hover:bg-slate-50 transition flex flex-col gap-1.5 ${
                selectedRowId === f.row_id ? "bg-sky-50" : ""
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-medium text-slate-800">{f.label}</span>
                <Badge tone={f.severity}>{f.severity}</Badge>
              </div>
              <p className="text-xs text-slate-500 line-clamp-2">{f.explanation}</p>
              <div className="flex items-center justify-between">
                <Badge tone={f.category}>{f.category}</Badge>
                <Confidence value={f.confidence} />
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
