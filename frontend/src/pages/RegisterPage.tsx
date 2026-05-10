/* pages/RegisterPage.tsx */
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../store/authStore";
import { Eye, EyeOff, Shield, AlertCircle, Loader2, CheckCircle } from "lucide-react";

function PasswordStrength({ password }: { password: string }) {
  const checks = [
    { label: "12+ characters", ok: password.length >= 12 },
    { label: "Uppercase letter", ok: /[A-Z]/.test(password) },
    { label: "Number", ok: /\d/.test(password) },
    { label: "Special character (!@#$...)", ok: /[!@#$%^&*()\-_=+\[\]{}|;:,.<>?]/.test(password) },
  ];
  const score = checks.filter((c) => c.ok).length;
  const colors = ["bg-red-500", "bg-orange-500", "bg-amber-500", "bg-emerald-500"];

  if (!password) return null;
  return (
    <div className="space-y-2 mt-2">
      <div className="flex gap-1">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className={`h-1 flex-1 rounded-full transition-all ${i < score ? colors[score - 1] : "bg-slate-800"}`} />
        ))}
      </div>
      <div className="grid grid-cols-2 gap-1">
        {checks.map((c) => (
          <div key={c.label} className={`flex items-center gap-1.5 text-xs ${c.ok ? "text-emerald-400" : "text-slate-600"}`}>
            <CheckCircle size={11} className={c.ok ? "text-emerald-400" : "text-slate-700"} />
            {c.label}
          </div>
        ))}
      </div>
    </div>
  );
}

export function RegisterPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ full_name: "", email: "", password: "" });
  const [showPwd, setShowPwd] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const f = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((p) => ({ ...p, [k]: e.target.value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const { apiClient } = await import("../api/client");
      await apiClient.post("/auth/register", form);
      // Auto-login after registration
      await login(form.email.toLowerCase(), form.password);
      navigate("/dashboard");
    } catch (err: any) {
      setError(err?.message ?? "Registration failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const passwordOk =
    form.password.length >= 12 &&
    /[A-Z]/.test(form.password) &&
    /\d/.test(form.password) &&
    /[!@#$%^&*()\-_=+\[\]{}|;:,.<>?]/.test(form.password);

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-6">
      <div className="w-full max-w-md space-y-8">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-amber-500/20 border border-amber-500/30 flex items-center justify-center">
            <Shield size={18} className="text-amber-400" />
          </div>
          <span className="text-white font-bold text-lg">PrivacyShield</span>
        </div>

        <div>
          <h1 className="text-2xl font-bold text-white">Create account</h1>
          <p className="text-slate-400 text-sm mt-1">Start protecting your digital identity</p>
        </div>

        {error && (
          <div className="flex items-center gap-3 p-3.5 bg-red-500/10 border border-red-500/30 rounded-xl text-red-400 text-sm">
            <AlertCircle size={16} className="flex-shrink-0" />
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-5" noValidate>
          {[
            { id: "full_name", label: "Full Name", type: "text", placeholder: "Arjun Kumar Sharma" },
            { id: "email", label: "Email Address", type: "email", placeholder: "you@example.com" },
          ].map(({ id, label, type, placeholder }) => (
            <div key={id} className="space-y-1.5">
              <label className="text-sm font-medium text-slate-300">{label}</label>
              <input
                type={type}
                value={form[id as keyof typeof form]}
                onChange={f(id as keyof typeof form)}
                required
                placeholder={placeholder}
                className="w-full px-4 py-3 rounded-xl bg-slate-900 border border-slate-700 text-slate-100 placeholder:text-slate-600 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500/50 transition-colors"
              />
            </div>
          ))}

          <div className="space-y-1.5">
            <label className="text-sm font-medium text-slate-300">Password</label>
            <div className="relative">
              <input
                type={showPwd ? "text" : "password"}
                value={form.password}
                onChange={f("password")}
                required
                placeholder="Min 12 chars, upper, number, symbol"
                className="w-full px-4 py-3 pr-12 rounded-xl bg-slate-900 border border-slate-700 text-slate-100 placeholder:text-slate-600 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/50 transition-colors"
              />
              <button type="button" onClick={() => setShowPwd(!showPwd)}
                className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300">
                {showPwd ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
            <PasswordStrength password={form.password} />
          </div>

          <button type="submit"
            disabled={loading || !form.full_name || !form.email || !passwordOk}
            className="w-full py-3 rounded-xl bg-amber-500 hover:bg-amber-400 disabled:bg-amber-500/30 disabled:cursor-not-allowed text-slate-950 font-semibold text-sm transition-colors flex items-center justify-center gap-2 shadow-lg shadow-amber-900/20">
            {loading ? <><Loader2 size={16} className="animate-spin" />Creating account…</> : "Create free account"}
          </button>
        </form>

        <p className="text-center text-sm text-slate-500">
          Already have an account?{" "}
          <Link to="/login" className="text-amber-400 hover:text-amber-300 font-medium">Sign in</Link>
        </p>

        <p className="text-center text-xs text-slate-700">
          By registering you agree to our Terms of Service and Privacy Policy.
          Data stored in compliance with DPDP Act 2023.
        </p>
      </div>
    </div>
  );
}
