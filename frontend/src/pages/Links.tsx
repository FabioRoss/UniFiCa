import { useMemo, useState } from "react";
import type { LinkGroup, LinkItem } from "../api";
import { Icon } from "../components/Icon";
import { Empty, ErrorBox, Highlight, Loading, PageTitle, SearchBox } from "../components/ui";
import { matchesQuery } from "../lib/format";
import { useFetch } from "../lib/useFetch";

function host(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function LinkCard({ l, q }: { l: LinkItem; q: string }) {
  const contact = l.kind === "contact";
  const main = (
    <>
      <div className="flex items-start gap-3">
        <div className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ${contact ? "bg-sky-50 text-sky-600 dark:bg-sky-950/50 dark:text-sky-300" : "bg-brand-50 text-brand-600 dark:bg-brand-900/40 dark:text-brand-300"}`}>
          <Icon name={contact ? (l.location && !l.email ? "pin" : "users") : "link"} className="h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-semibold leading-snug"><Highlight text={l.title} query={q} /></p>
          {l.description && <p className="mt-0.5 text-sm muted"><Highlight text={l.description} query={q} /></p>}
          {!contact && l.url && <p className="mt-1 truncate text-xs text-brand-700/80 dark:text-brand-300/80">{host(l.url)}</p>}
        </div>
        {!contact && l.url && <Icon name="external" className="h-4 w-4 shrink-0 text-slate-400" />}
      </div>
    </>
  );
  if (!contact) {
    return (
      <a href={l.url} target="_blank" rel="noopener noreferrer" className="card block p-4 transition hover:-translate-y-0.5 hover:border-brand-200 hover:shadow-lg dark:hover:border-brand-800">
        {main}
      </a>
    );
  }
  return (
    <div className="card p-4">
      {main}
      <div className="mt-3 space-y-1.5 pl-[52px] text-sm">
        {l.email && (
          <a href={`mailto:${l.email}`} className="flex items-center gap-2 font-medium text-brand-700 hover:underline dark:text-brand-300">
            <Icon name="mail" className="h-4 w-4 shrink-0" /> <span className="break-all"><Highlight text={l.email} query={q} /></span>
          </a>
        )}
        {l.phone && (
          <a href={`tel:${l.phone.replace(/[^\d+]/g, "")}`} className="flex items-center gap-2 font-medium text-brand-700 hover:underline dark:text-brand-300">
            <Icon name="phone" className="h-4 w-4 shrink-0" /> {l.phone}
          </a>
        )}
        {l.location && (
          <p className="flex items-center gap-2 muted"><Icon name="pin" className="h-4 w-4 shrink-0" /> <Highlight text={l.location} query={q} /></p>
        )}
        {l.hours && <p className="flex items-center gap-2 muted"><Icon name="clock" className="h-4 w-4 shrink-0" /> {l.hours}</p>}
        {l.url && (
          <a href={l.url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 font-medium text-brand-700 hover:underline dark:text-brand-300">
            <Icon name="external" className="h-4 w-4 shrink-0" /> {l.url.includes("google.com/maps") ? "Apri in Maps" : host(l.url)}
          </a>
        )}
      </div>
    </div>
  );
}

export default function Links() {
  const { data, error, loading, reload } = useFetch<LinkGroup[]>("/api/links");
  const [q, setQ] = useState("");

  const groups = useMemo(() => (data ?? [])
    .map((g) => ({
      ...g,
      links: g.links.filter((l) => matchesQuery(q, l.title, l.description, l.email, l.phone, l.location, l.tags, l.url, g.name)),
    }))
    .filter((g) => g.links.length > 0), [data, q]);

  const total = groups.reduce((n, g) => n + g.links.length, 0);

  return (
    <div>
      <PageTitle title="Link utili e contatti" subtitle="Uffici, portali e servizi: tutto quello che serve, senza perdersi tra i siti." />
      <div className="sticky top-[calc(3.5rem+env(safe-area-inset-top))] z-20 -mx-4 mb-4 space-y-3 bg-[#f5f8ff]/90 px-4 pb-3 pt-1 backdrop-blur-xl dark:bg-[#0b1220]/90">
        <SearchBox value={q} onChange={setQ} placeholder="Cerca: segreteria, mensa, tirocini, email..." />
        {!q && data && data.length > 1 && (
          <div className="no-scrollbar -mx-4 flex gap-2 overflow-x-auto px-4">
            {data.map((g) => (
              <a key={g.id} href={`#g${g.id}`} className="chip shrink-0">{g.name}</a>
            ))}
          </div>
        )}
        {q && <p className="px-1 text-xs muted">{total} risultat{total === 1 ? "o" : "i"}</p>}
      </div>

      {error && <ErrorBox message={error} onRetry={reload} />}
      {loading ? <Loading /> : !groups.length ? (
        <Empty title={q ? "Nessun risultato" : "Ancora nessun link"}>{q ? "Prova con un'altra parola." : "Torna presto."}</Empty>
      ) : (
        <div className="space-y-8">
          {groups.map((g) => (
            <section key={g.id} id={`g${g.id}`} className="scroll-mt-40">
              <h2 className="text-lg font-bold">{g.name}</h2>
              {g.description && <p className="mb-3 text-sm muted">{g.description}</p>}
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                {g.links.map((l) => <LinkCard key={l.id} l={l} q={q} />)}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
