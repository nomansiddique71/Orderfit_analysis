// Typed client for the SolvOrder FastAPI backend (server.py).

export type Severity = "critical" | "warning" | "info";

export interface Fact {
  key: string; label: string; value: string; source: string; span: string;
  confidence: number; verified: boolean; note: string; simulation: boolean; needs_review: boolean;
}
export interface Flag {
  code: string; severity: Severity; title: string; message: string; documents: string[];
  blocks_execution: boolean; resolved: boolean; resolution_note: string;
  category: "fraud" | "integrity" | "ambiguity" | "security";
}
export interface DocInfo { doc_id: string; filename: string; kind: string; scanned: boolean; chars: number; text: string }
export interface Profile {
  name: string; currency: string; opening_cash: string; reserve: string; max_financing_cost: string;
  obligations: { day: number; amount: string; label: string; kind: string; counterparty: string }[];
  offers: { id: string; lender: string; principal: string; terms: string; draw_day: number; repay_day: number }[];
}
export interface DocView {
  mode: string; note: string; sample_id: string | null; documents: DocInfo[]; facts: Fact[];
  supplier_payments: { label: string; amount: Fact; day: Fact }[];
  line_items: { description: string; amount: string; source: string }[];
  bank_details: { source: string; payee: string; bank: string; account: string; verified: boolean }[];
  flags: Flag[]; profile: Profile | null;
}
export interface Tolerance {
  kind: "never_pays_safe" | "fails_on_time" | "days"; days: number | null; label: string;
  last_safe_pay_day: number | null; survives: Record<string, boolean>;
}
export interface Plan {
  id: string; label: string; version: string; feasible: boolean; robust: boolean; reserve_ok: boolean;
  min_balance: number; min_day: number; first_breach_day: number | null; stress_fail_day: number | null;
  financing_cost: number; net_margin: number; gross_margin: number; consents: string[];
  advance_pct: number; supplier_extension: boolean;
  financing: { id: string; lender: string; principal: number; terms: string; draw_day: number; repay_day: number } | null;
  violations: string[]; tolerance: Tolerance | null; path: { day: number; low: number; end: number }[];
  recommended: boolean;
}
export interface Analysis {
  ok: boolean; missing?: string[];
  case: {
    name: string; currency: string; business: string; opening_cash: number; reserve: number;
    order_value: number; gross_margin: number; delivery_day: number; customer: string; supplier: string;
    order_ref: string; pay_day: number; document_pay_day: number; max_financing_cost: number;
    assumptions: string[]; payment_readings: Record<string, number>; basis_used: string;
    movements: { day: number; amount: number; label: string; counterparty: string; kind: string }[];
  };
  verdict: {
    headline: string; level: "LOW" | "MEDIUM" | "HIGH"; why: string; winner: string; provisional: boolean;
    provisional_fields: { name: string; value: string; key: string; question: string | null }[];
    no_plan_survives: boolean; smallest_changes: string[]; priority_conflict: boolean;
    near_tie: { id: string; label: string; strengths: string[] }[] | null; owner_tie_choice: string | null;
    execution_blocks: string[];
  };
  gap: { amount: number; from_day: number | null; until_day: number | null; days: number };
  plans: Plan[];
  alerts: { rule: string; day: number | null; message: string; severity: Severity }[];
  flags: Flag[];
  fields: { name: string; value: string; source: string; span: string; confidence: number; question: string | null; key: string; simulation: boolean }[];
  sensitivity: { flip_day: number | null; rows: { day: number; label: string }[] };
  min_safe_loans: { offer: string; lender: string; terms: string; principal: number | null; cost: number | null; min: number; max: number }[];
  offers: { id: string; lender: string; principal: number; terms: string; cost: number; draw_day: number; repay_day: number; ineligible: string | null }[];
  stages: { stage: string; title: string; detail: string }[];
  draft: string;
  approval: Approval | null;
  executed: Execution | null;
  ai: { label: string; gemini: boolean };
}
export interface Approval { id: string; plan_id: string; label: string; override: boolean; reason: string; version: string }
export interface Execution {
  ok: boolean; steps: string[]; consistency: string | null; override: boolean;
  ledger: { day: number; amount: string; label: string }[]; outbox: { to: string; subject: string; body: string; status: string }[];
}
export interface ScenarioResult {
  outcomes: { key: string; label: string; min_balance: number; min_day: number; first_breach_day: number | null;
    reserve_ok: boolean; order_net: number; penalty: number; violations: string[] }[];
  max_loss: number; money_at_risk: { day: number; amount: number }[];
}
export interface Pack { id: string; title: string; badge: string; subtitle: string; story: string; look_for: string[]; files: string[] }
export interface LogEntry { time: string; tool: string; tier: string; input_hash: string; approval_id: string; result: string; blocked_reason: string }

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

let sessionId: string | null = sessionStorage.getItem("solvorder.sid");

async function newSession(): Promise<string> {
  const r = await fetch("/api/session", { method: "POST" });
  const j = await r.json();
  sessionId = j.session_id as string;
  sessionStorage.setItem("solvorder.sid", sessionId);
  return sessionId;
}

export async function session(): Promise<string> {
  return sessionId ?? newSession();
}

export function resetSession() {
  sessionId = null;
  sessionStorage.removeItem("solvorder.sid");
}

async function handle<T>(r: Response): Promise<T> {
  if (r.ok) return r.json() as Promise<T>;
  let msg = `Request failed (${r.status})`;
  try {
    const j = await r.json();
    if (typeof j.detail === "string") msg = j.detail;
    else if (Array.isArray(j.detail)) msg = j.detail.map((d: { msg: string }) => d.msg).join("; ");
  } catch { /* keep the generic message */ }
  if (r.status === 404 && msg.startsWith("Session expired")) resetSession();
  throw new ApiError(r.status, msg);
}

// A server restart (or Cloud Run moving to a new instance) loses in-memory
// sessions: start a fresh one and retry once. Steps that need earlier state
// (analyse, approve) then report what is missing instead of failing silently.
async function withSession<T>(send: (sid: string) => Promise<Response>): Promise<T> {
  try {
    return await handle<T>(await send(await session()));
  } catch (e) {
    if (e instanceof ApiError && e.status === 404 && sessionId === null) {
      return handle<T>(await send(await newSession()));
    }
    throw e;
  }
}

export async function post<T>(path: string, body: Record<string, unknown> = {}): Promise<T> {
  return withSession<T>((sid) => fetch(path, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sid, ...body }),
  }));
}

export async function get<T>(path: string): Promise<T> {
  return handle<T>(await fetch(path));
}

export async function upload(files: File[], pasted: string): Promise<DocView> {
  return withSession<DocView>((sid) => {
    const fd = new FormData();
    fd.append("session_id", sid);
    files.forEach((f) => fd.append("files", f));
    if (pasted.trim()) fd.append("pasted", pasted);
    return fetch("/api/documents/upload", { method: "POST", body: fd });
  });
}

export const logUrl = async () => `/api/log/export?session_id=${encodeURIComponent(await session())}`;
