import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useEffect } from "react";
import { Icon } from "./Icon";

const NAV = [
  { to: "/", label: "Novità", icon: "news", end: true },
  { to: "/esami", label: "Appelli", icon: "calendar" },
  { to: "/notifiche", label: "Notifiche", icon: "bell" },
  { to: "/link", label: "Link utili", icon: "link" },
  { to: "/info", label: "Info", icon: "info" },
];

export function Logo({ className = "h-8 w-8" }: { className?: string }) {
  return <img src="/favicon.svg" alt="" className={`${className} rounded-[10px] shadow-sm shadow-brand-700/30`} />;
}

export default function Layout() {
  const { pathname } = useLocation();
  useEffect(() => window.scrollTo(0, 0), [pathname]);

  return (
    <div className="page-wash min-h-screen">
      <header className="sticky top-0 z-30 border-b border-white/60 bg-white/75 backdrop-blur-xl dark:border-slate-800/80 dark:bg-[#0b1220]/80"
        style={{ paddingTop: "env(safe-area-inset-top)" }}>
        <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-4">
          <NavLink to="/" className="flex items-center gap-2.5">
            <Logo />
            <span className="text-[19px] font-extrabold tracking-tight">
              <span className="text-slate-900 dark:text-white">Open </span><span className="brand-text">Unifi</span>
            </span>
          </NavLink>
          <nav className="hidden items-center gap-1 md:flex" aria-label="Principale">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end}
                className={({ isActive }) =>
                  `rounded-xl px-3 py-2 text-sm font-semibold transition ${isActive
                    ? "bg-brand-50 text-brand-700 dark:bg-brand-900/40 dark:text-brand-200"
                    : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"}`}>
                {n.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 pb-28 pt-6 md:pb-12">
        <Outlet />
      </main>

      <nav className="safe-bottom fixed inset-x-0 bottom-0 z-30 border-t border-slate-200/70 bg-white/85 backdrop-blur-xl md:hidden dark:border-slate-800 dark:bg-[#0b1220]/90"
        aria-label="Navigazione">
        <div className="mx-auto grid max-w-md grid-cols-5 px-1 pt-1.5">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end}
              className={({ isActive }) =>
                `flex flex-col items-center gap-0.5 rounded-xl py-1.5 text-[11px] font-semibold transition ${isActive
                  ? "text-brand-700 dark:text-brand-300" : "text-slate-500 dark:text-slate-400"}`}>
              {({ isActive }) => (
                <>
                  <span className={`grid h-8 w-12 place-items-center rounded-full transition ${isActive ? "bg-brand-100 dark:bg-brand-900/50" : ""}`}>
                    <Icon name={n.icon} className="h-[22px] w-[22px]" strokeWidth={isActive ? 2.1 : 1.8} />
                  </span>
                  {n.label}
                </>
              )}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  );
}
