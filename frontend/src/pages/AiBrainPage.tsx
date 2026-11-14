import { useState } from "react";
import { download, get, post } from "../api";
import { Badge, Button, Card, Input, Loading, Score, useLoad } from "../components/ui";

interface AutoStats { topics: number; topics_waiting: number; question_bank: Record<string, number>; auto_labels: number; learned_points: number; knowledge_by_source: Record<string, number> }
interface Status { providers: { name: string; available: boolean; kind: string }[]; sessions: number; answers: number; professor_reviews: number; knowledge_items: number; auto_learning: AutoStats; training_data_policy: string }
interface LearningEvent { kind: string; summary: string; created_at: string }
interface TopicRow { key: string; title: string; source: string; seen_in_projects: number; docs_status: string; teacher_status: string; learned_at: string | null }
interface QuestionStat { key: string; asked: number; average_score: number; discrimination: number | null; priority: number }
interface Learning { provider_calibration: Record<string, { bias: number; mean_error: number; reviews: number }>; most_revealing_questions: QuestionStat[]; least_revealing_questions: QuestionStat[]; notes: string }
interface Hit { source: string; type: string; title: string | null; text: string; score: number }

const PROVIDER_AR: Record<string, string> = { template: "المحرك المدمج", claude: "Claude", ollama: "نموذج محلي (Ollama)", openai_compatible: "خادم نماذج متوافق" };
const SOURCE_AR: Record<string, string> = { builtin: "الحزمة المدمجة", "teacher:claude": "علّمه Claude", "teacher:ollama": "علّمه النموذج المحلي", "teacher:openai_compatible": "علّمه خادم النماذج", web: "التوثيق الرسمي", project: "المشاريع", reviewed_qa: "تصحيحات الدكاترة" };
const EVENT_ICON: Record<string, string> = { builtin: "📦", project: "📁", session: "💬", web: "🌐", teacher: "🎓" };

export function AiBrainPage() {
  const [status] = useLoad(() => get<Status>("viva", "/api/v1/ai/status"));
  const [learning] = useLoad(() => get<Learning>("viva", "/api/v1/ai/learning"));
  return (
    <>
      <div>
        <h1 className="text-2xl font-black">🧠 عقل النظام</h1>
        <p className="mt-1 text-sm text-slate-500">ما يعرفه النظام وكيف يتعلّم بنفسه، وأي النماذج يعمل معها. يعمل دائماً بمحركه المدمج، ويستعين بأي نموذج متاح.</p>
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
      {status && <AutoLearning stats={status.auto_learning} />}
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
      <KnowledgeSearch />
      <Card title="بيانات التدريب" actions={<Button variant="secondary" onClick={() => void download("viva", "/api/v1/ai/dataset.jsonl", "viva-training.jsonl")}>⬇ تنزيل JSONL</Button>}>
        <p className="text-sm text-slate-600">كل إجابة صحّحها دكتور تصبح مثال تدريب لنموذج محلي خاص بالجامعة (fine-tuning)، يُشغَّل بعدها عبر Ollama ليصبح أحد مقيّمي النظام. الملف يحتوي تقييمات الدكاترة فقط: ما كتبته النماذج الخارجية يُستخدم أثناء العمل ولا يُصدَّر للتدريب، احتراماً لشروط مزوّديها.</p>
      </Card>
    </>
  );
}

function AutoLearning({ stats }: { stats: AutoStats }) {
  const [events, , reloadEvents] = useLoad(() => get<LearningEvent[]>("viva", "/api/v1/ai/learning/events?limit=30"));
  const [topics, , reloadTopics] = useLoad(() => get<TopicRow[]>("viva", "/api/v1/ai/topics"));
  const [started, setStarted] = useState(false);
  const learnNow = async () => {
    await post("viva", "/api/v1/ai/learn/now");
    setStarted(true);
    setTimeout(() => { reloadEvents(); reloadTopics(); setStarted(false); }, 4000);
  };
  const statusBadge = (value: string, done: string) =>
    value === "done" ? <Badge tone="green">{done}</Badge> : value === "pending" ? <Badge tone="amber">قيد التعلّم</Badge>
      : value === "skipped" ? <Badge tone="blue">معروف مسبقاً</Badge> : <Badge>—</Badge>;
  return (
    <>
      <Card title="🔄 التعلّم التلقائي" actions={<Button variant="secondary" disabled={started} onClick={() => void learnNow()}>{started ? "يتعلّم الآن…" : "دورة تعلّم الآن"}</Button>}>
        <p className="mb-4 text-sm text-slate-600">
          يتعلّم النظام بنفسه دون تدخّل: من كل مشروع يُحلَّل، ومن كل مناقشة تنتهي، ومن التوثيق الرسمي لكل تقنية يراها، ومن نموذج معلّم (Claude) للمواضيع الجديدة. دورة التعلّم تعمل تلقائياً في الخلفية.
        </p>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <Score count value={stats.topics} label="مواضيع يعرفها" />
          <Score count value={stats.topics_waiting} label="مواضيع ينتظر تعلّمها" />
          <Score count value={stats.learned_points} label="نقاط إجابة اكتشفها" />
          <Score count value={stats.auto_labels} label="تقييمات تعلّمها بنفسه" />
        </div>
        <div className="mt-4 flex flex-wrap gap-2 text-xs">
          <span className="text-slate-500">بنك الأسئلة:</span>
          {Object.entries(stats.question_bank).map(([source, n]) => <Badge key={source} tone="purple">{SOURCE_AR[source] ?? source}: {n}</Badge>)}
          <span className="mr-3 text-slate-500">المعرفة:</span>
          {Object.entries(stats.knowledge_by_source).map(([source, n]) => <Badge key={source}>{SOURCE_AR[source] ?? source}: {n}</Badge>)}
        </div>
      </Card>
      <div className="grid gap-6 md:grid-cols-2">
        <Card title="ماذا تعلّم مؤخراً">
          {!events ? <Loading /> : events.length === 0 ? <p className="text-sm text-slate-500">لا شيء بعد.</p> : (
            <ul className="space-y-2 text-sm">{events.map((e, i) => (
              <li key={i} className="flex gap-2">
                <span>{EVENT_ICON[e.kind] ?? "•"}</span>
                <div><div>{e.summary}</div><div className="text-xs text-slate-400">{new Date(e.created_at).toLocaleString("ar")}</div></div>
              </li>
            ))}</ul>
          )}
        </Card>
        <Card title="المواضيع">
          {!topics ? <Loading /> : (
            <div className="max-h-96 overflow-y-auto">
              <table className="w-full text-sm">
                <thead><tr className="border-b text-right text-slate-500"><th className="py-2">الموضوع</th><th>في المشاريع</th><th>التوثيق</th><th>المعلّم</th></tr></thead>
                <tbody>{topics.map((t) => (
                  <tr key={t.key} className="border-b border-slate-100">
                    <td className="py-1.5">{t.title} <span className="text-xs text-slate-400">{t.source === "builtin" ? "(مدمج)" : "(من المشاريع)"}</span></td>
                    <td>{t.seen_in_projects}</td>
                    <td>{statusBadge(t.docs_status, "تعلّمه")}</td>
                    <td>{statusBadge(t.teacher_status, "شرحه")}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </>
  );
}

function KnowledgeSearch() {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Hit[]>();
  const search = async () => setHits(await get<Hit[]>("viva", `/api/v1/ai/knowledge/search?q=${encodeURIComponent(query)}`));
  return (
    <Card title="📚 ابحث في معرفة النظام">
      <div className="flex gap-2">
        <Input placeholder="مثال: prepared statement، تطبيع، Flask…" value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && query.length >= 2 && void search()} />
        <Button variant="secondary" disabled={query.length < 2} onClick={() => void search()}>بحث</Button>
      </div>
      {hits && (hits.length === 0 ? <p className="mt-2 text-sm text-slate-500">لا نتائج.</p> : (
        <ul className="mt-3 space-y-2 text-sm">{hits.map((h, i) => (
          <li key={i} className="rounded-lg bg-slate-50 p-2"><div className="font-semibold">{h.title ?? h.source} <Badge>{SOURCE_AR[h.type] ?? h.type}</Badge></div><p className="mt-1 text-xs text-slate-600">{h.text}</p></li>
        ))}</ul>
      ))}
    </Card>
  );
}
