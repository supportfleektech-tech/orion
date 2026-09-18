const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export async function chat(message: string, conversationId?: string) {
  const r = await fetch(`${API}/v1/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, conversation_id: conversationId, mode: "auto" }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function getTools() {
  const r = await fetch(`${API}/v1/tools`);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
