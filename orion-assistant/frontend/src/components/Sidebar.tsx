import { NavLink } from "react-router-dom";
import {
  Activity,
  Bot,
  Brain,
  Cpu,
  Database,
  FlaskConical,
  GraduationCap,
  Home,
  Settings2,
  Shield,
  TerminalSquare,
} from "lucide-react";
import { api } from "../lib/api";
import { useAsync } from "../hooks/useApi";

const items = [
  ["/", "Command Center", Home],
  ["/chat", "Conversations", Bot],
  ["/memory", "Memory", Brain],
  ["/skills", "Skills", GraduationCap],
  ["/knowledge", "Knowledge", Database],
  ["/tools", "Tools", TerminalSquare],
  ["/automations", "Automations", Activity],
  ["/security", "Security", Shield],
  ["/observability", "Observability", FlaskConical],
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
      <div className="nav-group">
        {items.map(([to, label, Icon]) => (
          <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
            <Icon size={17} />
            <span>{label}</span>
          </NavLink>
        ))}
      </div>
      <div className="sidebar-footer">
        <div className="status-dot" style={{ background: data ? (online ? "#5ee2a1" : "#ffb454") : "#6b7484" }} />
        <span>{data ? (online ? "Runtime online" : "Degraded mode") : "Connecting…"}</span>
      </div>
    </aside>
  );
}
