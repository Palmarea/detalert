import type { Currency } from "./types";

export const money = (cents: number, cur: Currency) =>
  (cur === "USD" ? "US$ " : "S/ ") +
  (cents / 100).toLocaleString("es-PE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const hhmm = (iso: string) =>
  new Date(iso).toLocaleTimeString("es-PE", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

export const rel = (iso: string, now = Date.now()) => {
  const s = Math.max(0, Math.round((now - +new Date(iso)) / 1000));
  return s < 60 ? `hace ${s}s` : s < 3600 ? `hace ${Math.floor(s / 60)} min` : hhmm(iso);
};

const esc = (s: string) =>
  s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

/* Resaltado simple de JSON. Escapa primero, así que es seguro para dangerouslySetInnerHTML. */
export const jsonHTML = (o: unknown) =>
  esc(JSON.stringify(o, null, 2))
    .replace(/(&quot;[^&]*?&quot;)(\s*:)/g, '<span class="k">$1</span>$2')
    .replace(/(:\s*)(&quot;.*?&quot;)/g, '$1<span class="s">$2</span>')
    .replace(/(:\s*)(-?\d+\.?\d*|true|false|null)/g, '$1<span class="n">$2</span>');
