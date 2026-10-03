import { useState } from "react";
import { Link } from "react-router-dom";
import { authApi } from "../api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [resetUrl, setResetUrl] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setMessage("");
    setResetUrl("");
    setSubmitting(true);
    try {
      const res = await authApi.forgotPassword(email.trim());
      setMessage(res.message);
      if (res.reset_url) {
        setResetUrl(res.reset_url);
      }
    } catch (err) {
      setError(err.message || "Failed to generate password reset request.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-[80vh] flex items-center justify-center">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <span className="font-display text-3xl font-semibold text-ledger">Ledgerline</span>
          <p className="text-inkfaint text-sm mt-2">Reset your account password</p>
        </div>

        <form onSubmit={handleSubmit} className="border border-hairline rounded-md p-6 bg-surface space-y-4">
          {error && (
            <div className="text-sm text-critical bg-critical/5 border border-critical/30 rounded p-2.5">
              {error}
            </div>
          )}

          {message && (
            <div className="text-sm text-ok bg-ok/10 border border-ok/30 rounded p-3.5 space-y-1">
              <p className="font-semibold text-ok">Reset Link Sent</p>
              <p className="text-xs text-ledger">
                {message}
              </p>
              <p className="text-xs text-inkfaint pt-1">
                Please check your email inbox and click the reset link within 15 minutes.
              </p>
            </div>
          )}

          <div>
            <label className="block text-xs font-mono uppercase tracking-wide text-inkfaint mb-1">Account Email</label>
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

          <button
            type="submit"
            disabled={submitting}
            className="w-full font-mono text-xs uppercase tracking-wide px-4 py-2.5 rounded bg-ledger text-white hover:bg-ledgerlight transition disabled:opacity-50"
          >
            {submitting ? "Sending reset link…" : "Send reset link"}
          </button>
        </form>

        <p className="text-center text-sm text-inkfaint mt-5">
          Remember your password?{" "}
          <Link to="/login" className="text-ledger hover:underline">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
