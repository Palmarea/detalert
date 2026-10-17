import { redirect } from "next/navigation";
import { Monitor } from "@/components/monitor/Monitor";
import { getSession } from "@/lib/auth/server";

export default async function Page() {
  const session = await getSession(); // el middleware ya filtra; esto es la segunda barrera
  if (!session) redirect("/login");
  return <Monitor user={{ name: session.name, role: session.role }} />;
}
