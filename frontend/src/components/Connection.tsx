import { useEffect, useState } from "react";

export function useOnline(): boolean {
  const [online, setOnline] = useState(() => navigator.onLine);
  useEffect(() => {
    const up = () => setOnline(true), down = () => setOnline(false);
    window.addEventListener("online", up);
    window.addEventListener("offline", down);
    return () => { window.removeEventListener("online", up); window.removeEventListener("offline", down); };
  }, []);
  return online;
}

/** Tells the user their work is safe while the connection is down. */
export function ConnectionBanner() {
  const online = useOnline();
  if (online) return null;
  return (
    <div role="status" className="bg-amber-500 px-4 py-2 text-center text-sm font-semibold text-white">
      انقطع الاتصال. ما كتبته محفوظ على جهازك، وسيُستكمل الرفع والإرسال تلقائياً عند عودته.
    </div>
  );
}
