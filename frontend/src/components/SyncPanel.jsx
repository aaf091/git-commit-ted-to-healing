import { useState } from "react";
import { api } from "../api";

// Pipeline entrypoint: pull from the PointClickCare API. Pick facilities, cap
// patients for a fast demo, and watch the rate-limit stats prove the retry logic.
export default function SyncPanel({ facilities, onLoaded, compact }) {
  const [picked, setPicked] = useState([101]);
  const [limit, setLimit] = useState(30);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  function toggle(id) {
    setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  }

  async function runSync() {
    if (picked.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api.sync({
        facility_ids: picked,
        limit: limit ? Number(limit) : null,
      });
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
        onClick={runSync}
        disabled={busy}
        className="text-xs cursor-pointer rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-slate-600 hover:bg-slate-50 disabled:opacity-50"
      >
        {busy ? "Syncing…" : "↻ Re-sync"}
      </button>
    );
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6">
      <h2 className="text-sm font-semibold text-slate-700 mb-1">
        Sync from PointClickCare
      </h2>
      <p className="text-xs text-slate-500 mb-4">
        Pulls patients, diagnoses, coverage, notes &amp; assessments — and retries
        through the API's 30% rate-limiting automatically.
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

        <button
          onClick={runSync}
          disabled={busy || picked.length === 0}
          className="rounded-lg bg-slate-900 text-white text-sm font-medium px-4 py-2 hover:bg-slate-800 disabled:opacity-50"
        >
          {busy ? "Syncing… (retrying through rate limits)" : "⚡ Run sync"}
        </button>
      </div>

      {error && <p className="mt-3 text-sm text-red-600 break-words">⚠ {error}</p>}

      {result && (
        <div className="mt-4 text-sm text-slate-700">
          Synced <b>{result.patient_count}</b> patients ·{" "}
          <span className="text-slate-500">
            {result.api_stats.requests} API calls,{" "}
            <b className="text-amber-600">{result.api_stats.rate_limited}</b> rate-limits absorbed
          </span>
        </div>
      )}
    </div>
  );
}
