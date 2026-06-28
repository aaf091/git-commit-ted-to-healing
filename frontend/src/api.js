// Thin API client. All calls go through Vite's /api proxy -> FastAPI :8000.
// At kickoff you rarely touch this file; you change config.py + the components.

const BASE = "/api";

async function get(path) {
  const res = await fetch(BASE + path);
  if (!res.ok) throw new Error((await res.text()) || res.statusText);
  return res.json();
}

async function post(path, body) {
  const res = await fetch(BASE + path, {
    method: "POST",
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error((await res.text()) || res.statusText);
  return res.json();
}

export const api = {
  meta: () => get("/meta"),
  loadSample: () => post("/load-sample"),
  exportUrl: (status) =>
    BASE + "/flagged-events/export.csv" + (status ? `?status=${status}` : ""),
  uploadFile: async (file) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(BASE + "/upload", { method: "POST", body: fd });
    if (!res.ok) throw new Error((await res.text()) || res.statusText);
    return res.json();
  },
  runPipeline: () => post("/flagged-events/run"),
  stats: () => get("/flagged-events/stats"),
  records: (limit = 500) => get(`/patients?limit=${limit}`),
  record: (id) => get(`/patients/${id}`),
  flags: (filters = {}) => {
    const q = new URLSearchParams(
      Object.entries(filters).filter(([, v]) => v !== "" && v != null)
    ).toString();
    return get(`/flagged-events${q ? "?" + q : ""}`);
  },
  dedupe: () => post("/dedupe"),
  rules: () => get("/rules"),
  setStatus: (flagId, status, note) =>
    post(`/flagged-events/${encodeURIComponent(flagId)}/status`, { status, note }),
  explain: (flagId) => post(`/flagged-events/${encodeURIComponent(flagId)}/explain`),
};
