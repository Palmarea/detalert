import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { Dashboard } from "@/components/monitor/Dashboard";
import { getSession } from "@/lib/auth/server";

export const metadata: Metadata = { title: "Panel · Monitor de pagos" };

export default async function PanelPage() {
  const session = await getSession();
  if (!session) redirect("/login?next=/panel");
  return <Dashboard user={{ name: session.name, role: session.role }} />;
}
