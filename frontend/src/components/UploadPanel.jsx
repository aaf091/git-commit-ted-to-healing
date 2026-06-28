import { useState } from "react";
import { api } from "../api";

// Upload step: pick a CSV/JSON, send it, then run the full pipeline.
export default function UploadPanel({ onLoaded }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  async function handleFile(file) {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const up = await api.uploadFile(file);
      await api.runPipeline(); // build flags + dedupe immediately
      setResult(up);
      onLoaded?.(up);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  async function loadDemo() {
    setBusy(true);
    setError(null);
    try {
      const up = await api.loadSample(); // server-side load + pipeline
      setResult(up);
      onLoaded?.(up);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <h2 className="text-sm font-semibold text-slate-700 mb-3">1 · Upload data</h2>

      <label
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          handleFile(e.dataTransfer.files?.[0]);
        }}
        className="flex flex-col items-center justify-center gap-1 rounded-lg border-2 border-dashed border-slate-300 bg-slate-50 px-4 py-8 text-center cursor-pointer hover:border-slate-400 transition"
      >
        <span className="text-sm text-slate-600">
          Drop a <b>CSV</b> or <b>JSON</b> file, or click to browse
        </span>
        <span className="text-xs text-slate-400">
          Columns are auto-mapped to the canonical schema
        </span>
        <input
          type="file"
          accept=".csv,.json"
          className="hidden"
          onChange={(e) => handleFile(e.target.files?.[0])}
        />
      </label>

      <div className="mt-3 flex items-center gap-2">
        <button
          onClick={loadDemo}
          disabled={busy}
          className="rounded-lg bg-slate-900 text-white text-sm font-medium px-3 py-1.5 hover:bg-slate-800 disabled:opacity-50"
        >
          ⚡ Load demo data
        </button>
        <span className="text-xs text-slate-400">
          one click — no file picker needed for the demo
        </span>
      </div>

      {busy && <p className="mt-3 text-sm text-slate-500">Processing…</p>}
      {error && (
        <p className="mt-3 text-sm text-red-600 break-words">⚠ {error}</p>
      )}

      {result && (
        <div className="mt-4 text-sm">
          <p className="text-slate-700">
            Loaded <b>{result.row_count}</b> rows from{" "}
            <span className="font-mono">{result.dataset_name}</span>
          </p>
          {result.unmapped_columns.length > 0 && (
            <p className="mt-1 text-xs text-amber-600">
              Unmapped columns (add to SCHEMA if needed):{" "}
              {result.unmapped_columns.join(", ")}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
