import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bell, Search, Shield, Zap } from "lucide-react";
import { api } from "../lib/api";
import { useAsync } from "../hooks/useApi";

export function Topbar() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const { data } = useAsync(() => api.status(), [], 15000);
  const pending = data?.counts.pending_approvals ?? 0;

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!q.trim()) return;
    navigate(`/chat?q=${encodeURIComponent(q)}`);
    setQ("");
  }

  return (
    <header className="topbar">
      <form className="search" onSubmit={submit}>
        <Search size={16} />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask ORION anything…" />
      </form>
      <div className="top-actions">
        <div className="mode-pill">
          <Zap size={14} /> {data?.flags.local_only ? "LOCAL ONLY" : "AUTO / LOCAL-FIRST"}
        </div>
        {data?.kill_switch.enabled && (
          <button className="alarm" title="Kill switch engaged" onClick={() => navigate("/security")}>
            <Shield size={16} />
          </button>
        )}
        <button className={pending ? "alarm" : ""} title={`${pending} pending approvals`} onClick={() => navigate("/security")}>
          <Bell size={17} />
          {pending > 0 && <em>{pending}</em>}
        </button>
        <div className="avatar">O</div>
      </div>
    </header>
  );
}
