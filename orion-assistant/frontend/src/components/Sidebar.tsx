import { NavLink } from "react-router-dom";
import { Activity, Bot, Brain, Database, FlaskConical, GitBranch, Home, Plug, Settings2, Shield, TerminalSquare, Workflow } from "lucide-react";

const items = [
  ["/", "Command Center", Home],
  ["/chat", "Conversations", Bot],
  ["/tasks", "Tasks", Workflow],
  ["/memory", "Memory", Brain],
  ["/knowledge", "Knowledge", Database],
  ["/tools", "Tools", TerminalSquare],
  ["/mcp", "MCP", GitBranch],
  ["/automations", "Automations", Activity],
  ["/connectors", "Connectors", Plug],
  ["/evaluation", "Evaluation", FlaskConical],
  ["/security", "Security", Shield],
  ["/settings", "Settings", Settings2],
] as const;

export function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="brand"><div className="brand-orb">O</div><div><strong>ORION</strong><span>AI OPERATING SYSTEM</span></div></div>
      <div className="nav-group">
        {items.map(([to, label, Icon]) => (
          <NavLink key={to} to={to} className={({isActive}) => `nav-item ${isActive ? "active" : ""}`}>
            <Icon size={17}/><span>{label}</span>
          </NavLink>
        ))}
      </div>
      <div className="sidebar-footer">
        <div className="status-dot"/><span>Local runtime online</span>
      </div>
    </aside>
  );
}
