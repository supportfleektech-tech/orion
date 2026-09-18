import { ArrowUpRight, Brain, Cloud, Gauge, ShieldCheck, Sparkles, Wrench } from "lucide-react";

export function Dashboard() {
  const metrics = [
    {k:"Local model", v:"Qwen3 4B", I:Gauge},
    {k:"Cloud routing", v:"OpenRouter / free", I:Cloud},
    {k:"Memory", v:"8,421 indexed facts", I:Brain},
    {k:"Tool gateway", v:"12 connected", I:Wrench},
  ];
  return <div className="page dashboard">
    <section className="hero-card">
      <div><div className="eyebrow">PERSONAL AI OPERATING SYSTEM</div><h1>Command the whole stack.</h1><p>Local reasoning, persistent memory, tools, RAG and cloud burst routing in one lightweight control plane.</p></div>
      <div className="hero-orb"><div className="orb-core">O</div><span>READY</span></div>
    </section>
    <section className="metric-grid">
      {[
        ["Local model", "Qwen3 4B", Gauge],
        ["Cloud routing", "OpenRouter / free", Cloud],
        ["Memory", "8,421 indexed facts", Brain],
        ["Tool gateway", "12 connected", Wrench],
      ].map(([k,v,I]) => <div className="metric" key={String(k)}><I size={17}/><span>{k}</span><strong>{v}</strong></div>)}
    </section>
    <section className="grid-two">
      <div className="panel command-panel"><div className="panel-head"><div><div className="eyebrow">COMMAND</div><h2>What should ORION do?</h2></div><Sparkles size={19}/></div><p className="muted">Ask for research, code, file analysis, planning, automation, summaries, or multi-step work.</p><div className="suggestions"><button>Research a topic</button><button>Analyze my files</button><button>Plan a project</button><button>Run a workflow</button></div></div>
      <div className="panel activity-panel"><div className="panel-head"><div><div className="eyebrow">LIVE TRACE</div><h2>Agent runtime</h2></div><ArrowUpRight size={19}/></div><div className="trace"><div><b>Router</b><span>Selected local model</span></div><div><b>Memory</b><span>Retrieved 6 context items</span></div><div><b>Tools</b><span>Policy gate ready</span></div><div><b>Verifier</b><span>Post-action checks enabled</span></div></div></div>
    </section>
    <section className="panel security-strip"><ShieldCheck size={20}/><div><b>Autonomy is policy-bounded.</b><span>Read-only tasks can run automatically. External writes, account actions and destructive operations can be configured to require approval.</span></div></section>
  </div>;
}
