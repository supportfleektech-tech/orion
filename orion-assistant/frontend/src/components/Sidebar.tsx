import { NavLink } from "react-router-dom";
import {
  Activity,
  Bot,
  Brain,
  ClipboardCheck,
  Cpu,
  Database,
  FlaskConical,
  GraduationCap,
  Home,
  Plug,
  Settings2,
  Shield,
  TerminalSquare,
} from "lucide-react";
import { motion } from "framer-motion";
import { api } from "../lib/api";
import { useAsync } from "../hooks/useApi";

const items = [
  ["/", "Command Center", Home],
  ["/chat", "Conversations", Bot],
  ["/memory", "Memory", Brain],
  ["/skills", "Skills", GraduationCap],
  ["/knowledge", "Knowledge", Database],
  ["/tools", "Tools", TerminalSquare],
  ["/mcp", "MCP servers", Plug],
  ["/automations", "Automations", Activity],
  ["/security", "Security", Shield],
  ["/observability", "Observability", FlaskConical],
  ["/evaluation", "Evaluation", ClipboardCheck],
  ["/models", "Models", Cpu],
  ["/settings", "Settings", Settings2],
] as const;

export function Sidebar() {
  const { data } = useAsync(() => api.status(), [], 20000);
  const online = Boolean(data && !data.degraded);

  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-orb">O</div>
        <div>
          <strong>ORION</strong>
          <span>AI OPERATING SYSTEM</span>
        </div>
      </div>

      <nav className="nav-group">
        {items.map(([to, label, Icon], index) => (
          <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
            {({ isActive }) => (
              <>
                {/* A single shared element: Framer slides it between routes
                    rather than fading one pill out and another in. */}
                {isActive && (
                  <motion.span
                    layoutId="nav-pill"
                    className="nav-pill"
                    transition={{ type: "spring", stiffness: 480, damping: 38 }}
                  />
                )}
                <motion.span
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.03 * index, duration: 0.3 }}
                  style={{ display: "contents" }}
                >
                  <Icon size={17} />
                  <span className="nav-label">{label}</span>
                </motion.span>
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="sidebar-footer">
        <span className={`status-dot ${data ? "" : "off"}`} style={data && !online ? { background: "var(--warn)" } : undefined} />
        <span>{data ? (online ? "Runtime online" : "Degraded mode") : "Connecting…"}</span>
      </div>
    </aside>
  );
}
