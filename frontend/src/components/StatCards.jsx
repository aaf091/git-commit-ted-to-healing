import { DECISION_DOT } from "./ui";

// Headline numbers — what a billing manager reads in the first 5 seconds.
// Big bold mono figures, a small uppercase label, and a status dot per decision.
export default function StatCards({ stats }) {
  if (!stats) return null;
  const cards = [
    { label: "Patients Evaluated", value: stats.patient_count },
    { label: "Auto-Accept", value: stats.auto_accept, dot: DECISION_DOT.auto_accept },
    { label: "Flag for Review", value: stats.flag_for_review, dot: DECISION_DOT.flag_for_review },
    { label: "Reject", value: stats.reject, dot: DECISION_DOT.reject },
  ];
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {cards.map((c) => (
        <div key={c.label} className="rounded-xl border border-line bg-surface px-5 py-4 shadow-[0_1px_2px_rgba(18,20,22,0.04),0_8px_28px_rgba(18,20,22,0.04)]">
          <div className="text-4xl font-extrabold tabular-nums text-ink leading-none">{c.value}</div>
          <div className="mt-3 flex items-center gap-2 text-[11px] font-medium uppercase tracking-wide text-slate-500">
            {c.dot && <span className={`h-2 w-2 rounded-full ${c.dot}`} />}
            {c.label}
          </div>
        </div>
      ))}
    </div>
  );
}
