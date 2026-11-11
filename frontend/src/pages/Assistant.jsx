import { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import { Alert, Button, Card, Empty, SourceLink, Spinner, formatDate } from "../components/ui.jsx";
import { ConsentRequired } from "./Dashboard.jsx";

export function Answer({ reply }) {
  if (reply.urgent) return <Alert kind="urgent">{reply.answer}</Alert>;
  return (
    <div className="space-y-1">
      <p className={reply.found ? "" : "text-slate-500"}>{reply.answer}</p>
      {reply.citations?.length > 0 && (
        <ul className="space-y-1 border-l-2 border-emerald-200 pl-3" aria-label="Sources">
          {reply.citations.map((c) => (
            <li key={c.chunk_id}>
              <SourceLink documentId={c.document_id} page={c.page} excerpt={c.excerpt} />
              <p className="text-xs text-slate-500">“{c.excerpt}”</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function Assistant() {
  const [chats, setChats] = useState(null);
  const [active, setActive] = useState(null);
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const loadChats = useCallback(async () => setChats((await api("/patient/chats")).items), []);
  useEffect(() => { loadChats().catch((e) => setError(e.message)); }, [loadChats]);

  async function open(chatId) {
    setActive(chatId);
    setError("");
    const history = await api(`/patient/chats/${chatId}/messages`);
    setMessages(history.messages.map((m) => (m.role === "user" ? { question: m.content } : { reply: { answer: m.content, found: true, citations: [] } })));
  }

  async function newChat() {
    const chat = await api("/patient/chats", { method: "POST" });
    await loadChats();
    setActive(chat.id);
    setMessages([]);
  }

  async function send(event) {
    event.preventDefault();
    if (!question.trim() || !active) return;
    setBusy(true);
    setError("");
    try {
      const reply = await api(`/patient/chats/${active}/messages`, { method: "POST", json: { question } });
      setMessages((m) => [...m, { question }, { reply }]);
      setQuestion("");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(chatId) {
    if (!window.confirm("Delete this conversation?")) return;
    await api(`/patient/chats/${chatId}`, { method: "DELETE" });
    if (chatId === active) { setActive(null); setMessages([]); }
    await loadChats();
  }

  return (
    <ConsentRequired>
      <div className="grid gap-4 md:grid-cols-[16rem_1fr]">
        <Card title="Conversations" actions={<Button onClick={newChat}>New</Button>}>
          {chats === null ? <Spinner /> : chats.length === 0 ? <Empty>No conversations yet.</Empty> : (
            <ul className="space-y-1">
              {chats.map((c) => (
                <li key={c.id} className="flex items-center justify-between gap-1">
                  <button className={`flex-1 rounded px-2 py-1 text-left text-sm ${c.id === active ? "bg-emerald-50 font-semibold" : "hover:bg-slate-50"}`} onClick={() => open(c.id)}>
                    {formatDate(c.created_at)}
                  </button>
                  <button aria-label="Delete conversation" className="px-2 text-slate-400 hover:text-red-700" onClick={() => remove(c.id)}>✕</button>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Ask about your records">
          {!active ? <Empty>Start or open a conversation.</Empty> : (
            <>
              <div className="mb-4 max-h-[60vh] space-y-3 overflow-y-auto" aria-live="polite">
                {messages.length === 0 && <Empty>Ask, for example, “Is my HbA1c getting worse?”</Empty>}
                {messages.map((m, i) => m.question
                  ? <p key={i} className="ml-auto max-w-[85%] rounded-lg bg-emerald-50 p-2 text-sm">{m.question}</p>
                  : <div key={i} className="max-w-[95%] text-sm"><Answer reply={m.reply} /></div>)}
                {busy && <Spinner label="Checking your records" />}
              </div>
              {error && <div className="mb-2"><Alert>{error}</Alert></div>}
              <form onSubmit={send} className="flex gap-2">
                <label htmlFor="question" className="sr-only">Question</label>
                <input id="question" value={question} maxLength={1000} onChange={(e) => setQuestion(e.target.value)} placeholder="Ask a question" className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-base" />
                <Button type="submit" disabled={busy}>Ask</Button>
              </form>
            </>
          )}
        </Card>
      </div>
    </ConsentRequired>
  );
}
