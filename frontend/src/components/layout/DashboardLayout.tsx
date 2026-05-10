/* components/layout/DashboardLayout.tsx */

import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../../store/authStore";
import {
  Shield, LayoutDashboard, ScanLine, Trash2, Settings,
  LogOut, ChevronDown, Crown, Menu, X,
} from "lucide-react";
import { useState } from "react";

const NAV = [
  { to: "/dashboard",  label: "Overview",  icon: LayoutDashboard },
  { to: "/scans/new",  label: "New Scan",  icon: ScanLine },
  { to: "/removals",   label: "Removals",  icon: Trash2 },
  { to: "/settings",   label: "Settings",  icon: Settings },
];

const TIER_BADGE: Record<string, { label: string; cls: string }> = {
  free:       { label: "Free",       cls: "text-slate-400 bg-slate-800 border-slate-700" },
  basic:      { label: "Basic",      cls: "text-blue-400 bg-blue-400/10 border-blue-400/30" },
  pro:        { label: "Pro",        cls: "text-amber-400 bg-amber-400/10 border-amber-400/30" },
  enterprise: { label: "Enterprise", cls: "text-purple-400 bg-purple-400/10 border-purple-400/30" },
};

function Sidebar({ onClose }: { onClose?: () => void }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const tier = user?.subscription_tier ?? "free";
  const tierBadge = TIER_BADGE[tier];

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <div className="flex flex-col h-full bg-slate-950 border-r border-slate-800/60 w-64">
      {/* Logo */}
      <div className="flex items-center gap-3 px-5 h-16 border-b border-slate-800/60">
        <div className="w-8 h-8 rounded-lg bg-amber-500/20 border border-amber-500/30 flex items-center justify-center flex-shrink-0">
          <Shield size={16} className="text-amber-400" />
        </div>
        <span className="font-bold text-white tracking-tight">PrivacyShield</span>
        {onClose && (
          <button onClick={onClose} className="ml-auto text-slate-600 hover:text-slate-400 lg:hidden">
            <X size={18} />
          </button>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            onClick={onClose}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-colors duration-100 ${
                isActive
                  ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                  : "text-slate-500 hover:text-slate-200 hover:bg-slate-900"
              }`
            }
          >
            <Icon size={16} />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Upgrade CTA for free tier */}
      {tier === "free" && (
        <div className="mx-3 mb-4 p-4 bg-gradient-to-br from-amber-500/10 to-amber-900/5 border border-amber-500/20 rounded-xl">
          <Crown size={16} className="text-amber-400 mb-2" />
          <p className="text-xs font-semibold text-slate-300 mb-1">Upgrade to Pro</p>
          <p className="text-xs text-slate-500 mb-3 leading-relaxed">50 scans/day + automated removals</p>
          <button className="w-full py-1.5 rounded-lg bg-amber-500 text-slate-950 text-xs font-bold hover:bg-amber-400 transition-colors">
            Upgrade
          </button>
        </div>
      )}

      {/* User info */}
      <div className="px-3 pb-4 border-t border-slate-800/60 pt-4">
        <div className="flex items-center gap-3 px-2">
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-amber-500/30 to-amber-900/20 border border-amber-500/20 flex items-center justify-center flex-shrink-0">
            <span className="text-xs font-bold text-amber-400">
              {(user?.full_name ?? user?.email ?? "U")[0].toUpperCase()}
            </span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-slate-300 truncate">{user?.full_name ?? "User"}</p>
            <span className={`text-xs px-1.5 py-0.5 rounded-full border font-medium ${tierBadge.cls}`}>
              {tierBadge.label}
            </span>
          </div>
          <button
            onClick={handleLogout}
            title="Sign out"
            className="text-slate-600 hover:text-red-400 transition-colors"
          >
            <LogOut size={15} />
          </button>
        </div>
      </div>
    </div>
  );
}

export function DashboardLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="flex h-screen bg-slate-950 overflow-hidden">
      {/* Desktop sidebar */}
      <div className="hidden lg:flex flex-shrink-0">
        <Sidebar />
      </div>

      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <>
          <div className="fixed inset-0 bg-black/60 z-40 lg:hidden" onClick={() => setSidebarOpen(false)} />
          <div className="fixed inset-y-0 left-0 z-50 lg:hidden flex">
            <Sidebar onClose={() => setSidebarOpen(false)} />
          </div>
        </>
      )}

      {/* Main content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Mobile header */}
        <div className="lg:hidden flex items-center gap-3 px-4 h-14 border-b border-slate-800/60 flex-shrink-0">
          <button onClick={() => setSidebarOpen(true)} className="text-slate-500 hover:text-slate-200">
            <Menu size={20} />
          </button>
          <div className="flex items-center gap-2">
            <Shield size={16} className="text-amber-400" />
            <span className="font-bold text-white text-sm">PrivacyShield</span>
          </div>
        </div>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto">
          <div className="px-4 sm:px-6 lg:px-8 py-8 max-w-7xl mx-auto">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
