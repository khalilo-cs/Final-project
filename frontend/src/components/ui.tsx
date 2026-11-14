import { useEffect, useState, type ReactNode } from "react";

export function Card({ title, children, actions }: { title?: ReactNode; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      {(title || actions) && (
        <div className="mb-4 flex items-center justify-between gap-3">
          {title && <h2 className="text-lg font-bold text-slate-800">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

const tones = {
  green: "bg-emerald-100 text-emerald-800",
  red: "bg-rose-100 text-rose-800",
  amber: "bg-amber-100 text-amber-800",
  blue: "bg-sky-100 text-sky-800",
  gray: "bg-slate-100 text-slate-700",
  purple: "bg-violet-100 text-violet-800",
};

export function Badge({ tone = "gray", children }: { tone?: keyof typeof tones; children: ReactNode }) {
  return <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${tones[tone]}`}>{children}</span>;
}

export function severityTone(severity: string): keyof typeof tones {
  return ({ Critical: "red", High: "red", Medium: "amber", Low: "blue" } as const)[severity as "High"] ?? "gray";
}

/** A 0-100 grade (colored by level) or, with `count`, a plain number. */
export function Score({ value, label, count = false }: { value: number | null | undefined; label?: string; count?: boolean }) {
  const tone = value == null ? "text-slate-400" : count ? "text-indigo-700" : value >= 75 ? "text-emerald-600" : value >= 50 ? "text-amber-600" : "text-rose-600";
  return (
    <div className="text-center">
      <div className={`text-3xl font-black ${tone}`}>{value == null ? "—" : Math.round(value)}</div>
      {label && <div className="mt-1 text-xs text-slate-500">{label}</div>}
    </div>
  );
}

export function Button({ variant = "primary", className = "", ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" }) {
  const styles = {
    primary: "bg-indigo-600 text-white hover:bg-indigo-700",
    secondary: "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50",
    danger: "bg-rose-600 text-white hover:bg-rose-700",
  }[variant];
  return <button {...props} className={`whitespace-nowrap rounded-lg px-4 py-2 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 ${styles} ${className}`} />;
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none ${props.className ?? ""}`} />;
}

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  return <div className="rounded-lg bg-rose-50 p-3 text-sm text-rose-700">{error instanceof Error ? error.message : String(error)}</div>;
}

export function Loading() {
  return <div className="p-8 text-center text-slate-500">جارٍ التحميل…</div>;
}

/** Load data once (and again when `deps` change); returns [data, error, reload]. */
export function useLoad<T>(load: () => Promise<T>, deps: unknown[] = []): [T | undefined, unknown, () => void] {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<unknown>();
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    load()
      .then((value) => alive && (setData(value), setError(undefined)))
      .catch((reason) => alive && setError(reason));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  return [data, error, () => setTick((t) => t + 1)];
}

export function DiffView({ diff }: { diff: string }) {
  return (
    <pre className="overflow-x-auto rounded-lg bg-slate-900 p-3 text-xs leading-5">
      {diff.split("\n").map((line, i) => {
        const color = line.startsWith("+") && !line.startsWith("+++") ? "text-emerald-300 bg-emerald-950/60"
          : line.startsWith("-") && !line.startsWith("---") ? "text-rose-300 bg-rose-950/60"
          : line.startsWith("@@") ? "text-sky-300" : "text-slate-300";
        return <div key={i} className={color}>{line || " "}</div>;
      })}
    </pre>
  );
}

export const STATUS_AR: Record<string, string> = {
  submitted: "مُسلَّم",
  analyzing: "قيد التحليل",
  analyzed: "تم التحليل",
  analysis_failed: "فشل التحليل",
  viva_scheduled: "المناقشة جارية",
  viva_completed: "انتهت المناقشة",
  graded: "تم التقييم",
  in_progress: "جارية",
  completed: "مكتملة",
  abandoned: "متروكة",
};

export const VERDICT_AR: Record<string, { label: string; tone: keyof typeof tones }> = {
  correct: { label: "صحيحة", tone: "green" },
  partial: { label: "جزئية", tone: "amber" },
  wrong: { label: "خاطئة", tone: "red" },
  evasive: { label: "تهرّب", tone: "purple" },
};
