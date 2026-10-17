import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { History } from "@/components/monitor/History";
import { getSession } from "@/lib/auth/server";

export const metadata: Metadata = { title: "Historial · Monitor de pagos" };

export default async function HistoryPage({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const session = await getSession();
  if (!session) redirect("/login?next=/historial");
  const { q } = await searchParams;
  return <History user={{ name: session.name, role: session.role }} initialQuery={q ?? ""} />;
}
