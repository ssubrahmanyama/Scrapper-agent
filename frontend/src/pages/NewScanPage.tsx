/* pages/NewScanPage.tsx — Initiate a new PII scan */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { api } from "../api/client";
import { Shield, Loader2, AlertCircle, Info } from "lucide-react";
import toast from "react-hot-toast";

export function NewScanPage() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    target_name: "",
    target_email: "",
    target_phone: "",
    target_location: "",
  });

  const mutation = useMutation({
    mutationFn: () =>
      api.createScan({
        target_name: form.target_name.trim(),
        target_email: form.target_email.trim() || undefined,
        target_phone: form.target_phone.trim() || undefined,
        target_location: form.target_location.trim() || undefined,
      }),
    onSuccess: (res) => {
      toast.success("Scan started! Checking your digital footprint…");
      navigate(`/scans/${res.data.id}`);
    },
    onError: (err: any) => {
      toast.error(err?.message ?? "Failed to start scan");
    },
  });

  const field = (
    id: keyof typeof form,
    label: string,
    placeholder: string,
    required = false,
    hint?: string
  ) => (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2">
        <label htmlFor={id} className="text-sm font-medium text-slate-300">
          {label}
          {required && <span className="text-amber-500 ml-0.5">*</span>}
        </label>
        {hint && (
          <span className="group relative">
            <Info size={13} className="text-slate-600 cursor-help" />
            <span className="absolute left-5 -top-1 w-56 hidden group-hover:block text-xs text-slate-400 bg-slate-800 border border-slate-700 rounded-lg p-2 z-10 shadow-xl">
              {hint}
            </span>
          </span>
        )}
      </div>
      <input
        id={id}
        type="text"
        value={form[id]}
        onChange={(e) => setForm((prev) => ({ ...prev, [id]: e.target.value }))}
        required={required}
        placeholder={placeholder}
        className="w-full px-4 py-3 rounded-xl bg-slate-900 border border-slate-700 text-slate-100 placeholder:text-slate-600 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500/50 transition-colors"
      />
    </div>
  );

  return (
    <div className="max-w-2xl mx-auto space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white tracking-tight">New Privacy Scan</h1>
        <p className="text-slate-400 text-sm mt-1">
          Provide information to search for. More details = more accurate results.
        </p>
      </div>

      <div className="flex items-start gap-3 p-4 bg-blue-500/10 border border-blue-500/20 rounded-xl text-sm text-blue-300">
        <AlertCircle size={16} className="flex-shrink-0 mt-0.5" />
        <div>
          <strong className="font-medium">Your data is protected.</strong> Scan targets are never stored in plain text. All PII is masked immediately after detection.
        </div>
      </div>

      <form
        onSubmit={(e) => { e.preventDefault(); mutation.mutate(); }}
        className="bg-slate-900/60 border border-slate-800 rounded-2xl p-6 space-y-5"
      >
        <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-widest">Scan Target</h2>

        {field("target_name", "Full Name", "e.g. Arjun Kumar Sharma", true, "Full name as it would appear on data broker sites")}
        {field("target_email", "Email Address", "e.g. arjun@example.com", false, "Used to find accounts on data broker and people-finder sites")}
        {field("target_phone", "Phone Number", "e.g. +91 98765 43210", false, "Indian or international format")}
        {field("target_location", "City / Area", "e.g. Bandra West, Mumbai", false, "Helps narrow down results on people-finder sites")}

        <div className="pt-2">
          <button
            type="submit"
            disabled={!form.target_name.trim() || mutation.isPending}
            className="w-full py-3.5 rounded-xl bg-amber-500 hover:bg-amber-400 disabled:bg-amber-500/30 disabled:cursor-not-allowed text-slate-950 font-semibold text-sm transition-colors duration-150 flex items-center justify-center gap-2 shadow-lg shadow-amber-900/20"
          >
            {mutation.isPending ? (
              <><Loader2 size={16} className="animate-spin" />Starting scan…</>
            ) : (
              <><Shield size={16} />Run Privacy Scan</>
            )}
          </button>
        </div>
      </form>

      <div className="grid grid-cols-3 gap-4 text-center">
        {[["~2–5 min", "Scan duration"], ["500+", "Sources checked"], ["AI-powered", "PII detection"]].map(([val, label]) => (
          <div key={label} className="bg-slate-900/40 border border-slate-800 rounded-xl p-4">
            <p className="text-lg font-bold text-amber-400 font-mono">{val}</p>
            <p className="text-xs text-slate-500 mt-1">{label}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
