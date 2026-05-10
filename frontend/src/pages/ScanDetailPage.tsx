/* pages/ScanDetailPage.tsx — Real-time scan results with auto-refresh */

import { useParams, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import {
  Shield, AlertTriangle, CheckCircle, Clock, Activity,
  ExternalLink, Trash2, RefreshCw, ChevronLeft, Lock,
} from "lucide-react";
import toast from "react-hot-toast";

type RiskLevel = "low" | "medium" | "high" | "critical";

interface PIIMatch {
  pii_type: string;
  masked_value: string;
  confidence: number;
  source_url: string;
  source_domain: string;
  context_snippet: string;
}

interface ScanDetail {
  id: string;
  status: "pending" | "running" | "completed" | "failed";
  target_name: string;
  exposure_score: number | null;
  risk_level: RiskLevel | null;
  pii_instances_found: number;
  sources_scanned: number;
  created_at: string;
  completed_at: string | null;
  error_message: string | null;
  results: {
    matches: PIIMatch[];
    sources_checked: number;
    unique_sources_with_pii: number;
  } | null;
}

const RISK_COLORS: Record<RiskLevel, { text: string; bg: string; border: string }> = {
  critical: { text: "text-red-400",     bg: "bg-red-400/10",     border: "border-red-400/30"     },
  high:     { text: "text-orange-400",  bg: "bg-orange-400/10",  border: "border-orange-400/30"  },
  medium:   { text: "text-amber-400",   bg: "bg-amber-400/10",   border: "border-amber-400/30"   },
  low:      { text: "text-emerald-400", bg: "bg-emerald-400/10", border: "border-emerald-400/30" },
};

const PII_TYPE_LABELS: Record<string, string> = {
  PERSON_NAME:    "👤 Name",
  ADDRESS:        "🏠 Address",
  PHONE_NUMBER:   "📞 Phone",
  EMAIL_ADDRESS:  "✉️ Email",
  DATE_OF_BIRTH:  "🎂 DOB",
  NATIONAL_ID:    "🪪 National ID",
  FINANCIAL:      "💳 Financial",
  LOCATION_TRAIL: "📍 Location",
  IP_ADDRESS:     "🌐 IP Address",
  VEHICLE_REG:    "🚗 Vehicle",
};

function RunningOverlay() {
  return (
    <div className="bg-blue-500/10 border border-blue-500/20 rounded-2xl p-8 flex flex-col items-center gap-5">
      <div className="relative">
        <div className="w-16 h-16 rounded-full border-2 border-blue-500/30" />
        <div className="absolute inset-0 w-16 h-16 rounded-full border-t-2 border-blue-400 animate-spin" />
        <Shield size={24} className="absolute inset-0 m-auto text-blue-400" />
      </div>
      <div className="text-center">
        <p className="text-white font-semibold">Scanning in progress</p>
        <p className="text-slate-400 text-sm mt-1">Checking data brokers and search engines for your personal data…</p>
      </div>
      <div className="flex items-center gap-2 text-xs text-blue-400">
        <Activity size={13} className="animate-pulse" />
        <span>Auto-refreshing every 8 seconds</span>
      </div>
    </div>
  );
}

function PIIMatchCard({ match }: { match: PIIMatch }) {
  const confidence = Math.round(match.confidence * 100);
  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-slate-200">
            {PII_TYPE_LABELS[match.pii_type] ?? match.pii_type}
          </span>
          <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
            {confidence}%
          </span>
        </div>
        <a
          href={match.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1 text-xs text-amber-400 hover:text-amber-300 flex-shrink-0"
        >
          {match.source_domain}
          <ExternalLink size={11} />
        </a>
      </div>

      <div className="flex items-center gap-2">
        <Lock size={12} className="text-slate-600" />
        <span className="text-sm font-mono text-slate-400">{match.masked_value}</span>
      </div>

      {match.context_snippet && (
        <p className="text-xs text-slate-600 font-mono bg-slate-950/50 rounded-lg p-2 border border-slate-800/50 leading-relaxed">
          …{match.context_snippet}…
        </p>
      )}
    </div>
  );
}

export function ScanDetailPage() {
  const { scanId } = useParams<{ scanId: string }>();
  const qc = useQueryClient();

  const { data: scan, isLoading } = useQuery({
    queryKey: ["scan", scanId],
    queryFn: async () => {
      const r = await api.getScan(scanId!);
      return r.data as ScanDetail;
    },
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "pending" || status === "running" ? 8000 : false;
    },
  });

  const rescanMut = useMutation({
    mutationFn: () => api.rescan(scanId!),
    onSuccess: (res) => {
      toast.success("Re-scan queued!");
      qc.invalidateQueries({ queryKey: ["scans"] });
    },
  });

  const deleteMut = useMutation({
    mutationFn: () => api.deleteScan(scanId!),
    onSuccess: () => {
      toast.success("Scan deleted");
      window.history.back();
    },
  });

  if (isLoading) {
    return (
      <div className="space-y-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-20 bg-slate-900/40 rounded-2xl animate-pulse" />
        ))}
      </div>
    );
  }

  if (!scan) return <p className="text-slate-400">Scan not found.</p>;

  const risk = scan.risk_level ?? "low";
  const riskCfg = RISK_COLORS[risk];
  const matches: PIIMatch[] = scan.results?.matches ?? [];

  // Group matches by domain
  const byDomain = matches.reduce<Record<string, PIIMatch[]>>((acc, m) => {
    (acc[m.source_domain] = acc[m.source_domain] ?? []).push(m);
    return acc;
  }, {});

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Breadcrumb */}
      <div className="flex items-center gap-3">
        <Link to="/dashboard" className="flex items-center gap-1.5 text-slate-500 hover:text-slate-300 text-sm transition-colors">
          <ChevronLeft size={16} /> Dashboard
        </Link>
        <span className="text-slate-700">/</span>
        <span className="text-slate-400 text-sm">{scan.target_name}</span>
      </div>

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">{scan.target_name}</h1>
          <p className="text-slate-500 text-sm mt-1 font-mono">
            {new Date(scan.created_at).toLocaleString("en-IN")}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => rescanMut.mutate()}
            disabled={scan.status === "running" || rescanMut.isPending}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl border border-slate-700 text-slate-400 hover:text-slate-200 hover:border-slate-600 text-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <RefreshCw size={14} className={rescanMut.isPending ? "animate-spin" : ""} />
            Re-scan
          </button>
          <button
            onClick={() => deleteMut.mutate()}
            disabled={deleteMut.isPending}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl border border-red-900/50 text-red-500 hover:text-red-400 hover:border-red-900 text-sm transition-colors"
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      {/* Running state */}
      {(scan.status === "pending" || scan.status === "running") && <RunningOverlay />}

      {/* Failed state */}
      {scan.status === "failed" && (
        <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-2xl">
          <p className="text-red-400 text-sm font-medium">Scan failed</p>
          {scan.error_message && <p className="text-red-500/70 text-xs mt-1 font-mono">{scan.error_message}</p>}
        </div>
      )}

      {/* Completed results */}
      {scan.status === "completed" && (
        <>
          {/* Score row */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {[
              { label: "Exposure Score", value: scan.exposure_score != null ? `${Math.round(scan.exposure_score)}/100` : "N/A", cls: riskCfg.text },
              { label: "Risk Level", value: risk.charAt(0).toUpperCase() + risk.slice(1), cls: riskCfg.text },
              { label: "PII Found", value: scan.pii_instances_found, cls: "text-white" },
              { label: "Sources Checked", value: scan.sources_scanned, cls: "text-white" },
            ].map(({ label, value, cls }) => (
              <div key={label} className={`bg-slate-900/60 border rounded-2xl p-4 ${riskCfg.border}`}>
                <p className="text-xs text-slate-500 uppercase tracking-widest">{label}</p>
                <p className={`text-2xl font-bold font-mono mt-1 ${cls}`}>{value}</p>
              </div>
            ))}
          </div>

          {/* PII findings by domain */}
          {Object.keys(byDomain).length > 0 ? (
            <div className="space-y-5">
              <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-widest">
                Exposed Data Sources ({scan.results?.unique_sources_with_pii ?? 0} sites)
              </h2>
              {Object.entries(byDomain).map(([domain, domainMatches]) => (
                <div key={domain} className="space-y-2">
                  <div className="flex items-center gap-2 px-1">
                    <span className="text-sm font-semibold text-slate-300">{domain}</span>
                    <span className="text-xs bg-slate-800 text-slate-500 px-2 py-0.5 rounded-full border border-slate-700">
                      {domainMatches.length} instance{domainMatches.length !== 1 ? "s" : ""}
                    </span>
                  </div>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {domainMatches.map((m, i) => <PIIMatchCard key={i} match={m} />)}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center py-16 gap-4">
              <CheckCircle size={48} className="text-emerald-500/50" />
              <div className="text-center">
                <p className="text-white font-semibold">No PII exposure found</p>
                <p className="text-slate-500 text-sm mt-1">
                  Checked {scan.sources_scanned} sources — your data appears clean.
                </p>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
