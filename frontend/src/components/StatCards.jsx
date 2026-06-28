import { fmtMoney } from "./ui";

// Headline numbers. These are what a judge reads in the first 5 seconds.
export default function StatCards({ stats }) {
  if (!stats) return null;
  const resolved = (stats.by_status?.resolved || 0) + (stats.by_status?.dismissed || 0);
  const cards = [
    { label: "Records", value: stats.record_count, tone: "text-slate-900" },
    {
      label: "Open issues",
      value: stats.open_count ?? stats.flag_count,
      sub: `${stats.flag_count} total · ${resolved} cleared`,
      tone: "text-slate-900",
    },
    { label: "High severity", value: stats.high_severity, tone: "text-red-600" },
    { label: "Duplicate clusters", value: stats.duplicate_clusters, tone: "text-fuchsia-600" },
    {
      label: "Est. recoverable",
      value: fmtMoney(stats.estimated_recoverable),
      tone: "text-emerald-600",
    },
  ];
  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
      {cards.map((c) => (
        <div key={c.label} className="rounded-xl border border-slate-200 bg-white p-4">
          <div className={`text-2xl font-semibold tabular-nums ${c.tone}`}>
            {c.value}
          </div>
          <div className="text-xs text-slate-500 mt-1">{c.label}</div>
          {c.sub && <div className="text-[10px] text-slate-400 mt-0.5">{c.sub}</div>}
        </div>
      ))}
    </div>
  );
}
