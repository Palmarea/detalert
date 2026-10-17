import type { Metadata } from "next";
import { LoginScreen } from "@/components/auth/LoginScreen";
import { DEMO_PASSWORD, DEMO_USERS } from "@/lib/auth/users";

export const metadata: Metadata = { title: "Ingresar · Monitor de pagos" };

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ next?: string; expired?: string }> }) {
  const { next, expired } = await searchParams;
  return <LoginScreen next={next ?? "/"} expired={expired === "1"} demoUsers={DEMO_USERS} demoPassword={DEMO_PASSWORD} />;
}
