import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext.jsx";

export default function SignupPage() {
  const { signup } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const pwdChecks = {
    minLength: password.length >= 8,
    hasUpper: /[A-Z]/.test(password),
    hasLower: /[a-z]/.test(password),
    hasDigit: /[0-9]/.test(password),
    hasSpecial: /[!?@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?~#]/.test(password),
  };
  const isPasswordValid = Object.values(pwdChecks).every(Boolean);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    if (!isPasswordValid) {
      setError("Please satisfy all password security requirements.");
      return;
    }
    setSubmitting(true);
    try {
      await signup(email.trim(), password, name.trim());
      navigate("/", { replace: true });
    } catch (err) {
      let msg = err.message || "Could not create your account.";
      if (msg.includes(":") && msg.split(":")[0].length <= 3) {
        msg = msg.split(":").slice(1).join(":").trim();
      }
      if (msg.startsWith("{")) {
        try {
          const parsed = JSON.parse(msg);
          msg = parsed.detail || msg;
        } catch {}
      }
      setError(msg || "Could not create your account.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-[80vh] flex items-center justify-center">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <span className="font-display text-3xl font-semibold text-ledger">Ledgerline</span>
          <p className="text-inkfaint text-sm mt-2">Create an account to start processing documents</p>
        </div>

        <form onSubmit={handleSubmit} className="border border-hairline rounded-md p-6 bg-surface space-y-4">
          {error && (
            <div className="text-sm text-critical bg-critical/5 border border-critical/30 rounded p-2.5">
              {error}
            </div>
          )}
          <div>
            <label className="block text-xs font-mono uppercase tracking-wide text-inkfaint mb-1">Name (optional)</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full border border-hairline rounded px-3 py-2 bg-paper focus:outline-none focus:ring-2 focus:ring-ledger/40"
              placeholder="Jane Analyst"
            />
          </div>
          <div>
            <label className="block text-xs font-mono uppercase tracking-wide text-inkfaint mb-1">Email</label>
            <input
              type="email"
              required
              autoFocus
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full border border-hairline rounded px-3 py-2 bg-paper focus:outline-none focus:ring-2 focus:ring-ledger/40"
              placeholder="you@company.com"
            />
          </div>
          <div>
            <label className="block text-xs font-mono uppercase tracking-wide text-inkfaint mb-1">Password</label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full border border-hairline rounded px-3 py-2 bg-paper focus:outline-none focus:ring-2 focus:ring-ledger/40"
              placeholder="Strong password required"
            />

            <div className="mt-3 p-3 border border-hairline rounded bg-paper text-xs space-y-1">
              <p className="font-mono text-[10px] uppercase text-inkfaint mb-1">Password Requirements:</p>
              <div className={`flex items-center gap-1.5 ${pwdChecks.minLength ? "text-ok" : "text-inkfaint"}`}>
                <span>{pwdChecks.minLength ? "✓" : "○"}</span>
                <span>At least 8 characters</span>
              </div>
              <div className={`flex items-center gap-1.5 ${pwdChecks.hasUpper ? "text-ok" : "text-inkfaint"}`}>
                <span>{pwdChecks.hasUpper ? "✓" : "○"}</span>
                <span>At least 1 uppercase letter (A-Z)</span>
              </div>
              <div className={`flex items-center gap-1.5 ${pwdChecks.hasLower ? "text-ok" : "text-inkfaint"}`}>
                <span>{pwdChecks.hasLower ? "✓" : "○"}</span>
                <span>At least 1 lowercase letter (a-z)</span>
              </div>
              <div className={`flex items-center gap-1.5 ${pwdChecks.hasDigit ? "text-ok" : "text-inkfaint"}`}>
                <span>{pwdChecks.hasDigit ? "✓" : "○"}</span>
                <span>At least 1 digit (0-9)</span>
              </div>
              <div className={`flex items-center gap-1.5 ${pwdChecks.hasSpecial ? "text-ok" : "text-inkfaint"}`}>
                <span>{pwdChecks.hasSpecial ? "✓" : "○"}</span>
                <span>At least 1 special character (e.g. ?, #, /, @, !)</span>
              </div>
            </div>
          </div>
          <button
            type="submit"
            disabled={submitting || !isPasswordValid}
            className="w-full font-mono text-xs uppercase tracking-wide px-4 py-2.5 rounded bg-ledger text-white hover:bg-ledgerlight transition disabled:opacity-50"
          >
            {submitting ? "Creating account…" : "Create account"}
          </button>
        </form>

        <p className="text-center text-sm text-inkfaint mt-5">
          Already have an account?{" "}
          <Link to="/login" className="text-ledger hover:underline">Sign in</Link>
        </p>
      </div>
    </div>
  );
}

