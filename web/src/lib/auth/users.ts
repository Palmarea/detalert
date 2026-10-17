/* Usuarios de demo. Las credenciales son públicas a propósito (se muestran en /login).
   Para producción, reemplazar por el proveedor de identidad real. */

export interface DemoUser {
  id: string;
  email: string;
  name: string;
  role: string;
}

export const DEMO_PASSWORD = "demo1234";

export const DEMO_USERS: DemoUser[] = [
  { id: "analista", email: "analista@demo.local", name: "Lucía Paredes", role: "Analista de fraude" },
  { id: "supervisor", email: "supervisor@demo.local", name: "Diego Ramos", role: "Supervisor de riesgo" },
];

/* Comparación en tiempo constante para no filtrar por timing cuántos caracteres coinciden. */
function safeEqual(a: string, b: string) {
  let diff = a.length ^ b.length;
  for (let i = 0; i < Math.max(a.length, b.length); i++) diff |= (a.charCodeAt(i) | 0) ^ (b.charCodeAt(i) | 0);
  return diff === 0;
}

export function checkCredentials(email: string, password: string) {
  const user = DEMO_USERS.find((u) => u.email === email.trim().toLowerCase());
  const ok = safeEqual(password, DEMO_PASSWORD); // se compara siempre, exista o no el usuario
  return user && ok ? user : null;
}

export const initials = (name: string) => name.split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase();
