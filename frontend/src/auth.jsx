import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { api } from "./api.js";
import { Spinner } from "./components/ui.jsx";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [state, setState] = useState({ status: "loading", patient: null });

  const refresh = useCallback(async () => {
    try {
      setState({ status: "authenticated", patient: await api("/patient/me") });
    } catch {
      setState({ status: "anonymous", patient: null });
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const login = async (email, password) => {
    const patient = await api("/auth/login", { method: "POST", json: { email, password } });
    setState({ status: "authenticated", patient });
  };
  const register = async (email, password) => {
    await api("/auth/register", { method: "POST", json: { email, password } });
    await login(email, password);
  };
  const logout = async () => {
    await api("/auth/logout", { method: "POST" }).catch(() => null);
    setState({ status: "anonymous", patient: null });
  };

  return (
    <AuthContext.Provider value={{ ...state, login, register, logout }}>{children}</AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);

export function ProtectedRoute({ children }) {
  const { status } = useAuth();
  const location = useLocation();
  if (status === "loading") return <Spinner label="Checking your session" />;
  if (status !== "authenticated") return <Navigate to="/login" replace state={{ from: location }} />;
  return children;
}
