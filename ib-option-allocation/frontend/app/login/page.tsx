"use client";
import { useState } from "react";
import { api, auth, errorText } from "@/lib/api";
import { ErrorBox } from "@/components/ui";

export default function LoginPage() {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await api("/api/auth/login", { body: { username, password } });
      auth.save(r.token, { username: r.username, role: r.role });
      window.location.href = "/";
    } catch (err) {
      setError(errorText(err));
      setBusy(false);
    }
  };

  const quick = (u: string, p: string) => { setUsername(u); setPassword(p); };

  return (
    <div className="fixed inset-0 grid lg:grid-cols-2 bg-white">
      <div className="hidden lg:flex flex-col justify-between bg-slate-900 text-white p-10 relative overflow-hidden">
        <div className="absolute -top-24 -right-24 w-96 h-96 rounded-full bg-indigo-600/30 blur-3xl" />
        <div className="absolute bottom-0 -left-24 w-96 h-96 rounded-full bg-violet-600/20 blur-3xl" />
        <div className="relative flex items-center gap-3">
          <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-indigo-400 to-violet-500 grid place-items-center font-bold text-lg">IB</div>
          <div className="font-semibold">IB Option Allocation Tool</div>
        </div>
        <div className="relative space-y-5 max-w-md">
          <h2 className="text-3xl font-bold leading-tight">Allocate options and test changes with confidence.</h2>
          <ul className="space-y-2.5 text-slate-300 text-sm">
            {[
              "Existing choices loaded; new students allocated from remaining seats only",
              "Instant verdicts: FEASIBLE · WAITLIST · NOT FEASIBLE · NEEDS OVERRIDE",
              "Block, HL/SL, group coverage, Maths, Science and Language rules enforced",
              "Admin override with a required reason and a full audit trail",
            ].map((t) => (
              <li key={t} className="flex gap-2.5"><span className="text-indigo-400 mt-0.5">✓</span><span>{t}</span></li>
            ))}
          </ul>
        </div>
        <div className="relative text-xs text-slate-500">Runs entirely on this machine · IGCSE (7-10) & IBDP (11-12)</div>
      </div>

      <div className="flex items-center justify-center p-6 bg-slate-50">
        <form onSubmit={submit} className="card w-full max-w-sm space-y-4">
          <div>
            <h1 className="text-xl font-bold text-slate-900">Sign in</h1>
            <p className="muted">Timetabler access</p>
          </div>
          <div>
            <label className="label">Username</label>
            <input className="input" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
          </div>
          <div>
            <label className="label">Password</label>
            <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
          </div>
          <ErrorBox error={error} />
          <button className="btn w-full" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
          <div className="pt-1 border-t border-slate-100">
            <div className="label">Demo accounts</div>
            <div className="flex gap-2">
              <button type="button" className="btn-secondary btn-xs" onClick={() => quick("admin", "admin123")}>admin / admin123</button>
              <button type="button" className="btn-secondary btn-xs" onClick={() => quick("viewer", "viewer123")}>viewer / viewer123</button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
