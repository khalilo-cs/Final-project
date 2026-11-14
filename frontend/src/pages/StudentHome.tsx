import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { get, post } from "../api";
import { Badge, Button, Card, ErrorBox, Input, Loading, STATUS_AR, useLoad } from "../components/ui";
import type { Course, Project } from "../types";

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
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    for (const name of ["report", "database"]) {
      if (!(data.get(name) as File)?.size) data.delete(name);
    }
    setBusy(true);
    setError(undefined);
    try {
      await post("projects", "/api/v1/projects", data);
      event.currentTarget?.reset();
      onDone();
    } catch (reason) {
      setError(reason);
    } finally {
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
          {courses.map((c) => <option key={c.id} value={c.id}>{c.code} — {c.name}</option>)}
        </select>
        <label className="text-sm">الكود (ZIP) *<Input name="code" type="file" accept=".zip" required /></label>
        <label className="text-sm">التقرير (PDF/DOCX)<Input name="report" type="file" accept=".pdf,.docx" /></label>
        <label className="text-sm">قاعدة البيانات (SQL)<Input name="database" type="file" accept=".sql" /></label>
        <label className="text-sm">نوع قاعدة البيانات
          <select name="db_dialect" className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm">
            <option value="mysql">MySQL</option><option value="postgresql">PostgreSQL</option><option value="sqlite">SQLite</option>
          </select>
        </label>
        <div className="md:col-span-2 space-y-2">
          <ErrorBox error={error} />
          <Button type="submit" disabled={busy}>{busy ? "جارٍ الرفع…" : "تسليم وتحليل"}</Button>
        </div>
      </form>
    </Card>
  );
}
