import React, { useEffect, useState } from "react";
import { api } from "../services/api";

type Team = { id: number; name: string };
type Schedule = { id: number; team_id: number; name: string; members: string[]; rotation_hours: number; enabled: boolean };
type Policy = { id: number; team_id: number; name: string; rules: { delay_minutes: number; recipients: string[] }[]; enabled: boolean };
export default function OnCall() {
  const [teams, setTeams] = useState<Team[]>([]);
  const [rows, setRows] = useState<Schedule[]>([]);
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [teamId, setTeamId] = useState("");
  const [name, setName] = useState("Primary rotation");
  const [members, setMembers] = useState("");
  const [hours, setHours] = useState(168);
  const [policyName, setPolicyName] = useState("Primary escalation");
  const [delayMinutes, setDelayMinutes] = useState(5);
  const [recipients, setRecipients] = useState("");
  const [error, setError] = useState("");
  async function load() {
    try {
      const [t, s, p] = await Promise.all([api.teams(), api.schedules(), api.policies()]);
      setTeams(t); setRows(s); setPolicies(p);
      if (!teamId && t[0]) setTeamId(String(t[0].id));
    } catch (e: any) { setError(e.message); }
  }
  useEffect(() => { load(); }, []);
  async function saveSchedule(e: React.FormEvent) {
    e.preventDefault(); setError("");
    try {
      await api.saveSchedule({ team_id: Number(teamId), name, members: members.split(",").map(s => s.trim().toLowerCase()).filter(Boolean), rotation_hours: hours, enabled: true });
      setMembers(""); await load();
    } catch (e: any) { setError(e.message); }
  }
  async function savePolicy(e: React.FormEvent) {
    e.preventDefault(); setError("");
    try {
      const targets = recipients.split(",").map(s => s.trim().toLowerCase()).filter(Boolean);
      await api.savePolicy({ team_id: Number(teamId), name: policyName, rules: targets.length ? [{ delay_minutes: delayMinutes, recipients: targets }] : [], enabled: true });
      setRecipients(""); await load();
    } catch (e: any) { setError(e.message); }
  }
  return <>
    <div className="columns">
      <div className="panel"><div className="panel-head"><h3>Team rotation</h3></div><p className="muted inset">Configure a repeating on-call member rotation. Use email addresses for notifications.</p><form className="form" onSubmit={saveSchedule}>
        <label>Team<select required value={teamId} onChange={e => setTeamId(e.target.value)}>{teams.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}</select></label>
        <label>Schedule name<input required maxLength={120} value={name} onChange={e => setName(e.target.value)} /></label>
        <label>Members (comma-separated emails)<input required value={members} onChange={e => setMembers(e.target.value)} placeholder="engineer@example.com, oncall@example.com" /></label>
        <label>Rotation duration (hours)<input type="number" min="1" max="8760" required value={hours} onChange={e => setHours(Number(e.target.value))} /></label>
        <button disabled={!teams.length}>Save schedule</button>
      </form></div>
      <div className="panel"><div className="panel-head"><h3>Escalation policy</h3></div><p className="muted inset">Send a follow-up notification if the incident remains unacknowledged after the delay.</p><form className="form" onSubmit={savePolicy}>
        <label>Team<select required value={teamId} onChange={e => setTeamId(e.target.value)}>{teams.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}</select></label>
        <label>Policy name<input required maxLength={120} value={policyName} onChange={e => setPolicyName(e.target.value)} /></label>
        <label>Delay (minutes)<input type="number" min="0" max="10080" required value={delayMinutes} onChange={e => setDelayMinutes(Number(e.target.value))} /></label>
        <label>Escalation recipients (comma-separated emails)<input value={recipients} onChange={e => setRecipients(e.target.value)} placeholder="lead@example.com, manager@example.com" /></label>
        <button disabled={!teams.length}>Save policy</button>
      </form></div>
      {error && <p className="error">{error}</p>}
    </div>
    <div className="panel"><div className="panel-head"><h3>Configured schedules</h3></div>{rows.length === 0 ? <div className="empty">No on-call schedules configured.</div> : rows.map(s => <div className="list-row inset" key={s.id}><b>{s.name}</b><small>{teams.find(t => t.id === s.team_id)?.name || `Team ${s.team_id}`} · Every {s.rotation_hours} hours</small><p>{(s.members || []).join(" → ")}</p></div>)}</div>
    <div className="panel"><div className="panel-head"><h3>Configured escalation policies</h3></div>{policies.length === 0 ? <div className="empty">No escalation policies configured.</div> : policies.map(p => <div className="list-row inset" key={p.id}><b>{p.name}</b><small>{teams.find(t => t.id === p.team_id)?.name || `Team ${p.team_id}`}</small>{(p.rules || []).map((r, i) => <p key={i}>After {r.delay_minutes} minutes → {(r.recipients || []).join(", ")}</p>)}</div>)}</div>
  </>;
}
