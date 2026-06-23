import { useEffect, useState } from "react";
import { ControlBar } from "./components/ControlBar";
import type { AuthResponse } from "./api/types";
import { AuthoringConsole } from "./pages/AuthoringConsole";
import { Dashboard } from "./pages/Dashboard";
import { Login } from "./pages/Login";
import { LogsPage } from "./pages/LogsPage";
import { SimulationDetail } from "./pages/SimulationDetail";

export type View = "dashboard" | "create" | "detail" | "logs";

const AUTH_KEY = "allocation-room.auth";

type Auth = { token: string; email: string };

function loadAuth(): Auth | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(AUTH_KEY);
    return raw ? (JSON.parse(raw) as Auth) : null;
  } catch {
    return null;
  }
}

export default function App() {
  const [auth, setAuth] = useState<Auth | null>(loadAuth);
  const [view, setView] = useState<View>("dashboard");
  const [detailId, setDetailId] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (auth) window.localStorage.setItem(AUTH_KEY, JSON.stringify(auth));
    else window.localStorage.removeItem(AUTH_KEY);
  }, [auth]);

  function onAuthed(res: AuthResponse) {
    setAuth({ token: res.access_token, email: res.email });
    setView("dashboard");
  }

  function logout() {
    setAuth(null);
    setDetailId(null);
    setView("dashboard");
  }

  function openDetail(id: string) {
    setDetailId(id);
    setView("detail");
  }

  if (!auth) return <Login onAuthed={onAuthed} />;

  return (
    <div className="min-h-screen">
      <ControlBar
        email={auth.email}
        onHome={() => setView("dashboard")}
        onCreate={() => setView("create")}
        onLogs={() => setView("logs")}
        onLogout={logout}
      />

      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
        {view === "dashboard" && (
          <Dashboard token={auth.token} onOpen={openDetail} onCreate={() => setView("create")} />
        )}
        {view === "create" && (
          <AuthoringConsole
            token={auth.token}
            onOpenDetail={openDetail}
            onBack={() => setView("dashboard")}
          />
        )}
        {view === "logs" && <LogsPage token={auth.token} />}
        {view === "detail" && detailId && (
          <SimulationDetail
            simulationId={detailId}
            token={auth.token}
            onBack={() => setView("dashboard")}
          />
        )}
      </main>

      <footer className="mx-auto max-w-6xl px-4 pb-10 sm:px-6">
        <p className="text-xs text-faint">
          AI Simulation Maker · runs fully offline with the mock provider · stances stay hidden from
          participants until debrief.
        </p>
      </footer>
    </div>
  );
}
