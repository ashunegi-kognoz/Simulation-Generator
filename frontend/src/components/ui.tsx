import type { ReactNode } from "react";
import type { SimulationStatus } from "../api/types";
import { cn } from "../lib/cn";

export function Panel({
  eyebrow,
  title,
  right,
  children,
  className,
}: {
  eyebrow?: string;
  title?: string;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("panel p-5 sm:p-6", className)}>
      {(eyebrow || title || right) && (
        <header className="mb-4 flex items-start justify-between gap-4">
          <div>
            {eyebrow && <div className="eyebrow mb-1">{eyebrow}</div>}
            {title && <h2 className="font-display text-lg text-ink">{title}</h2>}
          </div>
          {right}
        </header>
      )}
      {children}
    </section>
  );
}

const STATUS_STYLES: Record<SimulationStatus, string> = {
  queued: "bg-canvas text-muted",
  generating: "bg-petrol-soft text-petrol",
  needs_review: "bg-amber-soft text-amber",
  ready: "bg-grass-soft text-grass",
  failed: "bg-coral-soft text-coral",
};

const STATUS_LABEL: Record<SimulationStatus, string> = {
  queued: "Queued",
  generating: "Generating",
  needs_review: "Needs review",
  ready: "Ready",
  failed: "Failed",
};

export function StatusBadge({ status }: { status: SimulationStatus }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium",
        STATUS_STYLES[status],
      )}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current opacity-70" />
      {STATUS_LABEL[status]}
    </span>
  );
}

export function Banner({
  tone = "info",
  title,
  children,
}: {
  tone?: "info" | "warn" | "error" | "empty";
  title?: string;
  children?: ReactNode;
}) {
  const styles = {
    info: "border-line bg-canvas text-muted",
    warn: "border-amber/30 bg-amber-soft text-[#7a4e06]",
    error: "border-coral/30 bg-coral-soft text-[#7a2722]",
    empty: "border-dashed border-line bg-panel text-muted",
  }[tone];
  return (
    <div className={cn("rounded-xl border px-4 py-3 text-sm", styles)}>
      {title && <div className="font-medium text-ink">{title}</div>}
      {children && <div className={title ? "mt-0.5" : ""}>{children}</div>}
    </div>
  );
}

export function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-xl border border-line bg-canvas px-3 py-2.5">
      <div className="eyebrow">{label}</div>
      <div className="num mt-1 text-base text-ink">{value}</div>
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-muted">
      <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-line border-t-petrol" />
      {label}
    </div>
  );
}
