const TZ = "Europe/Rome";

export function parseDate(s: string): Date {
  // Plain dates ("2026-11-05") are calendar days, not UTC midnights
  return /^\d{4}-\d{2}-\d{2}$/.test(s) ? new Date(`${s}T12:00:00`) : new Date(s);
}

export function fmtDate(s: string | null | undefined, opts: Intl.DateTimeFormatOptions = {}): string {
  if (!s) return "";
  return parseDate(s).toLocaleDateString("it-IT", { day: "numeric", month: "short", year: "numeric", timeZone: TZ, ...opts });
}

export function fmtDateTime(s: string | null | undefined): string {
  if (!s) return "";
  return parseDate(s).toLocaleString("it-IT", {
    day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: TZ,
  });
}

export function fmtDay(s: string): { weekday: string; day: string; month: string } {
  const d = parseDate(s);
  return {
    weekday: d.toLocaleDateString("it-IT", { weekday: "short", timeZone: TZ }).replace(".", ""),
    day: d.toLocaleDateString("it-IT", { day: "numeric", timeZone: TZ }),
    month: d.toLocaleDateString("it-IT", { month: "short", timeZone: TZ }).replace(".", ""),
  };
}

export function relTime(s: string | null | undefined): string {
  if (!s) return "";
  const diff = (Date.now() - parseDate(s).getTime()) / 1000;
  const rtf = new Intl.RelativeTimeFormat("it", { numeric: "auto" });
  if (diff < 60) return "adesso";
  if (diff < 3600) return rtf.format(-Math.round(diff / 60), "minute");
  if (diff < 86400) return rtf.format(-Math.round(diff / 3600), "hour");
  if (diff < 86400 * 7) return rtf.format(-Math.round(diff / 86400), "day");
  return fmtDate(s);
}

export function daysUntil(dateIso: string): number {
  const today = new Date();
  today.setHours(12, 0, 0, 0);
  return Math.round((parseDate(dateIso).getTime() - today.getTime()) / 86400000);
}

export function fileSize(n?: number | null): string {
  if (!n) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

/** Lowercase, accent-free: for client-side search. */
export function fold(s: string): string {
  return s.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

export function matchesQuery(q: string, ...fields: (string | undefined | null)[]): boolean {
  const words = fold(q).split(/\s+/).filter(Boolean);
  if (!words.length) return true;
  const hay = fold(fields.filter(Boolean).join(" "));
  return words.every((w) => hay.includes(w));
}

const SMALL = new Set(["e", "ed", "di", "del", "della", "dello", "dei", "degli", "delle", "dell", "da", "dal", "dalla",
  "in", "nel", "nella", "a", "al", "alla", "ai", "agli", "alle", "con", "per", "tra", "fra", "il", "lo", "la", "i", "gli", "le", "o", "su", "sul"]);

export function titleCase(s: string): string {
  // ESSE3 shouts in capitals: "MEDICINA LEGALE E MEDICINA DEL LAVORO (C.I.)"
  // becomes "Medicina Legale e Medicina del Lavoro (C.I.)". Roman numerals and
  // "(C.I.)" stay uppercase, Italian particles lowercase (except first word).
  // Word by word: only all-caps words are rewritten, so a mixed title like
  // "SPECIALITA' MEDICHE: Prova parziale di Chirurgia" keeps its second half.
  let first = true;
  return s.replace(/[a-zà-ù0-9.]+/gi, (orig) => {
    if (orig !== orig.toUpperCase()) { first = false; return orig; }
    const w = orig.toLowerCase();
    const out = /^(i{1,3}|iv|vi{0,3}|ix|x)$/.test(w) && !first ? w.toUpperCase()
      : /^c\.i\.?$/.test(w) ? w.toUpperCase()
        : !first && SMALL.has(w) ? w
          : w.charAt(0).toUpperCase() + w.slice(1);
    first = false;
    return out;
  });
}

/** "DI GRAZIA OMAR" -> "Di Grazia Omar" (names keep every word capitalised). */
export function nameCase(s: string): string {
  if (s !== s.toUpperCase()) return s;
  return s.toLowerCase().replace(/(^|[\s'-])([a-zà-ù])/g, (_, p, c) => p + c.toUpperCase());
}
