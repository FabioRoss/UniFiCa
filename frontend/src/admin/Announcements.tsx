import { useState } from "react";
import { api } from "../api";
import { Icon } from "../components/Icon";
import { Badge, ErrorBox, Field, Loading, PageTitle, Spinner, Toggle } from "../components/ui";
import { fmtDateTime } from "../lib/format";
import { useFetch } from "../lib/useFetch";

interface Ann { id: number; title: string; body: string; url: string; pinned: boolean; created_at: string; push_sent: number; telegram_sent: number }

export default function Announcements() {
  const { data, error, loading, reload } = useFetch<Ann[]>("/api/admin/announcements");
  const [d, setD] = useState({ title: "", body: "", url: "", pinned: false, send: true });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const submit = async () => {
    if (d.send && !confirm("Inviare la notifica a tutti gli iscritti?")) return;
    setBusy(true);
    setMsg(null);
    try {
      const r = await api.post<Ann & { result: { push?: number; telegram?: number; queued?: number } }>("/api/admin/announcements", d);
      setMsg(d.send ? `Inviato: ${r.result.push ?? 0} push, ${r.result.telegram ?? 0} Telegram${r.result.queued ? `, ${r.result.queued} in coda (orari di silenzio)` : ""}` : "Pubblicato senza notifica");
      setD({ title: "", body: "", url: "", pinned: false, send: true });
      reload();
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const update = async (a: Ann, patch: Partial<Ann>) => {
    await api.put(`/api/admin/announcements/${a.id}`, { ...a, ...patch, send: false });
    reload();
  };

  return (
    <div className="grid gap-6 lg:grid-cols-5">
      <div className="lg:col-span-2">
        <PageTitle title="Annunci" subtitle="Messaggi tuoi: compaiono in cima alla home e, se vuoi, arrivano come notifica." />
        <div className="card space-y-4 p-5">
          <Field label="Titolo"><input className="input" value={d.title} maxLength={200} onChange={(e) => setD({ ...d, title: e.target.value })} placeholder="es. Nuova fonte: Scuola di Scienze della Salute" /></Field>
          <Field label="Testo"><textarea className="input min-h-28" value={d.body} maxLength={3000} onChange={(e) => setD({ ...d, body: e.target.value })} /></Field>
          <Field label="Link (facoltativo)"><input className="input" value={d.url} onChange={(e) => setD({ ...d, url: e.target.value })} placeholder="https://... oppure /esami" /></Field>
          <div className="divide-y divide-slate-100 dark:divide-slate-800">
            <Toggle checked={d.pinned} onChange={(v) => setD({ ...d, pinned: v })} label="Fissa in home" hint="Altrimenti resta visibile 30 giorni" />
            <Toggle checked={d.send} onChange={(v) => setD({ ...d, send: v })} label="Invia notifica" hint="Push e Telegram a chi ha attivato le comunicazioni" />
          </div>
          {msg && <p className="text-sm font-medium text-brand-700 dark:text-brand-300">{msg}</p>}
          <button className="btn-primary w-full" onClick={submit} disabled={busy || !d.title}>
            {busy ? <Spinner className="h-4 w-4 text-white" /> : <Icon name="send" className="h-4 w-4" />}{d.send ? "Pubblica e invia" : "Pubblica"}
          </button>
        </div>
      </div>
      <div className="lg:col-span-3">
        <h2 className="mb-3 mt-1 font-bold">Storico</h2>
        {error && <ErrorBox message={error} onRetry={reload} />}
        {loading ? <Loading /> : !data?.length ? <p className="text-sm muted">Nessun annuncio.</p> : (
          <div className="space-y-3">
            {data.map((a) => (
              <div key={a.id} className="card p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="flex-1 font-semibold">{a.title}</p>
                  {a.pinned && <Badge>fissato</Badge>}
                </div>
                {a.body && <p className="mt-1 whitespace-pre-line text-sm muted">{a.body}</p>}
                <p className="mt-2 text-xs muted">{fmtDateTime(a.created_at)} · {a.push_sent} push · {a.telegram_sent} Telegram</p>
                <div className="mt-2 flex gap-2">
                  <button className="btn-ghost !py-1 text-xs" onClick={() => update(a, { pinned: !a.pinned })}>{a.pinned ? "Togli dalla home" : "Fissa in home"}</button>
                  <button className="btn-ghost !py-1 text-xs text-red-600" onClick={async () => { if (confirm("Eliminare l'annuncio?")) { await api.del(`/api/admin/announcements/${a.id}`); reload(); } }}>Elimina</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
