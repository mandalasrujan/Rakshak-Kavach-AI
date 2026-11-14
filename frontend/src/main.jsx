import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AuthProvider, ProtectedRoute } from "./auth.jsx";
import Assistant from "./pages/Assistant.jsx";
import Consent from "./pages/Consent.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import DoctorShare from "./pages/DoctorShare.jsx";
import Labs from "./pages/Labs.jsx";
import Login from "./pages/Login.jsx";
import Medications from "./pages/Medications.jsx";
import Records from "./pages/Records.jsx";
import Sharing from "./pages/Sharing.jsx";
import Summary from "./pages/Summary.jsx";
import "./index.css";

export const ROUTER_FUTURE = { v7_startTransition: true, v7_relativeSplatPath: true };

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/share" element={<DoctorShare />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Login mode="register" />} />
      <Route element={<ProtectedRoute><Dashboard /></ProtectedRoute>}>
        <Route path="/" element={<Records />} />
        <Route path="/assistant" element={<Assistant />} />
        <Route path="/labs" element={<Labs />} />
        <Route path="/medications" element={<Medications />} />
        <Route path="/summary" element={<Summary />} />
        <Route path="/sharing" element={<Sharing />} />
        <Route path="/consent" element={<Consent />} />
      </Route>
    </Routes>
  );
}

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(
    <React.StrictMode>
      <BrowserRouter future={ROUTER_FUTURE}>
        <AuthProvider><AppRoutes /></AuthProvider>
      </BrowserRouter>
    </React.StrictMode>,
  );
}
