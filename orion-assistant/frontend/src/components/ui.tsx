import { useEffect, useRef, useState, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";
import { AnimatePresence, motion, useInView, useReducedMotion } from "framer-motion";
import { modalVariants, riseIn, scaleIn, spring, stagger } from "../lib/motion";

/* ------------------------------------------------------------------ layout */

export function PageTitle({
  icon: Icon,
  title,
  subtitle,
  actions,
}: {
  icon: any;
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <motion.div
      className="page-title"
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
    >
      <motion.span
        initial={{ scale: 0.6, opacity: 0, rotate: -12 }}
        animate={{ scale: 1, opacity: 1, rotate: 0 }}
        transition={{ ...spring, delay: 0.05 }}
        style={{ display: "grid", placeItems: "center" }}
      >
        <Icon size={20} />
      </motion.span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="eyebrow">{subtitle ?? "CONTROL PLANE"}</div>
        <h1>{title}</h1>
      </div>
      {actions && <div className="row-actions">{actions}</div>}
    </motion.div>
  );
}

/**
 * A surface.
 *
 * Panels animate in once, when scrolled into view, rather than on every
 * render — repeated animation on re-render is the fastest way to make a UI
 * feel cheap. `interactive` adds a cursor-following highlight.
 */
export function Panel({
  title,
  subtitle,
  right,
  children,
  className = "",
  interactive = false,
  delay = 0,
}: {
  title?: string;
  subtitle?: string;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
  interactive?: boolean;
  delay?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-40px" });
  const reduce = useReducedMotion();

  function spotlight(event: React.MouseEvent<HTMLElement>) {
    if (!interactive) return;
    const box = event.currentTarget.getBoundingClientRect();
    event.currentTarget.style.setProperty("--mx", `${event.clientX - box.left}px`);
    event.currentTarget.style.setProperty("--my", `${event.clientY - box.top}px`);
  }

  return (
    <motion.section
      ref={ref}
      className={`panel ${interactive ? "interactive" : ""} ${className}`}
      onMouseMove={spotlight}
      initial={reduce ? false : { opacity: 0, y: 14 }}
      animate={inView ? { opacity: 1, y: 0 } : undefined}
      transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1], delay }}
    >
      {(title || right) && (
        <div className="panel-head">
          <div style={{ minWidth: 0 }}>
            {subtitle && <div className="eyebrow">{subtitle}</div>}
            {title && <h2>{title}</h2>}
          </div>
          {right}
        </div>
      )}
      {children}
    </motion.section>
  );
}

/** Wrap a list to have its children rise in one after another. */
export function Stagger({
  children,
  delay = 0.04,
  className = "",
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
}) {
  return (
    <motion.div className={className} variants={stagger(delay)} initial="initial" animate="animate">
      {children}
    </motion.div>
  );
}

export function StaggerItem({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <motion.div variants={riseIn} className={className}>
      {children}
    </motion.div>
  );
}

/**
 * An animated list row.
 *
 * Rows enter staggered by position and leave sideways, so adding or deleting
 * an item reads as a change to a list rather than a repaint of one. `index`
 * is capped so a hundred-item list does not take four seconds to appear.
 */
export function Row({
  children,
  index = 0,
  className = "",
  onClick,
}: {
  children: ReactNode;
  index?: number;
  className?: string;
  onClick?: () => void;
}) {
  return (
    <motion.div
      layout
      className={`list-row ${className}`}
      onClick={onClick}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, x: -14, transition: { duration: 0.16 } }}
      transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1], delay: Math.min(index, 12) * 0.035 }}
    >
      {children}
    </motion.div>
  );
}

/* ------------------------------------------------------------------ states */

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <motion.div className="state-block" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      <Loader2 size={20} className="spin" />
      <span>{label}</span>
    </motion.div>
  );
}

/**
 * Skeleton placeholder.
 *
 * Preferable to a spinner when the shape of the incoming content is known:
 * the layout does not jump when data lands.
 */
export function Skeleton({
  lines = 3,
  height = 14,
}: {
  lines?: number;
  height?: number;
}) {
  return (
    <div style={{ display: "grid", gap: 10, padding: "6px 0" }}>
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className="skeleton"
          style={{ height, width: `${100 - (i % 3) * 14}%` }}
        />
      ))}
    </div>
  );
}

export function ErrorBlock({ message }: { message: string }) {
  return (
    <motion.div
      className="state-block error"
      initial={{ opacity: 0, scale: 0.97 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={spring}
    >
      <motion.span
        animate={{ rotate: [0, -8, 8, -5, 0] }}
        transition={{ duration: 0.5, delay: 0.1 }}
        style={{ display: "grid", placeItems: "center" }}
      >
        <AlertTriangle size={20} />
      </motion.span>
      <span>{message}</span>
    </motion.div>
  );
}

export function EmptyBlock({ icon: Icon, title, hint }: { icon: any; title: string; hint?: string }) {
  return (
    <motion.div className="state-block" variants={scaleIn} initial="initial" animate="animate">
      <motion.span
        animate={{ y: [0, -5, 0] }}
        transition={{ duration: 3.5, repeat: Infinity, ease: "easeInOut" }}
        style={{ display: "grid", placeItems: "center" }}
      >
        <Icon size={26} />
      </motion.span>
      <strong>{title}</strong>
      {hint && <span>{hint}</span>}
    </motion.div>
  );
}

/* ------------------------------------------------------------------ atoms */

export function Badge({
  children,
  tone = "default",
  pulse = false,
}: {
  children: ReactNode;
  tone?: "default" | "ok" | "warn" | "err" | "info";
  pulse?: boolean;
}) {
  return (
    <motion.span
      className={`badge ${tone}`}
      initial={{ opacity: 0, scale: 0.85 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={spring}
    >
      {pulse && (
        <motion.i
          style={{
            width: 5,
            height: 5,
            borderRadius: "50%",
            background: "currentColor",
            display: "block",
          }}
          animate={{ opacity: [1, 0.25, 1] }}
          transition={{ duration: 1.8, repeat: Infinity, ease: "easeInOut" }}
        />
      )}
      {children}
    </motion.span>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label?: string;
}) {
  return (
    <label className="toggle">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="track" />
      {label && <span className="toggle-label">{label}</span>}
    </label>
  );
}

/**
 * A number that counts to its value instead of snapping.
 *
 * Only worth it for figures the user watches change (metrics, totals); it
 * draws the eye to what moved.
 */
export function Counter({
  value,
  duration = 900,
  format = (n: number) => String(Math.round(n)),
}: {
  value: number;
  duration?: number;
  format?: (n: number) => string;
}) {
  const [display, setDisplay] = useState(value);
  const from = useRef(value);
  const reduce = useReducedMotion();

  useEffect(() => {
    if (reduce) {
      setDisplay(value);
      return;
    }
    const start = performance.now();
    const origin = from.current;
    const delta = value - origin;
    if (delta === 0) return;

    let frame = 0;
    const tick = (now: number) => {
      const t = Math.min((now - start) / duration, 1);
      // easeOutExpo: fast then settling, so the final value is readable early.
      const eased = t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
      setDisplay(origin + delta * eased);
      if (t < 1) frame = requestAnimationFrame(tick);
      else from.current = value;
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value, duration, reduce]);

  return <>{format(display)}</>;
}

/**
 * Sparkline: a tiny trend line, drawn as an SVG path that animates on first
 * paint. No axes or labels — it exists to show shape, not values.
 */
export function Sparkline({
  values,
  width = 220,
  height = 38,
}: {
  values: number[];
  width?: number;
  height?: number;
}) {
  const reduce = useReducedMotion();
  if (values.length < 2) return null;

  const max = Math.max(...values);
  const min = Math.min(...values);
  const span = max - min || 1;
  const stepX = width / (values.length - 1);
  const pad = 3;

  const points = values.map((value, i) => {
    const x = i * stepX;
    const y = height - pad - ((value - min) / span) * (height - pad * 2);
    return [x, y] as const;
  });

  const line = points.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const area = `${line} L${width},${height} L0,${height} Z`;
  const [lastX, lastY] = points[points.length - 1];

  return (
    <svg className="sparkline" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
      <defs>
        <linearGradient id="spark-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.28" />
          <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <motion.path
        d={area}
        fill="url(#spark-fill)"
        initial={reduce ? false : { opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.5, delay: 0.25 }}
      />
      <motion.path
        d={line}
        fill="none"
        stroke="var(--accent)"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        initial={reduce ? false : { pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
      />
      <motion.circle
        cx={lastX}
        cy={lastY}
        r="2.5"
        fill="var(--accent)"
        initial={reduce ? false : { scale: 0 }}
        animate={{ scale: 1 }}
        transition={{ delay: 0.75, type: "spring", stiffness: 500, damping: 20 }}
      />
    </svg>
  );
}

/**
 * Circular gauge for a 0–1 rate.
 *
 * The arc is drawn with strokeDasharray and animated via strokeDashoffset,
 * which is GPU-cheap and works without any charting dependency.
 */
export function Gauge({
  value,
  size = 62,
  stroke = 6,
  tone = "var(--accent)",
}: {
  value: number;
  size?: number;
  stroke?: number;
  tone?: string;
}) {
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.max(0, Math.min(1, value));

  return (
    <svg width={size} height={size} aria-hidden="true">
      <circle
        className="eval-gauge-track"
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        strokeWidth={stroke}
      />
      <motion.circle
        className="eval-gauge-value"
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke={tone}
        strokeWidth={stroke}
        strokeDasharray={circumference}
        initial={{ strokeDashoffset: circumference }}
        animate={{ strokeDashoffset: circumference * (1 - clamped) }}
        transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
        style={{ filter: `drop-shadow(0 0 6px ${tone})` }}
      />
    </svg>
  );
}

/** Determinate progress bar. */
export function Bar({ value }: { value: number }) {
  return (
    <div className="bar" role="progressbar" aria-valuenow={Math.round(value)} aria-valuemin={0} aria-valuemax={100}>
      <i style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
}

/* ----------------------------------------------------------------- overlays */

export function Toast({ toast }: { toast: { kind: "ok" | "err"; text: string } | null }) {
  return (
    <AnimatePresence>
      {toast && (
        <motion.div
          className={`toast ${toast.kind}`}
          initial={{ opacity: 0, y: 20, scale: 0.94 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 10, scale: 0.96 }}
          transition={spring}
          role="status"
          aria-live="polite"
        >
          {toast.kind === "ok" ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}
          <span>{toast.text}</span>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/**
 * Modal dialog. Closes on Escape and on backdrop click, traps nothing else —
 * deliberately minimal, since every dialog here is a short confirmation.
 */
export function Modal({
  open,
  onClose,
  title,
  children,
  width,
}: {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
  width?: number;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="modal-backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
          onClick={onClose}
        >
          <motion.div
            className="modal"
            style={width ? { width: `min(${width}px, 100%)` } : undefined}
            variants={modalVariants}
            initial="initial"
            animate="animate"
            exit="exit"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
          >
            {title && <h3>{title}</h3>}
            {children}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/* ---------------------------------------------------------------- helpers */

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
