/* pages/DashboardHome.tsx — Main dashboard with exposure score, scan history */

import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Shield, AlertTriangle, CheckCircle, Clock, Plus, TrendingDown, Activity } from "lucide-react";
import { api } from "../api/client";
import { useAuth } from "../store/authStore";

interface Scan {
  id: string;
  status: "pending" | "running" | "completed" | "failed";
  target_name: string;
  exposure_score: number | null;
  risk_level: "low" | "medium" | "high" | "critical" | null;
  pii_instances_found: number;
  sources_scanned: number;
  created_at: string;
  completed_at: string | null;
}

const RISK_CONFIG = {
  critical: { color: "text-red-400", bg: "bg-red-400/10 border-red-400/30", bar: "bg-red-500", label: "Critical" },
  high:     { color: "text-orange-400", bg: "bg-orange-400/10 border-orange-400/30", bar: "bg-orange-500", label: "High" },
  medium:   { color: "text-amber-400", bg: "bg-amber-400/10 border-amber-400/30", bar: "bg-amber-500", label: "Medium" },
  low:      { color: "text-emerald-400", bg: "bg-emerald-400/10 border-emerald-400/30", bar: "bg-emerald-500", label: "Low" },
};

function ExposureGauge({ score }: { score: number }) {
  const risk = score >= 75 ? "critical" : score >= 50 ? "high" : score >= 25 ? "medium" : "low";
  const cfg = RISK_CONFIG[risk];
  const circumference = 2 * Math.PI * 54;
  const offset = circumference - (score / 100) * circumference;

  return (
    <div className="flex flex-col items-center gap-3">
      <div className="relative w-36 h-36">
        <svg className="w-full h-full -rotate-90" viewBox="0 0 120 120">
          <circle cx="60" cy="60" r="54" fill="none" stroke="#1e293b" strokeWidth="10" />
          <circle
            cx="60" cy="60" r="54" fill="none"
            stroke={risk === "critical" ? "#ef4444" : risk === "high" ? "#f97316" : risk === "medium" ? "#f59e0b" : "#10b981"}
            strokeWidth="10"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            className="transition-all duration-1000 ease-out"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={`text-3xl font-bold font-mono ${cfg.color}`}>{Math.round(score)}</span>
          <span className="text-xs text-slate-500 mt-0.5">/ 100</span>
        </div>
      </div>
      <span className={`text-sm font-semibold px-3 py-1 rounded-full border ${cfg.bg} ${cfg.color}`}>
        {cfg.label} Risk
      </span>
    </div>
  );
}

function ScanRow({ scan }: { scan: Scan }) {
  const risk = scan.risk_level ?? "low";
  const cfg = RISK_CONFIG[risk] ?? RISK_CONFIG.low;
  const date = new Date(scan.created_at).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });

  return (
    <Link to={`/scans/${scan.id}`} className="group flex items-center gap-4 px-4 py-3.5 rounded-xl border border-slate-800 hover:border-slate-700 bg-slate-900/40 hover:bg-slate-900/80 transition-all duration-150">
      <div className={`w-2 h-2 rounded-full flex-shrink-0 ${cfg.bar}`} />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-slate-200 truncate">{scan.target_name}</p>
        <p className="text-xs text-slate-500 mt-0.5 font-mono">{date}</p>
      </div>
      <div className="flex items-center gap-5 text-right">
        <div className="hidden sm:block">
          <p className={`text-sm font-bold font-mono ${cfg.color}`}>{scan.exposure_score != null ? Math.round(scan.exposure_score) : "—"}</p>
          <p className="text-xs text-slate-600">score</p>
        </div>
        <div className="hidden sm:block">
          <p className="text-sm font-mono text-slate-300">{scan.pii_instances_found}</p>
          <p className="text-xs text-slate-600">PII hits</p>
        </div>
        <StatusBadge status={scan.status} />
      </div>
    </Link>
  );
}

function StatusBadge({ status }: { status: Scan["status"] }) {
  const map = {
    completed: { icon: <CheckCircle size={13} />, label: "Done", cls: "text-emerald-400 bg-emerald-400/10" },
    running:   { icon: <Activity size={13} className="animate-pulse" />, label: "Scanning", cls: "text-blue-400 bg-blue-400/10" },
    pending:   { icon: <Clock size={13} />, label: "Queued", cls: "text-slate-400 bg-slate-700/50" },
    failed:    { icon: <AlertTriangle size={13} />, label: "Failed", cls: "text-red-400 bg-red-400/10" },
  };
  const { icon, label, cls } = map[status];
  return (
    <span className={`flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full ${cls}`}>
      {icon}{label}
    </span>
  );
}

export function DashboardHome() {
  const { user } = useAuth();

  const { data: scans = [], isLoading } = useQuery({
    queryKey: ["scans"],
    queryFn: async () => {
      const r = await api.listScans({ limit: 10 });
      return r.data as Scan[];
    },
  });

  const latestCompleted = scans.find(s => s.status === "completed" && s.exposure_score != null);
  const avgScore = scans.filter(s => s.exposure_score != null).reduce((sum, s) => sum + (s.exposure_score ?? 0), 0) / (scans.filter(s => s.exposure_score != null).length || 1);
  const totalPII = scans.reduce((sum, s) => sum + s.pii_instances_found, 0);
  const activeRemovals = scans.filter(s => s.status === "running").length;

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">
            Privacy Overview
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Welcome back, {user?.full_name?.split(" ")[0] ?? "User"}
          </p>
        </div>
        <Link
          to="/scans/new"
          className="flex items-center gap-2 px-4 py-2.5 bg-amber-500 hover:bg-amber-400 text-slate-950 font-semibold text-sm rounded-xl transition-colors duration-150 shadow-lg shadow-amber-900/20"
        >
          <Plus size={16} />
          New Scan
        </Link>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: "Exposure Score", value: latestCompleted ? Math.round(latestCompleted.exposure_score!) : "N/A", sub: "latest scan", icon: <Shield size={18} />, accent: "amber" },
          { label: "PII Instances", value: totalPII, sub: "across all scans", icon: <AlertTriangle size={18} />, accent: "red" },
          { label: "Scans Run", value: scans.length, sub: "total lifetime", icon: <Activity size={18} />, accent: "blue" },
          { label: "Active Jobs", value: activeRemovals, sub: "in progress", icon: <TrendingDown size={18} />, accent: "emerald" },
        ].map((stat) => (
          <div key={stat.label} className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5">
            <div className="flex items-center justify-between mb-3">
              <span className="text-slate-500 text-xs font-medium uppercase tracking-widest">{stat.label}</span>
              <span className="text-slate-600">{stat.icon}</span>
            </div>
            <p className="text-3xl font-bold font-mono text-white">{stat.value}</p>
            <p className="text-slate-600 text-xs mt-1">{stat.sub}</p>
          </div>
        ))}
      </div>

      {/* Main split */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Exposure gauge */}
        <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-6 flex flex-col items-center justify-center gap-4">
          <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-widest self-start">Current Exposure</h2>
          {latestCompleted ? (
            <ExposureGauge score={latestCompleted.exposure_score!} />
          ) : (
            <div className="flex flex-col items-center gap-3 py-8">
              <Shield size={40} className="text-slate-700" />
              <p className="text-slate-500 text-sm text-center">Run your first scan to see your exposure score</p>
              <Link to="/scans/new" className="text-amber-400 text-sm font-medium hover:text-amber-300">Start scan →</Link>
            </div>
          )}
          {latestCompleted && (
            <p className="text-xs text-slate-600 text-center">
              Based on scan from {new Date(latestCompleted.created_at).toLocaleDateString()}
            </p>
          )}
        </div>

        {/* Recent scans */}
        <div className="lg:col-span-2 bg-slate-900/60 border border-slate-800 rounded-2xl p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-widest">Recent Scans</h2>
            <Link to="/scans" className="text-xs text-amber-400 hover:text-amber-300">View all</Link>
          </div>

          {isLoading ? (
            <div className="space-y-3">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="h-14 bg-slate-800/50 rounded-xl animate-pulse" />
              ))}
            </div>
          ) : scans.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 gap-3">
              <Shield size={36} className="text-slate-700" />
              <p className="text-slate-500 text-sm">No scans yet</p>
              <Link to="/scans/new" className="text-amber-400 text-sm font-medium">Run your first scan →</Link>
            </div>
          ) : (
            <div className="space-y-2">
              {scans.map(scan => <ScanRow key={scan.id} scan={scan} />)}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
