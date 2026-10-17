/* Versión vacía del agente. Se usa cuando src/agent/ no existe (GitHub, Vercel):
   el panel no aparece y no agrega nada a la auditoría.
   El alias "@agent/*" apunta a src/agent si existe, o aquí (ver tsconfig.json y next.config.ts). */
import type { PaymentEvent } from "@/lib/payments/types";

export interface AgentPanelProps {
  event: PaymentEvent;
  userName: string;
}

export interface AgentAuditEntry {
  at: string;
  actor: string;
  action: string;
  hash: string;
}

const NONE: AgentAuditEntry[] = [];

export const AgentPanel: (props: AgentPanelProps) => null = () => null;

export const useAgentAudit: (eventId: string, userName: string) => AgentAuditEntry[] = () => NONE;
