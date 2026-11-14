import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../auth.jsx";
import { IconShield } from "../components/icons.jsx";
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
    <div className="flex min-h-screen flex-col items-center justify-center bg-gradient-to-br from-slate-950 via-slate-900 to-teal-950 px-4 py-12 sm:px-6 lg:px-8">
      <main className="w-full max-w-md space-y-6">
        {/* Brand Header */}
        <div className="text-center">
          <div className="mx-auto inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-teal-500 text-slate-950 shadow-lg shadow-teal-500/20 ring-4 ring-teal-400/20">
            <IconShield className="h-7 w-7" />
          </div>
          <h1 className="mt-4 text-2xl font-bold tracking-tight text-white sm:text-3xl">
            Rakshak Kavach AI
          </h1>
          <p className="mt-1 text-xs font-medium text-teal-300">
            Sovereign Patient-Held Health Intelligence
          </p>
        </div>

        {/* Auth Card */}
        <Card
          title={mode === "register" ? "Create your account" : "Sign in"}
          subtitle={
            mode === "register"
              ? "Start managing and analyzing your medical records privately"
              : "Access your private patient health record dashboard"
          }
          className="shadow-2xl ring-1 ring-white/10"
        >
          <form onSubmit={submit} className="space-y-4">
            <Field
              id="email"
              label="Email address"
              type="email"
              autoComplete="email"
              required
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <Field
              id="password"
              label={mode === "register" ? "Password (at least 12 characters)" : "Password"}
              type="password"
              autoComplete={mode === "register" ? "new-password" : "current-password"}
              required
              minLength={mode === "register" ? 12 : 1}
              placeholder="••••••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            {error && <Alert>{error}</Alert>}
            <Button
              type="submit"
              disabled={busy}
              className="w-full py-2.5 text-sm font-semibold shadow-md shadow-teal-600/20"
            >
              {busy ? "Please wait…" : mode === "register" ? "Create account" : "Sign in"}
            </Button>
          </form>

          <div className="mt-5 border-t border-slate-100 pt-4 text-center text-sm text-slate-600">
            {mode === "register" ? "Already have an account? " : "New to Rakshak Kavach? "}
            <a
              className="font-semibold text-teal-700 underline underline-offset-2 hover:text-teal-800"
              href={mode === "register" ? "/login" : "/register"}
            >
              {mode === "register" ? "Sign in" : "Create an account"}
            </a>
          </div>
        </Card>
      </main>
    </div>
  );
}
