export function ControlBar({
  email,
  onHome,
  onCreate,
  onLogs,
  onLogout,
}: {
  email: string;
  onHome: () => void;
  onCreate: () => void;
  onLogs: () => void;
  onLogout: () => void;
}) {
  return (
    <header className="sticky top-0 z-10 border-b border-line bg-canvas/85 backdrop-blur">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-5 gap-y-3 px-4 py-3 sm:px-6">
        <button className="flex items-center gap-2.5" onClick={onHome}>
          <span className="grid h-7 w-7 place-items-center rounded-lg bg-ink">
            <span className="num text-[13px] font-bold text-white">100</span>
          </span>
          <span className="font-display text-[15px] font-semibold tracking-tight text-ink">
            AI Simulation Maker
          </span>
        </button>

        <nav className="flex items-center gap-1 text-sm">
          <button className="rounded-lg px-2.5 py-1.5 font-medium text-muted hover:text-ink" onClick={onHome}>
            Simulations
          </button>
          <button className="rounded-lg px-2.5 py-1.5 font-medium text-muted hover:text-ink" onClick={onLogs}>
            API Logs
          </button>
        </nav>

        <div className="ml-auto flex items-center gap-3">
          <button className="btn-primary h-9 px-3 text-sm" onClick={onCreate}>
            + New simulation
          </button>
          <div className="flex items-center gap-2">
            <span className="hidden text-xs text-muted sm:inline" title={email}>
              {email}
            </span>
            <button className="btn-ghost h-9 px-3 text-sm" onClick={onLogout}>
              Log out
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
