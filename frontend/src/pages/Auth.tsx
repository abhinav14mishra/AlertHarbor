import React, { useState } from "react";
import { api, setAccessToken } from "../services/api";

type Props = { onAuthenticated: (user: { email: string; display_name: string; role: string }) => void };
export default function Auth({ onAuthenticated }: Props) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [organizationName, setOrganizationName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setError(""); setBusy(true);
    try {
      if (mode === "register") await api.register({ email, password, display_name: name, organization_name: organizationName || undefined });
      const result = await api.login({ email, password });
      setAccessToken(result.access_token);
      onAuthenticated(result.user);
    } catch (err: any) { setError(err.message || "Unable to authenticate"); }
    finally { setBusy(false); }
  }
  return <div className="auth-shell"><form className="auth-card" onSubmit={submit}>
    <div className="brand auth-brand"><span className="brand-icon">O</span><div><b>OpsPulse</b><small>Incident operations</small></div></div>
    <h1>{mode === "login" ? "Welcome back" : "Create your workspace account"}</h1>
    <p className="muted">{mode === "login" ? "Sign in to manage incidents, teams and on-call rotations." : "The first account becomes administrator and creates the workspace."}</p>
    {mode === "register" && <label>Display name<input required maxLength={160} value={name} onChange={e => setName(e.target.value)} autoComplete="name" /></label>}
    {mode === "register" && <label>Workspace name<input maxLength={120} value={organizationName} onChange={e => setOrganizationName(e.target.value)} placeholder="Platform Engineering" /></label>}
    <label>Email address<input required type="email" maxLength={320} value={email} onChange={e => setEmail(e.target.value)} autoComplete="email" /></label>
    <label>Password<input required type="password" minLength={12} maxLength={256} value={password} onChange={e => setPassword(e.target.value)} autoComplete={mode === "login" ? "current-password" : "new-password"} /><small>Use at least 12 characters.</small></label>
    {error && <p className="error">{error}</p>}
    <button disabled={busy}>{busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}</button>
    <button type="button" className="secondary" onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}>{mode === "login" ? "Create first account" : "Back to sign in"}</button>
  </form></div>;
}
