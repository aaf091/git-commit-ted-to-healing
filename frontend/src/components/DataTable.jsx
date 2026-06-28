import { useEffect, useState } from "react";
import { api } from "../api";
import { Spinner } from "./ui";

// Raw table view of all cleaned records. A quick "here's the structured data"
// tab. Click a row to inspect it in the detail panel.
export default function DataTable({ onSelect, selectedRowId }) {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");

  useEffect(() => {
    api.records().then((r) => setRecords(r.records)).catch(() => setRecords([])).finally(() => setLoading(false));
  }, []);

  if (loading) return <Spinner />;
  if (records.length === 0)
    return <p className="text-sm text-slate-400 text-center py-10">No data uploaded yet.</p>;

  const cols = Object.keys(records[0]).filter((c) => c !== "_row_id").slice(0, 9);
  const filtered = q
    ? records.filter((r) => JSON.stringify(r).toLowerCase().includes(q.toLowerCase()))
    : records;

  return (
    <div className="rounded-xl border border-slate-200 bg-white overflow-hidden">
      <div className="p-3 border-b border-slate-100 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-700">
          Records <span className="text-slate-400 font-normal">({filtered.length})</span>
        </h2>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search…"
          className="text-xs rounded-md border border-slate-200 px-2 py-1 w-48"
        />
      </div>
      <div className="overflow-auto max-h-[70vh]">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 sticky top-0">
            <tr>
              {cols.map((c) => (
                <th key={c} className="text-left font-medium text-slate-500 px-3 py-2 whitespace-nowrap">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {filtered.slice(0, 300).map((r) => (
              <tr
                key={r._row_id}
                onClick={() => onSelect?.(r._row_id)}
                className={`cursor-pointer hover:bg-slate-50 ${
                  selectedRowId === r._row_id ? "bg-sky-50" : ""
                }`}
              >
                {cols.map((c) => (
                  <td key={c} className="px-3 py-1.5 text-slate-700 whitespace-nowrap max-w-[160px] truncate">
                    {String(r[c] ?? "—")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
