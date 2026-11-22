import { isNetworkError, resumableUpload, waitForConnection, type UploadKind } from "../resilience";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { get, post } from "../api";
import { Badge, Button, Card, ErrorBox, Input, Loading, STATUS_AR, useLoad } from "../components/ui";
import { KINDS_AR, type Course, type Project } from "../types";

export function StudentHome() {
  const [projects, error, reload] = useLoad(() => get<Project[]>("projects", "/api/v1/projects"));
  const [courses] = useLoad(() => get<Course[]>("projects", "/api/v1/courses"));
  return (
    <>
      <Card title="مشاريعي">
        <ErrorBox error={error} />
        {!projects ? <Loading /> : projects.length === 0 ? (
          <p className="text-sm text-slate-500">لم تسلّم أي مشروع بعد.</p>
        ) : (
          <div className="divide-y divide-slate-100">
            {projects.map((p) => (
              <Link key={p.id} to={`/projects/${p.id}`} className="flex items-center justify-between py-3 hover:bg-slate-50">
                <div>
                  <div className="font-semibold">{p.title}</div>
                  <div className="text-xs text-slate-500">{new Date(p.submitted_at).toLocaleString("ar")}</div>
                </div>
                <Badge tone={p.status === "analysis_failed" ? "red" : p.status === "graded" ? "green" : "blue"}>{STATUS_AR[p.status] ?? p.status}</Badge>
              </Link>
            ))}
          </div>
        )}
      </Card>
      {courses && <SubmitForm courses={courses} onDone={reload} />}
    </>
  );
}

function SubmitForm({ courses, onDone }: { courses: Course[]; onDone: () => void }) {
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<{ label: string; sent: number; total: number; waiting: boolean }>();
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    setError(undefined);
    try {
      // Files go first, in small pieces that survive a dropped connection or a power cut.
      const files: [UploadKind, string, string][] = [["code", "code_upload_id", "الكود"], ["report", "report_upload_id", "التقرير"], ["database", "database_upload_id", "قاعدة البيانات"]];
      for (const [kind, field, label] of files) {
        const file = data.get(kind) as File | null;
        data.delete(kind);
        if (file?.size) data.set(field, await resumableUpload(file, kind, (p) => setProgress({ label, ...p })));
      }
      setProgress(undefined);
      for (;;) {
        try {
          await post("projects", "/api/v1/projects", data);
          break;
        } catch (reason) {
          if (!isNetworkError(reason)) throw reason;
          setProgress({ label: "التسليم", sent: 1, total: 1, waiting: true });
          await waitForConnection(3000);
        }
      }
      form.reset();
      onDone();
    } catch (reason) {
      setError(reason);
    } finally {
      setProgress(undefined);
      setBusy(false);
    }
  };
  if (courses.length === 0) {
    return <Card title="تسليم مشروع"><p className="text-sm text-slate-500">لست مسجّلاً في أي مادة بعد. اطلب من الدكتور إضافتك.</p></Card>;
  }
  return (
    <Card title="تسليم مشروع جديد">
      <form onSubmit={submit} className="grid gap-3 md:grid-cols-2">
        <Input name="title" placeholder="عنوان المشروع" required />
        <select name="course_id" required className="rounded-lg border border-slate-300 px-3 py-2 text-sm">
          {courses.map((c) => <option key={c.id} value={c.id}>{c.code} — {c.name} ({KINDS_AR[c.kind] ?? c.kind})</option>)}
        </select>
        <label className="text-sm">الكود (ZIP) *<Input name="code" type="file" accept=".zip" required /></label>
        <label className="text-sm">التقرير (PDF/DOCX)<Input name="report" type="file" accept=".pdf,.docx" /></label>
        <label className="text-sm">قاعدة البيانات (SQL أو MongoDB JSON)<Input name="database" type="file" accept=".sql,.json" /></label>
        <label className="text-sm">نوع قاعدة البيانات
          <select name="db_dialect" className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm">
            <option value="mysql">MySQL</option><option value="postgresql">PostgreSQL</option><option value="sqlite">SQLite</option><option value="mongodb">MongoDB</option>
          </select>
        </label>
        <div className="md:col-span-2 space-y-2">
          <ErrorBox error={error} />
          {progress && (
            <div role="status" className="space-y-1">
              <div className="flex justify-between text-xs text-slate-600">
                <span>{progress.waiting ? `انقطع الاتصال أثناء رفع ${progress.label}؛ سيُستكمل تلقائياً من حيث توقف…` : `جارٍ رفع ${progress.label}`}</span>
                <span className="ltr">{Math.round((100 * progress.sent) / progress.total)}%</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-slate-200">
                <div className={`h-full rounded-full ${progress.waiting ? "bg-amber-500" : "bg-indigo-600"}`} style={{ width: `${(100 * progress.sent) / progress.total}%` }} />
              </div>
            </div>
          )}
          <Button type="submit" disabled={busy}>{busy ? "جارٍ الرفع…" : "تسليم وتحليل"}</Button>
          <p className="text-xs text-slate-500">الرفع يتحمل ضعف الإنترنت وانقطاع الكهرباء: إن توقف، اختر الملف نفسه مرة أخرى وسيُكمل من حيث وصل.</p>
        </div>
      </form>
    </Card>
  );
}
