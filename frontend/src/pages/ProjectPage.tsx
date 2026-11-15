import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError, download, get, post, put } from "../api";
import { useAuth } from "../auth";
import { Badge, Button, Card, DiffView, ErrorBox, Input, Loading, Score, STATUS_AR, severityTone, useLoad } from "../components/ui";
import type { Advice, Fix, Grade, Project, VivaState } from "../types";
import { AuthenticityPanel } from "./AuthenticityPanel";
import { PerformancePanel } from "./PerformancePanel";

type Results = Record<"code" | "security" | "database" | "report", { [key: string]: unknown } | null>;

async function loadResults(project: Project): Promise<Results> {
  const id = project.id;
  const one = (path: string) => get<{ [key: string]: unknown }>("projects", path).catch((e) => (e instanceof ApiError && e.status === 404 ? null : Promise.reject(e)));
  // Only ask for results the project can have (no report uploaded -> no report results).
  const [code, security, database, report] = await Promise.all([
    one(`/api/v1/analysis/code/${id}/results`),
    one(`/api/v1/analysis/security/${id}/results`),
    project.has_database ? one(`/api/v1/analysis/database/${id}/results`) : null,
    project.has_report ? one(`/api/v1/analysis/report/${id}/results`) : null,
  ]);
  return { code, security, database, report };
}

export function ProjectPage() {
  const { id = "" } = useParams();
  const { user } = useAuth();
  const [project, error, reload] = useLoad(() => get<Project>("projects", `/api/v1/projects/${id}`), [id]);
  const busy = project?.status === "analyzing";
  useEffect(() => {
    if (!busy) return;
    const timer = setInterval(reload, 2000);
    return () => clearInterval(timer);
  }, [busy, reload]);

  if (error) return <ErrorBox error={error} />;
  if (!project) return <Loading />;
  const staff = user?.role === "faculty" || user?.role === "admin";
  const owner = user?.id === project.student_id;

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-black">{project.title}</h1>
          <div className="mt-1 flex flex-wrap gap-2">
            <Badge tone={project.status === "analysis_failed" ? "red" : "blue"}>{STATUS_AR[project.status] ?? project.status}</Badge>
            {project.programming_languages.map((l) => <Badge key={l}>{l}</Badge>)}
          </div>
        </div>
        {owner && <StartViva project={project} />}
      </div>
      {project.analysis_error && <ErrorBox error={project.analysis_error} />}
      {busy ? <Card><p className="animate-pulse text-center text-slate-600">جارٍ تحليل المشروع… (الكود، الأمان، قاعدة البيانات، التقرير)</p></Card> : (
        <>
          <ResultsSummary project={project} />
          {staff && <GradePanel id={id} />}
          {staff && <AuthenticityPanel id={id} />}
          <PerformancePanel id={id} canRun={(owner || staff) && project.status !== "graded"} />
          <AdvisorPanel project={project} owner={owner} onChanged={reload} />
          <VivaSessions id={id} staff={staff} />
        </>
      )}
    </>
  );
}

function ResultsSummary({ project }: { project: Project }) {
  const [results] = useLoad(() => loadResults(project), [project.id, project.status]);
  if (!results) return <Loading />;
  const n = (value: unknown) => (typeof value === "number" ? value : null);
  const vulnerabilities = (results.security?.vulnerabilities as { type: string; severity: string; file: string; line: number }[] | undefined) ?? [];
  return (
    <Card title="نتائج التحليل">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Score value={n(results.code?.overall_quality_score)} label="جودة الكود" />
        <Score value={n(results.security?.overall_security_score)} label="الأمان" />
        <Score value={n(results.database?.overall_db_score)} label="قاعدة البيانات" />
        <Score value={n(results.report?.overall_report_score)} label="التقرير" />
      </div>
      {vulnerabilities.length > 0 && (
        <div className="mt-4 space-y-1">
          {vulnerabilities.slice(0, 8).map((v, i) => (
            <div key={i} className="flex items-center gap-2 text-sm">
              <Badge tone={severityTone(v.severity)}>{v.severity}</Badge>
              <span className="font-semibold">{v.type}</span>
              <code className="text-xs text-slate-500">{v.file}:{v.line}</code>
            </div>
          ))}
        </div>
      )}
      {typeof results.report?.plagiarism_percentage === "number" && (
        <p className="mt-3 text-sm text-slate-600">نسبة التشابه في التقرير: <b className="ltr inline-block">{results.report.plagiarism_percentage as number}%</b></p>
      )}
    </Card>
  );
}

function AdviceList({ title, items, tone }: { title: string; items: Advice["strengths"]; tone: "green" | "red" | "blue" }) {
  const border = { green: "border-emerald-400", red: "border-rose-400", blue: "border-sky-400" }[tone];
  return (
    <div>
      <h3 className="mb-2 font-bold">{title} <span className="text-slate-400">({items.length})</span></h3>
      {items.length === 0 ? <p className="text-sm text-slate-400">لا شيء</p> : (
        <ul className="space-y-2">
          {items.map((item, i) => (
            <li key={i} className={`border-r-4 ${border} bg-slate-50 py-1.5 pr-3 text-sm`}>
              <div className="flex items-center gap-2 font-semibold">
                {item.priority && <Badge tone={item.priority === "critical" || item.priority === "high" ? "red" : item.priority === "medium" ? "amber" : "gray"}>
                  {{ critical: "حرجة", high: "أولوية عالية", medium: "متوسطة", low: "منخفضة" }[item.priority]}</Badge>}
                {item.title}
              </div>
              <div className="mt-0.5 text-xs text-slate-500">{item.evidence}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function AdvisorPanel({ project, owner, onChanged }: { project: Project; owner: boolean; onChanged: () => void }) {
  const [advice, error, reload] = useLoad(() => get<Advice>("projects", `/api/v1/projects/${project.id}/advice`), [project.id, project.status]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [result, setResult] = useState<{ applied: { title: string }[]; skipped: { id: string; reason: string }[] }>();
  const [busy, setBusy] = useState(false);
  const [applyError, setApplyError] = useState<unknown>();
  const canApply = owner && project.status !== "graded";

  const apply = async () => {
    const ok = window.confirm(
      `سيتم تطبيق ${selected.size} إصلاح على كودك.\n\n• تُحفظ نسخة كودك الأصلية ويمكنك تنزيلها.\n• يُسجَّل كل إصلاح ويظهر للدكتور.\n• يُعاد تحليل المشروع بعد التطبيق.\n\nهل توافق؟`,
    );
    if (!ok) return;
    setBusy(true);
    setApplyError(undefined);
    try {
      setResult(await post("projects", `/api/v1/projects/${project.id}/fixes/apply`, { fix_ids: [...selected] }));
      setSelected(new Set());
      onChanged();
      reload();
    } catch (reason) {
      setApplyError(reason);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="🤖 المستشار الذكي">
      <ErrorBox error={error} />
      {!advice ? <Loading /> : (
        <div className="space-y-6">
          {advice.summary && (
            <div className="rounded-lg bg-indigo-50 p-4 text-sm leading-7 text-indigo-900">
              {advice.summary.summary}
              <div className="mt-2 text-xs text-indigo-500">كتبه: {advice.summary.written_by}</div>
            </div>
          )}
          <div className="grid gap-6 md:grid-cols-3">
            <AdviceList title="💪 نقاط القوة" items={advice.strengths} tone="green" />
            <AdviceList title="⚠️ نقاط الضعف" items={advice.weaknesses} tone="red" />
            <AdviceList title="🚀 ما يمكن تطويره" items={advice.improvements} tone="blue" />
          </div>
          <FixList fixes={advice.fixes} selected={selected} setSelected={setSelected} canApply={canApply} />
          {canApply && advice.fixes?.some((f) => f.kind === "patch") && (
            <div className="flex items-center gap-3">
              <Button disabled={!selected.size || busy} onClick={() => void apply()}>
                {busy ? "جارٍ التطبيق…" : `موافق — طبّق ${selected.size} إصلاح`}
              </Button>
              <span className="text-xs text-slate-500">لا يتغير شيء في كودك قبل موافقتك.</span>
            </div>
          )}
          <ErrorBox error={applyError} />
          {result && (
            <div className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">
              طُبّق: {result.applied.map((a) => a.title).join("، ") || "لا شيء"}
              {result.skipped.length > 0 && <div className="text-amber-700">لم يُطبّق: {result.skipped.map((s) => s.reason).join("، ")}</div>}
            </div>
          )}
          {advice.applied_fixes.length > 0 && (
            <div className="text-sm">
              <h3 className="mb-1 font-bold">إصلاحات طُبّقت بالذكاء الاصطناعي</h3>
              <ul className="list-inside list-disc text-slate-600">
                {advice.applied_fixes.map((f) => <li key={f.fix_id}>{f.title} — <code>{f.file}:{f.line}</code></li>)}
              </ul>
              <a className="text-xs text-indigo-600 underline" href="#" onClick={(e) => { e.preventDefault(); void download("projects", `/api/v1/projects/${project.id}/code?original=true`, "code-original.zip"); }}>تنزيل الكود الأصلي</a>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

function FixList({ fixes, selected, setSelected, canApply }: { fixes: Fix[] | null; selected: Set<string>; setSelected: (s: Set<string>) => void; canApply: boolean }) {
  if (fixes === null) return <p className="text-sm text-slate-400">خدمة الإصلاحات غير متاحة حالياً.</p>;
  if (fixes.length === 0) return <p className="text-sm text-emerald-700">✅ لا توجد إصلاحات مقترحة.</p>;
  const toggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  };
  return (
    <div>
      <h3 className="mb-2 font-bold">🔧 إصلاحات مقترحة</h3>
      <div className="space-y-3">
        {fixes.map((fix) => (
          <div key={fix.id} className="rounded-lg border border-slate-200 p-3">
            <div className="flex items-start gap-3">
              {fix.kind === "patch" && canApply && (
                <input type="checkbox" className="mt-1 h-4 w-4" checked={selected.has(fix.id)} onChange={() => toggle(fix.id)} />
              )}
              <div className="flex-1 space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={fix.kind === "patch" ? "green" : "amber"}>{fix.kind === "patch" ? "إصلاح تلقائي" : "اقتراح يدوي"}</Badge>
                  <span className="font-semibold">{fix.title}</span>
                  <code className="text-xs text-slate-500">{fix.file}:{fix.line}</code>
                </div>
                <p className="ltr text-left text-xs text-slate-600">{fix.explanation}</p>
                {fix.diff && <DiffView diff={fix.diff} />}
                {fix.example && <pre className="overflow-x-auto rounded-lg bg-slate-100 p-3 text-xs">{fix.example}</pre>}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function StartViva({ project }: { project: Project }) {
  const navigate = useNavigate();
  const [error, setError] = useState<unknown>();
  const [language, setLanguage] = useState("ar");
  if (project.status !== "analyzed" && project.status !== "viva_scheduled") return null;
  const start = async () => {
    try {
      const state = await post<VivaState>("projects", `/api/v1/viva/start/${project.id}`, { language });
      navigate(`/viva/${state.session_id}`);
    } catch (reason) {
      setError(reason);
    }
  };
  return (
    <div className="flex items-center gap-2">
      <select value={language} onChange={(e) => setLanguage(e.target.value)} className="rounded-lg border border-slate-300 px-2 py-2 text-sm">
        <option value="ar">عربي</option><option value="en">English</option>
      </select>
      <Button onClick={() => void start()}>🎙️ ابدأ المناقشة الذكية</Button>
      <ErrorBox error={error} />
    </div>
  );
}

function VivaSessions({ id, staff }: { id: string; staff: boolean }) {
  const [sessions] = useLoad(() => get<{ session_id: string; status: string; score: number | null; started_at: string }[]>("projects", `/api/v1/viva/project/${id}`), [id]);
  if (!sessions?.length) return null;
  return (
    <Card title="جلسات المناقشة">
      <div className="divide-y divide-slate-100 text-sm">
        {sessions.map((s) => (
          <Link key={s.session_id} to={staff ? `/viva/${s.session_id}/review` : `/viva/${s.session_id}`} className="flex items-center justify-between py-2 hover:bg-slate-50">
            <span>{new Date(s.started_at).toLocaleString("ar")}</span>
            <span className="flex items-center gap-3"><Badge tone="blue">{STATUS_AR[s.status] ?? s.status}</Badge><b>{s.score ?? "—"}</b></span>
          </Link>
        ))}
      </div>
    </Card>
  );
}

function GradePanel({ id }: { id: string }) {
  const [grade, error, reload] = useLoad(() => get<Grade>("projects", `/api/v1/grades/${id}`), [id]);
  const [total, setTotal] = useState("");
  const [notes, setNotes] = useState("");
  const [saveError, setSaveError] = useState<unknown>();
  if (error) return <ErrorBox error={error} />;
  if (!grade) return <Loading />;
  const save = async () => {
    try {
      await put("projects", `/api/v1/grades/${id}`, { total: Number(total), notes: notes || null });
      reload();
    } catch (reason) {
      setSaveError(reason);
    }
  };
  return (
    <Card title="📊 الدرجة المقترحة">
      <div className="flex flex-wrap items-center gap-8">
        <Score value={grade.suggested_total} label="المقترحة من النظام" />
        <Score value={grade.final_total} label="النهائية (الدكتور)" />
        <div className="text-sm text-slate-600">التغطية: <b className="ltr inline-block">{grade.coverage}%</b>{grade.missing_criteria.length > 0 && <> — لم يُقيَّم بعد: {grade.missing_criteria.map((c) => grade.breakdown.find((b) => b.criterion === c)?.label_ar ?? c).join("، ")}</>}</div>
      </div>
      <table className="mt-4 w-full text-sm">
        <thead><tr className="border-b text-right text-slate-500"><th className="py-2">المعيار</th><th>الوزن</th><th>الدرجة</th><th>التبرير</th></tr></thead>
        <tbody>
          {grade.breakdown.map((b) => (
            <tr key={b.criterion} className="border-b border-slate-100">
              <td className="py-2 font-semibold">{b.label_ar}</td><td>{b.weight}%</td>
              <td>{b.score ?? <span className="text-slate-400">—</span>}</td>
              <td className="ltr text-left text-xs text-slate-500">{b.justification}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {grade.alerts.length > 0 && (
        <div className="mt-4 space-y-1">
          {grade.alerts.map((a, i) => <div key={i} className="flex items-center gap-2 text-sm"><Badge tone={severityTone(a.severity)}>{a.severity}</Badge><span className="ltr">{a.message}</span></div>)}
        </div>
      )}
      <div className="mt-4 flex flex-wrap items-end gap-3 border-t pt-4">
        <label className="text-sm">الدرجة النهائية<Input type="number" min={0} max={100} value={total} onChange={(e) => setTotal(e.target.value)} className="w-28" /></label>
        <label className="flex-1 text-sm">ملاحظات<Input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder={grade.faculty_notes ?? ""} /></label>
        <Button disabled={total === ""} onClick={() => void save()}>اعتماد الدرجة</Button>
      </div>
      <ErrorBox error={saveError} />
    </Card>
  );
}
