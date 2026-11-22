import { Link, NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth";
import { ConnectionBanner } from "./Connection";
import { NotificationBell } from "./Notifications";
import { Button } from "./ui";
import { LanguageSwitch } from "./LanguageSwitch";

export function Layout() {
  const { user, logout } = useAuth();
  const staff = user?.role === "faculty" || user?.role === "admin";
  const link = ({ isActive }: { isActive: boolean }) =>
    `rounded-lg px-3 py-1.5 text-sm font-semibold ${isActive ? "bg-indigo-100 text-indigo-700" : "text-slate-600 hover:bg-slate-100"}`;
  return (
    <div className="min-h-screen">
      <ConnectionBanner />
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
          <Link to="/" className="flex items-center gap-2 text-lg font-black text-indigo-700">
            <span className="rounded-lg bg-indigo-600 px-2 py-0.5 text-white">AI</span> مِحَكّ
          </Link>
          <nav className="flex flex-wrap items-center gap-1">
            {staff ? (
              <>
                <NavLink to="/" end className={link}>لوحة التحكم</NavLink>
                <NavLink to="/analytics" className={link}>الإحصائيات</NavLink>
                <NavLink to="/ai" className={link}>عقل النظام</NavLink>
              </>
            ) : (
              <NavLink to="/" end className={link}>مشاريعي</NavLink>
            )}
          </nav>
          <div className="flex items-center gap-3 text-sm">
            <LanguageSwitch />
            <NotificationBell />
            <span className="text-slate-600">{user?.full_name}</span>
            <Button variant="secondary" onClick={() => void logout()}>خروج</Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl space-y-6 px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
