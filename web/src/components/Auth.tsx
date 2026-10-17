import { useState } from "react";
import { BadgeCheck, CircleCheck, Inbox, KeyRound, LogOut, Mail, PlayCircle, ShieldCheck, Sparkles, UserRound, X } from "lucide-react";
import { authPost, setToken, type DemoMail, type User } from "../api";
import { Callout, LoadingButton, Pill } from "./ui";

type Authed = { token: string; user: User };

/** Where the "emailed" code lands in this demo. Nothing is really sent. */
export function DemoInbox({ mail }: { mail: DemoMail | null }) {
  if (!mail) return null;
  return (
    <div className="rounded-2xl border border-violet-200 bg-violet-50 p-4 text-sm">
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
      <input className="input mt-1" type={type} value={value} placeholder={placeholder} autoComplete={autoComplete} onChange={(e) => onChange(e.target.value)} /></label>
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
      <div className="hidden flex-col justify-between bg-gradient-to-br from-ink-950 via-ink-900 to-brand-700 p-12 text-white lg:flex">
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-xl bg-brand-600 shadow-lg"><CircleCheck className="h-6 w-6" /></div>
          <div><div className="text-xl font-extrabold">SolvOrder</div><div className="text-xs text-teal-200">Can my cash carry this order?</div></div>
        </div>
        <div>
          <h1 className="text-4xl font-extrabold leading-tight">Say yes to big orders,<br />without running out of cash.</h1>
          <ul className="mt-6 space-y-3 text-sm text-slate-200">
            <li className="flex gap-2"><ShieldCheck className="h-5 w-5 text-teal-300" /> Day-by-day cash risk, fraud checks and the safest plan</li>
            <li className="flex gap-2"><Sparkles className="h-5 w-5 text-teal-300" /> Google Gemini reads your documents; a deterministic engine checks every number</li>
            <li className="flex gap-2"><KeyRound className="h-5 w-5 text-teal-300" /> Nothing moves without your approval, and everything runs in a sandbox</li>
          </ul>
        </div>
        <p className="text-xs text-slate-400">Demo login for the Google Cloud AI Builder Cup. Accounts live in server memory; codes go to an on-screen demo inbox.</p>
      </div>

      <div className="flex items-center justify-center bg-slate-50 p-6">
        <div className="w-full max-w-md space-y-5 rounded-3xl bg-white p-8 shadow-xl">
          {(mode === "login" || mode === "signup") && (
            <div className="grid grid-cols-2 gap-1 rounded-xl bg-slate-100 p-1 text-sm font-semibold">
              {(["login", "signup"] as const).map((m) => (
                <button key={m} className={`rounded-lg py-2 ${mode === m ? "bg-white shadow-sm" : "text-slate-500"}`} onClick={() => { setMode(m); setErr(null); }}>
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
              <Field label="Username" value={f.username} onChange={set("username")} placeholder="3-30 letters or numbers" autoComplete="username" />
              <Field label="Email" type="email" value={f.email} onChange={set("email")} autoComplete="email" />
              <Field label="Password" type="password" value={f.password} onChange={set("password")} placeholder="8+ characters, letters and a number" autoComplete="new-password" />
              <LoadingButton type="submit" className="btn-primary w-full" loading={busy === "signup"} loadingText="Sending the code…" disabled={!f.name || !f.username || !f.email || !f.password}>
                <Mail className="h-4 w-4" /> Send me a verification code</LoadingButton>
            </form>
          )}

          {mode === "verify" && (
            <div className="space-y-3">
              <h2 className="text-lg font-bold">Verify your email</h2>
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
              <h2 className="text-lg font-bold">Reset your password</h2>
              <Field label="Your account email" type="email" value={f.email} onChange={set("email")} autoComplete="email" />
              <LoadingButton className="btn-primary w-full" loading={busy === "forgot"} loadingText="Sending…" disabled={!f.email}
                onClick={() => run("forgot", () => authPost<{ pending_id: string; demo_inbox: DemoMail | null; message: string }>("/api/auth/forgot", { email: f.email }),
                  (r) => { setPending(r.pending_id); setMail(r.demo_inbox); setInfo(r.message); setMode("reset"); })}>Send me a reset code</LoadingButton>
              <button className="text-sm font-semibold text-slate-500" onClick={() => setMode("login")}>Back to log in</button>
            </div>
          )}

          {mode === "reset" && (
            <div className="space-y-3">
              <h2 className="text-lg font-bold">Choose a new password</h2>
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

          <div className="relative py-1 text-center text-xs text-slate-400"><span className="bg-white px-2">or</span><div className="absolute inset-x-0 top-1/2 -z-10 border-t border-slate-200" /></div>
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
  const [p, setP] = useState({ name: user.name, business: user.business });
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
    <div role="dialog" aria-modal="true" className="fixed inset-0 z-40 grid place-items-center bg-ink-950/50 p-4 backdrop-blur-sm">
      <div className="max-h-[92vh] w-full max-w-2xl overflow-y-auto rounded-3xl bg-white shadow-2xl">
        <div className="flex items-start justify-between gap-4 border-b border-slate-100 p-6">
          <div className="flex items-center gap-4">
            <div className="grid h-14 w-14 place-items-center rounded-2xl bg-brand-600 text-lg font-bold text-white">{initials || <UserRound />}</div>
            <div>
              <div className="flex items-center gap-2 text-lg font-bold text-slate-900">{user.name}{user.demo && <Pill tone="amber">Demo account</Pill>}</div>
              <div className="text-sm text-slate-500">@{user.username} · {user.email} {user.verified && <BadgeCheck className="inline h-4 w-4 text-emerald-600" />}</div>
              <div className="text-xs text-slate-400">Member since {user.member_since}</div>
            </div>
          </div>
          <button className="text-slate-400 hover:text-slate-700" aria-label="Close" onClick={onClose}><X className="h-5 w-5" /></button>
        </div>

        <div className="space-y-6 p-6">
          {msg && <Callout tone={msg.tone}>{msg.text}</Callout>}
          <section className="space-y-3">
            <h3 className="font-bold">Your details</h3>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Name" value={p.name} onChange={(v) => setP({ ...p, name: v })} />
              <Field label="Business name" value={p.business} onChange={(v) => setP({ ...p, business: v })} placeholder="Acme Trading Co." />
            </div>
            <LoadingButton className="btn-primary" loading={busy === "profile"} loadingText="Saving…"
              onClick={() => run("profile", () => authPost<{ user: User }>("/api/auth/profile", p), (r) => onUser(r.user), "Profile saved.")}>Save details</LoadingButton>
          </section>

          {!user.demo && (
            <section className="space-y-3 border-t border-slate-100 pt-5">
              <h3 className="font-bold">Change password</h3>
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
                <div className="space-y-3 rounded-2xl border border-slate-200 p-4">
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

          <section className="flex items-center justify-between border-t border-slate-100 pt-5">
            <p className="text-xs text-slate-500">Demo login: accounts live in server memory and are cleared when the server restarts.</p>
            <button className="btn-danger" onClick={onLogout}><LogOut className="h-4 w-4" /> Log out</button>
          </section>
        </div>
      </div>
    </div>
  );
}
