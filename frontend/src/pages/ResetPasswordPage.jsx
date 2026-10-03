import { useState } from "react";
import { Link, useSearchParams, useNavigate } from "react-router-dom";
import { authApi } from "../api";

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get("token") || "";

  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

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
    if (!token) {
      setError("Missing or invalid password reset token.");
      return;
    }
    if (!isPasswordValid) {
      setError("Please satisfy all password security requirements.");
      return;
    }
    setSubmitting(true);
    try {
      await authApi.resetPassword(token, password);
      setSuccess(true);
    } catch (err) {
      setError(err.message || "Failed to reset password.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-[80vh] flex items-center justify-center">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <span className="font-display text-3xl font-semibold text-ledger">Ledgerline</span>
          <p className="text-inkfaint text-sm mt-2">Set your new password</p>
        </div>

        {success ? (
          <div className="border border-ok/30 bg-ok/5 rounded-md p-6 text-center space-y-4">
            <div className="w-12 h-12 rounded-full bg-ok/10 text-ok mx-auto flex items-center justify-center text-xl font-bold">✓</div>
            <h2 className="font-display text-xl text-ink font-semibold">Password Reset Complete!</h2>
            <p className="text-sm text-inkfaint">Your password has been updated successfully. You can now log in with your new credentials.</p>
            <button
              type="button"
              onClick={() => navigate("/login")}
              className="w-full font-mono text-xs uppercase tracking-wide px-4 py-2.5 rounded bg-ledger text-white hover:bg-ledgerlight transition"
            >
              Sign In Now
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="border border-hairline rounded-md p-6 bg-surface space-y-4">
            {error && (
              <div className="text-sm text-critical bg-critical/5 border border-critical/30 rounded p-2.5">
                {error}
              </div>
            )}

            {!token && (
              <div className="text-sm text-warn bg-warn/5 border border-warn/30 rounded p-2.5">
                No reset token provided in the URL. Please request a new reset link.
              </div>
            )}

            <div>
              <label className="block text-xs font-mono uppercase tracking-wide text-inkfaint mb-1">New Password</label>
              <input
                type="password"
                required
                autoFocus
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
              disabled={submitting || !isPasswordValid || !token}
              className="w-full font-mono text-xs uppercase tracking-wide px-4 py-2.5 rounded bg-ledger text-white hover:bg-ledgerlight transition disabled:opacity-50"
            >
              {submitting ? "Resetting password…" : "Reset password"}
            </button>
          </form>
        )}

        <p className="text-center text-sm text-inkfaint mt-5">
          Remember your password?{" "}
          <Link to="/login" className="text-ledger hover:underline">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
