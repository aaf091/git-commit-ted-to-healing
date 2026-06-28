// API client. All calls go through Vite's /api proxy -> FastAPI :8000.
// Domain: wound-care Part B eligibility (sync -> route -> review).

const BASE = "/api";

async function get(path) {
  const res = await fetch(BASE + path);
  if (!res.ok) throw new Error((await res.text()) || res.statusText);
  return res.json();
}

async function post(path, body) {
  const res = await fetch(BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  if (!res.ok) throw new Error((await res.text()) || res.statusText);
  return res.json();
}

export const api = {
  meta: () => get("/meta"),
  syncStatus: () => get("/sync/status"),
  sync: (opts) => post("/sync", opts), // { facility_ids, limit, since }
  patients: () => get("/patients"),
  patient: (id) => get(`/patients/${encodeURIComponent(id)}`),
  eligibility: (filters = {}) => {
    const q = new URLSearchParams(
      Object.entries(filters).filter(([, v]) => v !== "" && v != null)
    ).toString();
    return get(`/eligibility${q ? "?" + q : ""}`);
  },
  stats: () => get("/eligibility/stats"),
  exportUrl: (decision) =>
    BASE + "/eligibility/export.csv" + (decision ? `?decision=${decision}` : ""),
  setStatus: (id, status, note) =>
    post(`/eligibility/${encodeURIComponent(id)}/status`, { status, note }),
  explain: (id) => post(`/eligibility/${encodeURIComponent(id)}/explain`),
};
