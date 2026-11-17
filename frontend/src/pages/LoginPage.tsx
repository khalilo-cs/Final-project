import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, get } from "../api";
import { useAuth } from "../auth";
import { Button, Card, ErrorBox, Input } from "../components/ui";

const SSO_ERRORS: Record<string, string> = {
  cancelled: "أُلغي الدخول بحساب الجامعة.",
  expired: "انتهت صلاحية محاولة الدخول، حاول مرة أخرى.",
  domain_not_allowed: "هذا البريد ليس من نطاق الجامعة المسموح.",
  email_not_verified: "بريدك غير مؤكد لدى مزود حسابات الجامعة.",
  no_email: "لم يُرسل مزود حسابات الجامعة بريدك الإلكتروني.",
  account_conflict: "هذا البريد مرتبط بحساب جامعي آخر؛ راجع مسؤول النظام.",
  provider_unreachable: "تعذّر الاتصال بخادم حسابات الجامعة حالياً.",
};

/** Reads (and removes) the result the university sign-in left in the URL fragment. */
function takeSsoResult(): { handoff?: string; error?: string } {
  const params = new URLSearchParams(window.location.hash.slice(1));
  if (!params.has("oidc") && !params.has("oidc_error")) return {};
  window.history.replaceState(null, "", window.location.pathname);
  return { handoff: params.get("oidc") ?? undefined, error: params.get("oidc_error") ?? undefined };
}

export function LoginPage() {
  const { login, loginWithHandoff, register } = useAuth();
  const [sso, setSso] = useState<{ enabled: boolean; name: string } | null>(null);
  const handled = useRef(false);
  const [mode, setMode] = useState<"login" | "register">("login");
  const [form, setForm] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const field = (name: string) => ({
    value: form[name] ?? "",
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [name]: e.target.value }),
  });

  useEffect(() => {
    get<{ enabled: boolean; name: string }>("auth", "/api/v1/auth/oidc").then(setSso).catch(() => setSso(null));
    if (handled.current) return;
    handled.current = true;
    const result = takeSsoResult();
    if (result.error) setError(SSO_ERRORS[result.error] ?? "تعذّر الدخول بحساب الجامعة.");
    if (result.handoff) {
      setBusy(true);
      loginWithHandoff(result.handoff)
        .catch(() => setError(SSO_ERRORS.expired))
        .finally(() => setBusy(false));
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      if (mode === "login") await login(form.username ?? "", form.password ?? "");
      else await register(form);
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 429) {
        setError("محاولات دخول فاشلة كثيرة. انتظر ربع ساعة ثم حاول مرة أخرى.");
      } else if (reason instanceof ApiError && reason.status === 401) {
        setError("اسم المستخدم أو كلمة المرور غير صحيحة.");
      } else {
        setError(reason);
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="w-full max-w-md space-y-4">
        <div className="text-center">
          <div className="text-3xl font-black text-indigo-700">مِحَكّ</div>
          <p className="mt-2 text-sm text-slate-500">تقييم المشاريع البرمجية لكل مستويات الحاسوب والتحقق من فهم الطالب لها — جامعة صنعاء</p>
        </div>
        <Card>
          {sso?.enabled && (
            <>
              <a href="/svc/auth/api/v1/auth/oidc/login"
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-bold text-white hover:bg-indigo-700">
                <span aria-hidden>🎓</span> الدخول عبر {sso.name}
              </a>
              <div className="my-4 flex items-center gap-3 text-xs text-slate-400">
                <span className="h-px flex-1 bg-slate-200" />أو باسم المستخدم<span className="h-px flex-1 bg-slate-200" />
              </div>
            </>
          )}
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
