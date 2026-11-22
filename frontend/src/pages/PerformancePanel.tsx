import { useEffect, useState } from "react";
import { ApiError, get, post } from "../api";
import { Badge, Button, Card, ErrorBox, Score, severityTone, useLoad } from "../components/ui";

interface Level { concurrent_users: number; requests: number; error_rate: number; requests_per_second: number | null; p50_ms: number | null; p95_ms: number | null }
interface Endpoint { path: string; status: number; avg_ms: number; max_ms: number }
interface Details { stack?: string; startup_seconds?: number; endpoints?: Endpoint[]; load_test?: Level[]; memory_peak_mb?: number; cpu_peak_percent?: number; flags?: { type: string; severity: string; evidence: string; evidence_ar?: string }[]; logs?: string; notes?: string[]; screenshots?: { path: string; title: string; image_jpeg_base64: string }[] }
interface Perf { status: string; runs_successfully: boolean | null; overall_performance_score: number | null; error: string | null; details: Details }

export function PerformancePanel({ id, canRun }: { id: string; canRun: boolean }) {
  const [perf, , reload] = useLoad(
    () => get<Perf>("projects", `/api/v1/sandbox/${id}/results`).catch((e) => (e instanceof ApiError && e.status === 404 ? null : Promise.reject(e))),
    [id],
  );
  const [error, setError] = useState<unknown>();
  const running = perf?.status === "running";
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(reload, 5000);
    return () => clearInterval(timer);
  }, [running, reload]);
  if (!perf) return null;
  const rerun = async () => {
    setError(undefined);
    try {
      await post("projects", `/api/v1/sandbox/run/${id}`);
      reload();
    } catch (reason) {
      setError(reason);
    }
  };
  const d = perf.details ?? {};
  return (
    <Card title="⚡ الأداء (تشغيل المشروع في بيئة معزولة)" actions={canRun && !running ? <Button variant="secondary" onClick={() => void rerun()}>إعادة الاختبار</Button> : undefined}>
      <ErrorBox error={error} />
      {running && <p className="animate-pulse text-sm text-slate-600">يُبنى المشروع ويُشغَّل ويُختبر تحت الضغط… قد يستغرق ذلك بضع دقائق.</p>}
      {(perf.status === "unavailable" || perf.status === "lost") && <p className="text-sm text-slate-500">{perf.error}</p>}
      {perf.status === "done" && (
        <>
          <div className="flex flex-wrap items-center gap-8">
            <Score value={perf.overall_performance_score} label="درجة الأداء" />
            {perf.runs_successfully ? (
              <div className="grid grid-cols-3 gap-6 text-sm">
                <div><div className="text-slate-500">التقنية</div><b className="ltr inline-block">{d.stack}</b></div>
                <div><div className="text-slate-500">زمن التشغيل</div><b className="ltr inline-block">{d.startup_seconds}s</b></div>
                <div><div className="text-slate-500">أعلى ذاكرة</div><b className="ltr inline-block">{d.memory_peak_mb} MB</b></div>
              </div>
            ) : (
              <div className="text-sm text-rose-700">المشروع لم يعمل: {perf.error}</div>
            )}
          </div>
          {d.flags && d.flags.length > 0 && (
            <ul className="mt-3 space-y-1 text-sm">{d.flags.map((f, i) => (
              <li key={i} className="flex items-center gap-2"><Badge tone={severityTone(f.severity)}>{f.severity}</Badge><span>{f.evidence_ar ?? f.evidence}</span></li>
            ))}</ul>
          )}
          {d.load_test && d.load_test.length > 0 && (
            <table className="mt-4 w-full text-sm">
              <thead><tr className="border-b text-right text-slate-500"><th className="py-2">مستخدمون متزامنون</th><th>طلب/ثانية</th><th>p50</th><th>p95</th><th>أخطاء</th></tr></thead>
              <tbody>{d.load_test.map((l) => (
                <tr key={l.concurrent_users} className="border-b border-slate-100">
                  <td className="py-1.5 font-semibold">{l.concurrent_users}</td><td>{l.requests_per_second ?? "—"}</td>
                  <td className="ltr text-right">{l.p50_ms ?? "—"} ms</td><td className="ltr text-right">{l.p95_ms ?? "—"} ms</td>
                  <td className={l.error_rate ? "text-rose-600" : ""}><span className="ltr inline-block">{Math.round(l.error_rate * 100)}%</span></td>
                </tr>
              ))}</tbody>
            </table>
          )}
          {d.endpoints && d.endpoints.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2 text-xs">{d.endpoints.map((e) => (
              <Badge key={e.path} tone={e.status >= 500 ? "red" : "gray"}><span className="ltr">{e.path} · {e.status} · {e.avg_ms} ms</span></Badge>
            ))}</div>
          )}
          {d.screenshots && d.screenshots.length > 0 && (
            <div className="mt-4">
              <div className="mb-2 text-sm font-semibold">لقطات من واجهة المشروع أثناء تشغيله</div>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{d.screenshots.map((s) => (
                <figure key={s.path} className="overflow-hidden rounded-lg border border-slate-200">
                  <img src={`data:image/jpeg;base64,${s.image_jpeg_base64}`} alt={s.title || s.path} className="w-full" loading="lazy" />
                  <figcaption className="bg-slate-50 px-2 py-1 text-xs text-slate-600"><span className="ltr">{s.path}</span>{s.title ? ` — ${s.title}` : ""}</figcaption>
                </figure>
              ))}</div>
            </div>
          )}
          {d.logs && <pre className="mt-3 max-h-48 overflow-auto rounded-lg bg-slate-900 p-3 text-xs text-slate-200">{d.logs}</pre>}
        </>
      )}
    </Card>
  );
}
