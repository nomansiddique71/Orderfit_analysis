// Typed client for the SolvOrder FastAPI backend (server.py).

export type Severity = "critical" | "warning" | "info";

export interface Original { text: string; currency: string; amount: number; rate: string | null; rate_date: string; converted: number | null; to: string }
export interface FxRate {
  currency: string; to: string; rate: string | null; date: string; date_note: string;
  mode: "gemini" | "owner" | "missing"; source: string; sources: { title: string; uri: string }[]; note: string; suspicious: boolean;
}
export interface FxView { active: boolean; to: string; rates: FxRate[] }
export interface Fact {
  original?: Original | null;
  key: string; label: string; value: string; source: string; span: string;
  confidence: number; verified: boolean; note: string; simulation: boolean; needs_review: boolean;
}
export interface Flag {
  code: string; severity: Severity; title: string; message: string; documents: string[];
  blocks_execution: boolean; resolved: boolean; resolution_note: string;
  category: "fraud" | "integrity" | "ambiguity" | "security";
  options: { id: string; label: string; clears: boolean; needs_note: boolean }[];
  decision: { action: string; label: string; note: string; clears: boolean } | null;
}
export interface DocInfo { doc_id: string; filename: string; kind: string; scanned: boolean; chars: number; text: string }
export interface Profile {
  name: string; currency: string; opening_cash: string; reserve: string; max_financing_cost: string;
  obligations: { day: number; amount: string; label: string; kind: string; counterparty: string }[];
  offers: { id: string; lender: string; principal: string; terms: string; draw_day: number; repay_day: number }[];
}
export interface DocView {
  mode: string; note: string; sample_id: string | null; documents: DocInfo[]; facts: Fact[];
  supplier_payments: { label: string; amount: Fact; day: Fact; paid: boolean }[];
  line_items: { description: string; amount: string; source: string }[];
  bank_details: { source: string; payee: string; bank: string; account: string; verified: boolean }[];
  flags: Flag[]; profile: Profile | null; profile_source: "sample" | "owner" | "example" | "default";
  role: Role; role_source: "profile" | "documents" | "owner" | "sample" | "default"; fx: FxView;
  role_guess: { role: Role | null; evidence: string }; currency: string;
  questions: number; // required intake questions still open
}
export interface Need { key: string; question: string; why: string; widget: string; source: "gemini" | "rules"; required: boolean; suggested?: Role | null; rates?: FxRate[] }
export interface NeedsView { needs: Need[]; mode: "gemini" | "rules"; note: string; profile_source: string; profile: Profile | null }
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
  ok: boolean; missing?: string[]; needs_business?: boolean;
  case: {
    name: string; currency: string; business: string; opening_cash: number; reserve: number;
    role: Role; deal: "order" | "offer"; fx: FxView;
    order_value: number; gross_margin: number; delivery_day: number;
    advance_received: number; balance_due: number; costs_already_paid: number; customer: string; supplier: string;
    order_ref: string; pay_day: number; document_pay_day: number; max_financing_cost: number;
    assumptions: string[]; payment_readings: Record<string, number>; basis_used: string;
    movements: { day: number; amount: number; label: string; counterparty: string; kind: string; note: string }[];
  };
  verdict: {
    headline: string; level: "LOW" | "MEDIUM" | "HIGH"; why: string; winner: string; provisional: boolean;
    provisional_fields: { name: string; value: string; key: string; question: string | null }[];
    no_plan_survives: boolean; smallest_changes: string[]; priority_conflict: boolean;
    near_tie: { id: string; label: string; strengths: string[] }[] | null; owner_tie_choice: string | null;
    execution_blocks: string[];
  };
  gap: { amount: number; from_day: number | null; until_day: number | null; days: number };
  walk: { asis: CashWalk; recommended: CashWalk };
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
export interface CashWalk {
  plan: string; opening: number; reserve: number; low: number; low_day: number; headroom: number; end: number;
  out_until_low: Record<string, number>; in_until_low: Record<string, number>;
  rows: { day: number; label: string; group: string; kind: string; note: string; amount: number; balance: number; below_reserve: boolean }[];
}
export interface Breakdown {
  plan_id: string; plan: string; verdict: "accept" | "reject" | "neutral"; summary: string;
  reasons_for: string[]; reasons_against: string[];
  opening: number; reserve: number; end: number; low: number; low_day: number; headroom: number;
  money_in: Record<string, number>; money_out: Record<string, number>;
  total_in: number; total_out: number; net_change: number;
  profit: { income: number; costs: number; financing: number; net: number };
  rows: { day: number; label: string; group: string; kind: string; counterparty: string; note: string; amount: number; balance: number; below_reserve: boolean }[];
}
export interface SentMessage { party?: string; to: string; to_name: string; subject: string; body: string; source: string; status: string; sent: boolean }
export interface Approval { id: string; plan_id: string; label: string; override: boolean; reason: string; version: string; messages: SentMessage[]; notified: boolean }
export interface ApprovedRecord {
  id: string; time: string; case: string; business: string; role: Role; counterparty: string; party: string;
  plan_id: string; plan: string; override: boolean; reason: string; currency: string; order_ref: string;
  numbers: { low: number; low_day: number; reserve: number; net_profit: number; financing_cost: number; opening: number };
  summary: string; reasons_for: string[]; reasons_against: string[]; mails: SentMessage[];
  sandbox: { ok: boolean; consistency: string | null; steps: string[] };
}
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
export interface LogEntry {
  time: string; tool: string; tier: string; input_hash: string; approval_id: string; result: string; blocked_reason: string;
  where: "sandbox" | "gemini" | "engine" | "owner" | "blocked"; what: string;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

let sessionId: string | null = sessionStorage.getItem("solvorder.sid");

// ---- in-flight request tracking (drives the global progress bar) ----
let inflight = 0;
const listeners = new Set<() => void>();
export function subscribePending(cb: () => void) { listeners.add(cb); return () => { listeners.delete(cb); }; }
export function pendingCount() { return inflight; }
async function tracked<T>(p: Promise<T>): Promise<T> {
  inflight += 1; listeners.forEach((l) => l());
  try { return await p; } finally { inflight -= 1; listeners.forEach((l) => l()); }
}

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

// ---- lost-session recovery ----
// Sessions live in server memory, so a Cloud Run restart or a new instance
// loses them. The client remembers how the current case was loaded (sample,
// upload or manual entry) and which fraud flags the owner resolved; on a
// "session expired" 404 it opens a new session, replays those calls and
// retries the original request, so the owner never notices.
type LoadCall = { path: string; body: Record<string, unknown> } | { files: File[]; pasted: string };
let lastLoad: LoadCall | null = null;
let resolvedFlags: Record<string, unknown>[] = [];
let lastProfile: Record<string, unknown> | null = null; // business details survive a new case
const LOAD_PATHS = new Set(["/api/documents/sample", "/api/documents/manual"]);

function remember(path: string, body: Record<string, unknown>) {
  if (LOAD_PATHS.has(path)) {
    lastLoad = { path, body }; resolvedFlags = [];
    if (path === "/api/documents/sample") lastProfile = null; // a sample brings its own business
  }
  else if (path === "/api/flags/resolve") resolvedFlags.push(body);
  else if (path === "/api/profile") lastProfile = body;
}

// The login token rides along so the server knows whose company profile (role,
// currency) applies to the case; the analysis itself stays session-based.
function authHeader(): Record<string, string> {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

function jsonPost(path: string, sid: string, body: Record<string, unknown>) {
  return fetch(path, { method: "POST", headers: { "Content-Type": "application/json", ...authHeader() }, body: JSON.stringify({ session_id: sid, ...body }) });
}

function uploadPost(sid: string, files: File[], pasted: string) {
  const fd = new FormData();
  fd.append("session_id", sid);
  files.forEach((f) => fd.append("files", f));
  if (pasted.trim()) fd.append("pasted", pasted);
  return fetch("/api/documents/upload", { method: "POST", body: fd, headers: authHeader() });
}

async function replay(sid: string) {
  if (lastLoad) await handle(await ("path" in lastLoad ? jsonPost(lastLoad.path, sid, lastLoad.body) : uploadPost(sid, lastLoad.files, lastLoad.pasted)));
  if (lastProfile) await handle(await jsonPost("/api/profile", sid, lastProfile));
  for (const r of resolvedFlags) await handle(await jsonPost("/api/flags/resolve", sid, r));
}

export function forgetCase() { lastLoad = null; resolvedFlags = []; lastProfile = null; }

async function withSession<T>(send: (sid: string) => Promise<Response>): Promise<T> {
  return tracked(withSessionInner<T>(send));
}

async function withSessionInner<T>(send: (sid: string) => Promise<Response>): Promise<T> {
  try {
    return await handle<T>(await send(await session()));
  } catch (e) {
    if (e instanceof ApiError && e.status === 404 && sessionId === null) {
      const sid = await newSession();
      await replay(sid);
      return handle<T>(await send(sid));
    }
    throw e;
  }
}

export async function post<T>(path: string, body: Record<string, unknown> = {}): Promise<T> {
  const r = await withSession<T>((sid) => jsonPost(path, sid, body));
  remember(path, body);
  return r;
}

export async function get<T>(path: string): Promise<T> {
  return tracked(fetch(path).then((r) => handle<T>(r)));
}

export async function upload(files: File[], pasted: string): Promise<DocView> {
  const r = await withSession<DocView>((sid) => uploadPost(sid, files, pasted));
  lastLoad = { files, pasted }; resolvedFlags = [];
  return r;
}

export const logUrl = async () => `/api/log/export?session_id=${encodeURIComponent(await session())}`;

// ---- demo login (auth.py). The token lives in localStorage so a reload keeps you signed in.
export type Role = "seller" | "buyer";
export interface User {
  email: string; username: string; name: string; business: string; verified: boolean; demo: boolean; member_since: string;
  company_email: string; role: Role; currency: string;
}
export interface DemoMail { to: string; subject: string; body: string; time: string; note: string }
const TOKEN_KEY = "solvorder.token";

export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function setToken(t: string | null) {
  try { if (t) localStorage.setItem(TOKEN_KEY, t); else localStorage.removeItem(TOKEN_KEY); } catch { /* private mode: session-only */ }
}

export async function authPost<T>(path: string, body: Record<string, unknown> = {}): Promise<T> {
  const t = getToken();
  return tracked(fetch(path, {
    method: "POST", headers: { "Content-Type": "application/json", ...(t ? { Authorization: `Bearer ${t}` } : {}) },
    body: JSON.stringify(body),
  }).then((r) => handle<T>(r)));
}

/** Approved plans of the logged-in owner (or of this session when nobody is logged in). */
export async function approvedPlans(): Promise<ApprovedRecord[]> {
  const r = await tracked(fetch(`/api/approved?session_id=${encodeURIComponent(sessionId ?? "")}`, { headers: authHeader() }).then((x) => handle<{ plans: ApprovedRecord[] }>(x)));
  return r.plans;
}

export async function me(): Promise<User | null> {
  const t = getToken();
  if (!t) return null;
  const r = await fetch("/api/auth/me", { headers: { Authorization: `Bearer ${t}` } });
  if (!r.ok) { setToken(null); return null; }
  return (await r.json()).user as User;
}
