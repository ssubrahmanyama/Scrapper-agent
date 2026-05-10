/* ─────────────────────────────────────────────────────────────────────────────
   PrivacyShield Dashboard — React + TypeScript + Tailwind
   Aesthetic: Dark precision — think Palantir meets premium security console.
   Font: Syne (display) + JetBrains Mono (data/numbers) + Geist (body)
   Palette: Deep slate + electric amber + red threat indicators
───────────────────────────────────────────────────────────────────────────── */

import { useState, useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "react-hot-toast";

import { AuthProvider, useAuth } from "./store/authStore";
import { DashboardLayout } from "./components/layout/DashboardLayout";
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";
import { DashboardHome } from "./pages/DashboardHome";
import { NewScanPage } from "./pages/NewScanPage";
import { ScanDetailPage } from "./pages/ScanDetailPage";
import { RemovalsPage } from "./pages/RemovalsPage";
import { SettingsPage } from "./pages/SettingsPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
});

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 rounded-full border-2 border-amber-400 border-t-transparent animate-spin" />
          <span className="text-slate-400 font-mono text-sm">Initializing...</span>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children}</>;
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            {/* Public routes */}
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />

            {/* Protected dashboard routes */}
            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <DashboardLayout />
                </ProtectedRoute>
              }
            >
              <Route index element={<Navigate to="/dashboard" replace />} />
              <Route path="dashboard" element={<DashboardHome />} />
              <Route path="scans/new" element={<NewScanPage />} />
              <Route path="scans/:scanId" element={<ScanDetailPage />} />
              <Route path="removals" element={<RemovalsPage />} />
              <Route path="settings" element={<SettingsPage />} />
            </Route>

            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </BrowserRouter>

        <Toaster
          position="top-right"
          toastOptions={{
            style: {
              background: "#1e293b",
              color: "#f1f5f9",
              border: "1px solid #334155",
              fontFamily: "Geist, sans-serif",
              fontSize: "13px",
            },
            success: { iconTheme: { primary: "#f59e0b", secondary: "#1e293b" } },
            error: { iconTheme: { primary: "#ef4444", secondary: "#1e293b" } },
          }}
        />
      </AuthProvider>
    </QueryClientProvider>
  );
}

export default App;
