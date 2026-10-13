import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { api, ApiError, type Prefs, type SourceInfo, type Subscription } from "../api";
import { Icon, TelegramIcon } from "../components/Icon";
import { ErrorBox, Loading, PageTitle, Spinner, Toggle } from "../components/ui";
import { useConfig } from "../lib/app";
import { getToken, platform, pushState, setToken, subscribe, unsubscribe, type PushState } from "../lib/push";
import { useFetch } from "../lib/useFetch";

function Step({ n, children }: { n: number; children: ReactNode }) {
  return (
    <li className="flex gap-3">
      <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-brand-600 text-sm font-bold text-white">{n}</span>
      <span className="pt-0.5 text-[15px]">{children}</span>
    </li>
  );
}

function IosInstall() {
  return (
    <div className="space-y-4">
      <p className="text-[15px]">
        Su iPhone le notifiche funzionano solo se aggiungi l'app alla schermata Home (serve iOS 16.4 o successivo). Bastano tre passaggi:
      </p>
      <ol className="space-y-3">
        <Step n={1}>Tocca <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-1.5 py-0.5 font-semibold dark:bg-slate-800"><Icon name="share" className="h-4 w-4" /> Condividi</span> nella barra di Safari</Step>
        <Step n={2}>Scegli <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-1.5 py-0.5 font-semibold dark:bg-slate-800"><Icon name="plusSquare" className="h-4 w-4" /> Aggiungi alla schermata Home</span></Step>
        <Step n={3}>Apri Open Unifi dall'icona sulla Home e torna in questa pagina per attivare le notifiche</Step>
      </ol>
    </div>
  );
}

function TelegramCard({ compact }: { compact?: boolean }) {
  const cfg = useConfig();
  if (!cfg?.telegram_enabled || !cfg.telegram_bot) return null;
  return (
    <div className="card p-5">
      <div className="flex items-start gap-4">
        <div className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-[#229ED9] text-white"><TelegramIcon className="h-6 w-6" /></div>
        <div className="min-w-0 flex-1">
          <p className="font-bold">{compact ? "Anche su Telegram" : "Preferisci Telegram?"}</p>
          <p className="mt-0.5 text-sm muted">Ricevi gli stessi avvisi dal nostro bot, senza installare nulla. Funziona su qualsiasi telefono.</p>
          <a href={`https://t.me/${cfg.telegram_bot}?start=web`} target="_blank" rel="noopener noreferrer" className="btn mt-3 bg-[#229ED9] text-white hover:brightness-110">
            Apri @{cfg.telegram_bot}
          </a>
        </div>
      </div>
    </div>
  );
}

function PushSetup({ state, onSubscribed }: { state: PushState; onSubscribed: (s: Subscription) => void }) {
  const cfg = useConfig();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const go = async () => {
    if (!cfg) return;
    setBusy(true);
    setErr(null);
    try {
      onSubscribed(await subscribe(cfg.vapid_public_key));
    } catch (e) {
      setErr((e as Error).message || "Attivazione non riuscita");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card overflow-hidden">
      <div className="brand-gradient flex items-center gap-4 p-5 text-white">
        <div className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-white/15 ring-1 ring-white/25"><Icon name="bell" className="h-6 w-6" /></div>
        <div>
          <p className="text-lg font-bold">Notifiche push</p>
          <p className="text-sm text-white/85">Un avviso sul telefono appena un sito UniFI pubblica o modifica qualcosa.</p>
        </div>
      </div>
      <div className="p-5">
        {state === "ready" && (
          <>
            <button className="btn-primary w-full py-3 text-[15px]" onClick={go} disabled={busy || !cfg}>
              {busy ? <Spinner className="h-4 w-4 text-white" /> : <Icon name="bell" className="h-4 w-4" />} Attiva le notifiche
            </button>
            <p className="mt-3 text-center text-xs muted">Gratis e anonimo: niente account, niente email. Puoi disattivarle quando vuoi.</p>
          </>
        )}
        {state === "ios-install" && <IosInstall />}
        {state === "ios-old" && <p className="text-[15px]">La tua versione di iOS non supporta le notifiche web (serve iOS 16.4 o successivo). Puoi usare Telegram qui sotto.</p>}
        {state === "unsupported" && <p className="text-[15px]">Questo browser non supporta le notifiche push. Prova con Chrome, Edge, Firefox o Safari aggiornati, oppure usa Telegram.</p>}
        {state === "denied" && (
          <p className="text-[15px]">
            Hai bloccato le notifiche per questo sito. Riattivale dalle impostazioni del browser
            ({platform() === "android" ? "icona del lucchetto accanto all'indirizzo, poi Notifiche" : "impostazioni del sito, poi Notifiche"}) e ricarica la pagina.
          </p>
        )}
        {err && <p className="mt-3 text-sm font-medium text-red-600">{err}</p>}
      </div>
    </div>
  );
}

function KeywordInput({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  const [draft, setDraft] = useState("");
  const add = () => {
    const k = draft.trim();
    if (k.length >= 2 && !value.some((x) => x.toLowerCase() === k.toLowerCase())) onChange([...value, k]);
    setDraft("");
  };
  return (
    <div>
      <div className="flex gap-2">
        <input className="input" value={draft} placeholder="es. tirocinio, Anatomia, borsa di studio" maxLength={60}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(); } }} />
        <button className="btn-soft shrink-0" onClick={add} disabled={draft.trim().length < 2}><Icon name="plus" className="h-4 w-4" />Aggiungi</button>
      </div>
      {value.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {value.map((k) => (
            <span key={k} className="chip chip-on !pr-1.5">
              {k}
              <button className="grid h-5 w-5 place-items-center rounded-full hover:bg-white/20" onClick={() => onChange(value.filter((x) => x !== k))} aria-label={`Rimuovi ${k}`}>
                <Icon name="x" className="h-3.5 w-3.5" strokeWidth={2.4} />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

type Mode = "instant" | "quiet" | "digest";

function PrefsEditor({ sub, sources, onSaved }: { sub: Subscription; sources: SourceInfo[]; onSaved: (s: Subscription) => void }) {
  const [p, setP] = useState<Prefs>(sub.prefs);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const dirty = JSON.stringify(p) !== JSON.stringify(sub.prefs);
  const mode: Mode = p.digest ? "digest" : p.quiet ? "quiet" : "instant";

  useEffect(() => setP(sub.prefs), [sub]);

  const byCat = useMemo(() => {
    const m = new Map<string, SourceInfo[]>();
    for (const s of sources) m.set(s.category || "Altro", [...(m.get(s.category || "Altro") ?? []), s]);
    return [...m.entries()];
  }, [sources]);

  const all = p.sources === null;
  const selected = new Set(p.sources ?? []);
  const toggleSource = (id: number) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    setP({ ...p, sources: [...next] });
  };

  const setMode = (m: Mode) => {
    if (m === "instant") setP({ ...p, quiet: null, digest: null });
    if (m === "quiet") setP({ ...p, digest: null, quiet: p.quiet ?? { start: "23:00", end: "07:30" } });
    if (m === "digest") setP({ ...p, quiet: null, digest: p.digest ?? "18:00" });
  };

  const save = async () => {
    setSaving(true);
    setMsg(null);
    try {
      const r = await api.put<Subscription>(`/api/subscription/${sub.token}`, { prefs: p });
      onSaved(r);
      setMsg("Preferenze salvate");
      setTimeout(() => setMsg(null), 2500);
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-5">
      <section className="card p-5">
        <h2 className="text-lg font-bold">Cosa vuoi seguire</h2>
        <Toggle checked={all} onChange={(v) => setP({ ...p, sources: v ? null : sources.map((s) => s.id) })}
          label="Tutte le fonti" hint="Anche quelle aggiunte in futuro" />
        {!all && (
          <div className="mt-1 space-y-4 border-t border-slate-100 pt-4 dark:border-slate-800">
            {byCat.map(([cat, list]) => (
              <div key={cat}>
                <p className="mb-2 text-xs font-bold uppercase tracking-wider muted">{cat}</p>
                <div className="flex flex-wrap gap-2">
                  {list.map((s) => (
                    <button key={s.id} className={`chip ${selected.has(s.id) ? "chip-on" : ""}`} onClick={() => toggleSource(s.id)} aria-pressed={selected.has(s.id)}>
                      {selected.has(s.id) && <Icon name="check" className="h-3.5 w-3.5" strokeWidth={2.6} />}
                      {s.name}
                    </button>
                  ))}
                </div>
              </div>
            ))}
            {selected.size === 0 && p.keywords.length === 0 && (
              <p className="text-sm font-medium text-amber-700 dark:text-amber-300">Nessuna fonte selezionata: aggiungi almeno una parola chiave o non riceverai nulla.</p>
            )}
          </div>
        )}
      </section>

      <section className="card p-5">
        <h2 className="text-lg font-bold">Parole chiave</h2>
        <p className="mb-3 mt-0.5 text-sm muted">Ti avvisiamo quando compaiono in qualsiasi fonte, anche in quelle che non segui. Funziona anche con il nome di un esame per i nuovi appelli.</p>
        <KeywordInput value={p.keywords} onChange={(keywords) => setP({ ...p, keywords })} />
      </section>

      <section className="card divide-y divide-slate-100 px-5 py-1 dark:divide-slate-800">
        <Toggle checked={p.notify_new} onChange={(v) => setP({ ...p, notify_new: v })} label="Nuove pubblicazioni" hint="Avvisi, pagine e appelli appena pubblicati" />
        <Toggle checked={p.notify_modified} onChange={(v) => setP({ ...p, notify_modified: v })} label="Modifiche" hint="Quando cambia il testo, una data o un allegato" />
        <Toggle checked={p.announcements} onChange={(v) => setP({ ...p, announcements: v })} label="Comunicazioni di Open Unifi" hint="Rare, solo cose importanti" />
      </section>

      <section className="card p-5">
        <h2 className="text-lg font-bold">Quando</h2>
        <div className="mt-3 grid grid-cols-3 gap-2 rounded-2xl bg-slate-100 p-1 dark:bg-slate-900">
          {([["instant", "Subito"], ["quiet", "Silenzio notturno"], ["digest", "Riepilogo"]] as [Mode, string][]).map(([m, l]) => (
            <button key={m} onClick={() => setMode(m)}
              className={`rounded-xl px-2 py-2 text-[13px] font-semibold transition ${mode === m ? "bg-white text-brand-700 shadow dark:bg-slate-800 dark:text-brand-200" : "text-slate-600 dark:text-slate-400"}`}>
              {l}
            </button>
          ))}
        </div>
        {mode === "instant" && <p className="mt-3 text-sm muted">Ricevi ogni avviso appena lo troviamo, a qualsiasi ora.</p>}
        {mode === "quiet" && p.quiet && (
          <div className="mt-4">
            <p className="mb-3 text-sm muted">Gli avvisi trovati in queste ore ti arrivano tutti insieme alla fine del silenzio.</p>
            <div className="flex items-center gap-3">
              <input type="time" className="input" value={p.quiet.start} onChange={(e) => setP({ ...p, quiet: { ...p.quiet!, start: e.target.value } })} aria-label="Inizio silenzio" />
              <span className="shrink-0 muted">fino alle</span>
              <input type="time" className="input" value={p.quiet.end} onChange={(e) => setP({ ...p, quiet: { ...p.quiet!, end: e.target.value } })} aria-label="Fine silenzio" />
            </div>
          </div>
        )}
        {mode === "digest" && p.digest && (
          <div className="mt-4">
            <p className="mb-3 text-sm muted">Un solo messaggio al giorno con tutte le novità.</p>
            <div className="flex items-center gap-3">
              <span className="shrink-0 muted">Ogni giorno alle</span>
              <input type="time" className="input max-w-36" value={p.digest} onChange={(e) => setP({ ...p, digest: e.target.value })} aria-label="Orario riepilogo" />
            </div>
          </div>
        )}
      </section>

      <div className="sticky bottom-24 z-10 flex items-center justify-end gap-3 md:bottom-4">
        {msg && <span className="rounded-full bg-white px-3 py-1.5 text-sm font-medium shadow dark:bg-slate-800">{msg}</span>}
        <button className="btn-primary px-6 py-3" onClick={save} disabled={!dirty || saving}>
          {saving ? <Spinner className="h-4 w-4 text-white" /> : <Icon name="check" className="h-4 w-4" />} Salva preferenze
        </button>
      </div>
    </div>
  );
}

export default function Notifications() {
  const [params] = useSearchParams();
  const tgToken = params.get("t");
  const { data: sources } = useFetch<SourceInfo[]>("/api/sources");
  const [sub, setSub] = useState<Subscription | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [state, setState] = useState<PushState>(pushState());
  const [testMsg, setTestMsg] = useState<string | null>(null);
  const token = tgToken || getToken();

  useEffect(() => {
    if (!token) { setLoading(false); return; }
    api.get<Subscription>(`/api/subscription/${token}`)
      .then(setSub)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 404) { if (!tgToken) setToken(null); }
        else setError(e.message);
      })
      .finally(() => setLoading(false));
  }, [token, tgToken]);

  useEffect(() => {
    const onVis = () => setState(pushState());
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, []);

  const test = async () => {
    if (!sub) return;
    setTestMsg("Invio in corso...");
    const r = await api.post<{ result: string }>(`/api/subscription/${sub.token}/test`).catch(() => ({ result: "error" }));
    setTestMsg(r.result === "ok" ? "Inviata! Dovrebbe arrivare tra pochi secondi." : "Invio non riuscito: prova a disattivare e riattivare.");
  };

  const off = async () => {
    if (!sub) return;
    if (!confirm("Disattivare le notifiche su questo dispositivo?")) return;
    await unsubscribe(sub.token);
    setSub(null);
    setState(pushState());
  };

  if (loading) return <Loading />;

  const isTelegram = sub?.channel === "telegram";

  return (
    <div className="mx-auto max-w-2xl">
      <PageTitle title="Notifiche" subtitle={isTelegram ? "Stai modificando le preferenze del tuo bot Telegram." : "Scegli come e quando ricevere gli avvisi."} />
      {error && <div className="mb-4"><ErrorBox message={error} /></div>}

      <div className="space-y-5">
        {!sub && (
          <>
            <PushSetup state={state} onSubscribed={(s) => { setSub(s); setState(pushState()); }} />
            <TelegramCard />
          </>
        )}

        {sub && !isTelegram && (
          <div className="card p-5 sm:flex sm:items-center sm:gap-4">
            <div className="flex min-w-0 flex-1 items-center gap-4">
              <div className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-emerald-50 text-emerald-600 dark:bg-emerald-950/50 dark:text-emerald-300">
                <Icon name="check" className="h-6 w-6" strokeWidth={2.4} />
              </div>
              <div className="min-w-0">
                <p className="font-bold">Notifiche attive su questo dispositivo</p>
                <p className="text-sm muted">{testMsg ?? "Personalizza qui sotto cosa ricevere."}</p>
              </div>
            </div>
            <div className="mt-4 flex gap-2 sm:mt-0 sm:shrink-0">
              <button className="btn-soft flex-1 sm:flex-none" onClick={test}><Icon name="send" className="h-4 w-4" />Invia una prova</button>
              <button className="btn-ghost" onClick={off}>Disattiva</button>
            </div>
          </div>
        )}

        {sub && isTelegram && !sub.active && (
          <div className="card p-4 text-sm">Il bot è in pausa. Salvando le preferenze le notifiche si riattivano.</div>
        )}

        {sub && sources && <PrefsEditor sub={sub} sources={sources} onSaved={setSub} />}
        {sub && !isTelegram && <TelegramCard compact />}
      </div>
    </div>
  );
}
