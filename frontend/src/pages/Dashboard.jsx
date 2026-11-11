import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Alert, Button } from "../components/ui.jsx";

const ConsentContext = createContext(null);
export const useConsent = () => useContext(ConsentContext);

const TABS = [
  ["/", "Records"], ["/assistant", "Assistant"], ["/labs", "Labs"], ["/medications", "Medications"],
  ["/summary", "Summary"], ["/sharing", "Sharing"], ["/consent", "Consent"],
];

export function ConsentRequired({ children }) {
  const { consent } = useConsent();
  if (consent?.granted) return children;
  return (
    <Alert kind="info">
      This needs your consent first. <a className="underline" href="/consent">Review the consent notice</a>.
    </Alert>
  );
}

export default function Dashboard() {
  const { patient, logout } = useAuth();
  const [consent, setConsent] = useState(null);
  const refreshConsent = useCallback(async () => setConsent(await api("/patient/consent")), []);
  useEffect(() => {
    refreshConsent().catch(() => null);
  }, [refreshConsent]);

  return (
    <ConsentContext.Provider value={{ consent, setConsent, refreshConsent }}>
      <div className="min-h-screen">
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2 px-4 py-3">
            <h1 className="text-lg font-bold text-emerald-800">Rakshak Kavach AI</h1>
            <div className="flex items-center gap-3 text-sm">
              <span className="hidden text-slate-600 sm:inline">{patient?.email}</span>
              <Button variant="secondary" onClick={logout}>Log out</Button>
            </div>
          </div>
          <nav aria-label="Dashboard" className="mx-auto flex max-w-6xl gap-1 overflow-x-auto px-4">
            {TABS.map(([to, label]) => (
              <NavLink key={to} to={to} end
                className={({ isActive }) => `whitespace-nowrap border-b-2 px-3 py-2 text-sm ${isActive ? "border-emerald-700 font-semibold text-emerald-800" : "border-transparent text-slate-600 hover:text-slate-900"}`}>
                {label}
              </NavLink>
            ))}
          </nav>
        </header>
        <main className="mx-auto max-w-6xl space-y-4 px-4 py-6">
          {consent && !consent.granted && (
            <Alert kind="info">Uploads, the assistant and sharing are paused until you give consent. <a className="underline" href="/consent">Open consent</a></Alert>
          )}
          <Outlet />
          <p className="pt-4 text-xs text-slate-500">This assistant shows what your records say. It does not diagnose, predict or prescribe; discuss results with your doctor.</p>
        </main>
      </div>
    </ConsentContext.Provider>
  );
}
