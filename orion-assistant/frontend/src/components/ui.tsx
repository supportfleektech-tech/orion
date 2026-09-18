import { ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";

export function PageTitle({ icon: Icon, title, subtitle, actions }: { icon: any; title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="page-title">
      <Icon size={20} />
      <div style={{ flex: 1 }}>
        <div className="eyebrow">{subtitle ?? "CONTROL PLANE"}</div>
        <h1>{title}</h1>
      </div>
      {actions}
    </div>
  );
}

export function Panel({ title, subtitle, right, children, className = "" }: { title?: string; subtitle?: string; right?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`panel ${className}`}>
      {(title || right) && (
        <div className="panel-head">
          <div>
            {subtitle && <div className="eyebrow">{subtitle}</div>}
            {title && <h2>{title}</h2>}
          </div>
          {right}
        </div>
      )}
      {children}
    </section>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="state-block">
      <Loader2 size={20} className="spin" />
      <span>{label}</span>
    </div>
  );
}

export function ErrorBlock({ message }: { message: string }) {
  return (
    <div className="state-block error">
      <AlertTriangle size={20} />
      <span>{message}</span>
    </div>
  );
}

export function EmptyBlock({ icon: Icon, title, hint }: { icon: any; title: string; hint?: string }) {
  return (
    <div className="state-block">
      <Icon size={26} />
      <strong>{title}</strong>
      {hint && <span>{hint}</span>}
    </div>
  );
}

export function Badge({ children, tone = "default" }: { children: ReactNode; tone?: "default" | "ok" | "warn" | "err" | "info" }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label?: string }) {
  return (
    <label className="toggle">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="track" />
      {label && <span className="toggle-label">{label}</span>}
    </label>
  );
}

export function Toast({ toast }: { toast: { kind: "ok" | "err"; text: string } | null }) {
  if (!toast) return null;
  return (
    <div className={`toast ${toast.kind}`}>
      {toast.kind === "ok" ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}
      <span>{toast.text}</span>
    </div>
  );
}

export function riskTone(risk: string) {
  return risk === "destructive" ? "err" : risk === "high" ? "warn" : risk === "medium" ? "info" : "ok";
}

export function timeAgo(iso?: string | null) {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export function bytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
