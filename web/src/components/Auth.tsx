import { useState } from "react";
import { BadgeCheck, Building2, Inbox, KeyRound, LogOut, Mail, PlayCircle, ShieldCheck, Sparkles, UserRound, X } from "lucide-react";
import { Logo } from "./Sidebar";
import { authPost, setToken, type DemoMail, type Role, type User } from "../api";
import { CURRENCIES } from "../format";
import { Callout, LoadingButton, Pill } from "./ui";

type Authed = { token: string; user: User };

/** Where the "emailed" code lands in this demo. Nothing is really sent. */
export function DemoInbox({ mail }: { mail: DemoMail | null }) {
  if (!mail) return null;
  return (
    <div className="rounded-lg border border-violet-200 bg-violet-50 p-4 text-sm">
      <div className="mb-1 flex items-center gap-2 font-semibold text-violet-900"><Inbox className="h-4 w-4" /> Demo inbox <Pill tone="violet">no real email sent</Pill></div>
      <div className="text-xs text-violet-800">To {mail.to} · {mail.time}</div>
      <div className="mt-1 font-semibold text-slate-900">{mail.subject}</div>
      <p className="text-slate-700">{mail.body}</p>
    </div>
  );
}

function Field({ label, type = "text", value, onChange, placeholder, autoComplete }: {
  label: string; type?: string; value: string; onChange: (v: string) => void; placeholder?: string; autoComplete?: string;
}) {
  return (
    <label className="block"><span className="label">{label}</span>
      <input className="input mt-1.5" type={type} value={value} placeholder={placeholder} autoComplete={autoComplete} onChange={(e) => onChange(e.target.value)} /></label>
  );
}

/** Log in, sign up (with an emailed code), or reset a forgotten password. */
export function AuthScreen({ onAuthed }: { onAuthed: (a: Authed) => void }) {
  const [mode, setMode] = useState<"login" | "signup" | "verify" | "forgot" | "reset">("login");
  const [f, setF] = useState({ name: "", username: "", email: "", password: "", login: "", code: "", newPassword: "" });
  const [pending, setPending] = useState<string | null>(null);
  const [mail, setMail] = useState<DemoMail | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const set = (k: keyof typeof f) => (v: string) => setF({ ...f, [k]: v });

  async function run<T>(label: string, fn: () => Promise<T>, then: (r: T) => void) {
    setBusy(label); setErr(null); setInfo(null);
    try { then(await fn()); } catch (e) { setErr((e as Error).message); } finally { setBusy(null); }
  }
  const done = (r: Authed) => { setToken(r.token); onAuthed(r); };

  return (
    <div className="grid min-h-full lg:grid-cols-2">
      <div className="hidden flex-col justify-between bg-brand-800 p-12 text-white lg:flex">
        <div className="flex items-center gap-3">
          <Logo className="h-10 w-10" />
          <div><div className="font-serif text-2xl font-semibold leading-none">SolvOrder</div><div className="mt-1 text-xs text-brand-200">Can my cash carry this order?</div></div>
        </div>
        <div>
          {/* A cash line that dips toward the reserve but stays above it */}
          <svg viewBox="0 0 420 120" className="mb-8 w-full max-w-md" aria-hidden>
            <path d="M0 92h420" stroke="#86b597" strokeWidth="1.5" strokeDasharray="5 5" />
            <text x="420" y="110" textAnchor="end" fill="#86b597" fontSize="12">your reserve</text>
            <path d="M0 24h70v28h60v22h70v-46h80v18h140" fill="none" stroke="#fff" strokeWidth="2.5" strokeLinejoin="round" />
            <circle cx="200" cy="74" r="4.5" fill="#fff" />
          </svg>
          <h1 className="text-[40px] font-semibold leading-[1.1]">Say yes to big orders, without running out of cash.</h1>
          <ul className="mt-7 space-y-3.5 text-[15px] text-brand-100">
            <li className="flex gap-3"><ShieldCheck className="h-5 w-5 shrink-0 text-brand-300" /> Your cash for every day of the deal, fraud checks, and the safest plan</li>
            <li className="flex gap-3"><Sparkles className="h-5 w-5 shrink-0 text-brand-300" /> Google Gemini reads your documents; a fixed calculator checks every number</li>
            <li className="flex gap-3"><KeyRound className="h-5 w-5 shrink-0 text-brand-300" /> Nothing happens without your approval, and it all runs in practice systems</li>
          </ul>
        </div>
        <p className="text-xs text-brand-200/80">Demo login for the Google Cloud AI Builder Cup. Accounts live in server memory; codes appear in an on-screen demo inbox.</p>
      </div>

      <div className="flex flex-col items-center justify-center bg-slate-100 p-4 sm:p-6">
        <div className="mb-6 flex items-center gap-2.5 lg:hidden"><Logo /><span className="font-serif text-2xl font-semibold text-slate-900">SolvOrder</span></div>
        <div className="w-full max-w-md space-y-5 rounded-2xl border border-slate-200 bg-white p-6 shadow-lg sm:p-8">
          {(mode === "login" || mode === "signup") && (
            <div className="grid grid-cols-2 gap-1 rounded-lg border border-slate-200 bg-slate-50 p-1 text-sm font-semibold" role="tablist">
              {(["login", "signup"] as const).map((m) => (
                <button key={m} role="tab" aria-selected={mode === m} className={`rounded-md py-2 transition ${mode === m ? "bg-white text-slate-900 shadow-md ring-1 ring-slate-200" : "text-slate-500 hover:text-slate-800"}`} onClick={() => { setMode(m); setErr(null); }}>
                  {m === "login" ? "Log in" : "Create account"}</button>
              ))}
            </div>
          )}

          {mode === "login" && (
            <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); run("login", () => authPost<Authed>("/api/auth/login", { login: f.login, password: f.password }), done); }}>
              <Field label="Email or username" value={f.login} onChange={set("login")} autoComplete="username" />
              <Field label="Password" type="password" value={f.password} onChange={set("password")} autoComplete="current-password" />
              <LoadingButton type="submit" className="btn-primary w-full" loading={busy === "login"} loadingText="Logging in…" disabled={!f.login || !f.password}>Log in</LoadingButton>
              <button type="button" className="text-sm font-semibold text-brand-700" onClick={() => { setMode("forgot"); setErr(null); }}>Forgot password?</button>
            </form>
          )}

          {mode === "signup" && (
            <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); run("signup", () => authPost<{ pending_id: string; demo_inbox: DemoMail }>("/api/auth/signup",
              { name: f.name, username: f.username, email: f.email, password: f.password }), (r) => { setPending(r.pending_id); setMail(r.demo_inbox); setMode("verify"); }); }}>
              <Field label="Your name" value={f.name} onChange={set("name")} autoComplete="name" />
              <Field label="Username" value={f.username} onChange={set("username")} placeholder="3 to 30 letters or numbers" autoComplete="username" />
              <Field label="Email" type="email" value={f.email} onChange={set("email")} autoComplete="email" />
              <Field label="Password" type="password" value={f.password} onChange={set("password")} placeholder="8+ characters, letters and a number" autoComplete="new-password" />
              <LoadingButton type="submit" className="btn-primary w-full" loading={busy === "signup"} loadingText="Sending the code…" disabled={!f.name || !f.username || !f.email || !f.password}>
                <Mail className="h-4 w-4" /> Send me a verification code</LoadingButton>
            </form>
          )}

          {mode === "verify" && (
            <div className="space-y-3">
              <h2 className="text-xl font-semibold text-slate-900">Check your email</h2>
              <p className="text-sm text-slate-600">We "sent" a 6-digit code to <b>{f.email}</b>. In this demo it appears below instead of in your mailbox.</p>
              <DemoInbox mail={mail} />
              <Field label="6-digit code" value={f.code} onChange={set("code")} autoComplete="one-time-code" />
              <LoadingButton className="btn-primary w-full" loading={busy === "verify"} loadingText="Checking…" disabled={f.code.trim().length !== 6}
                onClick={() => run("verify", () => authPost<Authed>("/api/auth/verify", { pending_id: pending, code: f.code }), done)}>
                <BadgeCheck className="h-4 w-4" /> Verify and create my account</LoadingButton>
              <button className="text-sm font-semibold text-brand-700" disabled={!!busy}
                onClick={() => run("resend", () => authPost<{ pending_id: string; demo_inbox: DemoMail }>("/api/auth/resend", { pending_id: pending }),
                  (r) => { setPending(r.pending_id); setMail(r.demo_inbox); setInfo("A new code was sent."); })}>Send a new code</button>
            </div>
          )}

          {mode === "forgot" && (
            <div className="space-y-3">
              <h2 className="text-xl font-semibold text-slate-900">Reset your password</h2>
              <Field label="Your account email" type="email" value={f.email} onChange={set("email")} autoComplete="email" />
              <LoadingButton className="btn-primary w-full" loading={busy === "forgot"} loadingText="Sending…" disabled={!f.email}
                onClick={() => run("forgot", () => authPost<{ pending_id: string; demo_inbox: DemoMail | null; message: string }>("/api/auth/forgot", { email: f.email }),
                  (r) => { setPending(r.pending_id); setMail(r.demo_inbox); setInfo(r.message); setMode("reset"); })}>Send me a reset code</LoadingButton>
              <button className="text-sm font-semibold text-slate-500" onClick={() => setMode("login")}>Back to log in</button>
            </div>
          )}

          {mode === "reset" && (
            <div className="space-y-3">
              <h2 className="text-xl font-semibold text-slate-900">Choose a new password</h2>
              <DemoInbox mail={mail} />
              <Field label="6-digit code" value={f.code} onChange={set("code")} autoComplete="one-time-code" />
              <Field label="New password" type="password" value={f.newPassword} onChange={set("newPassword")} autoComplete="new-password" />
              <LoadingButton className="btn-primary w-full" loading={busy === "reset"} loadingText="Saving…" disabled={f.code.trim().length !== 6 || !f.newPassword}
                onClick={() => run("reset", () => authPost<Authed>("/api/auth/reset", { pending_id: pending, code: f.code, new_password: f.newPassword }), done)}>
                Save and log in</LoadingButton>
              <button className="text-sm font-semibold text-slate-500" onClick={() => setMode("login")}>Back to log in</button>
            </div>
          )}

          {info && <Callout tone="info">{info}</Callout>}
          {err && <Callout tone="critical">{err}</Callout>}

          <div className="flex items-center gap-3 text-xs text-slate-400"><span className="h-px flex-1 bg-slate-200" />or<span className="h-px flex-1 bg-slate-200" /></div>
          <LoadingButton className="btn-secondary w-full" loading={busy === "demo"} loadingText="Opening the demo…"
            onClick={() => run("demo", () => authPost<Authed>("/api/auth/demo"), done)}>
            <PlayCircle className="h-4 w-4" /> Try the demo account (no sign-up)</LoadingButton>
        </div>
      </div>
    </div>
  );
}

/** Profile: details, change password, forgot password (code via demo inbox), log out. */
export function ProfileModal({ user, onClose, onUser, onLogout }: {
  user: User; onClose: () => void; onUser: (u: User) => void; onLogout: () => void;
}) {
  const [p, setP] = useState({ name: user.name, business: user.business, company_email: user.company_email, role: user.role, currency: user.currency });
  const [pw, setPw] = useState({ old: "", next: "" });
  const [reset, setReset] = useState<{ pending: string; mail: DemoMail | null; code: string; next: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ tone: "success" | "critical"; text: string } | null>(null);

  async function run<T>(label: string, fn: () => Promise<T>, then: (r: T) => void, ok?: string) {
    setBusy(label); setMsg(null);
    try { then(await fn()); if (ok) setMsg({ tone: "success", text: ok }); } catch (e) { setMsg({ tone: "critical", text: (e as Error).message }); } finally { setBusy(null); }
  }
  const initials = user.name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();

  return (
    <div role="dialog" aria-modal="true" className="fixed inset-0 z-40 grid place-items-center bg-ink-950/45 p-3 sm:p-4">
      <div className="max-h-[92vh] w-full max-w-2xl overflow-y-auto rounded-3xl border border-slate-200 bg-white shadow-2xl">
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 p-5 sm:p-6">
          <div className="flex items-center gap-4">
            <div className="grid h-14 w-14 shrink-0 place-items-center rounded-full bg-brand-100 text-lg font-bold text-brand-800">{initials || <UserRound />}</div>
            <div>
              <div className="flex flex-wrap items-center gap-2 font-serif text-xl font-semibold text-slate-900">{user.name}{user.demo && <Pill tone="amber">Demo account</Pill>}</div>
              <div className="text-sm text-slate-500">@{user.username} · {user.email} {user.verified && <BadgeCheck className="inline h-4 w-4 text-emerald-600" />}</div>
              <div className="text-xs text-slate-400">Member since {user.member_since}</div>
            </div>
          </div>
          <button className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700" aria-label="Close" onClick={onClose}><X className="h-5 w-5" /></button>
        </div>

        <div className="space-y-6 p-6">
          {msg && <Callout tone={msg.tone}>{msg.text}</Callout>}
          <section className="space-y-3">
            <h3 className="text-lg font-semibold text-slate-900">Your details</h3>
            <Field label="Name" value={p.name} onChange={(v) => setP({ ...p, name: v })} />
          </section>

          <section className="space-y-3 border-t border-slate-200 pt-5">
            <h3 className="flex items-center gap-2 text-lg font-semibold text-slate-900"><Building2 className="h-4 w-4 text-brand-600" /> Your company</h3>
            <p className="text-xs text-slate-500">SolvOrder uses this to know which side of a deal you are on, who to notify after you approve a plan, and which currency to show.</p>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Company name" value={p.business} onChange={(v) => setP({ ...p, business: v })} placeholder="Acme Trading Co." />
              <Field label="Company email" type="email" value={p.company_email} onChange={(v) => setP({ ...p, company_email: v })} placeholder="accounts@yourcompany.com" />
            </div>
            <div>
              <span className="label">In my deals I am usually the…</span>
              <div className="mt-1 grid gap-2 sm:grid-cols-2">
                {([["seller", "Seller (supplier)", "Customers send me orders; I buy what I need and deliver. I notify my customer."],
                   ["buyer", "Buyer (customer)", "Suppliers send me quotes; I pay them for goods I use or resell. I notify my supplier."]] as [Role, string, string][]).map(([r, t, d]) => (
                  <button key={r} type="button" onClick={() => setP({ ...p, role: r })}
                    aria-pressed={p.role === r} className={`rounded-lg border p-3 text-left transition ${p.role === r ? "border-brand-500 bg-brand-50 ring-1 ring-brand-500" : "border-slate-300 hover:border-slate-400"}`}>
                    <div className="text-sm font-bold text-slate-900">{t}</div>
                    <div className="text-xs text-slate-500">{d}</div>
                  </button>
                ))}
              </div>
              <p className="mt-1 text-xs text-slate-500">You can change this any time. For uploaded or typed orders SolvOrder also checks your company name and email against the documents and asks you if they say otherwise.</p>
            </div>
            <label className="block">
              <span className="label">Currency my business runs in</span>
              <select className="input mt-1" value={p.currency} onChange={(e) => setP({ ...p, currency: e.target.value })}>
                {CURRENCIES.map((c) => <option key={c.code} value={c.code}>{c.symbol} {c.code} · {c.name}</option>)}
              </select>
              <span className="mt-1 block text-xs text-slate-500">Every amount you type and see is in this currency. Documents in another currency are converted at the rate for the document's date; sample cases keep their own currency.</span>
            </label>
            <LoadingButton className="btn-primary" loading={busy === "profile"} loadingText="Saving…"
              onClick={() => run("profile", () => authPost<{ user: User }>("/api/auth/profile", p), (r) => onUser(r.user), "Profile saved.")}>Save profile</LoadingButton>
          </section>

          {!user.demo && (
            <section className="space-y-3 border-t border-slate-200 pt-5">
              <h3 className="text-lg font-semibold text-slate-900">Change password</h3>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Current password" type="password" value={pw.old} onChange={(v) => setPw({ ...pw, old: v })} autoComplete="current-password" />
                <Field label="New password" type="password" value={pw.next} onChange={(v) => setPw({ ...pw, next: v })} autoComplete="new-password" />
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <LoadingButton className="btn-primary" loading={busy === "pw"} loadingText="Saving…" disabled={!pw.old || !pw.next}
                  onClick={() => run("pw", () => authPost("/api/auth/password", { old_password: pw.old, new_password: pw.next }), () => setPw({ old: "", next: "" }), "Password changed.")}>Change password</LoadingButton>
                <button className="text-sm font-semibold text-brand-700" disabled={!!busy}
                  onClick={() => run("forgot", () => authPost<{ pending_id: string; demo_inbox: DemoMail | null }>("/api/auth/forgot", { email: user.email }),
                    (r) => setReset({ pending: r.pending_id, mail: r.demo_inbox, code: "", next: "" }))}>Forgot password?</button>
              </div>
              {reset && (
                <div className="space-y-3 rounded-lg border border-slate-200 p-4">
                  <DemoInbox mail={reset.mail} />
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Field label="6-digit code" value={reset.code} onChange={(v) => setReset({ ...reset, code: v })} autoComplete="one-time-code" />
                    <Field label="New password" type="password" value={reset.next} onChange={(v) => setReset({ ...reset, next: v })} autoComplete="new-password" />
                  </div>
                  <LoadingButton className="btn-primary" loading={busy === "reset"} loadingText="Saving…" disabled={reset.code.length !== 6 || !reset.next}
                    onClick={() => run("reset", () => authPost<{ token: string; user: User }>("/api/auth/reset", { pending_id: reset.pending, code: reset.code, new_password: reset.next }),
                      (r) => { setToken(r.token); onUser(r.user); setReset(null); }, "Password reset. Other sessions were logged out.")}>Reset password</LoadingButton>
                </div>
              )}
            </section>
          )}

          <section className="flex flex-col gap-3 border-t border-slate-200 pt-5 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs text-slate-500">Demo login: accounts live in server memory and are cleared when the server restarts.</p>
            <button className="btn-secondary text-rose-700" onClick={onLogout}><LogOut className="h-4 w-4" /> Log out</button>
          </section>
        </div>
      </div>
    </div>
  );
}
