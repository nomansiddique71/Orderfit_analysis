import { useEffect, useState } from "react";
import { get, post, type Analysis, type Approval, type ApprovedRecord, type Execution, type LogEntry } from "../api";
import type { Choice } from "../components/OptionsStep";
import type { SandboxTab } from "../components/Sandbox";

export type Draft = { body: string; to: string; to_name: string; subject: string; source: string; note?: string; party?: string };

/** State and server calls for "Approve and Notify" (moved out of ActStep.tsx unchanged). */
export function useActStep({ a, refresh, choice, onSent }: {
  a: Analysis; refresh: () => Promise<void>; choice: Choice; onSent: (text: string) => void;
}) {
  const [notifyOpen, setNotifyOpen] = useState(false);
  const [record, setRecord] = useState<ApprovedRecord | null>(null);
  const [bd, setBd] = useState(false);
  const [approval, setApproval] = useState<Approval | null>(a.approval);
  const [exec, setExec] = useState<Execution | null>(a.executed);
  const [err, setErr] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Draft[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [log, setLog] = useState<LogEntry[]>([]);
  const feasibleIds = a.plans.filter((p) => p.feasible && p.id !== "decline").map((p) => p.id);
  const [planId, setPlanId] = useState(choice && !choice.override && feasibleIds.includes(choice.id) ? choice.id
    : feasibleIds.includes(a.verdict.winner) ? a.verdict.winner : feasibleIds[0] ?? "");
  const [ovr, setOvr] = useState({ open: !!choice?.override, plan: choice?.override ? choice.id : "", reason: "", ack: false });
  const [draftLoading, setDraftLoading] = useState(false);
  // The message always matches the plan about to be approved (the override plan
  // while the override panel is open).
  const overridable0 = a.plans.find((p) => !p.reserve_ok && p.violations.length === 0 && p.id !== "decline")?.id ?? "";
  const draftPlan = ovr.open ? (ovr.plan || overridable0) : planId;
  useEffect(() => {
    if (!draftPlan) return;
    setDraftLoading(true);
    post<{ messages: Draft[] }>("/api/draft", { plan_id: draftPlan })
      .then((d) => setDrafts(d.messages.map((m) => ({ ...m, source: "engine" })))).catch((e) => setErr((e as Error).message))
      .finally(() => setDraftLoading(false));
  }, [draftPlan]);
  const [t3, setT3] = useState<string | null>(null);
  const [t3Busy, setT3Busy] = useState<string | null>(null);
  const [logLoading, setLogLoading] = useState(false);
  const [sbTab, setSbTab] = useState<SandboxTab>("outbox");
  const [sbVersion, setSbVersion] = useState(0);
  const openSandbox = (t: SandboxTab) => { setSbTab(t); document.getElementById("sandbox-panel")?.scrollIntoView({ behavior: "smooth", block: "start" }); };

  const feasible = a.plans.filter((p) => p.feasible && p.id !== "decline");
  const overridable = a.plans.filter((p) => !p.reserve_ok && p.violations.length === 0 && p.id !== "decline");
  const ovrPlan = a.plans.find((p) => p.id === (ovr.plan || overridable[0]?.id));
  const loadLog = async () => {
    setLogLoading(true);
    try { setLog((await get<{ entries: LogEntry[] }>(`/api/log?session_id=${encodeURIComponent(sessionStorage.getItem("solvorder.sid") ?? "")}`)).entries); }
    finally { setLogLoading(false); }
  };
  useEffect(() => { loadLog().catch(() => undefined); setSbVersion((n) => n + 1); }, [approval, exec, t3]); // eslint-disable-line react-hooks/exhaustive-deps

  async function act<T>(label: string, fn: () => Promise<T>, then: (r: T) => void) {
    setBusy(label); setErr(null);
    try { then(await fn()); } catch (e) { setErr((e as Error).message); } finally { setBusy(null); }
  }
  const blocked = a.verdict.execution_blocks.length > 0;
  const polished = () => !!drafts?.some((d) => d.source === "gemini");

  const sendNotify = () => act("notify", () => post<{ approval: Approval; executed: Execution; record: ApprovedRecord }>("/api/notify", { polished: polished() }),
    async (r) => {
      setApproval(r.approval); setExec(r.executed); setRecord(r.record); setNotifyOpen(false);
      const sent = r.approval.messages.filter((m) => m.sent).map((m) => m.to_name);
      onSent(sent.length ? `Email sent to ${sent.join(", ")} (demo outbox). Saved under Approved / declined plans.` : "No email could be sent: see the approval card.");
      await refresh();
    });
  const polish = () => act("polish", () => Promise.all((drafts ?? []).map((_, i) =>
    post<{ text: string; source: string; note: string }>("/api/ai/polish", { plan_id: draftPlan, index: i }))),
    (rs) => setDrafts((drafts ?? []).map((d, i) => ({ ...d, body: rs[i].text, source: rs[i].source, note: rs[i].note }))));
  const approve = () => act("approve", () => post<{ approval: Approval }>("/api/approve", { plan_id: planId, polished: polished() }), (r) => { setApproval(r.approval); setExec(null); });
  const approveOverride = () => act("override", () => post<{ approval: Approval }>("/api/approve", { plan_id: ovr.plan || overridable[0].id, override: true, reason: ovr.reason, polished: polished() }), (r) => { setApproval(r.approval); setExec(null); });
  const tryT3 = (k: string) => { setT3Busy(k); post<{ reason: string }>("/api/t3", { action: k }).then((r) => setT3(r.reason)).finally(() => setT3Busy(null)); };

  return {
    notifyOpen, setNotifyOpen, record, bd, setBd, approval, exec, err, drafts, busy, log, planId, setPlanId, ovr, setOvr,
    draftLoading, draftPlan, t3, t3Busy, logLoading, sbTab, setSbTab, sbVersion, openSandbox, feasible, overridable, ovrPlan,
    blocked, sendNotify, polish, approve, approveOverride, tryT3,
  };
}

/** State and server calls for the decline screen (moved out of ActStep.tsx unchanged). */
export function useDeclineStep(onSent: (text: string) => void) {
  const [drafts, setDrafts] = useState<Draft[] | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState<ApprovedRecord | null>(null);
  const [bd, setBd] = useState(false);
  useEffect(() => {
    post<{ messages: Draft[] }>("/api/draft", { plan_id: "decline" })
      .then((d) => setDrafts(d.messages.map((m) => ({ ...m, source: "engine" })))).catch((e) => setErr((e as Error).message));
  }, []);
  async function act<T>(label: string, fn: () => Promise<T>, then: (r: T) => void) {
    setBusy(label); setErr(null);
    try { then(await fn()); } catch (e) { setErr((e as Error).message); } finally { setBusy(null); }
  }
  const send = () => act("send", () => post<{ approval: Approval; record: ApprovedRecord }>("/api/decline", { polished: !!drafts?.some((d) => d.source === "gemini") }),
    (r) => { setDone(r.record); setOpen(false); onSent(`Decline sent to ${r.record.counterparty} (demo outbox). Saved under Approved / declined plans.`); });
  const polish = () => act("polish", () => post<{ text: string; source: string; note: string }>("/api/ai/polish", { plan_id: "decline", index: 0 }),
    (r) => setDrafts((drafts ?? []).map((d, i) => i === 0 ? { ...d, body: r.text, source: r.source, note: r.note } : d)));
  return { drafts, open, setOpen, busy, err, done, bd, setBd, send, polish };
}
