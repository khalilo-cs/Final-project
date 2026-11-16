import { useEffect, useRef, useState } from "react";
import { ApiError, del, get, post } from "../api";
import { Badge, Button, Card, ErrorBox, useLoad } from "../components/ui";

interface Answer { line: number; original_line: string; mutated_line: string; description_ar: string }
interface Challenge {
  id: string; position: number; status: "pending" | "active" | "answered" | "expired";
  file: string; function: string; seconds_allowed: number; seconds_left?: number;
  code?: string; start_line?: number; located?: boolean; fixed?: boolean; score?: number;
  seconds?: number; chosen_line?: number; fixed_line?: string; explanation?: string;
  answer?: Answer; focus_losses?: number;
}
interface State { started: boolean; score: number | null; challenges: Challenge[] }

const clock = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

function Code({ challenge, selected, onSelect, mark }: { challenge: Challenge; selected?: number; onSelect?: (line: number, text: string) => void; mark?: number }) {
  const lines = (challenge.code ?? "").split("\n");
  const first = challenge.start_line ?? 1;
  return (
    <div dir="ltr" className="overflow-x-auto rounded-lg border border-slate-200 bg-slate-50 py-2 font-mono text-xs leading-6">
      {lines.map((text, i) => {
        const line = first + i;
        const tone = line === mark ? "bg-rose-100" : line === selected ? "bg-indigo-100" : onSelect ? "hover:bg-slate-100" : "";
        return (
          <div key={line} role={onSelect ? "button" : undefined} tabIndex={onSelect ? 0 : undefined}
            onClick={() => onSelect?.(line, text)} onKeyDown={(e) => e.key === "Enter" && onSelect?.(line, text)}
            className={`flex gap-3 px-3 ${tone} ${onSelect ? "cursor-pointer" : ""}`}>
            <span className="w-8 shrink-0 select-none text-right text-slate-400">{line}</span>
            <span className="whitespace-pre">{text || " "}</span>
          </div>
        );
      })}
    </div>
  );
}

function Active({ challenge, onDone }: { challenge: Challenge; onDone: (state: State) => void }) {
  const [left, setLeft] = useState(challenge.seconds_left ?? challenge.seconds_allowed);
  const [line, setLine] = useState<number>();
  const [fixed, setFixed] = useState("");
  const [why, setWhy] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const losses = useRef(0);

  useEffect(() => {
    const timer = window.setInterval(() => setLeft((s) => Math.max(0, s - 1)), 1000);
    const lost = () => { if (document.visibilityState === "hidden") losses.current += 1; };
    document.addEventListener("visibilitychange", lost);
    return () => { window.clearInterval(timer); document.removeEventListener("visibilitychange", lost); };
  }, []);

  const send = async () => {
    setBusy(true);
    setError(undefined);
    try {
      onDone(await post<State>("projects", `/api/v1/fingerprint/challenges/${challenge.id}/answer`,
        { line: line ?? 1, fixed_line: fixed, explanation: why, focus_losses: losses.current }));
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) onDone(await get<State>("projects", `/api/v1/fingerprint/${location.pathname.split("/").pop()}`));
      else setError(e);
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => { if (left === 0 && !busy) void send(); }, [left]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm">
          التحدي {challenge.position}: الدالة <code className="ltr inline-block">{challenge.function}</code> في <code className="ltr inline-block">{challenge.file}</code>
        </div>
        <Badge tone={left <= 30 ? "red" : "blue"}><span className="ltr inline-block font-mono">{clock(left)}</span></Badge>
      </div>
      <p className="text-sm text-slate-600">هذه دالتك، وغُيّر فيها <b>شيء واحد صغير</b> عمّا كتبته. اضغط على السطر الذي تغيّر، ثم اكتبه كما كان.</p>
      <Code challenge={challenge} selected={line} onSelect={(n, text) => { setLine(n); setFixed(text.trim()); }} />
      {line !== undefined && (
        <div className="space-y-2">
          <label className="block text-sm font-semibold">السطر {line} بعد تصحيحه
            <input dir="ltr" value={fixed} onChange={(e) => setFixed(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 p-2 font-mono text-xs focus:border-indigo-500 focus:outline-none" />
          </label>
          <label className="block text-sm font-semibold">ما أثر هذا التغيير على عمل البرنامج؟ <span className="font-normal text-slate-400">(يقرؤه الدكتور)</span>
            <textarea value={why} onChange={(e) => setWhy(e.target.value)} rows={2}
              className="mt-1 w-full rounded-lg border border-slate-300 p-2 text-sm focus:border-indigo-500 focus:outline-none" />
          </label>
        </div>
      )}
      <ErrorBox error={error} />
      <Button onClick={() => void send()} disabled={busy || line === undefined}>تأكيد الإجابة</Button>
    </div>
  );
}

function Result({ challenge, staff }: { challenge: Challenge; staff: boolean }) {
  const verdict = challenge.status === "expired" ? ["انتهى الوقت", "red"] : challenge.fixed ? ["وجده وأصلحه", "green"]
    : challenge.located ? ["وجده ولم يصلحه", "amber"] : ["لم يجده", "red"];
  return (
    <details className="rounded-lg border border-slate-200 p-3">
      <summary className="flex cursor-pointer flex-wrap items-center gap-2 text-sm">
        <Badge tone={verdict[1] as "red" | "green" | "amber"}>{verdict[0]}</Badge>
        <code className="ltr">{challenge.function}</code>
        <span className="text-slate-500">{challenge.score ?? 0}/100</span>
        {challenge.seconds !== undefined && <span className="text-xs text-slate-400">خلال {clock(challenge.seconds)}</span>}
        {staff && (challenge.focus_losses ?? 0) > 0 && <Badge tone="amber">غادر الصفحة {challenge.focus_losses} مرة</Badge>}
      </summary>
      {challenge.answer && (
        <div className="mt-3 space-y-2 text-sm">
          <div>التغيير المزروع (السطر {challenge.answer.line}): {challenge.answer.description_ar}</div>
          <Code challenge={challenge} mark={challenge.answer.line} selected={challenge.chosen_line} />
          <div dir="ltr" className="rounded bg-emerald-50 px-3 py-1 font-mono text-xs">{challenge.answer.original_line.trim()}</div>
          {challenge.fixed_line && <div>إجابة الطالب: <code className="ltr inline-block text-xs">{challenge.fixed_line}</code></div>}
          {challenge.explanation && <div className="text-slate-600">شرحه: {challenge.explanation}</div>}
        </div>
      )}
    </details>
  );
}

export function FingerprintPanel({ id, owner, staff }: { id: string; owner: boolean; staff: boolean }) {
  const [loaded, , reload] = useLoad(() => get<State>("projects", `/api/v1/fingerprint/${id}`), [id]);
  const [state, setState] = useState<State>();
  const [error, setError] = useState<unknown>();
  const current = state ?? loaded;
  if (!current || (!owner && !current.started)) return null;
  const active = current.challenges.find((c) => c.status === "active");
  const pending = current.challenges.some((c) => c.status === "pending");
  const done = current.challenges.filter((c) => c.status === "answered" || c.status === "expired");
  const act = (path: string) => post<State>("projects", path, {}).then(setState).catch(setError);

  return (
    <Card title="🧬 بصمة الفهم" actions={current.score !== null ? <Badge tone={current.score >= 60 ? "green" : "red"}>{current.score}/100</Badge> : undefined}>
      {!current.started && (
        <div className="space-y-3 text-sm">
          <p>اختبار قصير يثبت أنك تفهم كودك: نعرض عليك {3} دوال من مشروعك وقد غُيّر في كل منها شيء صغير واحد، وعليك أن تجده وتعيده كما كان.</p>
          <ul className="list-disc space-y-1 pr-5 text-slate-600">
            <li>لكل تحدٍّ 4 دقائق، ويبدأ العدّ عند فتحه.</li>
            <li>محاولة واحدة فقط، والنتيجة تظهر للدكتور ضمن أصالة المشروع.</li>
            <li>أجب دون الرجوع لملفاتك؛ مغادرة الصفحة تُسجَّل.</li>
          </ul>
          <Button onClick={() => void act(`/api/v1/fingerprint/${id}/start`)}>ابدأ الاختبار</Button>
        </div>
      )}
      {current.started && (
        <div className="space-y-4">
          {owner && active && <Active key={active.id} challenge={active} onDone={setState} />}
          {owner && !active && pending && (
            <div className="flex items-center gap-3">
              <Button onClick={() => void act(`/api/v1/fingerprint/${id}/next`)}>افتح التحدي التالي ({done.length + 1} من {current.challenges.length})</Button>
              <span className="text-xs text-slate-500">يبدأ الوقت فور الفتح.</span>
            </div>
          )}
          {done.length > 0 && <div className="space-y-2">{done.map((c) => <Result key={c.id} challenge={c} staff={staff} />)}</div>}
          {staff && current.challenges.some((c) => c.status === "pending" || c.status === "active") && <p className="text-sm text-slate-500">الطالب لم يُكمل الاختبار بعد.</p>}
          {staff && (
            <Button variant="secondary" onClick={() => { if (confirm("السماح بمحاولة جديدة يحذف نتيجة المحاولة الحالية. متابعة؟")) void del("projects", `/api/v1/fingerprint/${id}`).then(() => { setState(undefined); reload(); }).catch(setError); }}>
              السماح بمحاولة جديدة
            </Button>
          )}
        </div>
      )}
      <ErrorBox error={error} />
    </Card>
  );
}
