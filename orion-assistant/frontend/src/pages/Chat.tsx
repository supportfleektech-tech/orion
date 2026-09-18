import { FormEvent, useState } from "react";
import { Bot, Send, UserRound } from "lucide-react";
import { chat } from "../lib/api";

export function Chat() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<{role:string,content:string}[]>([]);
  const [busy, setBusy] = useState(false);
  const [conversation, setConversation] = useState<string>();
  async function send() {
    const text = input.trim(); if (!text || busy) return;
    setInput(""); setMessages(m => [...m, {role:"user",content:text}]); setBusy(true);
    try {
      const res = await chat(text, conversation);
      setConversation(res.conversation_id);
      setMessages(m => [...m, {role:"assistant", content:res.result || "No response returned."}]);
    } catch (err) {
      setMessages(m => [...m, {role:"assistant", content:`Error: ${String(err)}`}]);
    } finally { setBusy(false); }
  }
  function submit(e: FormEvent) { e.preventDefault(); void send(); }
  return <div className="page chat-page"><div className="chat-shell">
    <div className="chat-head"><div><div className="eyebrow">CONVERSATION</div><h2>ORION</h2></div><div className="live-badge">LOCAL-FIRST</div></div>
    <div className="messages">{messages.length===0 ? <div className="empty-chat"><Bot size={40}/><h3>Ready when you are.</h3><p>Ask anything. ORION will retrieve memory and choose the appropriate execution path.</p></div> : messages.map((m,i)=><div key={i} className={`msg ${m.role}`}><div className="msg-icon">{m.role === "user" ? <UserRound size={16}/> : <Bot size={16}/>}</div><div><div className="msg-role">{m.role}</div><div className="msg-body">{m.content}</div></div></div>)}</div>
    <form onSubmit={submit} className="composer"><textarea value={input} onChange={e=>setInput(e.target.value)} placeholder="Give ORION a task…" onKeyDown={e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();void send()}}}/><button disabled={busy}>{busy?"…":<Send size={17}/>}</button></form>
  </div></div>;
}
