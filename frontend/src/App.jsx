import { useEffect, useState } from "react";
import { api } from "./api";
import SyncPanel from "./components/SyncPanel";
import StatCards from "./components/StatCards";
import EligibilityQueue from "./components/EligibilityQueue";
import DataTable from "./components/DataTable";
import PatientDetail from "./components/PatientDetail";

export default function App() {
  const [meta, setMeta] = useState(null);
  const [stats, setStats] = useState(null);
  const [loaded, setLoaded] = useState(false);
  const [tab, setTab] = useState("queue"); // queue | table
  const [selected, setSelected] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [offline, setOffline] = useState(false);
  const [masked, setMasked] = useState(true); // PHI minimized by default
  const [autoLoading, setAutoLoading] = useState(false);

  function refreshStats() {
    api.stats().then(setStats).catch(() => setStats(null));
  }
  function handleChanged() {
    refreshStats();
    setRefreshKey((k) => k + 1);
  }
  function handleLoaded() {
    setLoaded(true);
    setSelected(null);
    refreshStats();
    setRefreshKey((k) => k + 1);
  }
  function checkBackend() {
    api.meta().then((m) => { setMeta(m); setOffline(false); }).catch(() => setOffline(true));
  }

  useEffect(() => {
    checkBackend();
    // Pick up an existing sync; otherwise auto-load from the Stage-1 DB so the
    // dashboard comes up populated (matches the "data's already here" demo flow).
    api.syncStatus().then((s) => {
      if (s.has_data) { setLoaded(true); refreshStats(); }
      else if (s.db_available) {
        setAutoLoading(true);
        api.loadDb({}).then(handleLoaded).catch(() => {}).finally(() => setAutoLoading(false));
      }
    }).catch(() => {});
    const id = setInterval(checkBackend, 5000);
    return () => clearInterval(id);
  }, []);

  const d = meta?.dashboard;
  const facilities = meta?.facilities || [];

  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-surface">
        <div className="max-w-[1400px] mx-auto px-6 py-3.5 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center justify-center h-8 px-2 rounded-md bg-accent text-white font-extrabold tracking-tight text-sm">
              ABI
            </span>
            <div>
              <h1 className="text-lg font-bold text-ink leading-tight">WoundScope</h1>
              <p className="text-xs text-slate-500 leading-tight">Medicare Part B Wound-Care Eligibility</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <span className="hidden md:inline text-xs text-slate-400">PointClickCare ingest · Skilled Nursing</span>
            <button
              onClick={() => setMasked((m) => !m)}
              title={masked ? "PHI is masked (minimum-necessary). Click to reveal." : "PHI is visible. Click to mask."}
              className={`inline-flex items-center gap-1.5 text-xs rounded-full px-3 py-1.5 border transition ${
                masked
                  ? "border-slate-200 text-slate-600 hover:bg-slate-50"
                  : "border-amber-300 text-amber-700 bg-amber-50 hover:bg-amber-100"
              }`}
            >
              <span>{masked ? "🔒" : "🔓"}</span>
              {masked ? "PHI Masked" : "PHI Visible"}
            </button>
            <a
              href={api.exportUrl()}
              className="text-xs font-medium rounded-lg bg-accent px-3.5 py-1.5 text-white hover:bg-accent-hover transition"
              title="Download the biller worklist as CSV"
            >
              Export CSV
            </a>
          </div>
        </div>
      </header>

      {/* Compliance posture — reassures the biller before any PHI is shown. */}
      <div className="max-w-[1400px] mx-auto px-6 pt-4">
        <div className="flex items-center gap-2 rounded-lg border border-line bg-surface px-4 py-2 text-xs text-slate-500">
          <span>🔒</span>
          <span>
            HIPAA-aligned: PHI minimized by default (minimum-necessary), processed locally,
            every decision audit-logged. No PHI leaves this environment.
          </span>
        </div>
      </div>

      {offline && (
        <div className="bg-ink text-white text-sm text-center py-2 px-4 mt-4">
          ⚠ Cannot reach the backend on <span className="font-mono">localhost:8000</span>. Start it with{" "}
          <span className="font-mono">python -m uvicorn main:app --port 8000</span> — this clears automatically.
        </div>
      )}

      <main className="max-w-[1400px] mx-auto px-6 py-6 space-y-6">
        {!loaded ? (
          <div className="max-w-2xl mx-auto pt-8">
            {autoLoading ? (
              <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-sm text-slate-500">
                Loading patient data from the Stage-1 database…
              </div>
            ) : (
              <>
                <SyncPanel facilities={facilities} onLoaded={handleLoaded} />
                <p className="text-center text-xs text-slate-400 mt-4">
                  Tip: start with one facility, ~30 patients, for a fast demo. Bump the cap for the full run.
                </p>
              </>
            )}
          </div>
        ) : (
          <>
            <StatCards stats={stats} />

            <div className="flex items-center gap-2">
              <TabButton active={tab === "queue"} onClick={() => setTab("queue")}>Routing queue</TabButton>
              <TabButton active={tab === "table"} onClick={() => setTab("table")}>Eligibility table</TabButton>
              <div className="ml-auto">
                <SyncPanel facilities={facilities} onLoaded={handleLoaded} compact />
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-5 gap-6 items-start">
              <div className="h-[72vh] lg:col-span-3">
                {tab === "queue" ? (
                  <EligibilityQueue onSelect={setSelected} selectedId={selected} refreshKey={refreshKey} facilities={facilities} masked={masked} />
                ) : (
                  <DataTable onSelect={setSelected} selectedId={selected} masked={masked} />
                )}
              </div>
              <div className="h-[72vh] lg:col-span-2">
                <PatientDetail rowId={selected} onChanged={handleChanged} masked={masked} />
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}

function TabButton({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 rounded-lg text-sm font-medium transition ${
        active ? "bg-ink text-white" : "bg-surface text-slate-600 border border-line hover:bg-soft"
      }`}
    >
      {children}
    </button>
  );
}
