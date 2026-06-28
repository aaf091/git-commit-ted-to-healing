// Shared presentational helpers — WoundScope monochrome theme.

const TONES = {
  auto_accept: "bg-ink text-white ring-ink",
  flag_for_review: "bg-accent-soft text-accent ring-accent/30",
  reject: "bg-soft text-slate-500 ring-line",
  open: "bg-soft text-slate-600 ring-line",
  billed: "bg-[rgba(31,148,102,0.1)] text-good ring-good/30",
  dismissed: "bg-soft text-slate-400 ring-line",
  slate: "bg-soft text-slate-600 ring-line",
  pass: "bg-[rgba(31,148,102,0.1)] text-good ring-good/30",
  fail: "bg-red-50 text-red-600 ring-red-200",
};

export const DECISION_LABEL = {
  auto_accept: "Auto-Accept",
  flag_for_review: "Flag for Review",
  reject: "Reject",
};

// Status dot color per decision — drives stat cards and decision pills.
export const DECISION_DOT = {
  auto_accept: "bg-good",
  flag_for_review: "bg-peach",
  reject: "bg-slate-300",
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

// The pill on each routing row — dark capsule + status-colored dot.
export function DecisionPill({ decision }) {
  const dot =
    decision === "auto_accept"
      ? "bg-good"
      : decision === "flag_for_review"
      ? "bg-peach"
      : "bg-slate-400";
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-ink px-3 py-1 text-xs font-medium text-white whitespace-nowrap">
      <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
      {DECISION_LABEL[decision] || decision}
    </span>
  );
}

// Thin solid bar — the at-a-glance confidence read on each row.
export function ConfidenceBar({ value, width = "w-full" }) {
  const v = Math.max(0, Math.min(100, Math.round(value || 0)));
  return (
    <div className="flex items-center gap-2">
      <div className={`h-1 ${width} rounded-full bg-soft overflow-hidden`}>
        <div className="h-full rounded-full bg-ink" style={{ width: `${v}%` }} />
      </div>
      <span className="text-[11px] tabular-nums text-slate-400">{v}%</span>
    </div>
  );
}

export function Confidence({ value }) {
  return <ConfidenceBar value={value} width="w-14" />;
}

export function Spinner({ label = "Loading…" }) {
  return (
    <div className="flex items-center gap-2 text-slate-400 text-sm py-8 justify-center">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-slate-700" />
      {label}
    </div>
  );
}

// ---------------------------------------------------------------------------
// PHI masking (minimum-necessary by default). The toggle lives in the header;
// these helpers are pure so any view can render masked or cleartext from state.
// ---------------------------------------------------------------------------
export function maskName(name, masked = true) {
  if (!name) return "—";
  if (!masked) return name;
  return String(name)
    .trim()
    .split(/\s+/)
    .map((w) => (w ? w[0].toUpperCase() + "•••" : ""))
    .join(" ");
}

export function maskId(id, masked = true) {
  if (id == null || id === "") return "—";
  if (!masked) return String(id);
  // "FA-001" -> "FA-•••"
  return String(id).replace(/\d+/g, "•••");
}
