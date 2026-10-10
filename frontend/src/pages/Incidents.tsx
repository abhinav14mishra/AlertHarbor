import React, { useEffect, useState } from "react";
import { api } from "../services/api";

type Incident = { incident_id: string; entity_id: string; entity_display_name: string; state_message: string; message_type: string; status: string; created_at: string };
type Detail = Incident & { annotations: Record<string, unknown>; timeline: { type: string; actor: string; message: string; details: Record<string, unknown>; created_at: string }[] };
export default function Incidents() {
  const [rows, setRows] = useState<Incident[]>([]);
  const [selected, setSelected] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function load() { try { setRows(await api.incidents()); setError(""); } catch (e: any) { setError(e.message); } }
  useEffect(() => { load(); }, []);
  async function openDetail(id: string) { try { setSelected(await api.incident(id)); setError(""); } catch (e: any) { setError(e.message); } }
  async function action(kind: "acknowledge" | "resolve") {
    if (!selected) return;
    setBusy(true);
    try {
      await (kind === "acknowledge" ? api.acknowledgeIncident(selected.incident_id, "Acknowledged from OpsPulse UI") : api.resolveIncident(selected.incident_id, "Resolved from OpsPulse UI"));
      await load(); await openDetail(selected.incident_id);
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  }
  return <>
    <div className="panel"><div className="panel-head"><h3>Incident history</h3><span>Latest 1,000 records · Select an incident for its timeline</span></div>
      {error && <p className="error">{error}</p>}
      {rows.length === 0 ? <div className="empty">No incidents found.</div> : <div className="table-wrap"><table><thead><tr><th>Service / entity</th><th>Message</th><th>Type</th><th>Status</th><th>Created</th></tr></thead><tbody>{rows.map(i => <tr key={i.incident_id} className="clickable-row" onClick={() => openDetail(i.incident_id)}><td><b>{i.entity_display_name || i.entity_id}</b><small>{i.entity_id}</small></td><td>{i.state_message}</td><td>{i.message_type}</td><td><span className={`status ${i.status}`}>{i.status}</span></td><td>{new Date(i.created_at).toLocaleString()}</td></tr>)}</tbody></table></div>}
    </div>
    {selected && <div className="panel"><div className="panel-head"><div><h3>{selected.entity_display_name || selected.entity_id}</h3><span>{selected.incident_id} · {selected.status}</span></div><div className="action-buttons"><button disabled={busy || selected.status !== "open"} onClick={() => action("acknowledge")}>Acknowledge</button><button className="secondary" disabled={busy || selected.status === "resolved"} onClick={() => action("resolve")}>Resolve</button><button className="secondary" onClick={() => setSelected(null)}>Close</button></div></div><div className="detail-summary"><b>{selected.state_message || "No state message"}</b><small>Entity ID: {selected.entity_id} · Type: {selected.message_type}</small></div><div className="panel-head"><h3>Incident timeline</h3><span>Append-only event history</span></div>{selected.timeline.length === 0 ? <div className="empty">No timeline events.</div> : <div className="timeline">{selected.timeline.map((event, index) => <div className="timeline-event" key={`${event.created_at}-${index}`}><i/><div><b>{event.type}</b><p>{event.message || "No message"}</p><small>{event.actor || "system"} · {new Date(event.created_at).toLocaleString()}</small></div></div>)}</div>}
    </div>}
  </>;
}
