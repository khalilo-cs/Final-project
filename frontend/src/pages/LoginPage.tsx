import { useState, type FormEvent } from "react";
import { useAuth } from "../auth";
import { Button, Card, ErrorBox, Input } from "../components/ui";

export function LoginPage() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [form, setForm] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const field = (name: string) => ({
    value: form[name] ?? "",
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [name]: e.target.value }),
  });

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      if (mode === "login") await login(form.username ?? "", form.password ?? "");
      else await register(form);
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="w-full max-w-md space-y-4">
        <div className="text-center">
          <div className="text-3xl font-black text-indigo-700">فاحص المشاريع الذكي</div>
          <p className="mt-2 text-sm text-slate-500">تحليل مشاريع التخرج ومناقشتها بالذكاء الاصطناعي — جامعة صنعاء</p>
        </div>
        <Card>
          <div className="mb-4 grid grid-cols-2 gap-1 rounded-lg bg-slate-100 p-1">
            {(["login", "register"] as const).map((m) => (
              <button key={m} onClick={() => setMode(m)}
                className={`rounded-md py-1.5 text-sm font-semibold ${mode === m ? "bg-white shadow" : "text-slate-500"}`}>
                {m === "login" ? "تسجيل الدخول" : "حساب طالب جديد"}
              </button>
            ))}
          </div>
          <form onSubmit={submit} className="space-y-3">
            <Input placeholder="اسم المستخدم أو البريد" required {...field("username")} />
            {mode === "register" && (
              <>
                <Input placeholder="الاسم الكامل" required {...field("full_name")} />
                <Input placeholder="البريد الإلكتروني" type="email" required {...field("email")} />
                <Input placeholder="الرقم الجامعي" {...field("student_id")} />
              </>
            )}
            <Input placeholder="كلمة المرور" type="password" required minLength={mode === "register" ? 8 : 1} {...field("password")} />
            <ErrorBox error={error} />
            <Button type="submit" disabled={busy} className="w-full">{mode === "login" ? "دخول" : "إنشاء الحساب"}</Button>
          </form>
        </Card>
      </div>
    </div>
  );
}
