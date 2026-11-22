import { CodeView } from "../components/CodeView";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { get, post, put } from "../api";
import { Badge, Button, Card, ErrorBox, Input, Loading, Score, VERDICT_AR, useLoad } from "../components/ui";
import type { QA, VivaState } from "../types";
import { canSpeak, speak, useDictation } from "../components/voice";
import { drafts, isNetworkError, waitForConnection } from "../resilience";

const PROVIDER_AR: Record<string, string> = { template: "المحرك المدمج", claude: "Claude", ollama: "نموذج محلي", openai_compatible: "خادم نماذج" };
const TYPE_AR: Record<string, string> = { understanding: "فهم عام", technical: "تقني", challenge: "تحدٍّ", verification: "تحقق" };

export function VivaPage() {
  const { id = "" } = useParams();
  const [state, setState] = useState<VivaState>();
  const [error, setError] = useState<unknown>();
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [waiting, setWaiting] = useState(false);
  const box = useRef<HTMLTextAreaElement>(null);
  const [autoRead, setAutoRead] = useState(false);
  const dictation = useDictation(
    state?.language ?? "ar",
    (text) => setAnswer((current) => (current ? `${current} ${text}` : text)),
    state?.current_question?.text,
  );

  useEffect(() => {
    get<VivaState>("viva", `/api/v1/viva/${id}`).then(setState).catch(setError);
  }, [id]);
  useEffect(() => box.current?.focus(), [state?.question_number]);
  useEffect(() => {
    if (autoRead && state?.current_question) speak(state.current_question.text, state.language);
  }, [autoRead, state?.question_number]); // eslint-disable-line react-hooks/exhaustive-deps

  // The answer in progress is kept on this device: a power cut does not lose it.
  const draftKey = `${id}.${state?.question_number ?? 0}`;
  useEffect(() => { if (state?.status === "in_progress") setAnswer(drafts.load(draftKey)); }, [draftKey]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (state?.status === "in_progress") drafts.save(draftKey, answer); }, [answer]); // eslint-disable-line react-hooks/exhaustive-deps
  // Signs of life: the server stops the clock while this page cannot reach it.
  useEffect(() => {
    if (state?.status !== "in_progress") return;
    const beat = () => post<{ seconds_left: number; paused_seconds: number; interruptions: number }>("viva", `/api/v1/viva/${id}/heartbeat`)
      .then((b) => setState((current) => (current ? { ...current, ...b } : current))).catch(() => undefined);
    const timer = window.setInterval(beat, 15000);
    window.addEventListener("online", beat);
    return () => { window.clearInterval(timer); window.removeEventListener("online", beat); };
  }, [id, state?.status]);

  const send = async () => {
    dictation.cancel();
    setBusy(true);
    setError(undefined);
    const number = state?.question_number;
    try {
      for (;;) {
        try {
          // question_number makes a repeat harmless if the first try did arrive.
          setState(await post<VivaState>("viva", `/api/v1/viva/${id}/answer`, { answer, question_number: number }));
          break;
        } catch (reason) {
          if (!isNetworkError(reason)) throw reason;
          setWaiting(true);
          await waitForConnection(3000);
        }
      }
      drafts.save(draftKey, "");
      setAnswer("");
    } catch (reason) {
      setError(reason);
    } finally {
      setWaiting(false);
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
        <div className="flex items-start gap-3">
          <p className="flex-1 text-lg leading-8">{question.text}</p>
          {canSpeak() && (
            <button title="اقرأ السؤال بصوت" onClick={() => speak(question.text, state.language)} className="rounded-full bg-slate-100 p-2 text-lg hover:bg-indigo-100">🔊</button>
          )}
        </div>
        {question.code && <CodeView code={question.code} file={question.related_file} lines={question.related_lines} />}
      </Card>
      <Card>
        <textarea ref={box} value={answer} onChange={(e) => setAnswer(e.target.value)} rows={6}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && answer.trim()) void send(); }}
          placeholder="اكتب إجابتك بتفصيل: اذكر أسماء الدوال والملفات والجداول من مشروعك…"
          className="w-full rounded-lg border border-slate-300 p-3 text-sm leading-7 focus:border-indigo-500 focus:outline-none" />
        {dictation.error && <p className="mt-2 text-sm text-rose-600">{dictation.error}</p>}
        {waiting && <p role="status" className="mt-2 text-sm font-semibold text-amber-700">انقطع الاتصال. إجابتك محفوظة وستُرسل تلقائياً عند عودته، والوقت متوقف.</p>}
        {(state.interruptions ?? 0) > 0 && !waiting && (
          <p className="mt-2 text-xs text-slate-500">سُجّل {state.interruptions} انقطاع، وأُعيد لك {Math.round((state.paused_seconds ?? 0) / 60)} دقيقة من الوقت.</p>
        )}
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Button variant="secondary" onClick={() => void end()}>إنهاء المناقشة</Button>
            {dictation.supported && (
              <Button variant={dictation.listening ? "danger" : "secondary"} disabled={dictation.transcribing}
                onClick={dictation.listening ? dictation.stop : dictation.start}
                title={dictation.engine === "server" ? "يُحوَّل صوتك إلى نص على خادم الجامعة" : "التعرّف على الصوت من المتصفح"}>
                {dictation.transcribing ? "… جارٍ تحويل الصوت إلى نص" : dictation.listening ? "⏹ إيقاف التسجيل" : "🎤 أجب بصوتك"}
              </Button>
            )}
            {canSpeak() && (
              <label className="flex items-center gap-1 text-xs text-slate-500">
                <input type="checkbox" checked={autoRead} onChange={(e) => setAutoRead(e.target.checked)} /> قراءة الأسئلة تلقائياً
              </label>
            )}
          </div>
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
        {(state.pauses?.length ?? 0) > 0 && (
          <div className="mt-3 rounded-lg bg-amber-50 p-3 text-sm">
            <b>انقطاعات أثناء المناقشة ({state.pauses!.length})</b>: أُعيد للطالب {Math.round((state.paused_seconds ?? 0) / 60)} دقيقة من الوقت.
            <ul className="mt-1 text-xs text-slate-600">
              {state.pauses!.map((p, i) => (
                <li key={i}>
                  <span className="ltr inline-block">{new Date(p.from).toLocaleTimeString("ar")}</span>: غاب {Math.round(p.seconds / 60) || 1} دقيقة
                  {p.credited < p.seconds && " (تجاوز الحد المسموح، لم يُعوَّض كاملاً)"}
                </li>
              ))}
            </ul>
          </div>
        )}
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
