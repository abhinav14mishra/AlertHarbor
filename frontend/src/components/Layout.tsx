import React from "react";
import { Activity, AlertTriangle, Users, CalendarClock, LogOut } from "lucide-react";
export type Page = "Dashboard" | "Incidents" | "Teams" | "OnCall";
type User = { email: string; display_name: string; role: string } | null;
export default function Layout({ page, setPage, children, user, onLogout }: { page: Page; setPage: (p: Page) => void; children: React.ReactNode; user: User; onLogout: () => void }) {
  const items: [Page, React.ReactNode][] = [["Dashboard", <Activity size={17} />], ["Incidents", <AlertTriangle size={17} />], ["Teams", <Users size={17} />], ["OnCall", <CalendarClock size={17} />]];
  return <div className="shell"><aside><div className="brand"><span className="brand-icon">O</span><div><b>OpsPulse</b><small>Incident operations</small></div></div><nav>{items.map(([name, icon]) => <button key={name} className={page === name ? "nav active" : "nav"} onClick={() => setPage(name)}>{icon}<span>{name === "OnCall" ? "On-call" : name}</span></button>)}</nav><div className="side-foot"><span>{user?.display_name || user?.email || "Signed in"}</span><button className="nav logout" onClick={onLogout}><LogOut size={16} /><span>Sign out</span></button></div></aside><main><header><div><small>INCIDENT RESPONSE</small><h1>{page === "OnCall" ? "On-call schedules" : page}</h1></div><span className="live"><i /> API workspace</span></header><section>{children}</section></main></div>;
}
