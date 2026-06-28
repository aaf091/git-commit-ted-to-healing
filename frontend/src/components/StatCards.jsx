// Headline numbers — what a billing manager reads in the first 5 seconds.
export default function StatCards({ stats }) {
  if (!stats) return null;
  const billed = stats.by_status?.billed || 0;
  const cards = [
    { label: "Patients", value: stats.patient_count, tone: "text-slate-900" },
    {
      label: "Auto-accept",
      value: stats.auto_accept,
      sub: "clean to bill",
      tone: "text-emerald-600",
    },
    {
      label: "Flag for review",
      value: stats.flag_for_review,
      sub: "needs a human",
      tone: "text-amber-600",
    },
    { label: "Reject", value: stats.reject, sub: "not Part B billable", tone: "text-red-600" },
    {
      label: "Medicare Part B",
      value: `${stats.part_b_pct}%`,
      sub: `${stats.part_b_count} of ${stats.patient_count} · ${billed} billed`,
      tone: "text-indigo-600",
    },
  ];
  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
      {cards.map((c) => (
        <div key={c.label} className="rounded-xl border border-slate-200 bg-white p-4">
          <div className={`text-2xl font-semibold tabular-nums ${c.tone}`}>{c.value}</div>
          <div className="text-xs text-slate-500 mt-1">{c.label}</div>
          {c.sub && <div className="text-[10px] text-slate-400 mt-0.5">{c.sub}</div>}
        </div>
      ))}
    </div>
  );
}
