import { useState } from "react";
import { ApiError, api } from "../api/client";
import type { AuthResponse } from "../api/types";
import { Banner } from "../components/ui";

export function Login({ onAuthed }: { onAuthed: (auth: AuthResponse) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [workspace, setWorkspace] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const auth =
        mode === "login"
          ? await api.login(email, password)
          : await api.register(email, password, workspace || undefined);
      onAuthed(auth);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center justify-center gap-2.5">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-ink">
            <span className="num text-sm font-bold text-white">100</span>
          </span>
          <span className="font-display text-lg font-semibold tracking-tight text-ink">
            AI Simulation Maker
          </span>
        </div>

        <div className="panel p-6">
          <div className="eyebrow mb-1">{mode === "login" ? "Welcome back" : "Get started"}</div>
          <h1 className="font-display text-xl text-ink">
            {mode === "login" ? "Sign in" : "Create your workspace"}
          </h1>

          <div className="mt-5 space-y-4">
            <div>
              <label className="label">Email</label>
              <input
                className="input"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                onKeyDown={(e) => e.key === "Enter" && void submit()}
              />
            </div>
            <div>
              <label className="label">Password</label>
              <input
                className="input"
                type="password"
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={mode === "register" ? "at least 8 characters" : "••••••••"}
                onKeyDown={(e) => e.key === "Enter" && void submit()}
              />
            </div>
            {mode === "register" && (
              <div>
                <label className="label">Workspace name (optional)</label>
                <input
                  className="input"
                  value={workspace}
                  onChange={(e) => setWorkspace(e.target.value)}
                  placeholder="Acme executive simulations"
                  onKeyDown={(e) => e.key === "Enter" && void submit()}
                />
              </div>
            )}

            {error && <Banner tone="error">{error}</Banner>}

            <button className="btn-primary w-full" onClick={() => void submit()} disabled={busy}>
              {busy ? "Working…" : mode === "login" ? "Sign in" : "Create workspace"}
            </button>
          </div>

          {/* <div className="mt-4 text-center text-sm text-muted">
            {mode === "login" ? "No account yet?" : "Already have an account?"}{" "}
            <button
              className="font-medium text-petrol hover:text-petrol-hover"
              onClick={() => {
                setMode(mode === "login" ? "register" : "login");
                setError(null);
              }}
            >
              {mode === "login" ? "Create one" : "Sign in"}
            </button>
          </div> */}
        </div>
      </div>
    </div>
  );
}
