const base = "/api";
let accessToken = sessionStorage.getItem("opspulse.access_token") || "";
export function setAccessToken(token: string) {
  accessToken = token;
  if (token) sessionStorage.setItem("opspulse.access_token", token);
  else sessionStorage.removeItem("opspulse.access_token");
}
export function hasAccessToken() { return Boolean(accessToken); }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json", ...(init?.headers as Record<string, string> || {}) };
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  const response = await fetch(`${base}${path}`, { ...init, headers });
  const data = await response.json().catch(() => ({ message: response.statusText }));
  if (!response.ok) {
    if (response.status === 401 && path !== "/auth/login" && path !== "/auth/register") setAccessToken("");
    const detail = typeof data.detail === "string" ? data.detail : data.detail?.message;
    throw new Error(detail || data.message || `Request failed (${response.status})`);
  }
  return data as T;
}

export const api = {
  login: (body: { email: string; password: string }) => request<{ access_token: string; user: { email: string; display_name: string; role: string } }>("/auth/login", { method: "POST", body: JSON.stringify(body) }),
  register: (body: { email: string; password: string; display_name: string; organization_name?: string }) => request<any>("/auth/register", { method: "POST", body: JSON.stringify(body) }),
  incidents: () => request<any[]>("/incidents/"),
  incident: (id: string) => request<any>(`/incidents/${encodeURIComponent(id)}`),
  acknowledgeIncident: (id: string, state_message: string) => request<any>(`/incidents/${encodeURIComponent(id)}/acknowledge`, { method: "POST", body: JSON.stringify({ state_message }) }),
  resolveIncident: (id: string, state_message: string) => request<any>(`/incidents/${encodeURIComponent(id)}/resolve`, { method: "POST", body: JSON.stringify({ state_message }) }),
  teams: () => request<any[]>("/teams/teams"),
  createTeam: (body: { name: string; description: string }) => request<any>("/teams/teams", { method: "POST", body: JSON.stringify(body) }),
  routingKeys: () => request<any[]>("/routing-keys/routing-keys"),
  createRoutingKey: (body: { team_id: number; name: string; warnings_enabled: boolean }) => request<any>("/routing-keys/routing-keys", { method: "POST", body: JSON.stringify(body) }),
  schedules: () => request<any[]>("/on-call/on-call"),
  saveSchedule: (body: any) => request<any>("/on-call/on-call", { method: "POST", body: JSON.stringify(body) }),
  policies: () => request<any[]>("/escalation/escalation"),
  savePolicy: (body: any) => request<any>("/escalation/escalation", { method: "POST", body: JSON.stringify(body) }),
};
