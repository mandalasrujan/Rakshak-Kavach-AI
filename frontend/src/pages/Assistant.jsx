import { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import {
  IconAssistant,
  IconExternalLink,
  IconSend,
  IconTrash,
  IconUser,
} from "../components/icons.jsx";
import { Alert, Button, Card, Empty, SourceLink, Spinner, formatDate } from "../components/ui.jsx";
import { ConsentRequired } from "./Dashboard.jsx";

export function Answer({ reply }) {
  if (reply.urgent) {
    return (
      <div className="animate-pulse">
        <Alert kind="urgent">{reply.answer}</Alert>
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <p className={`leading-relaxed ${reply.found ? "text-slate-800" : "text-slate-500 italic"}`}>
        {reply.answer}
      </p>
      {reply.citations?.length > 0 && (
        <div className="mt-3 rounded-xl border border-teal-100 bg-teal-50/40 p-3">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-teal-800">
            Verified Citations from Medical Records
          </p>
          <ul className="space-y-2 border-l-2 border-teal-300 pl-3" aria-label="Sources">
            {reply.citations.map((c) => (
              <li key={c.chunk_id} className="text-xs">
                <SourceLink documentId={c.document_id} page={c.page} excerpt={c.excerpt} />
                <p className="mt-1 text-slate-600 italic">“{c.excerpt}”</p>
              </li>
            ))}
          </ul>
        </div>
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
  useEffect(() => {
    loadChats().catch((e) => setError(e.message));
  }, [loadChats]);

  async function open(chatId) {
    setActive(chatId);
    setError("");
    const history = await api(`/patient/chats/${chatId}/messages`);
    setMessages(
      history.messages.map((m) =>
        m.role === "user"
          ? { question: m.content }
          : { reply: { answer: m.content, found: true, citations: [] } }
      )
    );
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
      const reply = await api(`/patient/chats/${active}/messages`, {
        method: "POST",
        json: { question },
      });
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
    if (chatId === active) {
      setActive(null);
      setMessages([]);
    }
    await loadChats();
  }

  return (
    <ConsentRequired>
      <div className="grid gap-6 md:grid-cols-[18rem_1fr]">
        {/* Left: Chat Sessions History */}
        <Card
          title="Conversations"
          subtitle="Your private consultation history"
          actions={
            <Button onClick={newChat} className="px-3 py-1.5 text-xs">
              <IconAssistant className="h-3.5 w-3.5" />
              <span>New</span>
            </Button>
          }
        >
          {chats === null ? (
            <Spinner />
          ) : chats.length === 0 ? (
            <Empty>No conversations yet.</Empty>
          ) : (
            <ul className="space-y-1.5">
              {chats.map((c) => (
                <li key={c.id} className="flex items-center justify-between gap-1">
                  <button
                    className={`flex flex-1 items-center gap-2 rounded-xl px-3 py-2 text-left text-xs transition-all ${
                      c.id === active
                        ? "bg-teal-50/90 font-semibold text-teal-900 ring-1 ring-teal-200/80 shadow-2xs"
                        : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                    }`}
                    onClick={() => open(c.id)}
                  >
                    <IconAssistant
                      className={`h-3.5 w-3.5 shrink-0 ${
                        c.id === active ? "text-teal-600" : "text-slate-400"
                      }`}
                    />
                    <span className="truncate">{formatDate(c.created_at)}</span>
                  </button>
                  <button
                    aria-label="Delete conversation"
                    className="p-1.5 text-slate-400 transition-colors hover:text-rose-600"
                    onClick={() => remove(c.id)}
                  >
                    <IconTrash className="h-3.5 w-3.5" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {/* Right: Active Chat Area */}
        <Card
          title="Ask about your records"
          subtitle="Evidence-based answers strictly grounded in your uploaded documents"
        >
          {!active ? (
            <Empty>Start or open a conversation.</Empty>
          ) : (
            <div className="flex flex-col">
              <div
                className="mb-4 max-h-[62vh] space-y-4 overflow-y-auto px-1 py-2"
                aria-live="polite"
              >
                {messages.length === 0 && (
                  <Empty>Ask, for example, “Is my HbA1c getting worse?”</Empty>
                )}
                {messages.map((m, i) =>
                  m.question ? (
                    <div key={i} className="flex justify-end">
                      <div className="flex max-w-[85%] items-start gap-2.5">
                        <div className="rounded-2xl rounded-tr-xs bg-slate-900 p-3.5 text-sm text-white shadow-sm">
                          <p className="leading-relaxed">{m.question}</p>
                        </div>
                        <div className="mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-slate-200 text-slate-700">
                          <IconUser className="h-3.5 w-3.5" />
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div key={i} className="flex justify-start">
                      <div className="flex max-w-[92%] items-start gap-2.5">
                        <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-xl bg-teal-500 text-slate-950 shadow-xs">
                          <IconAssistant className="h-4 w-4" />
                        </div>
                        <div className="flex-1 rounded-2xl rounded-tl-xs border border-slate-200/80 bg-white p-4 shadow-sm text-sm">
                          <Answer reply={m.reply} />
                        </div>
                      </div>
                    </div>
                  )
                )}
                {busy && (
                  <div className="flex justify-start">
                    <div className="flex items-center gap-2 rounded-2xl border border-slate-100 bg-slate-50 p-3">
                      <Spinner label="Checking your records" />
                    </div>
                  </div>
                )}
              </div>

              {error && (
                <div className="mb-3">
                  <Alert>{error}</Alert>
                </div>
              )}

              <form onSubmit={send} className="mt-2 flex items-center gap-2 pt-3 border-t border-slate-100">
                <label htmlFor="question" className="sr-only">
                  Question
                </label>
                <input
                  id="question"
                  value={question}
                  maxLength={1000}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="Ask a question about your tests, medications, or trends…"
                  className="flex-1 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-900 shadow-xs placeholder:text-slate-400 focus:border-teal-500 focus:outline-none focus:ring-4 focus:ring-teal-500/10"
                />
                <Button type="submit" disabled={busy} className="px-5 py-2.5">
                  <IconSend className="h-4 w-4" />
                  <span>Ask</span>
                </Button>
              </form>
            </div>
          )}
        </Card>
      </div>
    </ConsentRequired>
  );
}
