import { useEffect, useState } from "react";
import { api } from "./api";
import UploadPanel from "./components/UploadPanel";
import StatCards from "./components/StatCards";
import IssueQueue from "./components/IssueQueue";
import DataTable from "./components/DataTable";
import PatientDetail from "./components/PatientDetail";

export default function App() {
  const [meta, setMeta] = useState(null);
  const [stats, setStats] = useState(null);
  const [loaded, setLoaded] = useState(false);
  const [tab, setTab] = useState("queue"); // queue | table
  const [selected, setSelected] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0); // bump to reload the queue
  const [offline, setOffline] = useState(false);

  function handleChanged() {
    refreshStats();
    setRefreshKey((k) => k + 1);
  }

  function checkBackend() {
    api.meta().then((m) => { setMeta(m); setOffline(false); })
      .catch(() => setOffline(true));
  }

  useEffect(() => {
    checkBackend();
    const id = setInterval(checkBackend, 5000); // recover automatically when it comes back
    return () => clearInterval(id);
  }, []);

  function refreshStats() {
    api.stats().then(setStats).catch(() => setStats(null));
  }

  function handleLoaded() {
    setLoaded(true);
    setSelected(null);
    refreshStats();
  }

  const d = meta?.dashboard;

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="border-b border-slate-200 bg-white">
        <div className="max-w-[1400px] mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold text-slate-900">
              {d?.app_name || "ABI Ops Radar"}
            </h1>
            <p className="text-xs text-slate-500">{d?.tagline}</p>
          </div>
          {meta && (
            <div className="text-xs text-slate-400">
              {meta.rules.length} rules · {meta.schema_fields.length} canonical fields
            </div>
          )}
        </div>
      </header>

      {offline && (
        <div className="bg-red-600 text-white text-sm text-center py-2 px-4">
          ⚠ Cannot reach the backend on <span className="font-mono">localhost:8000</span>.
          Start it with <span className="font-mono">python -m uvicorn main:app --port 8000</span> — this banner clears automatically.
        </div>
      )}

      <main className="max-w-[1400px] mx-auto px-6 py-6 space-y-6">
        {!loaded ? (
          <div className="max-w-xl mx-auto pt-10">
            <UploadPanel onLoaded={handleLoaded} />
            <p className="text-center text-xs text-slate-400 mt-4">
              Tip: use <span className="font-mono">backend/data/synthetic_patients.csv</span> for the demo.
            </p>
          </div>
        ) : (
          <>
            <StatCards stats={stats} />

            <div className="flex items-center gap-2">
              <TabButton active={tab === "queue"} onClick={() => setTab("queue")}>
                Issue queue
              </TabButton>
              <TabButton active={tab === "table"} onClick={() => setTab("table")}>
                Data table
              </TabButton>
              <div className="ml-auto">
                <UploadInline onLoaded={handleLoaded} />
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
              <div className="h-[72vh]">
                {tab === "queue" ? (
                  <IssueQueue onSelect={setSelected} selectedRowId={selected} refreshKey={refreshKey} />
                ) : (
                  <DataTable onSelect={setSelected} selectedRowId={selected} />
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

// Compact re-upload control once data is loaded.
function UploadInline({ onLoaded }) {
  return (
    <label className="text-xs cursor-pointer rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-slate-600 hover:bg-slate-50">
      Replace data
      <input
        type="file"
        accept=".csv,.json"
        className="hidden"
        onChange={async (e) => {
          const file = e.target.files?.[0];
          if (!file) return;
          await api.uploadFile(file);
          await api.runPipeline();
          onLoaded?.();
        }}
      />
    </label>
  );
}
