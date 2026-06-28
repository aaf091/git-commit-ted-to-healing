// Shared presentational helpers.

const TONES = {
  auto_accept: "bg-emerald-100 text-emerald-700 ring-emerald-200",
  flag_for_review: "bg-amber-100 text-amber-700 ring-amber-200",
  reject: "bg-red-100 text-red-700 ring-red-200",
  open: "bg-slate-100 text-slate-600 ring-slate-200",
  billed: "bg-emerald-100 text-emerald-700 ring-emerald-200",
  dismissed: "bg-slate-100 text-slate-500 ring-slate-200",
  slate: "bg-slate-100 text-slate-600 ring-slate-200",
  pass: "bg-emerald-100 text-emerald-700 ring-emerald-200",
  fail: "bg-red-100 text-red-700 ring-red-200",
};

export const DECISION_LABEL = {
  auto_accept: "Auto-accept",
  flag_for_review: "Flag for review",
  reject: "Reject",
};

export function Badge({ tone = "slate", children }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${
        TONES[tone] || TONES.slate
      }`}
    >
      {children}
    </span>
  );
}

export function Confidence({ value }) {
  const v = Math.round(value);
  const color = v >= 90 ? "bg-emerald-500" : v >= 75 ? "bg-amber-500" : "bg-slate-400";
  return (
    <div className="flex items-center gap-2 min-w-[90px]">
      <div className="h-1.5 w-14 rounded-full bg-slate-200 overflow-hidden">
        <div className={`h-full ${color}`} style={{ width: `${v}%` }} />
      </div>
      <span className="text-xs tabular-nums text-slate-500">{v}%</span>
    </div>
  );
}

export function Spinner({ label = "Loading…" }) {
  return (
    <div className="flex items-center gap-2 text-slate-400 text-sm py-8 justify-center">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-slate-500" />
      {label}
    </div>
  );
}
