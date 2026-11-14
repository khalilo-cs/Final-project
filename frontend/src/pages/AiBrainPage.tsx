import { useState } from "react";
import { download, get, post } from "../api";
import { Badge, Button, Card, ErrorBox, Input, Loading, Score, useLoad } from "../components/ui";

interface Status { providers: { name: string; available: boolean; kind: string }[]; sessions: number; answers: number; professor_reviews: number; knowledge_items: number }
interface QuestionStat { key: string; asked: number; average_score: number; discrimination: number | null; priority: number }
interface Learning { provider_calibration: Record<string, { bias: number; mean_error: number; reviews: number }>; most_revealing_questions: QuestionStat[]; least_revealing_questions: QuestionStat[]; notes: string }
interface Source { id: string; url: string; status: string; error: string | null; items: number; fetched_at: string | null }
interface Hit { source: string; type: string; title: string | null; text: string; score: number }

const PROVIDER_AR: Record<string, string> = { template: "المحرك المدمج", claude: "Claude", ollama: "نموذج محلي (Ollama)", openai_compatible: "خادم نماذج متوافق" };

export function AiBrainPage() {
  const [status] = useLoad(() => get<Status>("viva", "/api/v1/ai/status"));
  const [learning] = useLoad(() => get<Learning>("viva", "/api/v1/ai/learning"));
  return (
    <>
      <div>
        <h1 className="text-2xl font-black">🧠 عقل النظام</h1>
        <p className="mt-1 text-sm text-slate-500">ما يعرفه النظام، ومن يتعلم، وأي النماذج يعمل معها. يعمل دائماً بمحركه المدمج، ويستعين بأي نموذج متاح.</p>
      </div>
      <div className="grid gap-4 md:grid-cols-4">
        <Card><Score count value={status?.sessions} label="جلسات مناقشة" /></Card>
        <Card><Score count value={status?.answers} label="إجابات قيّمها" /></Card>
        <Card><Score count value={status?.professor_reviews} label="تصحيحات الدكاترة (تعلّم)" /></Card>
        <Card><Score count value={status?.knowledge_items} label="عناصر المعرفة" /></Card>
      </div>
      <Card title="النماذج المتصلة">
        {!status ? <Loading /> : (
          <div className="grid gap-3 md:grid-cols-4">
            {status.providers.map((p) => (
              <div key={p.name} className="rounded-lg border border-slate-200 p-3">
                <div className="font-semibold">{PROVIDER_AR[p.name] ?? p.name}</div>
                <Badge tone={p.available ? "green" : "gray"}>{p.available ? "متصل" : "غير مفعّل"}</Badge>
              </div>
            ))}
          </div>
        )}
      </Card>
      {learning && (
        <div className="grid gap-6 md:grid-cols-2">
          <Card title="معايرة النماذج مقابل تقييم الدكاترة">
            {Object.keys(learning.provider_calibration).length === 0 ? (
              <p className="text-sm text-slate-500">يحتاج 3 تصحيحات على الأقل من الدكاترة لكل نموذج. صحّح تقييمات المناقشات من صفحة المراجعة.</p>
            ) : (
              <table className="w-full text-sm">
                <thead><tr className="border-b text-right text-slate-500"><th className="py-2">النموذج</th><th>الانحياز</th><th>متوسط الخطأ</th><th>تصحيحات</th></tr></thead>
                <tbody>{Object.entries(learning.provider_calibration).map(([name, c]) => (
                  <tr key={name} className="border-b border-slate-100"><td className="py-2">{PROVIDER_AR[name] ?? name}</td>
                    <td className={c.bias < 0 ? "text-rose-600" : "text-emerald-600"}>{c.bias > 0 ? "+" : ""}{c.bias} {c.bias < 0 ? "(متساهل)" : c.bias > 0 ? "(متشدد)" : ""}</td>
                    <td>{c.mean_error}</td><td>{c.reviews}</td></tr>
                ))}</tbody>
              </table>
            )}
          </Card>
          <Card title="أكثر الأسئلة كشفاً للفهم">
            {learning.most_revealing_questions.length === 0 ? <p className="text-sm text-slate-500">تظهر بعد اكتمال عدة مناقشات.</p> : (
              <ul className="space-y-1 text-sm">{learning.most_revealing_questions.map((q) => (
                <li key={q.key} className="flex justify-between"><code className="text-xs">{q.key}</code>
                  <span>تمييز <b>{q.discrimination ?? "—"}</b> · سُئل {q.asked}</span></li>
              ))}</ul>
            )}
          </Card>
        </div>
      )}
      <Knowledge />
      <Card title="بيانات التدريب" actions={<Button variant="secondary" onClick={() => void download("viva", "/api/v1/ai/dataset.jsonl", "viva-training.jsonl")}>⬇ تنزيل JSONL</Button>}>
        <p className="text-sm text-slate-600">كل إجابة صحّحها دكتور تصبح مثال تدريب. استخدم الملف لتدريب (fine-tune) نموذج محلي خاص بالجامعة، ثم شغّله عبر Ollama ليصبح أحد مقيّمي النظام.</p>
      </Card>
    </>
  );
}

function Knowledge() {
  const [sources, , reload] = useLoad(() => get<Source[]>("viva", "/api/v1/ai/knowledge/sources"));
  const [url, setUrl] = useState("");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Hit[]>();
  const [error, setError] = useState<unknown>();
  const add = async () => {
    setError(undefined);
    try {
      await post("viva", "/api/v1/ai/knowledge/sources", { url });
      setUrl("");
      setTimeout(reload, 1500);
    } catch (reason) {
      setError(reason);
    }
  };
  const search = async () => setHits(await get<Hit[]>("viva", `/api/v1/ai/knowledge/search?q=${encodeURIComponent(query)}`));
  return (
    <Card title="📚 مصادر المعرفة">
      <p className="mb-3 text-sm text-slate-500">أضف صفحات توثيق موثوقة (مثل OWASP أو توثيق Java) ليتعلم منها النظام ويستشهد بها عند كتابة الأسئلة. يحترم قواعد كل موقع (robots.txt).</p>
      <div className="flex gap-2">
        <Input placeholder="https://cheatsheetseries.owasp.org/..." value={url} onChange={(e) => setUrl(e.target.value)} className="ltr" />
        <Button disabled={!url} onClick={() => void add()}>تعلّم من هذه الصفحة</Button>
      </div>
      <ErrorBox error={error} />
      {sources && sources.length > 0 && (
        <ul className="mt-3 space-y-1 text-sm">{sources.map((s) => (
          <li key={s.id} className="flex items-center gap-2">
            <Badge tone={s.status === "indexed" ? "green" : s.status === "failed" ? "red" : "amber"}>{s.status}</Badge>
            <span className="ltr truncate">{s.url}</span>
            {s.items > 0 && <span className="text-slate-400">({s.items} مقطع)</span>}
            {s.error && <span className="text-xs text-rose-600">{s.error}</span>}
          </li>
        ))}</ul>
      )}
      <div className="mt-4 flex gap-2 border-t pt-4">
        <Input placeholder="ابحث في معرفة النظام…" value={query} onChange={(e) => setQuery(e.target.value)} />
        <Button variant="secondary" disabled={query.length < 2} onClick={() => void search()}>بحث</Button>
      </div>
      {hits && (hits.length === 0 ? <p className="mt-2 text-sm text-slate-500">لا نتائج.</p> : (
        <ul className="mt-3 space-y-2 text-sm">{hits.map((h, i) => (
          <li key={i} className="rounded-lg bg-slate-50 p-2"><div className="font-semibold">{h.title ?? h.source} <Badge>{h.type}</Badge></div><p className="ltr text-left text-xs text-slate-600">{h.text}</p></li>
        ))}</ul>
      ))}
    </Card>
  );
}
