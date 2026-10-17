"use server";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { SESSION_COOKIE, SESSION_TTL_S, createSession } from "@/lib/auth/session";
import { DEMO_USERS, checkCredentials } from "@/lib/auth/users";

export interface LoginState {
  error: string | null;
  email: string;
}

/* Solo rutas internas: evita usar ?next= para redirigir a otro sitio. */
const safeNext = (v: FormDataEntryValue | null) => (typeof v === "string" && v.startsWith("/") && !v.startsWith("//") ? v : "/");

export async function login(_prev: LoginState, form: FormData): Promise<LoginState> {
  const demo = form.get("demo");
  const email = String(form.get("email") ?? "");
  const user = demo ? DEMO_USERS.find((u) => u.id === demo) : checkCredentials(email, String(form.get("password") ?? ""));

  if (!user) return { error: "Correo o contraseña incorrectos. Revisa los datos o entra con un acceso de demo.", email };

  (await cookies()).set(SESSION_COOKIE, await createSession({ sub: user.email, name: user.name, role: user.role }), {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: SESSION_TTL_S,
  });
  redirect(safeNext(form.get("next")));
}

export async function logout() {
  (await cookies()).delete(SESSION_COOKIE);
  redirect("/login");
}
