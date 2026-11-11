import { useCallback, useEffect, useState } from "react";
import { api } from "./api.js";

function Login({ onLogin }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function submit(mode) {
    setError("");
    try {
      if (mode === "register") await api("/auth/register", { method: "POST", json: { email, password } });
      onLogin(await api("/auth/login", { method: "POST", json: { email, password } }));
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <section className="card">
      <h2>Sign in</h2>
      <input placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
      <input placeholder="Password (12+ characters)" type="password" value={password}
        onChange={(e) => setPassword(e.target.value)} />
      <div className="row">
        <button onClick={() => submit("login")}>Log in</button>
        <button className="secondary" onClick={() => submit("register")}>Register</button>
      </div>
      {error && <p className="error">{error}</p>}
    </section>
  );
}

function Consent({ consent, onChange }) {
  const grant = async () =>
    onChange(await api("/patient/consent", { method: "POST", json: { notice_version: consent.notice_version } }));
  const revoke = async () => onChange(await api("/patient/consent", { method: "DELETE" }));
  return (
    <section className="card">
      <h2>Consent</h2>
      <p className="notice">{consent.notice_text}</p>
      {consent.granted
        ? <button className="secondary" onClick={revoke}>Revoke consent</button>
        : <button onClick={grant}>I agree</button>}
    </section>
  );
}

function Documents() {
  const [documents, setDocuments] = useState([]);
  const [error, setError] = useState("");
  const refresh = useCallback(async () => setDocuments((await api("/patient/documents")).items), []);
  useEffect(() => { refresh(); }, [refresh]);

  async function onUpload(event) {
    const file = event.target.files[0];
    if (!file) return;
    setError("");
    const form = new FormData();
    form.append("file", file);
    try {
      await api("/patient/documents", { method: "POST", form });
      await refresh();
    } catch (e) {
      setError(e.message);
    }
    event.target.value = "";
  }

  return (
    <section className="card">
      <h2>Documents</h2>
      <input type="file" accept="application/pdf" onChange={onUpload} />
      <button className="secondary" onClick={refresh}>Refresh</button>
      {error && <p className="error">{error}</p>}
      <ul>
        {documents.map((d) => (
          <li key={d.id}>
            {new Date(d.uploaded_at).toLocaleString()} · <b>{d.status}</b>
            {d.pages ? ` · ${d.pages} page(s)` : ""}{d.failure_reason ? ` · ${d.failure_reason}` : ""}
          </li>
        ))}
      </ul>
    </section>
  );
}

function Chat() {
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState([]);
  const [busy, setBusy] = useState(false);

  async function ask(event) {
    event.preventDefault();
    if (!question.trim()) return;
    setBusy(true);
    try {
      const answer = await api("/patient/ask", { method: "POST", json: { question } });
      setTurns((t) => [...t, { question, answer }]);
      setQuestion("");
    } catch (e) {
      setTurns((t) => [...t, { question, error: e.message }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card">
      <h2>Ask about your records</h2>
      {turns.map((turn, i) => (
        <div key={i} className="turn">
          <p className="question">{turn.question}</p>
          {turn.error ? <p className="error">{turn.error}</p> : (
            <>
              <p>{turn.answer.answer}</p>
              {turn.answer.citations.map((c) => (
                <p key={c.chunk_id} className="citation">
                  Source: document {c.document_id.slice(0, 8)}, page {c.page}: “{c.excerpt}”
                </p>
              ))}
            </>
          )}
        </div>
      ))}
      <form onSubmit={ask} className="row">
        <input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="e.g. What was my HbA1c?" />
        <button disabled={busy}>{busy ? "Checking your records…" : "Ask"}</button>
      </form>
      <p className="hint">Answers come only from your uploaded records. This is not medical advice.</p>
    </section>
  );
}

export default function App() {
  const [patient, setPatient] = useState(null);
  const [consent, setConsent] = useState(null);

  useEffect(() => {
    api("/patient/me").then(setPatient).catch(() => setPatient(null));
  }, []);
  useEffect(() => {
    if (patient) api("/patient/consent").then(setConsent);
  }, [patient]);

  async function logout() {
    await api("/auth/logout", { method: "POST" });
    setPatient(null);
    setConsent(null);
  }

  return (
    <main>
      <header className="row">
        <h1>Rakshak Kavach AI</h1>
        {patient && <button className="secondary" onClick={logout}>Log out</button>}
      </header>
      {!patient && <Login onLogin={setPatient} />}
      {patient && consent && <Consent consent={consent} onChange={setConsent} />}
      {patient && consent?.granted && (<><Documents /><Chat /></>)}
    </main>
  );
}
