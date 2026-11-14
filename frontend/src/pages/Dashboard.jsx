import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import {
  IconAssistant,
  IconConsent,
  IconLabs,
  IconMedications,
  IconRecords,
  IconSharing,
  IconShield,
  IconSummary,
} from "../components/icons.jsx";
import { Alert, Button } from "../components/ui.jsx";

const ConsentContext = createContext(null);
export const useConsent = () => useContext(ConsentContext);

const TABS = [
  ["/", "Records", IconRecords],
  ["/assistant", "Assistant", IconAssistant],
  ["/labs", "Labs", IconLabs],
  ["/medications", "Medications", IconMedications],
  ["/summary", "Summary", IconSummary],
  ["/sharing", "Sharing", IconSharing],
  ["/consent", "Consent", IconConsent],
];

export function ConsentRequired({ children }) {
  const { consent } = useConsent();
  if (consent?.granted) return children;
  return (
    <Alert kind="info">
      This needs your consent first.{" "}
      <a className="font-medium underline hover:text-sky-950" href="/consent">
        Review the consent notice
      </a>
      .
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

  const userInitial = patient?.email ? patient.email.charAt(0).toUpperCase() : "P";

  return (
    <ConsentContext.Provider value={{ consent, setConsent, refreshConsent }}>
      <div className="min-h-screen bg-slate-50/70">
        {/* Top Header */}
        <header className="border-b border-slate-800 bg-slate-900 text-white shadow-sm">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:py-3.5">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-teal-500 text-slate-950 shadow-sm ring-2 ring-teal-400/30">
                <IconShield className="h-5 w-5" />
              </div>
              <div>
                <h1 className="text-base font-bold tracking-tight text-white sm:text-lg">
                  Rakshak Kavach AI
                </h1>
                <span className="hidden text-[10px] font-semibold uppercase tracking-wider text-teal-400 sm:inline-block">
                  Sovereign Health Intelligence
                </span>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <div className="hidden items-center gap-2 sm:flex">
                <div className="flex h-7 w-7 items-center justify-center rounded-full bg-slate-800 text-xs font-semibold text-teal-400 ring-1 ring-slate-700">
                  {userInitial}
                </div>
                <span className="max-w-[200px] truncate text-xs text-slate-300">
                  {patient?.email}
                </span>
              </div>
              <Button
                variant="secondary"
                onClick={logout}
                className="bg-slate-800 text-xs text-slate-200 hover:bg-slate-700 hover:text-white border-slate-700 py-1.5 px-3"
              >
                Log out
              </Button>
            </div>
          </div>

          {/* Tab Navigation */}
          <div className="border-t border-slate-800/80 bg-slate-900/60 backdrop-blur-sm">
            <nav
              aria-label="Dashboard"
              className="mx-auto flex max-w-6xl gap-1 overflow-x-auto px-4 py-1.5"
            >
              {TABS.map(([to, label, IconComponent]) => (
                <NavLink
                  key={to}
                  to={to}
                  end
                  className={({ isActive }) =>
                    `inline-flex items-center gap-2 whitespace-nowrap rounded-xl px-3 py-2 text-xs font-medium transition-all duration-150 ${
                      isActive
                        ? "bg-teal-500/15 text-teal-300 ring-1 ring-teal-500/30"
                        : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
                    }`
                  }
                >
                  <IconComponent className="h-4 w-4" />
                  <span>{label}</span>
                </NavLink>
              ))}
            </nav>
          </div>
        </header>

        {/* Main Content Area */}
        <main className="mx-auto max-w-6xl space-y-6 px-4 py-6 sm:py-8">
          {consent && !consent.granted && (
            <Alert kind="info">
              Uploads, the assistant and sharing are paused until you give consent.{" "}
              <a className="font-semibold underline hover:text-sky-950" href="/consent">
                Open consent
              </a>
            </Alert>
          )}

          <Outlet />

          <footer className="mt-8 flex items-center gap-2 border-t border-slate-200/80 pt-6 text-xs text-slate-500">
            <IconShield className="h-4 w-4 shrink-0 text-slate-400" />
            <p>
              This assistant shows what your records say. It does not diagnose, predict or prescribe;
              discuss results with your doctor.
            </p>
          </footer>
        </main>
      </div>
    </ConsentContext.Provider>
  );
}
