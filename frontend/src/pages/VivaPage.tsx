import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { get, post, put } from "../api";
import { Badge, Button, Card, ErrorBox, Input, Loading, Score, VERDICT_AR, useLoad } from "../components/ui";
import type { QA, VivaState } from "../types";

const PROVIDER_AR: Record<string, string> = { template: "المحرك المدمج", claude: "Claude", ollama: "نموذج محلي", openai_compatible: "خادم نماذج" };
const TYPE_AR: Record<string, string> = { understanding: "فهم عام", technical: "تقني", challenge: "تحدٍّ", verification: "تحقق" };

export function VivaPage() {
  const { id = "" } = useParams();
  const [state, setState] = useState<VivaState>();
  const [error, setError] = useState<unknown>();
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const box = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    get<VivaState>("viva", `/api/v1/viva/${id}`).then(setState).catch(setError);
  }, [id]);
  useEffect(() => box.current?.focus(), [state?.question_number]);

  const send = async () => {
    setBusy(true);
    setError(undefined);
    try {
      setState(await post<VivaState>("viva", `/api/v1/viva/${id}/answer`, { answer }));
      setAnswer("");
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(false);
    }
  };
  const end = async () => {
    if (window.confirm("إنهاء المناقشة الآن؟ ستُحسب الدرجة على الأسئلة التي أجبت عنها.")) {
      setState(await post<VivaState>("viva", `/api/v1/viva/${id}/end`));
    }
  };

  if (error && !state) return <ErrorBox error={error} />;
  if (!state) return <Loading />;
  if (state.status !== "in_progress") return <VivaResult state={state} />;
  const question = state.current_question!;
  const progress = Math.round(((state.question_number - 1) / state.max_questions) * 100);

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-black">🎙️ المناقشة الذكية</h1>
        <div className="flex items-center gap-2 text-sm">
          <span>المستوى</span>
          {[1, 2, 3, 4].map((l) => <span key={l} className={`h-3 w-6 rounded ${l <= state.level ? "bg-indigo-600" : "bg-slate-200"}`} />)}
        </div>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-200"><div className="h-full bg-indigo-500 transition-all" style={{ width: `${progress}%` }} /></div>
      <Card>
        <div className="mb-3 flex flex-wrap items-center gap-2 text-sm text-slate-500">
          <span>السؤال {state.question_number} من {state.max_questions}</span>
          <Badge tone="blue">{TYPE_AR[question.type] ?? question.type}</Badge>
          {question.related_file && <code className="text-xs">{question.related_file}{question.related_lines ? `:${question.related_lines}` : ""}</code>}
        </div>
        <p className="text-lg leading-8">{question.text}</p>
        {question.code && <pre className="mt-3 max-h-80 overflow-auto rounded-lg bg-slate-900 p-3 text-xs leading-5 text-slate-100">{question.code}</pre>}
      </Card>
      <Card>
        <textarea ref={box} value={answer} onChange={(e) => setAnswer(e.target.value)} rows={6}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && answer.trim()) void send(); }}
          placeholder="اكتب إجابتك بتفصيل: اذكر أسماء الدوال والملفات والجداول من مشروعك…"
          className="w-full rounded-lg border border-slate-300 p-3 text-sm leading-7 focus:border-indigo-500 focus:outline-none" />
        <div className="mt-3 flex items-center justify-between">
          <Button variant="secondary" onClick={() => void end()}>إنهاء المناقشة</Button>
          <div className="flex items-center gap-3">
            <span className="text-xs text-slate-400">Ctrl + Enter للإرسال</span>
            <Button disabled={!answer.trim() || busy} onClick={() => void send()}>{busy ? "جارٍ التقييم…" : "إرسال الإجابة"}</Button>
          </div>
        </div>
        <ErrorBox error={error} />
      </Card>
      <p className="text-center text-xs text-slate-400">الأسئلة مولّدة من كود مشروعك. المقيّمون: {state.providers.map((p) => PROVIDER_AR[p] ?? p).join("، ")}</p>
    </div>
  );
}

function VivaResult({ state }: { state: VivaState }) {
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <Card title="انتهت المناقشة">
        <div className="flex items-center gap-8">
          <Score value={state.overall_score} label="درجة المناقشة" />
          <p className="text-sm text-slate-600">ستدخل هذه الدرجة في تقييم مشروعك، ويمكن للدكتور مراجعتها.</p>
        </div>
        <Link to={`/projects/${state.project_id}`} className="mt-4 inline-block text-sm text-indigo-600 underline">العودة إلى المشروع</Link>
      </Card>
      {state.transcript && <Transcript items={state.transcript} />}
    </div>
  );
}

function Transcript({ items, review }: { items: QA[]; review?: (qa: QA) => React.ReactNode }) {
  return (
    <div className="space-y-3">
      {items.map((qa) => (
        <Card key={qa.id}>
          <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
            <b>س{qa.number}</b>
            <Badge tone="blue">{TYPE_AR[qa.type] ?? qa.type} · مستوى {qa.level}</Badge>
            <Badge tone={VERDICT_AR[qa.verdict]?.tone ?? "gray"}>{VERDICT_AR[qa.verdict]?.label ?? qa.verdict}</Badge>
            <span className="font-bold">{qa.score}</span>
            <span className="text-xs text-slate-400">ثقة التقييم {Math.round(qa.confidence * 100)}%</span>
          </div>
          <p className="font-semibold">{qa.question}</p>
          <p className="mt-2 whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-sm">{qa.answer}</p>
          {review && review(qa)}
        </Card>
      ))}
    </div>
  );
}

export function VivaReviewPage() {
  const { id = "" } = useParams();
  const [state, error, reload] = useLoad(() => get<VivaState>("viva", `/api/v1/viva/${id}`), [id]);
  if (error) return <ErrorBox error={error} />;
  if (!state) return <Loading />;
  return (
    <div className="space-y-4">
      <Card title="مراجعة المناقشة">
        <div className="flex items-center gap-8">
          <Score value={state.overall_score} label="درجة المناقشة" />
          <p className="text-sm text-slate-600">صحّح تقييم أي إجابة: يتعلم النظام من تصحيحاتك ويقيّم الإجابات المشابهة لاحقاً بناءً عليها، ويصحّح انحياز كل نموذج.</p>
        </div>
        <Link to={`/projects/${state.project_id}`} className="mt-3 inline-block text-sm text-indigo-600 underline">المشروع</Link>
      </Card>
      <Transcript items={state.transcript ?? []} review={(qa) => <ReviewForm qa={qa} onSaved={reload} />} />
    </div>
  );
}

function ReviewForm({ qa, onSaved }: { qa: QA; onSaved: () => void }) {
  const [score, setScore] = useState(String(qa.score));
  const [verdict, setVerdict] = useState(qa.verdict);
  const [notes, setNotes] = useState("");
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<unknown>();
  const save = async () => {
    try {
      await put("viva", `/api/v1/viva/qa/${qa.id}/review`, { score: Number(score), verdict, notes: notes || null });
      setSaved(true);
      onSaved();
    } catch (reason) {
      setError(reason);
    }
  };
  return (
    <div className="mt-3 space-y-2 border-t pt-3">
      <div className="flex flex-wrap gap-2 text-xs text-slate-500">
        {Object.entries(qa.provider_scores).map(([name, value]) => <Badge key={name}>{name}: {value}</Badge>)}
      </div>
      {qa.reasoning && <p className="ltr text-left text-xs text-slate-500">{qa.reasoning}</p>}
      <div className="flex flex-wrap items-end gap-2">
        <Input type="number" min={0} max={100} value={score} onChange={(e) => setScore(e.target.value)} className="w-24" />
        <select value={verdict} onChange={(e) => setVerdict(e.target.value)} className="rounded-lg border border-slate-300 px-2 py-2 text-sm">
          {Object.entries(VERDICT_AR).map(([key, v]) => <option key={key} value={key}>{v.label}</option>)}
        </select>
        <Input placeholder="ملاحظة (اختياري)" value={notes} onChange={(e) => setNotes(e.target.value)} className="flex-1" />
        <Button variant="secondary" onClick={() => void save()}>{saved ? "✓ حُفظ" : "حفظ التصحيح"}</Button>
      </div>
      <ErrorBox error={error} />
    </div>
  );
}
