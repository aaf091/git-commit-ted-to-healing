import { useEffect, useState } from "react";
import { api } from "../api";

// Pipeline entrypoint. Two sources:
//   - Database: read the Stage-1 SQLite store (fast, no rate-limits) — default
//   - Live API: pull fresh from PointClickCare, retrying through its 429s
export default function SyncPanel({ facilities, onLoaded, compact }) {
  const [picked, setPicked] = useState([101]);
  const [limit, setLimit] = useState(30);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [db, setDb] = useState(null); // { available, counts }

  useEffect(() => {
    api.syncStatus().then((s) => setDb({ available: s.db_available, counts: s.db_counts || {} })).catch(() => {});
  }, []);

  function toggle(id) {
    setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  }

  async function run(fromDb) {
    if (picked.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const opts = { facility_ids: picked, limit: limit ? Number(limit) : null };
      const r = fromDb ? await api.loadDb(opts) : await api.sync(opts);
      setResult(r);
      onLoaded?.(r);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  if (compact) {
    return (
      <button
        onClick={() => run(db?.available)}
        disabled={busy}
        className="text-xs cursor-pointer rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-slate-600 hover:bg-slate-50 disabled:opacity-50"
      >
        {busy ? "Loading…" : "↻ Reload"}
      </button>
    );
  }

  const dbReady = db?.available;
  const dbTotal = dbReady ? (db.counts.patients || 0) : 0;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6">
      <h2 className="text-sm font-semibold text-slate-700 mb-1">Load patient data</h2>
      <p className="text-xs text-slate-500 mb-4">
        Read the Stage-1 database (fast, queryable) or pull fresh from the
        PointClickCare API (retries through its 30% rate-limiting).
      </p>

      <div className="space-y-3">
        <div>
          <div className="text-xs font-medium text-slate-500 mb-1.5">Facilities</div>
          <div className="flex flex-wrap gap-2">
            {(facilities || []).map((f) => (
              <button
                key={f.id}
                onClick={() => toggle(f.id)}
                className={`text-sm rounded-lg border px-3 py-1.5 ${
                  picked.includes(f.id)
                    ? "border-slate-900 bg-slate-900 text-white"
                    : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                }`}
              >
                {f.name} <span className="opacity-60">#{f.id}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <label className="text-xs font-medium text-slate-500">Patients per facility</label>
          <input
            type="number"
            min="1"
            value={limit}
            onChange={(e) => setLimit(e.target.value)}
            className="w-20 text-sm rounded-md border border-slate-200 px-2 py-1"
          />
          <span className="text-xs text-slate-400">(blank/large = all 100 — slower with 429s)</span>
        </div>

        <div className="flex items-center gap-2 pt-1">
          <button
            onClick={() => run(true)}
            disabled={busy || picked.length === 0 || !dbReady}
            title={dbReady ? "" : "No pcc_data.db found — run the Stage-1 ingester"}
            className="rounded-lg bg-slate-900 text-white text-sm font-medium px-4 py-2 hover:bg-slate-800 disabled:opacity-50"
          >
            {busy ? "Loading…" : `⚡ Load from database${dbReady ? ` (${dbTotal})` : ""}`}
          </button>
          <button
            onClick={() => run(false)}
            disabled={busy || picked.length === 0}
            className="rounded-lg border border-slate-300 text-slate-700 text-sm font-medium px-4 py-2 hover:bg-slate-50 disabled:opacity-50"
          >
            {busy ? "…" : "↻ Pull live from API"}
          </button>
        </div>
        {dbReady ? (
          <p className="text-[11px] text-slate-400">
            Database ready: {dbTotal} patients, {db.counts.progress_notes || 0} notes,{" "}
            {db.counts.assessments || 0} assessments.
          </p>
        ) : (
          <p className="text-[11px] text-amber-500">No database found — use “Pull live from API”.</p>
        )}
      </div>

      {error && <p className="mt-3 text-sm text-red-600 break-words">⚠ {error}</p>}

      {result && (
        <div className="mt-4 text-sm text-slate-700">
          Loaded <b>{result.patient_count}</b> patients ·{" "}
          {result.source === "database" ? (
            <span className="text-slate-500">from the Stage-1 database (no rate-limits)</span>
          ) : (
            <span className="text-slate-500">
              {result.api_stats.requests} API calls,{" "}
              <b className="text-amber-600">{result.api_stats.rate_limited}</b> rate-limits absorbed
            </span>
          )}
        </div>
      )}
    </div>
  );
}
