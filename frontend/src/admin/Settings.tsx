import { useEffect, useState } from "react";
import { api, type SiteTexts } from "../api";
import { Icon } from "../components/Icon";
import { Field, Loading, PageTitle, Spinner } from "../components/ui";
import { getToken } from "../lib/push";
import { useFetch } from "../lib/useFetch";

export default function Settings() {
  const { data } = useFetch<SiteTexts>("/api/admin/settings");
  const [d, setD] = useState<SiteTexts | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [adminMsg, setAdminMsg] = useState<string | null>(null);
  const [code, setCode] = useState<{ code: string; link: string | null } | null>(null);

  useEffect(() => { if (data) setD(data); }, [data]);
  if (!d) return <Loading />;

  const save = async () => {
    setBusy(true);
    try {
      setD(await api.put<SiteTexts>("/api/admin/settings", d));
      setMsg("Salvato");
      setTimeout(() => setMsg(null), 2000);
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const thisDevice = async () => {
    const token = getToken();
    if (!token) { setAdminMsg("Attiva prima le notifiche push su questo dispositivo (pagina Notifiche)."); return; }
    try {
      await api.post("/api/admin/admin-device", { token });
      setAdminMsg("Fatto: questo dispositivo riceverà gli avvisi di amministrazione.");
    } catch (e) {
      setAdminMsg((e as Error).message);
    }
  };

  const tgCode = async () => {
    try {
      setCode(await api.post("/api/admin/telegram-code"));
    } catch (e) {
      setAdminMsg((e as Error).message);
    }
  };

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <div>
        <PageTitle title="Impostazioni" subtitle="Testi del sito." />
        <div className="card space-y-4 p-5">
          <Field label="Presentazione (home e Info)"><textarea className="input min-h-24" value={d.intro} onChange={(e) => setD({ ...d, intro: e.target.value })} /></Field>
          <Field label="Avviso di progetto non ufficiale"><textarea className="input min-h-28" value={d.disclaimer} onChange={(e) => setD({ ...d, disclaimer: e.target.value })} /></Field>
          <Field label="Email per segnalazioni (facoltativa)"><input className="input" value={d.contact_email} onChange={(e) => setD({ ...d, contact_email: e.target.value })} /></Field>
          <Field label="Link al canale Telegram pubblico (facoltativo)"><input className="input" value={d.telegram_channel_url} onChange={(e) => setD({ ...d, telegram_channel_url: e.target.value })} placeholder="https://t.me/..." /></Field>
          <div className="flex items-center justify-end gap-3">
            {msg && <span className="text-sm muted">{msg}</span>}
            <button className="btn-primary" onClick={save} disabled={busy}>{busy && <Spinner className="h-4 w-4 text-white" />}Salva</button>
          </div>
        </div>
      </div>
      <div>
        <PageTitle title="Avvisi per te" subtitle="Quando una fonte smette di funzionare (3 errori di fila) ti scriviamo." />
        <div className="card space-y-4 p-5">
          <div>
            <p className="font-semibold">Su questo dispositivo</p>
            <p className="mb-2 text-sm muted">Usa le notifiche push già attive in questo browser.</p>
            <button className="btn-soft" onClick={thisDevice}><Icon name="bell" className="h-4 w-4" />Ricevi qui gli avvisi admin</button>
          </div>
          <div className="border-t border-slate-100 pt-4 dark:border-slate-800">
            <p className="font-semibold">Su Telegram</p>
            <p className="mb-2 text-sm muted">Genera un codice valido 15 minuti e aprilo con il bot.</p>
            <button className="btn-soft" onClick={tgCode}>Genera codice</button>
            {code && (
              <div className="mt-3 rounded-xl bg-slate-50 p-3 text-sm dark:bg-slate-900">
                {code.link ? <a className="font-semibold text-brand-700 underline dark:text-brand-300" href={code.link} target="_blank" rel="noopener noreferrer">Apri il bot e conferma</a>
                  : <>Scrivi al bot: <code className="font-mono font-bold">/admin {code.code}</code></>}
              </div>
            )}
          </div>
          <div className="border-t border-slate-100 pt-4 dark:border-slate-800">
            <button className="btn-ghost" onClick={async () => { await api.post("/api/admin/test-admin-alert"); setAdminMsg("Avviso di prova inviato."); }}>Invia un avviso di prova</button>
          </div>
          {adminMsg && <p className="text-sm font-medium text-brand-700 dark:text-brand-300">{adminMsg}</p>}
        </div>
      </div>
    </div>
  );
}
