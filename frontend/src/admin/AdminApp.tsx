import { useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { api, ApiError } from "../api";
import { Icon } from "../components/Icon";
import { Logo } from "../components/Layout";
import { Field, Loading, Spinner } from "../components/ui";
import Dashboard from "./Dashboard";
import Sources from "./Sources";
import LinksAdmin from "./LinksAdmin";
import Announcements from "./Announcements";
import Subscribers from "./Subscribers";
import Items from "./Items";
import Settings from "./Settings";

const NAV = [
  { to: "/admin", label: "Panoramica", icon: "grid", end: true },
  { to: "/admin/fonti", label: "Fonti", icon: "sources" },
  { to: "/admin/contenuti", label: "Contenuti", icon: "news" },
  { to: "/admin/link", label: "Link utili", icon: "link" },
  { to: "/admin/annunci", label: "Annunci", icon: "megaphone" },
  { to: "/admin/iscritti", label: "Iscritti", icon: "users" },
  { to: "/admin/impostazioni", label: "Impostazioni", icon: "settings" },
];

function Login({ onDone }: { onDone: () => void }) {
  const [username, setU] = useState("");
  const [password, setP] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await api.post("/api/admin/login", { username, password });
      onDone();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="page-wash grid min-h-screen place-items-center px-4">
      <form onSubmit={submit} className="card w-full max-w-sm space-y-4 p-6">
        <div className="flex items-center gap-3">
          <Logo className="h-10 w-10" />
          <div>
            <p className="text-lg font-extrabold">Open Unifi</p>
            <p className="text-sm muted">Pannello di amministrazione</p>
          </div>
        </div>
        <Field label="Email o nome utente"><input className="input" value={username} onChange={(e) => setU(e.target.value)} autoComplete="username" autoCapitalize="none" spellCheck={false} autoFocus /></Field>
        <Field label="Password"><input className="input" type="password" value={password} onChange={(e) => setP(e.target.value)} autoComplete="current-password" /></Field>
        {err && <p className="text-sm font-medium text-red-600">{err}</p>}
        <button className="btn-primary w-full" disabled={busy || !password || !username.trim()}>{busy && <Spinner className="h-4 w-4 text-white" />}Accedi</button>
      </form>
    </div>
  );
}

export default function AdminApp() {
  const [state, setState] = useState<"loading" | "in" | "out">("loading");
  const check = () => api.get("/api/admin/me").then(() => setState("in")).catch((e) => setState(e instanceof ApiError && e.status === 401 ? "out" : "out"));
  useEffect(() => {
    check();
    document.title = "Admin · Open Unifi";
  }, []);

  if (state === "loading") return <Loading />;
  if (state === "out") return <Login onDone={() => setState("in")} />;

  const logout = async () => {
    await api.post("/api/admin/logout").catch(() => undefined);
    setState("out");
  };

  return (
    <div className="page-wash min-h-screen">
      <header className="sticky top-0 z-30 border-b border-white/60 bg-white/80 backdrop-blur-xl dark:border-slate-800 dark:bg-[#0b1220]/85" style={{ paddingTop: "env(safe-area-inset-top)" }}>
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-3 px-4">
          <NavLink to="/" className="flex items-center gap-2"><Logo /><span className="font-extrabold">Admin</span></NavLink>
          <div className="flex-1" />
          <a href="/" className="btn-ghost hidden sm:inline-flex">Vai al sito</a>
          <button className="btn-ghost" onClick={logout}><Icon name="logout" className="h-4 w-4" />Esci</button>
        </div>
        <nav className="no-scrollbar mx-auto flex max-w-6xl gap-1 overflow-x-auto px-3 pb-2" aria-label="Sezioni admin">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end}
              className={({ isActive }) => `inline-flex shrink-0 items-center gap-1.5 rounded-xl px-3 py-1.5 text-sm font-semibold transition ${isActive
                ? "bg-brand-600 text-white" : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"}`}>
              <Icon name={n.icon} className="h-4 w-4" />{n.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Routes>
          <Route index element={<Dashboard />} />
          <Route path="fonti" element={<Sources />} />
          <Route path="contenuti" element={<Items />} />
          <Route path="link" element={<LinksAdmin />} />
          <Route path="annunci" element={<Announcements />} />
          <Route path="iscritti" element={<Subscribers />} />
          <Route path="impostazioni" element={<Settings />} />
        </Routes>
      </main>
    </div>
  );
}
