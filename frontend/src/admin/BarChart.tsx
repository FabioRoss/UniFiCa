import { useState } from "react";

/** Single-series column chart (updates per day). Follows the dataviz specs:
 *  bars capped at 24px with a 4px rounded top and square base, hairline
 *  recessive grid, one labelled extreme, per-bar hover tooltip, and a
 *  screen-reader table. No legend: the card title names the series. */
export default function BarChart({ data, label }: { data: { date: string; count: number }[]; label: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 720, H = 200, padL = 28, padB = 24, padT = 16;
  const max = Math.max(1, ...data.map((d) => d.count));
  const step = max <= 4 ? 1 : max <= 10 ? 2 : Math.ceil(max / 4 / 5) * 5;
  const top = Math.ceil(max / step) * step;
  const ticks = Array.from({ length: top / step + 1 }, (_, i) => i * step);
  const slot = (W - padL) / data.length;
  const bw = Math.min(24, slot - 2); // 2px surface gap between touching bars
  const y = (v: number) => padT + (H - padT - padB) * (1 - v / top);
  const peak = data.reduce((best, d, i) => (d.count > data[best].count ? i : best), 0);
  const fmt = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString("it-IT", { day: "numeric", month: "short" });

  const bar = (x: number, h: number) => {
    // Rounded top (r=4), square at the baseline
    const r = Math.min(4, h, bw / 2);
    const yb = y(0);
    return `M${x},${yb} V${yb - h + r} Q${x},${yb - h} ${x + r},${yb - h} H${x + bw - r} Q${x + bw},${yb - h} ${x + bw},${yb - h + r} V${yb} Z`;
  };

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label={label} onMouseLeave={() => setHover(null)}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={padL} x2={W} y1={y(t)} y2={y(t)} stroke="currentColor" className="text-slate-200 dark:text-slate-800" strokeWidth="1" />
            <text x={padL - 6} y={y(t) + 4} textAnchor="end" className="fill-slate-500 text-[11px] dark:fill-slate-400">{t}</text>
          </g>
        ))}
        {data.map((d, i) => {
          const x = padL + i * slot + (slot - bw) / 2;
          const h = y(0) - y(d.count);
          return (
            <g key={d.date}>
              {d.count > 0 && <path d={bar(x, h)} fill="var(--chart-bar)" opacity={hover === null || hover === i ? 1 : 0.45} />}
              {/* hit target: the whole slot, taller than the mark */}
              <rect x={padL + i * slot} y={padT} width={slot} height={H - padT - padB} fill="transparent"
                onMouseEnter={() => setHover(i)} onTouchStart={() => setHover(i)} />
              {i === peak && d.count > 0 && (
                <text x={x + bw / 2} y={y(d.count) - 5} textAnchor="middle" className="fill-slate-700 text-[11px] font-semibold dark:fill-slate-200">{d.count}</text>
              )}
              {(data.length - 1 - i) % 7 === 0 && (
                <text x={x + bw / 2} y={H - 6} textAnchor="middle" className="fill-slate-500 text-[11px] dark:fill-slate-400">{fmt(d.date)}</text>
              )}
            </g>
          );
        })}
      </svg>
      {hover !== null && (
        <div className="pointer-events-none absolute top-0 -translate-x-1/2 rounded-lg bg-slate-900 px-2.5 py-1.5 text-xs text-white shadow-lg dark:bg-slate-100 dark:text-slate-900"
          style={{ left: `${((padL + hover * slot + slot / 2) / W) * 100}%` }}>
          <span className="font-semibold">{data[hover].count}</span> · {fmt(data[hover].date)}
        </div>
      )}
      <table className="sr-only">
        <caption>{label}</caption>
        <tbody>{data.map((d) => <tr key={d.date}><th>{d.date}</th><td>{d.count}</td></tr>)}</tbody>
      </table>
    </div>
  );
}
