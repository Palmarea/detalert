import { cookies } from "next/headers";
import { SESSION_COOKIE, verifySession } from "./session";

export async function getSession() {
  return verifySession((await cookies()).get(SESSION_COOKIE)?.value);
}
