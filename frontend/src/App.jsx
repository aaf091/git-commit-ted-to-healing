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
    // If a sync already happened (e.g. backend restarted), pick it back up.
    api.syncStatus().then((s) => { if (s.has_data) { setLoaded(true); refreshStats(); } }).catch(() => {});
    const id = setInterval(checkBackend, 5000);
    return () => clearInterval(id);
  }, []);

  const d = meta?.dashboard;
  const facilities = meta?.facilities || [];

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="max-w-[1400px] mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold text-slate-900">{d?.app_name || "ABI Wound-Care Eligibility Radar"}</h1>
            <p className="text-xs text-slate-500">{d?.tagline}</p>
          </div>
          <div className="text-xs text-slate-400">Medicare Part B · PointClickCare pipeline</div>
        </div>
      </header>

      {offline && (
        <div className="bg-red-600 text-white text-sm text-center py-2 px-4">
          ⚠ Cannot reach the backend on <span className="font-mono">localhost:8000</span>. Start it with{" "}
          <span className="font-mono">python -m uvicorn main:app --port 8000</span> — this clears automatically.
        </div>
      )}

      <main className="max-w-[1400px] mx-auto px-6 py-6 space-y-6">
        {!loaded ? (
          <div className="max-w-2xl mx-auto pt-8">
            <SyncPanel facilities={facilities} onLoaded={handleLoaded} />
            <p className="text-center text-xs text-slate-400 mt-4">
              Tip: start with one facility, ~30 patients, for a fast demo. Bump the cap for the full run.
            </p>
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

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
              <div className="h-[72vh]">
                {tab === "queue" ? (
                  <EligibilityQueue onSelect={setSelected} selectedId={selected} refreshKey={refreshKey} facilities={facilities} />
                ) : (
                  <DataTable onSelect={setSelected} selectedId={selected} />
                )}
              </div>
              <div className="h-[72vh]">
                <PatientDetail rowId={selected} onChanged={handleChanged} />
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
        active ? "bg-slate-900 text-white" : "bg-white text-slate-600 border border-slate-200 hover:bg-slate-50"
      }`}
    >
      {children}
    </button>
  );
}
