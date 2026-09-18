import { Search, Mic, Bell, Zap } from "lucide-react";

export function Topbar() {
  return <header className="topbar">
    <div className="search"><Search size={16}/><input placeholder="Ask ORION anything…  ⌘K"/></div>
    <div className="top-actions">
      <div className="mode-pill"><Zap size={14}/> AUTO / LOCAL-FIRST</div>
      <button aria-label="voice"><Mic size={17}/></button>
      <button aria-label="notifications"><Bell size={17}/></button>
      <div className="avatar">B</div>
    </div>
  </header>;
}
