import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { download, get, post, put } from "../api";
import { Badge, Button, Card, ErrorBox, Input, Loading, Score, STATUS_AR, severityTone, useLoad } from "../components/ui";
import type { Alert, Course, User } from "../types";

interface Summary { total_projects: number; by_status: Record<string, number>; average_suggested_total: number | null; average_by_criterion: Record<string, number | null>; alerts: number }

const CRITERIA_AR: Record<string, string> = { code_quality: "جودة الكود", security: "الأمان", database: "قاعدة البيانات", report: "التقرير", viva: "المناقشة", authenticity: "الأصالة", performance: "الأداء" };

export function FacultyDashboard() {
  const [summary] = useLoad(() => get<Summary>("projects", "/api/v1/dashboard/faculty/summary"));
  const [alerts] = useLoad(() => get<Alert[]>("projects", "/api/v1/dashboard/faculty/alerts"));
  const [courses, , reloadCourses] = useLoad(() => get<Course[]>("projects", "/api/v1/courses"));
  return (
    <>
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
        {!alerts ? <Loading /> : alerts.length === 0 ? <p className="text-sm text-slate-500">لا توجد تنبيهات.</p> : (
          <div className="divide-y divide-slate-100">
            {alerts.map((a, i) => (
              <Link key={i} to={`/projects/${a.project_id}`} className="flex items-center gap-3 py-2 text-sm hover:bg-slate-50">
                <Badge tone={severityTone(a.severity)}>{a.severity}</Badge>
                <span className="font-semibold">{a.project_title}</span>
                <span className="ltr flex-1 truncate text-left text-slate-500">{a.message}</span>
              </Link>
            ))}
          </div>
        )}
      </Card>
      <Card title="المواد">
        {!courses ? <Loading /> : (
          <div className="divide-y divide-slate-100">
            {courses.map((c) => (
              <Link key={c.id} to={`/courses/${c.id}`} className="flex justify-between py-2 hover:bg-slate-50">
                <span className="font-semibold">{c.code} — {c.name}</span>
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
    <form onSubmit={submit} className="mt-4 grid gap-2 border-t pt-4 md:grid-cols-5">
      <Input name="code" placeholder="رمز المادة" required />
      <Input name="name" placeholder="اسم المادة" required className="md:col-span-2" />
      <Input name="semester" placeholder="الفصل" />
      <Button type="submit">إضافة مادة</Button>
      <div className="md:col-span-5"><ErrorBox error={error} /></div>
    </form>
  );
}

interface Row { project_id: string; student_name: string | null; student_number: string | null; title: string; status: string; scores: Record<string, number | null>; suggested_total: number | null; coverage: number; final_total: number | null; alerts: number }
interface Criterion { criterion: string; label_ar: string; weight: number }

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
  if (!criteria) return <Loading />;
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
        <Button disabled={Math.abs(total - 100) > 0.01} onClick={() => void save()}>حفظ الأوزان</Button>
      </div>
      <ErrorBox error={error} />
    </Card>
  );
}
