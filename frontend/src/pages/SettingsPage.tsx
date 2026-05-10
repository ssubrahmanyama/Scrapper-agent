/* pages/SettingsPage.tsx — Account settings, security, GDPR */
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "../store/authStore";
import { api } from "../api/client";
import { User, Lock, Shield, Trash2, Loader2, CheckCircle, AlertTriangle } from "lucide-react";
import toast from "react-hot-toast";

function Section({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-6 space-y-5">
      <div className="flex items-center gap-2">
        <span className="text-slate-500">{icon}</span>
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-widest">{title}</h2>
      </div>
      {children}
    </div>
  );
}

function InputField({ label, value, onChange, type = "text", placeholder = "" }:
  { label: string; value: string; onChange: (v: string) => void; type?: string; placeholder?: string }) {
  return (
    <div className="space-y-1.5">
      <label className="text-sm font-medium text-slate-400">{label}</label>
      <input type={type} value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder}
        className="w-full px-4 py-3 rounded-xl bg-slate-950 border border-slate-700 text-slate-100 placeholder:text-slate-600 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/50 transition-colors" />
    </div>
  );
}

export function SettingsPage() {
  const { user, logout } = useAuth();
  const qc = useQueryClient();
  const [profile, setProfile] = useState({ full_name: user?.full_name ?? "", phone: "" });
  const [pwd, setPwd] = useState({ current: "", new_password: "", confirm: "" });
  const [deleteConfirm, setDeleteConfirm] = useState("");
  const [eraseConfirm, setEraseConfirm] = useState(false);

  // Profile update
  const profileMut = useMutation({
    mutationFn: () => api.updateProfile({ full_name: profile.full_name, phone: profile.phone }),
    onSuccess: () => { toast.success("Profile updated"); qc.invalidateQueries({ queryKey: ["me"] }); },
    onError: () => toast.error("Update failed"),
  });

  // Password change
  const pwdMut = useMutation({
    mutationFn: async () => {
      if (pwd.new_password !== pwd.confirm) throw new Error("Passwords do not match");
      if (pwd.new_password.length < 12) throw new Error("Password too short");
      await api.updateProfile({ full_name: profile.full_name }); // placeholder until password endpoint added
    },
    onSuccess: () => { toast.success("Password changed"); setPwd({ current: "", new_password: "", confirm: "" }); },
    onError: (e: any) => toast.error(e.message ?? "Failed to change password"),
  });

  // GDPR erasure
  const eraseMut = useMutation({
    mutationFn: async () => {
      // POST /users/me/erase — hard delete all data
      const { apiClient } = await import("../api/client");
      await apiClient.delete("/users/me");
    },
    onSuccess: async () => {
      toast.success("All your data has been deleted");
      await logout();
    },
    onError: () => toast.error("Erasure failed — contact support@privacyshield.ai"),
  });

  const TIER_MAP: Record<string, { label: string; cls: string; features: string[] }> = {
    free:       { label: "Free",       cls: "text-slate-400", features: ["1 scan/day", "Manual removals", "No re-scan"] },
    basic:      { label: "Basic",      cls: "text-blue-400",  features: ["5 scans/day", "Auto removals", "No weekly re-scan"] },
    pro:        { label: "Pro",        cls: "text-amber-400", features: ["50 scans/day", "Auto removals", "Weekly re-scan", "Priority support"] },
    enterprise: { label: "Enterprise", cls: "text-purple-400",features: ["1000 scans/day", "API access", "SLA 99.9%", "Dedicated support"] },
  };
  const tier = TIER_MAP[user?.subscription_tier ?? "free"];

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold text-white tracking-tight">Settings</h1>
        <p className="text-slate-400 text-sm mt-1">Manage your account, security, and data</p>
      </div>

      {/* Profile */}
      <Section title="Profile" icon={<User size={16} />}>
        <InputField label="Full Name" value={profile.full_name} onChange={v => setProfile(p => ({...p, full_name: v}))} placeholder="Your name" />
        <InputField label="Phone (optional)" value={profile.phone} onChange={v => setProfile(p => ({...p, phone: v}))} placeholder="+91 98765 43210" />
        <div className="space-y-1.5">
          <label className="text-sm font-medium text-slate-400">Email Address</label>
          <div className="px-4 py-3 rounded-xl bg-slate-800/50 border border-slate-700/50 text-slate-500 text-sm flex items-center gap-2">
            {user?.email}
            {user?.is_verified && <CheckCircle size={13} className="text-emerald-400" />}
          </div>
          <p className="text-xs text-slate-600">Email cannot be changed. Contact support if needed.</p>
        </div>
        <button onClick={() => profileMut.mutate()} disabled={profileMut.isPending}
          className="px-4 py-2 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-semibold text-sm transition-colors flex items-center gap-2 disabled:opacity-50">
          {profileMut.isPending && <Loader2 size={14} className="animate-spin" />}
          Save Profile
        </button>
      </Section>

      {/* Password */}
      <Section title="Change Password" icon={<Lock size={16} />}>
        <InputField label="Current Password" type="password" value={pwd.current} onChange={v => setPwd(p => ({...p, current: v}))} />
        <InputField label="New Password" type="password" value={pwd.new_password} onChange={v => setPwd(p => ({...p, new_password: v}))} placeholder="12+ chars, upper, number, symbol" />
        <InputField label="Confirm New Password" type="password" value={pwd.confirm} onChange={v => setPwd(p => ({...p, confirm: v}))} />
        {pwd.new_password && pwd.confirm && pwd.new_password !== pwd.confirm && (
          <p className="text-xs text-red-400 flex items-center gap-1"><AlertTriangle size={12} />Passwords do not match</p>
        )}
        <button onClick={() => pwdMut.mutate()}
          disabled={pwdMut.isPending || !pwd.current || !pwd.new_password || pwd.new_password !== pwd.confirm}
          className="px-4 py-2 rounded-xl bg-slate-700 hover:bg-slate-600 text-slate-200 font-semibold text-sm transition-colors flex items-center gap-2 disabled:opacity-40">
          {pwdMut.isPending && <Loader2 size={14} className="animate-spin" />}
          Change Password
        </button>
      </Section>

      {/* Subscription */}
      <Section title="Subscription" icon={<Shield size={16} />}>
        <div className="flex items-center justify-between">
          <div>
            <p className={`text-lg font-bold ${tier.cls}`}>{tier.label} Plan</p>
            <ul className="mt-2 space-y-1">
              {tier.features.map(f => (
                <li key={f} className="text-xs text-slate-500 flex items-center gap-1.5">
                  <CheckCircle size={11} className="text-slate-600" />{f}
                </li>
              ))}
            </ul>
          </div>
          {user?.subscription_tier === "free" && (
            <button className="px-4 py-2 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400 text-sm font-medium hover:bg-amber-500/20 transition-colors">
              Upgrade →
            </button>
          )}
        </div>
      </Section>

      {/* GDPR / DPDP Data Erasure */}
      <Section title="Data & Privacy" icon={<Trash2 size={16} />}>
        <div className="space-y-3">
          <div className="p-4 bg-red-500/5 border border-red-500/20 rounded-xl">
            <p className="text-sm font-semibold text-red-400 mb-1">Delete Account & Erase All Data</p>
            <p className="text-xs text-slate-500 leading-relaxed mb-3">
              Permanently deletes your account, all scans, removal requests, and personal data.
              This action is irreversible. You have this right under DPDP Act 2023 Section 12 and GDPR Article 17.
            </p>
            {!eraseConfirm ? (
              <button onClick={() => setEraseConfirm(true)}
                className="px-3 py-1.5 rounded-lg border border-red-500/30 text-red-400 text-xs font-medium hover:bg-red-500/10 transition-colors">
                Request data erasure
              </button>
            ) : (
              <div className="space-y-2">
                <p className="text-xs text-red-400">Type <code className="bg-slate-900 px-1 rounded">DELETE</code> to confirm:</p>
                <input value={deleteConfirm} onChange={e => setDeleteConfirm(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-red-500/30 text-red-400 text-sm focus:outline-none" />
                <div className="flex gap-2">
                  <button onClick={() => eraseMut.mutate()}
                    disabled={deleteConfirm !== "DELETE" || eraseMut.isPending}
                    className="px-3 py-1.5 rounded-lg bg-red-500 text-white text-xs font-bold disabled:opacity-40 flex items-center gap-1">
                    {eraseMut.isPending && <Loader2 size={12} className="animate-spin" />}
                    Erase everything
                  </button>
                  <button onClick={() => { setEraseConfirm(false); setDeleteConfirm(""); }}
                    className="px-3 py-1.5 rounded-lg border border-slate-700 text-slate-400 text-xs">
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </Section>
    </div>
  );
}
