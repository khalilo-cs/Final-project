import { useState } from "react";

// FR-10.3: students of a course side by side. One series at a time (total, or one
// criterion), so the bars need no legend; the value is written at the end of each bar.
export interface CompareRow { project_id: string; label: string; total: number | null; scores: Record<string, number | null> }

export function CompareStudents({ rows, criteria }: { rows: CompareRow[]; criteria: { key: string; label: string }[] }) {
  const [metric, setMetric] = useState("total");
  const value = (r: CompareRow) => (metric === "total" ? r.total : r.scores[metric] ?? null);
  const shown = rows.filter((r) => value(r) !== null).sort((a, b) => (value(b) ?? 0) - (value(a) ?? 0));
  const average = shown.length ? shown.reduce((s, r) => s + (value(r) ?? 0), 0) / shown.length : null;
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
        <span className="text-slate-500">قارن حسب:</span>
        <select className="rounded-lg border border-slate-300 px-2 py-1" value={metric} onChange={(e) => setMetric(e.target.value)}>
          <option value="total">الدرجة الكلية</option>
          {criteria.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
        </select>
        {average !== null && <span className="text-slate-500">المتوسط: <b className="text-slate-800">{average.toFixed(1)}</b></span>}
      </div>
      {shown.length === 0 ? <p className="text-sm text-slate-500">لا درجات بعد.</p> : (
        <div className="space-y-1.5" role="list">
          {shown.map((r) => {
            const v = value(r) ?? 0;
            return (
              <div key={r.project_id} role="listitem" className="grid grid-cols-[minmax(6rem,12rem)_1fr] items-center gap-3 text-sm" title={`${r.label}: ${v}`}>
                <span className="truncate text-slate-700">{r.label}</span>
                <div className="relative h-5 rounded bg-slate-100">
                  <div className="h-full rounded bg-indigo-500" style={{ width: `${Math.max(0, Math.min(100, v))}%` }} />
                  {average !== null && <div className="absolute top-0 h-full w-0.5 bg-slate-500" style={{ insetInlineStart: `${average}%` }} aria-hidden />}
                  <span className="absolute inset-y-0 flex items-center px-1.5 text-xs font-bold text-slate-800" style={{ insetInlineStart: `${Math.min(v, 88)}%` }}>{v}</span>
                </div>
              </div>
            );
          })}
          <p className="pt-1 text-xs text-slate-500">الخط الرمادي هو متوسط المادة. الدرجة النهائية إن اعتُمدت، وإلا المقترحة.</p>
        </div>
      )}
    </div>
  );
}
