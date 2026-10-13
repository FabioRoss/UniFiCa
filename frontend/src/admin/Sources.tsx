import { useEffect, useState } from "react";
import { api } from "../api";
import { Icon } from "../components/Icon";
import { Badge, ErrorBox, Field, Loading, Modal, PageTitle, Spinner, Toggle } from "../components/ui";
import { fmtDateTime, relTime } from "../lib/format";
import { useFetch } from "../lib/useFetch";

interface AdminSource {
  id: number;
  slug: string;
  name: string;
  category: string;
  kind: "news" | "page" | "exams";
  parser: string;
  url: string;
  archive_url: string | null;
  config: Record<string, string>;
  interval_minutes: number;
  enabled: boolean;
  track_attachments: boolean;
  position: number;
  baseline_done: boolean;
  last_run_at: string | null;
  last_ok_at: string | null;
  last_error: string | null;
  consecutive_failures: number;
  last_item_count: number;
  items: number;
}

type Draft = Omit<AdminSource, "id" | "slug" | "baseline_done" | "last_run_at" | "last_ok_at" | "last_error" | "consecutive_failures" | "last_item_count" | "items"> & { id?: number };

const EMPTY: Draft = {
  name: "", category: "", kind: "news", parser: "unifi_news", url: "", archive_url: "", config: {},
  interval_minutes: 15, enabled: true, track_attachments: true, position: 0,
};

const KINDS = [
  { value: "news", label: "Lista di notizie", hint: "Una pagina con l'elenco degli avvisi: ogni avviso diventa un contenuto." },
  { value: "page", label: "Pagina da monitorare", hint: "Una singola pagina (orari, calendari, regolamenti): notifica quando cambia testo o allegati." },
  { value: "exams", label: "Appelli ESSE3", hint: "La bacheca pubblica degli appelli di studenti.unifi.it." },
] as const;

const SELECTOR_LABELS: Record<string, string> = {
  item: "Elemento della lista", link: "Link all'articolo", title: "Titolo", summary: "Sommario", date: "Data",
  content: "Area del contenuto", content_title: "Titolo nel contenuto", remove: "Elementi da ignorare",
};

const INTERVALS = [[5, "5 min"], [10, "10 min"], [15, "15 min"], [30, "30 min"], [60, "1 ora"], [180, "3 ore"], [360, "6 ore"], [720, "12 ore"], [1440, "1 giorno"]] as const;

interface Preview {
  kind: string;
  title?: string;
  text?: string;
  count?: number;
  attachments?: { url: string; name: string }[];
  entries?: { url: string; title: string; summary: string; published_on: string | null }[];
  detail?: { title: string; text: string; attachments: { url: string; name: string }[] } | null;
}

function Esse3Picker({ config, onChange }: { config: Record<string, string>; onChange: (c: Record<string, string>) => void }) {
  const [schools, setSchools] = useState<{ value: string; label: string }[]>([]);
  const [courses, setCourses] = useState<{ value: string; label: string }[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const fac = config.fac_id ?? "";
  const cds = (config.cds_ids ?? "").split(",").filter(Boolean);

  useEffect(() => {
    setLoading(true);
    setErr(null);
    api.get<{ schools: typeof schools; courses: typeof courses }>(`/api/admin/esse3/options${fac ? `?fac_id=${fac}` : ""}`)
      .then((r) => { setSchools(r.schools); setCourses(r.courses); })
      .catch((e) => setErr(e.message))
      .finally(() => setLoading(false));
  }, [fac]);

  const toggle = (v: string) => onChange({ ...config, cds_ids: (cds.includes(v) ? cds.filter((x) => x !== v) : [...cds, v]).join(",") });

  return (
    <div className="space-y-3">
      <Field label="Scuola">
        <select className="input" value={fac} onChange={(e) => onChange({ ...config, fac_id: e.target.value, cds_ids: "" })}>
          <option value="">Scegli...</option>
          {schools.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
      </Field>
      {loading && <p className="flex items-center gap-2 text-sm muted"><Spinner className="h-4 w-4" />Carico da ESSE3...</p>}
      {err && <p className="text-sm text-red-600">{err}</p>}
      {fac && courses.length > 0 && (
        <Field label={`Corsi di studio (${cds.length} selezionati)`} hint="Seleziona tutti i codici del corso (es. vecchio e nuovo ordinamento): le sessioni condivise vengono unite.">
          <div className="max-h-56 space-y-1 overflow-y-auto rounded-xl border border-slate-200 p-2 dark:border-slate-700">
            {courses.map((c) => (
              <label key={c.value} className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1 text-sm hover:bg-slate-50 dark:hover:bg-slate-800">
                <input type="checkbox" checked={cds.includes(c.value)} onChange={() => toggle(c.value)} className="accent-brand-600" />
                {c.label}
              </label>
            ))}
          </div>
        </Field>
      )}
      <Field label="Mesi in avanti">
        <input className="input max-w-28" type="number" min={1} max={12} value={config.months_ahead ?? "6"} onChange={(e) => onChange({ ...config, months_ahead: e.target.value })} />
      </Field>
    </div>
  );
}

function SourceForm({ initial, presets, onClose, onSaved }: {
  initial: Draft; presets: Record<string, Record<string, string>>; onClose: () => void; onSaved: () => void;
}) {
  const [d, setD] = useState<Draft>(initial);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [advanced, setAdvanced] = useState(Object.keys(initial.config).length > 0 && initial.kind !== "exams");

  const setKind = (kind: Draft["kind"]) => {
    const parser = kind === "page" ? "page" : kind === "exams" ? "esse3_appelli" : "unifi_news";
    setD({
      ...d, kind, parser,
      url: kind === "exams" ? "https://studenti.unifi.it/ListaAppelliOfferta.do" : d.url,
      track_attachments: kind !== "exams",
      interval_minutes: kind === "exams" ? 60 : d.interval_minutes,
      config: kind === "exams" ? { months_ahead: "6" } : {},
    });
    setPreview(null);
  };

  const save = async () => {
    setBusy(true);
    setErr(null);
    try {
      const body = { ...d, archive_url: d.archive_url || null };
      if (d.id) await api.put(`/api/admin/sources/${d.id}`, body);
      else await api.post("/api/admin/sources", body);
      onSaved();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const runPreview = async () => {
    setPreviewing(true);
    setErr(null);
    setPreview(null);
    try {
      setPreview(await api.post<Preview>("/api/admin/sources/preview", { parser: d.parser, url: d.url, config: d.config }));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setPreviewing(false);
    }
  };

  const preset = presets[d.parser] ?? {};
  const selectorKeys = Object.keys(preset).filter((k) => k in SELECTOR_LABELS);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        {KINDS.map((k) => (
          <button key={k.value} onClick={() => setKind(k.value)}
            className={`rounded-xl border p-3 text-left transition ${d.kind === k.value ? "border-brand-500 bg-brand-50 ring-2 ring-brand-200 dark:bg-brand-900/30 dark:ring-brand-800" : "border-slate-200 hover:border-brand-300 dark:border-slate-700"}`}>
            <p className="text-sm font-semibold">{k.label}</p>
            <p className="mt-0.5 text-xs muted">{k.hint}</p>
          </button>
        ))}
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Nome"><input className="input" value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} placeholder="es. News Medicina e Chirurgia" /></Field>
        <Field label="Gruppo" hint="Raggruppa le fonti nelle preferenze degli utenti"><input className="input" value={d.category} onChange={(e) => setD({ ...d, category: e.target.value })} placeholder="es. Medicina e Chirurgia" /></Field>
      </div>
      {d.kind !== "exams" && (
        <Field label="URL della pagina"><input className="input" value={d.url} onChange={(e) => setD({ ...d, url: e.target.value })} placeholder="https://www.medicina.unifi.it/news.html" /></Field>
      )}
      {d.kind === "news" && (
        <>
          <Field label="Tipo di sito">
            <select className="input" value={d.parser} onChange={(e) => setD({ ...d, parser: e.target.value })}>
              <option value="unifi_news">Sito di un corso UniFI</option>
              <option value="css_list">Altro sito (selettori CSS)</option>
            </select>
          </Field>
          <Field label="URL archivio (facoltativo)" hint="Letto una sola volta al primo controllo, per importare le notizie passate.">
            <input className="input" value={d.archive_url ?? ""} onChange={(e) => setD({ ...d, archive_url: e.target.value })} placeholder="https://.../index.php?module=NEWSpro&func=list&filter=arch&catid=1" />
          </Field>
        </>
      )}
      {d.kind === "exams" && <Esse3Picker config={d.config} onChange={(config) => setD({ ...d, config })} />}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Frequenza di controllo">
          <select className="input" value={d.interval_minutes} onChange={(e) => setD({ ...d, interval_minutes: Number(e.target.value) })}>
            {INTERVALS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </Field>
        <Field label="Ordine"><input className="input" type="number" value={d.position} onChange={(e) => setD({ ...d, position: Number(e.target.value) })} /></Field>
      </div>
      <div className="divide-y divide-slate-100 dark:divide-slate-800">
        <Toggle checked={d.enabled} onChange={(v) => setD({ ...d, enabled: v })} label="Attiva" />
        {d.kind !== "exams" && <Toggle checked={d.track_attachments} onChange={(v) => setD({ ...d, track_attachments: v })} label="Controlla gli allegati" hint="Scarica PDF e documenti per accorgersi quando vengono sostituiti" />}
      </div>

      {d.kind !== "exams" && selectorKeys.length > 0 && (
        <div>
          <button className="text-sm font-semibold text-brand-700 dark:text-brand-300" onClick={() => setAdvanced(!advanced)}>
            {advanced ? "Nascondi" : "Mostra"} selettori CSS avanzati
          </button>
          {advanced && (
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              {selectorKeys.map((k) => (
                <Field key={k} label={SELECTOR_LABELS[k]}>
                  <input className="input font-mono text-[13px]" value={d.config[k] ?? ""} placeholder={preset[k]}
                    onChange={(e) => setD({ ...d, config: { ...d.config, [k]: e.target.value } })} />
                </Field>
              ))}
              <p className="text-xs muted sm:col-span-2">Lascia vuoto per usare il valore predefinito mostrato in grigio. Più selettori separati da virgola: vale il primo trovato.</p>
            </div>
          )}
        </div>
      )}

      {preview && (
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm dark:border-slate-700 dark:bg-slate-900/60">
          {preview.kind === "page" && (
            <>
              <p className="font-semibold">{preview.title}</p>
              <p className="mt-2 max-h-48 overflow-y-auto whitespace-pre-line text-xs muted">{preview.text}</p>
              <p className="mt-2 text-xs">{preview.attachments?.length ?? 0} allegati trovati</p>
            </>
          )}
          {preview.kind !== "page" && (
            <>
              <p className="mb-2 font-semibold">{preview.count ?? preview.entries?.length ?? 0} elementi trovati{preview.entries && preview.entries.length >= 30 ? " (primi 30)" : ""}</p>
              <ul className="max-h-48 space-y-1 overflow-y-auto text-xs">
                {preview.entries?.map((e) => <li key={e.url}><b>{e.title}</b> {e.published_on && <span className="muted">· {e.published_on}</span>}{e.summary && <span className="muted"> · {e.summary.slice(0, 80)}</span>}</li>)}
              </ul>
              {preview.detail && (
                <div className="mt-3 border-t border-slate-200 pt-3 dark:border-slate-700">
                  <p className="text-xs font-semibold">Contenuto del primo elemento:</p>
                  <p className="mt-1 max-h-32 overflow-y-auto whitespace-pre-line text-xs muted">{preview.detail.text}</p>
                </div>
              )}
            </>
          )}
        </div>
      )}
      {err && <p className="text-sm font-medium text-red-600">{err}</p>}
      <div className="flex flex-wrap justify-end gap-2 pt-2">
        <button className="btn-ghost" onClick={onClose}>Annulla</button>
        <button className="btn-soft" onClick={runPreview} disabled={previewing || !d.url}>
          {previewing ? <Spinner className="h-4 w-4" /> : <Icon name="eye" className="h-4 w-4" />}Anteprima
        </button>
        <button className="btn-primary" onClick={save} disabled={busy || !d.name || !d.url}>{busy && <Spinner className="h-4 w-4 text-white" />}Salva</button>
      </div>
      {!d.id && <p className="text-xs muted">Il primo controllo importa ciò che c'è già senza inviare notifiche: da lì in poi ogni novità viene notificata.</p>}
    </div>
  );
}

export default function Sources() {
  const { data, error, loading, reload } = useFetch<AdminSource[]>("/api/admin/sources");
  const { data: presets } = useFetch<Record<string, Record<string, string>>>("/api/admin/parsers");
  const [editing, setEditing] = useState<Draft | null>(null);
  const [running, setRunning] = useState<number | null>(null);
  const [result, setResult] = useState<Record<number, string>>({});

  const run = async (s: AdminSource) => {
    setRunning(s.id);
    try {
      const r = await api.post<{ ok: boolean; items: number; new: number; modified: number; error: string; seconds: number }>(`/api/admin/sources/${s.id}/run`);
      setResult({ ...result, [s.id]: r.ok ? `OK: ${r.items} elementi, ${r.new} nuovi, ${r.modified} modificati (${r.seconds}s)` : `Errore: ${r.error}` });
      reload();
    } finally {
      setRunning(null);
    }
  };

  const remove = async (s: AdminSource) => {
    if (!confirm(`Eliminare "${s.name}" e tutto il suo storico (${s.items} contenuti)?`)) return;
    await api.del(`/api/admin/sources/${s.id}`);
    reload();
  };

  const toggle = async (s: AdminSource) => {
    const { id, slug, baseline_done, last_run_at, last_ok_at, last_error, consecutive_failures, last_item_count, items, ...rest } = s;
    void slug; void baseline_done; void last_run_at; void last_ok_at; void last_error; void consecutive_failures; void last_item_count; void items;
    await api.put(`/api/admin/sources/${id}`, { ...rest, enabled: !s.enabled });
    reload();
  };

  return (
    <div>
      <PageTitle title="Fonti" subtitle="Le pagine che Open Unifi controlla. Aggiungine di nuove quando vuoi."
        action={<button className="btn-primary" onClick={() => setEditing({ ...EMPTY, position: (data?.length ?? 0) + 1 })}><Icon name="plus" className="h-4 w-4" />Nuova</button>} />
      {error && <ErrorBox message={error} onRetry={reload} />}
      {loading ? <Loading /> : (
        <div className="space-y-3">
          {data?.map((s) => (
            <div key={s.id} className={`card p-4 ${s.enabled ? "" : "opacity-60"}`}>
              <div className="flex flex-wrap items-start gap-3">
                <span className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${!s.enabled ? "bg-slate-300" : s.consecutive_failures ? "bg-red-500" : s.last_ok_at ? "bg-emerald-500" : "bg-amber-400"}`} />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-semibold">{s.name}</p>
                    <Badge tone="slate">{KINDS.find((k) => k.value === s.kind)?.label}</Badge>
                    {!s.baseline_done && <Badge tone="amber">primo controllo in attesa</Badge>}
                  </div>
                  <a href={s.url} target="_blank" rel="noopener noreferrer" className="block truncate text-xs text-brand-700 hover:underline dark:text-brand-300">{s.url}</a>
                  <p className="mt-1 text-xs muted">
                    {s.category || "Senza gruppo"} · ogni {s.interval_minutes} min · {s.items} contenuti · ultimo controllo {relTime(s.last_run_at) || "mai"}
                    {s.last_ok_at && <span title={fmtDateTime(s.last_ok_at)}> · ultimo OK {relTime(s.last_ok_at)}</span>}
                  </p>
                  {s.last_error && <p className="mt-1 text-xs font-medium text-red-600 dark:text-red-400">{s.consecutive_failures} errori di fila: {s.last_error}</p>}
                  {result[s.id] && <p className="mt-1 text-xs font-medium text-brand-700 dark:text-brand-300">{result[s.id]}</p>}
                </div>
                <div className="flex shrink-0 gap-1">
                  <button className="btn-ghost h-9 w-9 !p-0" title="Controlla ora" onClick={() => run(s)} disabled={running === s.id}>
                    {running === s.id ? <Spinner className="h-4 w-4" /> : <Icon name="refresh" className="h-4 w-4" />}
                  </button>
                  <button className="btn-ghost h-9 w-9 !p-0" title={s.enabled ? "Disattiva" : "Attiva"} onClick={() => toggle(s)}>
                    <Icon name={s.enabled ? "eye" : "eyeOff"} className="h-4 w-4" />
                  </button>
                  <button className="btn-ghost h-9 w-9 !p-0" title="Modifica" onClick={() => setEditing({ ...s, archive_url: s.archive_url ?? "" })}><Icon name="edit" className="h-4 w-4" /></button>
                  <button className="btn-ghost h-9 w-9 !p-0 text-red-600" title="Elimina" onClick={() => remove(s)}><Icon name="trash" className="h-4 w-4" /></button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
      <Modal open={!!editing} onClose={() => setEditing(null)} title={editing?.id ? "Modifica fonte" : "Nuova fonte"} wide>
        {editing && presets && <SourceForm initial={editing} presets={presets} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); reload(); }} />}
      </Modal>
    </div>
  );
}
