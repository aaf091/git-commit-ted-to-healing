import { useEffect, useState } from "react";
import { api } from "../api";
import { Badge, DECISION_LABEL, Spinner } from "./ui";

// The eligibility output table — one row per patient, the literal deliverable.
// Click a row to open the biller detail panel.
export default function DataTable({ onSelect, selectedId }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");

  useEffect(() => {
    api.patients().then((r) => setRows(r.rows)).catch(() => setRows([])).finally(() => setLoading(false));
  }, []);

  if (loading) return <Spinner />;
  if (rows.length === 0)
    return <p className="text-sm text-slate-400 text-center py-10">No data synced yet.</p>;

  const filtered = q
    ? rows.filter((r) => JSON.stringify(r).toLowerCase().includes(q.toLowerCase()))
    : rows;

  const cell = (v) => (v == null || v === "" ? "—" : String(v));

  return (
    <div className="rounded-xl border border-slate-200 bg-white overflow-hidden h-full flex flex-col">
      <div className="p-3 border-b border-slate-100 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-700">
          Eligibility table <span className="text-slate-400 font-normal">({filtered.length})</span>
        </h2>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search…"
          className="text-xs rounded-md border border-slate-200 px-2 py-1 w-48"
        />
      </div>
      <div className="overflow-auto flex-1">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 sticky top-0">
            <tr className="text-left text-slate-500">
              {["Patient", "ID", "Decision", "Wound", "L×W×D", "Drainage", "Part B"].map((h) => (
                <th key={h} className="font-medium px-3 py-2 whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {filtered.map((r) => {
              const w = r.wound || {};
              return (
                <tr
                  key={r.row_id}
                  onClick={() => onSelect?.(r.row_id)}
                  className={`cursor-pointer hover:bg-slate-50 ${selectedId === r.row_id ? "bg-sky-50" : ""}`}
                >
                  <td className="px-3 py-1.5 text-slate-700 whitespace-nowrap">{cell(r.name)}</td>
                  <td className="px-3 py-1.5 text-slate-400 font-mono text-xs">{cell(r.patient_id)}</td>
                  <td className="px-3 py-1.5"><Badge tone={r.decision}>{DECISION_LABEL[r.decision]}</Badge></td>
                  <td className="px-3 py-1.5 text-slate-600 whitespace-nowrap">{cell(w.wound_type)}</td>
                  <td className="px-3 py-1.5 text-slate-600 tabular-nums whitespace-nowrap">
                    {cell(w.length_cm)}×{cell(w.width_cm)}×{cell(w.depth_cm)}
                  </td>
                  <td className="px-3 py-1.5 text-slate-600">{cell(w.drainage_amount)}</td>
                  <td className="px-3 py-1.5">{r.part_b_active ? "✓" : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
