import { useState, type FormEvent } from "react";
import { CompareStudents } from "../components/CompareStudents";
import { Link, useParams } from "react-router-dom";
import { download, get, post, put } from "../api";
import { Badge, Button, Card, ErrorBox, Input, Loading, Score, STATUS_AR, severityTone, useLoad } from "../components/ui";
import { KINDS_AR, LEVELS_AR, type Alert, type Course, type User } from "../types";

interface Summary { total_projects: number; by_status: Record<string, number>; average_suggested_total: number | null; average_by_criterion: Record<string, number | null>; alerts: number }

const CRITERIA_AR: Record<string, string> = { code_quality: "جودة الكود", security: "الأمان", database: "قاعدة البيانات", report: "التقرير", viva: "المناقشة", authenticity: "الأصالة", performance: "الأداء" };

export function FacultyDashboard() {
  const [summary] = useLoad(() => get<Summary>("projects", "/api/v1/dashboard/faculty/summary"));
  const [alerts] = useLoad(() => get<Alert[]>("projects", "/api/v1/dashboard/faculty/alerts"));
  const [courses, , reloadCourses] = useLoad(() => get<Course[]>("projects", "/api/v1/courses"));
  // FR-10.2: filter by course, cohort (term) and type of work.
  const [filter, setFilter] = useState({ course: "", term: "", kind: "" });
  const term = (c: Course) => `${c.semester ?? ""} ${c.year ?? ""}`.trim();
  const terms = [...new Set((courses ?? []).map(term).filter(Boolean))];
  const visible = (courses ?? []).filter((c) =>
    (!filter.course || c.id === filter.course) && (!filter.term || term(c) === filter.term) && (!filter.kind || c.kind === filter.kind));
  const visibleIds = new Set(visible.map((c) => c.id));
  const shownAlerts = alerts?.filter((a) => visibleIds.has(a.course_id));
  const select = "rounded-lg border border-slate-300 px-2 py-1 text-sm";
  return (
    <>
      {courses && courses.length > 1 && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-slate-500">تصفية:</span>
          <select aria-label="المادة" className={select} value={filter.course} onChange={(e) => setFilter({ ...filter, course: e.target.value })}>
            <option value="">كل المواد</option>
            {courses.map((c) => <option key={c.id} value={c.id}>{c.code} — {c.name}</option>)}
          </select>
          <select aria-label="الدفعة" className={select} value={filter.term} onChange={(e) => setFilter({ ...filter, term: e.target.value })}>
            <option value="">كل الدفعات</option>
            {terms.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <select aria-label="نوع العمل" className={select} value={filter.kind} onChange={(e) => setFilter({ ...filter, kind: e.target.value })}>
            <option value="">كل الأنواع</option>
            {Object.entries(KINDS_AR).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
      )}
      <div className="grid gap-4 md:grid-cols-4">
        <Card><Score count value={summary?.total_projects} label="مشاريع" /></Card>
        <Card><Score value={summary?.average_suggested_total} label="متوسط الدرجة المقترحة" /></Card>
        <Card><Score count value={summary?.by_status.graded ?? 0} label="تم تقييمها" /></Card>
        <Card><Score count value={summary?.alerts} label="تنبيهات" /></Card>
      </div>
      {summary && (
        <Card title="متوسط كل معيار">
          <div className="grid grid-cols-3 gap-4 md:grid-cols-7">
            {Object.entries(summary.average_by_criterion).map(([key, value]) => <Score key={key} value={value} label={CRITERIA_AR[key] ?? key} />)}
          </div>
        </Card>
      )}
      <Card title="🚨 تنبيهات تحتاج انتباهك">
        {!shownAlerts ? <Loading /> : shownAlerts.length === 0 ? <p className="text-sm text-slate-500">لا توجد تنبيهات.</p> : (
          <div className="divide-y divide-slate-100">
            {shownAlerts.map((a, i) => (
              <Link key={i} to={`/projects/${a.project_id}`} className="flex items-center gap-3 py-2 text-sm hover:bg-slate-50">
                <Badge tone={severityTone(a.severity)}>{a.severity}</Badge>
                <span className="font-semibold">{a.project_title}</span>
                <span className="flex-1 truncate text-slate-500">{a.message_ar ?? a.message}</span>
              </Link>
            ))}
          </div>
        )}
      </Card>
      <Card title="المواد">
        {!courses ? <Loading /> : (
          <div className="divide-y divide-slate-100">
            {visible.map((c) => (
              <Link key={c.id} to={`/courses/${c.id}`} className="flex justify-between py-2 hover:bg-slate-50">
                <span className="font-semibold">{c.code} — {c.name}</span>
                <span className="mx-2 inline-flex gap-1 align-middle"><Badge>{KINDS_AR[c.kind] ?? c.kind}</Badge><Badge tone="blue">{LEVELS_AR[c.level] ?? c.level}</Badge></span>
                <span className="text-sm text-slate-500">{c.semester ?? ""} {c.year ?? ""}</span>
              </Link>
            ))}
          </div>
        )}
        <CreateCourse onDone={reloadCourses} />
      </Card>
    </>
  );
}

function CreateCourse({ onDone }: { onDone: () => void }) {
  const [error, setError] = useState<unknown>();
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form)) as Record<string, string>;
    try {
      await post("projects", "/api/v1/courses", { ...data, year: data.year ? Number(data.year) : null });
      form.reset();
      onDone();
    } catch (reason) {
      setError(reason);
    }
  };
  return (
    <form onSubmit={submit} className="mt-4 grid gap-2 border-t pt-4 md:grid-cols-6">
      <Input name="code" placeholder="رمز المادة" required />
      <Input name="name" placeholder="اسم المادة" required className="md:col-span-2" />
      <Input name="semester" placeholder="الفصل" />
      <select name="level" defaultValue="year4" aria-label="مستوى الطلاب" className="rounded-lg border border-slate-300 px-3 py-2 text-sm">
        {Object.entries(LEVELS_AR).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
      <select name="kind" defaultValue="graduation" aria-label="نوع العمل" className="rounded-lg border border-slate-300 px-3 py-2 text-sm">
        {Object.entries(KINDS_AR).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
      <p className="text-xs text-slate-500 md:col-span-5">المستوى ونوع العمل يحددان أوزان التقييم الافتراضية (الواجب لا يُحاسَب على تقرير)، وطول المناقشة وصعوبتها، ووقت اختبار بصمة الفهم. يمكن تعديل الأوزان لاحقاً من صفحة المادة.</p>
      <Button type="submit">إضافة مادة</Button>
      <div className="md:col-span-6"><ErrorBox error={error} /></div>
    </form>
  );
}

interface Row { project_id: string; student_name: string | null; student_number: string | null; title: string; status: string; scores: Record<string, number | null>; suggested_total: number | null; coverage: number; final_total: number | null; alerts: number }
interface Criterion { criterion: string; label_ar: string; weight: number }
interface Learned { graded_projects: number; suggested: Record<string, number> | null; error_now: number | null; error_suggested: number | null; note_ar: string }
const CRITERION_AR: Record<string, string> = {
  code_quality: "جودة الكود", security: "الأمان", database: "قاعدة البيانات", report: "التقرير",
  viva: "المناقشة", authenticity: "الأصالة", performance: "الأداء",
};

export function CoursePage() {
  const { id = "" } = useParams();
  const [grades, error, reload] = useLoad(() => get<{ projects: Row[] }>("projects", `/api/v1/grades/course/${id}`), [id]);
  return (
    <>
      <Card title="مشاريع المادة ودرجاتها" actions={<div className="flex gap-2">
        <Button variant="secondary" onClick={() => void download("projects", `/api/v1/reports/course/${id}/pdf.zip`, "reports.zip")}>⬇ تقارير PDF للجميع</Button>
        <Button variant="secondary" onClick={() => void download("projects", `/api/v1/reports/course/${id}/excel`, "grades.xlsx")}>⬇ تصدير Excel</Button>
      </div>}>
        <ErrorBox error={error} />
        {!grades ? <Loading /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="border-b text-right text-slate-500"><th className="py-2">الطالب</th><th>المشروع</th><th>الحالة</th><th>المقترحة</th><th>التغطية</th><th>النهائية</th><th>تنبيهات</th></tr></thead>
              <tbody>
                {grades.projects.map((r) => (
                  <tr key={r.project_id} className="border-b border-slate-100 hover:bg-slate-50">
                    <td className="py-2">{r.student_name ?? "—"} <span className="text-xs text-slate-400">{r.student_number}</span></td>
                    <td><Link className="text-indigo-700 hover:underline" to={`/projects/${r.project_id}`}>{r.title}</Link></td>
                    <td><Badge tone="blue">{STATUS_AR[r.status] ?? r.status}</Badge></td>
                    <td className="font-bold">{r.suggested_total ?? "—"}</td><td>{r.coverage}%</td>
                    <td className="font-bold">{r.final_total ?? "—"}</td>
                    <td>{r.alerts ? <Badge tone="red">{r.alerts}</Badge> : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      {grades && grades.projects.length > 1 && (
        <Card title="مقارنة الطلاب">
          <CompareStudents
            rows={grades.projects.map((r) => ({ project_id: r.project_id, label: r.student_name ?? r.title, total: r.final_total ?? r.suggested_total, scores: r.scores }))}
            criteria={Object.keys(grades.projects[0]?.scores ?? {}).map((key) => ({ key, label: CRITERION_AR[key] ?? key }))}
          />
        </Card>
      )}
      <div className="grid gap-6 md:grid-cols-2">
        <EnrollStudents courseId={id} onDone={reload} />
        <Weights courseId={id} onDone={reload} />
      </div>
    </>
  );
}

function EnrollStudents({ courseId, onDone }: { courseId: string; onDone: () => void }) {
  const [username, setUsername] = useState("");
  const [message, setMessage] = useState<string>();
  const [error, setError] = useState<unknown>();
  const enroll = async () => {
    setError(undefined);
    try {
      const student = await get<User>("auth", `/api/v1/users/by-username/${encodeURIComponent(username)}`);
      await post("projects", `/api/v1/courses/${courseId}/students`, { student_ids: [student.id] });
      setMessage(`أُضيف ${student.full_name}`);
      setUsername("");
      onDone();
    } catch (reason) {
      setError(reason);
    }
  };
  return (
    <Card title="إضافة طالب">
      <div className="flex gap-2">
        <Input placeholder="اسم المستخدم للطالب" value={username} onChange={(e) => setUsername(e.target.value)} />
        <Button disabled={!username} onClick={() => void enroll()}>إضافة</Button>
      </div>
      {message && <p className="mt-2 text-sm text-emerald-700">{message}</p>}
      <ErrorBox error={error} />
    </Card>
  );
}

function Weights({ courseId, onDone }: { courseId: string; onDone: () => void }) {
  const [criteria, , reload] = useLoad(() => get<Criterion[]>("projects", `/api/v1/courses/${courseId}/criteria`), [courseId]);
  const [values, setValues] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>();
  const [learned, setLearned] = useState<Learned>();
  if (!criteria) return <Loading />;
  const learn = async () => {
    setError(undefined);
    try {
      const result = await get<Learned>("projects", `/api/v1/courses/${courseId}/criteria/learned`);
      setLearned(result);
      if (result.suggested) setValues(Object.fromEntries(Object.entries(result.suggested).map(([k, v]) => [k, String(v)])));
    } catch (reason) {
      setError(reason);
    }
  };
  const current = (c: Criterion) => values[c.criterion] ?? String(c.weight);
  const total = criteria.reduce((sum, c) => sum + Number(current(c) || 0), 0);
  const save = async () => {
    try {
      await put("projects", `/api/v1/courses/${courseId}/criteria`, { weights: Object.fromEntries(criteria.map((c) => [c.criterion, Number(current(c))])) });
      setValues({});
      reload();
      onDone();
    } catch (reason) {
      setError(reason);
    }
  };
  return (
    <Card title="أوزان التقييم">
      <div className="space-y-2">
        {criteria.map((c) => (
          <label key={c.criterion} className="flex items-center justify-between gap-3 text-sm">
            <span>{c.label_ar}</span>
            <Input type="number" min={0} max={100} value={current(c)} onChange={(e) => setValues({ ...values, [c.criterion]: e.target.value })} className="w-24" />
          </label>
        ))}
      </div>
      <div className="mt-3 flex items-center justify-between">
        <span className={`text-sm font-bold ${Math.abs(total - 100) < 0.01 ? "text-emerald-600" : "text-rose-600"}`}>المجموع: {total}%</span>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => void learn()} title="أوزان تطابق درجاتكم المعتمدة في هذه المادة">اقترح من درجاتي</Button>
          <Button disabled={Math.abs(total - 100) > 0.01} onClick={() => void save()}>حفظ الأوزان</Button>
        </div>
      </div>
      {learned && <p className={`mt-2 text-xs ${learned.suggested ? "text-indigo-700" : "text-slate-500"}`}>{learned.note_ar}{learned.suggested ? " راجع القيم ثم احفظ." : ""}</p>}
      <ErrorBox error={error} />
    </Card>
  );
}
