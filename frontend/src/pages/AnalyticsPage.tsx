import { get } from "../api";
import { Card, ErrorBox, Loading, Score, useLoad } from "../components/ui";

interface Named { name: string; count: number }
interface Analytics {
  projects: number; graded: number; low_authenticity: number; low_authenticity_rate: number;
  common_issues: Named[]; languages: Named[]; technologies: Named[];
  grade_distribution: { range: string; count: number }[];
  terms: { term: string; projects: number; average: number }[];
}

/** One series, ranked: thin horizontal bars, value at the end in text ink, tooltip on hover. */
function BarList({ rows, empty }: { rows: Named[]; empty: string }) {
  if (rows.length === 0) return <p className="text-sm text-slate-500">{empty}</p>;
  const max = Math.max(...rows.map((r) => r.count));
  return (
    <ul className="space-y-2">
      {rows.map((row) => (
        <li key={row.name} className="grid grid-cols-[minmax(0,14rem)_1fr_2.5rem] items-center gap-3 text-sm" title={`${row.name}: ${row.count}`}>
          <span className="truncate text-slate-700">{row.name}</span>
          <span className="h-2.5 rounded-full bg-slate-100">
            <span className="block h-2.5 rounded-full bg-indigo-500" style={{ width: `${(row.count / max) * 100}%` }} />
          </span>
          <span className="text-left font-semibold text-slate-700">{row.count}</span>
        </li>
      ))}
    </ul>
  );
}

function Histogram({ bins }: { bins: Analytics["grade_distribution"] }) {
  const max = Math.max(1, ...bins.map((b) => b.count));
  return (
    <div className="ltr">
      <div className="flex h-40 items-end gap-0.5 border-b border-slate-300">
        {bins.map((bin) => (
          <div key={bin.range} className="flex h-full flex-1 flex-col justify-end" title={`${bin.range}: ${bin.count} مشروع`}>
            {bin.count > 0 && <span className="mb-1 text-center text-xs font-semibold text-slate-700">{bin.count}</span>}
            <div className="rounded-t bg-indigo-500 hover:bg-indigo-700" style={{ height: `${(bin.count / max) * 85}%`, minHeight: bin.count ? 4 : 0 }} />
          </div>
        ))}
      </div>
      <div className="mt-1 flex gap-0.5 text-[10px] text-slate-500">
        {bins.map((bin) => <span key={bin.range} className="flex-1 text-center">{bin.range}</span>)}
      </div>
    </div>
  );
}

export function AnalyticsPage() {
  const [data, error] = useLoad(() => get<Analytics>("projects", "/api/v1/dashboard/department/analytics"));
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading />;
  return (
    <>
      <h1 className="text-2xl font-black">📈 إحصائيات القسم</h1>
      <div className="grid gap-4 md:grid-cols-4">
        <Card><Score count value={data.projects} label="مشاريع" /></Card>
        <Card><Score count value={data.graded} label="تم تقييمها" /></Card>
        <Card><Score count value={data.low_authenticity} label="أصالة أقل من 50" /></Card>
        <Card><Score count value={data.low_authenticity_rate} label="نسبة الاشتباه بالنسخ %" /></Card>
      </div>
      <div className="grid gap-6 md:grid-cols-2">
        <Card title="توزيع الدرجات (النهائية، أو المقترحة قبل الاعتماد)"><Histogram bins={data.grade_distribution} /></Card>
        <Card title="أكثر الأخطاء شيوعاً"><BarList rows={data.common_issues} empty="لا أخطاء مسجّلة بعد." /></Card>
        <Card title="اللغات الأكثر استخداماً"><BarList rows={data.languages} empty="لا بيانات بعد." /></Card>
        <Card title="التقنيات الأكثر استخداماً"><BarList rows={data.technologies} empty="لا بيانات بعد." /></Card>
      </div>
      <Card title="مقارنة الفصول الدراسية">
        {data.terms.length === 0 ? <p className="text-sm text-slate-500">لا بيانات بعد.</p> : (
          <table className="w-full text-sm">
            <thead><tr className="border-b text-right text-slate-500"><th className="py-2">الفصل / المادة</th><th>المشاريع</th><th>متوسط الدرجة</th></tr></thead>
            <tbody>{data.terms.map((t) => (
              <tr key={t.term} className="border-b border-slate-100"><td className="py-1.5">{t.term}</td><td>{t.projects}</td><td className="font-semibold">{t.average}</td></tr>
            ))}</tbody>
          </table>
        )}
      </Card>
    </>
  );
}
