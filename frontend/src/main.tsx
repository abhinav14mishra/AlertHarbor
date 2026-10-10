import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import Layout, { Page } from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import Incidents from "./pages/Incidents";
import Teams from "./pages/Teams";
import OnCall from "./pages/OnCall";
import Auth from "./pages/Auth";
import { hasAccessToken, setAccessToken } from "./services/api";
import "./styles.css";

type User = { email: string; display_name: string; role: string };
function App() {
  const [page, setPage] = useState<Page>("Dashboard");
  const [authenticated, setAuthenticated] = useState(hasAccessToken());
  const [user, setUser] = useState<User | null>(null);
  if (!authenticated) return <Auth onAuthenticated={u => { setUser(u); setAuthenticated(true); }} />;
  return <Layout page={page} setPage={setPage} user={user} onLogout={() => { setAccessToken(""); setAuthenticated(false); setUser(null); }}>
    {page === "Dashboard" ? <Dashboard /> : page === "Incidents" ? <Incidents /> : page === "Teams" ? <Teams /> : <OnCall />}
  </Layout>;
}
createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
