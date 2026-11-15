import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { get, post } from "../api";

interface Item {
  id: string; kind: string; title: string; body: string; link: string | null;
  created_at: string; read: boolean;
}
interface Inbox { unread: number; items: Item[] }

const POLL_MS = 30_000;
const ICONS: Record<string, string> = {
  analysis_done: "✓", analysis_failed: "!", grade_final: "★", new_submission: "＋",
  project_alert: "⚠", fixes_applied: "✎",
};

function ago(iso: string): string {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
  if (minutes < 1) return "الآن";
  if (minutes < 60) return `قبل ${minutes} دقيقة`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `قبل ${hours} ساعة`;
  return new Date(iso).toLocaleDateString("ar");
}

export function NotificationBell() {
  const [inbox, setInbox] = useState<Inbox>({ unread: 0, items: [] });
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  const refresh = useCallback(() => {
    get<Inbox>("projects", "/api/v1/notifications").then(setInbox).catch(() => undefined);
  }, []);

  useEffect(() => {
    refresh();
    const timer = window.setInterval(() => document.visibilityState === "visible" && refresh(), POLL_MS);
    return () => window.clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const select = async (item: Item) => {
    setOpen(false);
    if (!item.read) await post("projects", `/api/v1/notifications/${item.id}/read`, {}).catch(() => undefined);
    refresh();
    if (item.link) navigate(item.link);
  };
  const readAll = async () => {
    await post("projects", "/api/v1/notifications/read-all", {}).catch(() => undefined);
    refresh();
  };

  return (
    <div className="relative" ref={box}>
      <button
        type="button"
        aria-label={`الإشعارات${inbox.unread ? ` (${inbox.unread} غير مقروءة)` : ""}`}
        aria-expanded={open}
        onClick={() => { setOpen(!open); if (!open) refresh(); }}
        className="relative rounded-lg p-2 text-slate-600 hover:bg-slate-100"
      >
        <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
          <path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.7 21a2 2 0 0 1-3.4 0" />
        </svg>
        {inbox.unread > 0 && (
          <span className="absolute -top-0.5 -left-0.5 min-w-5 rounded-full bg-rose-600 px-1 text-center text-xs font-bold leading-5 text-white">
            {inbox.unread > 99 ? "99+" : inbox.unread}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute left-0 z-20 mt-2 w-80 max-w-[calc(100vw-2rem)] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-lg">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2">
            <span className="font-bold text-slate-800">الإشعارات</span>
            {inbox.unread > 0 && (
              <button type="button" onClick={() => void readAll()} className="text-xs font-semibold text-indigo-700 hover:underline">
                تعليم الكل كمقروء
              </button>
            )}
          </div>
          <ul className="max-h-96 overflow-y-auto">
            {inbox.items.length === 0 && <li className="px-4 py-6 text-center text-sm text-slate-500">لا إشعارات بعد.</li>}
            {inbox.items.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => void select(item)}
                  className={`flex w-full gap-3 px-4 py-3 text-right hover:bg-slate-50 ${item.read ? "" : "bg-indigo-50/60"}`}
                >
                  <span aria-hidden className="mt-0.5 w-5 shrink-0 text-center text-indigo-700">{ICONS[item.kind] ?? "•"}</span>
                  <span className="min-w-0 flex-1">
                    <span className={`block text-sm ${item.read ? "text-slate-700" : "font-bold text-slate-900"}`}>{item.title}</span>
                    {item.body && <span className="mt-0.5 block whitespace-pre-line text-xs text-slate-500">{item.body}</span>}
                    <span className="mt-1 block text-xs text-slate-400">{ago(item.created_at)}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
