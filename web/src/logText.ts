import type { LogEntry } from "./api";

export type LogStatus = "success" | "warning" | "failed";

export interface LogLine {
  /** One plain sentence: what happened, who did it, and the outcome. */
  sentence: string;
  /** Who or what did it, in everyday words. */
  who: string;
  status: LogStatus;
  /** Short word shown next to the status icon. */
  statusText: string;
  /** What the owner can do about it, when something went wrong. */
  next?: string;
}

const WHO: Record<LogEntry["where"], string> = {
  owner: "You", gemini: "Gemini (Google AI)", engine: "SolvOrder", sandbox: "Practice systems", blocked: "Safety check",
};

const OVERRIDE_TAG = /\s*\[RESERVE OVERRIDE\]/;
const quote = (s: string) => `“${s.replace(OVERRIDE_TAG, "").trim()}”`;
const after = (s: string, prefix: string) => s.slice(s.indexOf(prefix) + prefix.length);

/** Plain explanation and next step for the reasons the permission gate gives. */
function explainBlock(reason: string): { why: string; next?: string } {
  if (/no approval id/i.test(reason)) return { why: "there was no approval for it", next: "Approve a plan first, then press Notify." };
  if (/unknown approval id/i.test(reason)) return { why: "the approval it used could not be found", next: "Approve the plan again." };
  if (/different plan version/i.test(reason)) return { why: "the plan changed after you approved it, so that approval no longer applies", next: "Approve the current plan again." };
  if (/fraud\/integrity flag/i.test(reason)) return { why: "a fraud or document check is still open", next: "On Check the facts, record how you verified it with the supplier." };
  if (/not in catalogue|differ from catalogue|not allowed/i.test(reason)) return { why: "the loan terms didn't match the lender's own offer", next: "Only loans exactly as the lender offers them can be used." };
  if (/ledger path != engine/i.test(reason)) return { why: "the practice bank's balance did not match SolvOrder's calculation", next: "Start a new case and try again; if it repeats, the payments should not go ahead." };
  return { why: reason };
}

const T3_TEXT: Record<string, string> = {
  "smtp.send": "Someone tried to send a real email",
  "bank.live_transfer": "Someone tried to make a real bank transfer",
  "lender.create_terms": "Someone tried to invent loan terms",
  "documents.edit": "Someone tried to edit one of your source documents",
};

/** Plain wording for the reasons forbidden ("T3") actions are refused. */
export function plainT3Reason(reason: string) {
  if (/real email/i.test(reason)) return "it has no way to send real email.";
  if (/live bank/i.test(reason)) return "it has no connection to a real bank.";
  if (/catalogue/i.test(reason)) return "loan terms can only come from the lender's own offer.";
  if (/read-only/i.test(reason)) return "your documents are kept exactly as you gave them.";
  return reason.replace(/^T3:\s*/i, "");
}

/** Turn one raw operation-log entry into a sentence a non-technical owner can read. Display only. */
export function describe(e: LogEntry): LogLine {
  const who = WHO[e.where];
  const r = e.result ?? "";
  const ok = (sentence: string): LogLine => ({ sentence, who, status: "success", statusText: "Done" });
  const override = OVERRIDE_TAG.test(r) ? " This was a reserve override you chose on purpose." : "";

  // Anything stopped by the permission gate, or a forbidden action
  if (r.startsWith("BLOCKED") || e.tier === "T3") {
    const { why, next } = explainBlock(e.blocked_reason || r.replace(/^BLOCKED:?\s*/, ""));
    if (e.tier === "T3") {
      return { sentence: `${T3_TEXT[e.tool] ?? e.what}. SolvOrder refused: ${plainT3Reason(e.blocked_reason || why)}`,
        who, status: "warning", statusText: "Blocked" };
    }
    const what = ({ "outbox.send": "Sending the email", "bank.post": "Booking the payments", "lender.accept": "Accepting the loan",
      execute_plan: "Carrying out the plan" } as Record<string, string>)[e.tool] ?? e.what;
    return { sentence: `${what} was stopped because ${why}.`, who, status: "failed", statusText: "Stopped", next };
  }

  switch (e.tool) {
    case "session_start": return ok("A new SolvOrder session started.");
    case "extract_fields": {
      const n = Number(r.match(/^(\d+)/)?.[1] ?? 0);
      const docs = n === 1 ? "your document" : `your ${n || ""} documents`.replace("  ", " ");
      return e.where === "gemini" ? ok(`Gemini read ${docs} and pulled out the amounts, dates and terms.`)
        : ok(`SolvOrder read ${docs} with its built-in reader (Gemini wasn't used).`);
    }
    case "manual_entry": return ok("You typed in the order details yourself.");
    case "set_profile": return /example/.test(r) ? ok("You chose to use the example business's numbers.") : ok("You saved your business's cash numbers.");
    case "set_role": { const role = r.match(/the (seller|buyer)/)?.[1]; return ok(role ? `You said you are the ${role} in this deal.` : "You set your side of the deal."); }
    case "resolve_flag": {
      const label = r.includes(": ") ? after(r, ": ").replace(" (payments stay blocked)", "") : "";
      const stays = r.includes("payments stay blocked");
      return { sentence: `You decided how to handle a document check${label ? `: ${quote(label)}` : ""}.${stays ? " Payments stay blocked for now." : ""}`,
        who, status: stays ? "warning" : "success", statusText: stays ? "Still blocked" : "Done",
        next: stays ? "To unblock payments, choose an option that confirms you checked with the supplier." : undefined };
    }
    case "simulate+rank_plans": return ok(`SolvOrder worked out your cash for every day and recommended ${quote(after(r, "decision: "))}.`);
    case "request_approval":
      if (r.startsWith("owner declined")) return ok(`You chose to decline the deal (${quote(after(r, ": "))}).`);
      return ok(`You approved the plan ${quote(after(r, ": "))}.${override}`);
    case "outbox.send": return ok(`The email to the other side was placed in the demo outbox. Nothing was really delivered.${override}`);
    case "lender.accept": return ok(`The loan was accepted in the practice lender portal, on the lender's own terms.${override}`);
    case "bank.post": {
      const n = r.match(/^(\d+)/)?.[1];
      return ok(`${n ? `${n} payments` : "The payments"} for the approved plan were booked in the practice bank.${override}`);
    }
    case "consistency_check":
      return r.startsWith("FAILED")
        ? { sentence: "The practice bank's balance did not match SolvOrder's calculation, so the run was stopped.", who, status: "failed", statusText: "Failed",
            next: "Start a new case and try again; if it repeats, the payments should not go ahead." }
        : ok("SolvOrder checked the practice bank's balance against its own calculation: they match on every day.");
    case "gemini.exchange_rate": {
      const missing = r.startsWith("missing");
      return missing
        ? { sentence: "Gemini could not find an exchange rate for your documents' currency.", who, status: "warning", statusText: "Needs you",
            next: "Type the rate in on the Check the facts screen." }
        : ok(r.startsWith("owner") ? "The exchange rate you entered is being used." : "Gemini looked up the exchange rate with Google Search.");
    }
    case "set_exchange_rate": return ok(`You set the exchange rate yourself (${after(r, "owner set ")}).`);
  }

  if (e.tool.startsWith("gemini.")) {
    const source = r.replace(/^source:\s*/, "");
    const action = ({ "gemini.explain": "explained the decision in plain language", "gemini.ask": "answered your question",
      "gemini.polish": "reworded the email (every number was checked afterwards)", "gemini.what_else_needed": "chose which questions to ask you",
      "gemini.google_search": "looked the companies up on Google" } as Record<string, string>)[e.tool] ?? "helped";
    // result is "source: gemini|template|rules" or "company web check: on|off|error"
    if (/(^|\s)(gemini|on)$/i.test(source.trim())) return ok(`Gemini ${action}.`);
    return { sentence: `Gemini wasn't available, so SolvOrder used its standard version instead (${e.what.toLowerCase()}).`, who: "SolvOrder",
      status: "warning", statusText: "Fallback used" };
  }
  return ok(`${e.what}.`);
}

/** "2:14 PM" from the server's "14:14:03". */
export function friendlyTime(t: string) {
  const [h, m] = t.split(":").map(Number);
  if (Number.isNaN(h) || Number.isNaN(m)) return t;
  const d = new Date(2000, 0, 1, h, m);
  return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}
