/* Sesión firmada (HMAC-SHA256) guardada en una cookie httpOnly.
   Usa solo Web Crypto, así que funciona igual en el middleware (edge) y en el servidor. */

export const SESSION_COOKIE = "monitor_session";
export const SESSION_TTL_S = 8 * 60 * 60; // 8 h

export interface Session {
  sub: string; // email
  name: string;
  role: string;
  exp: number; // epoch en segundos
}

const enc = new TextEncoder();
let keyPromise: Promise<CryptoKey> | null = null;

function secret() {
  const s = process.env.AUTH_SECRET;
  if (s) return s;
  if (process.env.NODE_ENV === "production") throw new Error("Falta AUTH_SECRET: sin él cualquiera podría firmar sesiones.");
  return "solo-desarrollo-cambiar-en-produccion";
}

function key() {
  return (keyPromise ??= crypto.subtle.importKey("raw", enc.encode(secret()), { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]));
}

function toB64url(bytes: Uint8Array) {
  let s = "";
  bytes.forEach((b) => (s += String.fromCharCode(b)));
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function fromB64url(s: string) {
  return Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));
}

export async function createSession(user: Omit<Session, "exp">) {
  const payload: Session = { ...user, exp: Math.floor(Date.now() / 1000) + SESSION_TTL_S };
  const body = toB64url(enc.encode(JSON.stringify(payload)));
  const sig = new Uint8Array(await crypto.subtle.sign("HMAC", await key(), enc.encode(body)));
  return `${body}.${toB64url(sig)}`;
}

/* Devuelve la sesión solo si la firma es válida y no venció. */
export async function verifySession(token: string | undefined): Promise<Session | null> {
  if (!token) return null;
  const [body, sig] = token.split(".");
  if (!body || !sig) return null;
  try {
    if (!(await crypto.subtle.verify("HMAC", await key(), fromB64url(sig), enc.encode(body)))) return null;
    const p = JSON.parse(new TextDecoder().decode(fromB64url(body))) as Session;
    return typeof p.exp === "number" && p.exp * 1000 > Date.now() ? p : null;
  } catch {
    return null;
  }
}
