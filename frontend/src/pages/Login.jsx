import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../auth.jsx";
import { Alert, Button, Card, Field } from "../components/ui.jsx";

export default function Login({ mode = "login" }) {
  const { status, login, register } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  if (status === "authenticated") return <Navigate to="/" replace />;

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await (mode === "register" ? register(email, password) : login(email, password));
      navigate("/", { replace: true });
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto mt-10 max-w-md px-4">
      <h1 className="mb-4 text-2xl font-bold">Rakshak Kavach AI</h1>
      <Card title={mode === "register" ? "Create your account" : "Sign in"}>
        <form onSubmit={submit} className="space-y-3">
          <Field id="email" label="Email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          <Field id="password" label={mode === "register" ? "Password (at least 12 characters)" : "Password"} type="password"
            autoComplete={mode === "register" ? "new-password" : "current-password"} required minLength={mode === "register" ? 12 : 1}
            value={password} onChange={(e) => setPassword(e.target.value)} />
          {error && <Alert>{error}</Alert>}
          <Button type="submit" disabled={busy} className="w-full">{busy ? "Please wait…" : mode === "register" ? "Register" : "Log in"}</Button>
        </form>
        <p className="mt-3 text-sm text-slate-600">
          {mode === "register" ? "Already registered? " : "New here? "}
          <a className="text-emerald-800 underline" href={mode === "register" ? "/login" : "/register"}>
            {mode === "register" ? "Sign in" : "Create an account"}
          </a>
        </p>
      </Card>
    </main>
  );
}
