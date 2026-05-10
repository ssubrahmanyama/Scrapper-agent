/* pages/RemovalsPage.tsx — Removal request tracker */
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { ExternalLink, RefreshCw, Clock, CheckCircle, XCircle, AlertTriangle, Send, Loader2 } from "lucide-react";
import toast from "react-hot-toast";

type RemovalStatus = "pending" | "submitted" | "acknowledged" | "completed" | "rejected" | "manual_required";

interface Removal {
  id: string;
  source_domain: string;
  source_url: string;
  data_type: string;
  status: RemovalStatus;
  removal_method: string | null;
  submitted_at: string | null;
  completed_at: string | null;
  retry_count: number;
  created_at: string;
}

const STATUS_CONFIG: Record<RemovalStatus, { icon: React.ReactNode; label: string; cls: string }> = {
  pending:         { icon: <Clock size={13} />,        label: "Pending",         cls: "text-slate-400 bg-slate-700/50" },
  submitted:       { icon: <Send size={13} />,         label: "Submitted",       cls: "text-blue-400 bg-blue-400/10" },
  acknowledged:    { icon: <RefreshCw size={13} />,    label: "Acknowledged",    cls: "text-amber-400 bg-amber-400/10" },
  completed:       { icon: <CheckCircle size={13} />,  label: "Removed",         cls: "text-emerald-400 bg-emerald-400/10" },
  rejected:        { icon: <XCircle size={13} />,      label: "Rejected",        cls: "text-red-400 bg-red-400/10" },
  manual_required: { icon: <AlertTriangle size={13} />,label: "Manual Required", cls: "text-orange-400 bg-orange-400/10" },
};

const PII_LABELS: Record<string, string> = {
  PERSON_NAME: "Name", ADDRESS: "Address", PHONE_NUMBER: "Phone",
  EMAIL_ADDRESS: "Email", NATIONAL_ID: "National ID", FINANCIAL: "Financial",
  DATE_OF_BIRTH: "Date of Birth", LOCATION_TRAIL: "Location",
};

function StatusBadge({ status }: { status: RemovalStatus }) {
  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.pending;
  return (
    <span className={`flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full ${cfg.cls}`}>
      {cfg.icon}{cfg.label}
    </span>
  );
}

function RemovalRow({ removal, onProcess }: { removal: Removal; onProcess: (id: string) => void }) {
  const canProcess = removal.status === "pending" || removal.status === "rejected";
  return (
    <div className="flex items-center gap-4 px-4 py-3.5 rounded-xl border border-slate-800 bg-slate-900/40 hover:bg-slate-900/70 transition-all">
      <div className="w-2 h-2 rounded-full flex-shrink-0 bg-amber-500/50" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium text-slate-200 truncate">{removal.source_domain}</p>
          <span className="text-xs px-1.5 py-0.5 rounded bg-slate-800 text-slate-500 border border-slate-700">
            {PII_LABELS[removal.data_type] ?? removal.data_type}
          </span>
        </div>
        <p className="text-xs text-slate-600 mt-0.5 font-mono truncate max-w-xs">{removal.source_url}</p>
      </div>
      <div className="flex items-center gap-3 flex-shrink-0">
        {removal.retry_count > 0 && (
          <span className="text-xs text-slate-600">retry #{removal.retry_count}</span>
        )}
        <StatusBadge status={removal.status} />
        <a href={removal.source_url} target="_blank" rel="noopener noreferrer"
          className="text-slate-600 hover:text-slate-400">
          <ExternalLink size={13} />
        </a>
        {canProcess && (
          <button onClick={() => onProcess(removal.id)}
            className="flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 hover:bg-amber-500/20 transition-colors">
            <Send size={11} />Submit
          </button>
        )}
      </div>
    </div>
  );
}

export function RemovalsPage() {
  const qc = useQueryClient();

  const { data: removals = [], isLoading } = useQuery({
    queryKey: ["removals"],
    queryFn: async () => {
      const r = await api.listRemovals({ limit: 100 });
      return r.data as Removal[];
    },
    refetchInterval: 30_000,
  });

  const processMut = useMutation({
    mutationFn: (id: string) => api.processRemoval(id),
    onSuccess: () => {
      toast.success("Removal request submitted");
      qc.invalidateQueries({ queryKey: ["removals"] });
    },
    onError: () => toast.error("Submission failed — will retry automatically"),
  });

  const processAllMut = useMutation({
    mutationFn: async () => {
      const pending = removals.filter(r => r.status === "pending");
      for (const r of pending) await api.processRemoval(r.id);
    },
    onSuccess: () => {
      toast.success("All pending removals submitted");
      qc.invalidateQueries({ queryKey: ["removals"] });
    },
  });

  const counts = {
    total: removals.length,
    completed: removals.filter(r => r.status === "completed").length,
    pending: removals.filter(r => r.status === "pending").length,
    submitted: removals.filter(r => r.status === "submitted" || r.status === "acknowledged").length,
    manual: removals.filter(r => r.status === "manual_required").length,
  };

  return (
    <div className="space-y-8 max-w-5xl">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Removal Requests</h1>
          <p className="text-slate-400 text-sm mt-1">Track automated opt-outs from data broker sites</p>
        </div>
        {counts.pending > 0 && (
          <button onClick={() => processAllMut.mutate()} disabled={processAllMut.isPending}
            className="flex items-center gap-2 px-4 py-2.5 bg-amber-500 hover:bg-amber-400 text-slate-950 font-semibold text-sm rounded-xl transition-colors shadow-lg shadow-amber-900/20">
            {processAllMut.isPending ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
            Submit All ({counts.pending})
          </button>
        )}
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          { label: "Total", value: counts.total, cls: "text-white" },
          { label: "Removed", value: counts.completed, cls: "text-emerald-400" },
          { label: "In Progress", value: counts.submitted, cls: "text-blue-400" },
          { label: "Manual Needed", value: counts.manual, cls: "text-orange-400" },
        ].map(({ label, value, cls }) => (
          <div key={label} className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4">
            <p className="text-xs text-slate-500 uppercase tracking-widest">{label}</p>
            <p className={`text-2xl font-bold font-mono mt-1 ${cls}`}>{value}</p>
          </div>
        ))}
      </div>

      {/* Progress bar */}
      {counts.total > 0 && (
        <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5">
          <div className="flex justify-between text-xs text-slate-500 mb-2">
            <span>Overall removal progress</span>
            <span>{Math.round((counts.completed / counts.total) * 100)}% complete</span>
          </div>
          <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
            <div className="h-full bg-emerald-500 rounded-full transition-all duration-500"
              style={{ width: `${(counts.completed / counts.total) * 100}%` }} />
          </div>
        </div>
      )}

      {/* List */}
      <div className="space-y-2">
        {isLoading ? (
          [...Array(5)].map((_, i) => <div key={i} className="h-14 bg-slate-900/40 rounded-xl animate-pulse" />)
        ) : removals.length === 0 ? (
          <div className="flex flex-col items-center py-16 gap-3">
            <CheckCircle size={40} className="text-emerald-500/30" />
            <p className="text-slate-500 text-sm">No removal requests yet. Run a scan to find exposed data.</p>
          </div>
        ) : (
          removals.map(r => (
            <RemovalRow key={r.id} removal={r} onProcess={(id) => processMut.mutate(id)} />
          ))
        )}
      </div>

      {/* Manual removal instructions */}
      {counts.manual > 0 && (
        <div className="p-5 bg-orange-500/10 border border-orange-500/20 rounded-2xl space-y-2">
          <p className="text-sm font-semibold text-orange-400">
            {counts.manual} removal{counts.manual > 1 ? "s" : ""} require manual action
          </p>
          <p className="text-xs text-slate-400 leading-relaxed">
            Some sites (e.g. JustDial, MyLife) don't support automated opt-out.
            Click the external link icon to visit their opt-out page directly.
            Use your registered email and cite DPDP Act 2023 Section 12 (right to erasure).
          </p>
        </div>
      )}
    </div>
  );
}
