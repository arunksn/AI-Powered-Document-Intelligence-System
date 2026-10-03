import { Routes, Route, Link, useLocation, useNavigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth/AuthContext.jsx";
import ProtectedRoute from "./auth/ProtectedRoute.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import SignupPage from "./pages/SignupPage.jsx";
import ForgotPasswordPage from "./pages/ForgotPasswordPage.jsx";
import ResetPasswordPage from "./pages/ResetPasswordPage.jsx";
import ProjectsView from "./pages/ProjectsView.jsx";
import ProjectDetail from "./pages/ProjectDetail.jsx";
import DocumentProcessing from "./pages/DocumentProcessing.jsx";
import DocumentDetail from "./pages/DocumentDetail.jsx";


function Header() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <header className="border-b border-hairline bg-surface">
      <div className="max-w-6xl mx-auto px-6 py-4 flex items-baseline justify-between">
        <Link to="/" className="flex items-baseline gap-3">
          <span className="font-display text-2xl font-semibold text-ledger tracking-tight">
            Ledgerline
          </span>
          <span className="font-mono text-xs text-inkfaint uppercase tracking-widest">
            Document Intelligence
          </span>
        </Link>
        <nav className="flex items-center gap-5 font-mono text-xs uppercase tracking-widest text-inkfaint">
          <span className={location.pathname === "/" ? "text-ledger" : ""}>Projects</span>
          {user && (
            <>
              <span className="text-inkfaint normal-case tracking-normal font-body">
                {user.name || user.email}
              </span>
              <button onClick={handleLogout} className="hover:text-ledger transition">
                Log out
              </button>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <div className="min-h-screen bg-paper">
        <Header />
        <main className="max-w-6xl mx-auto px-6 py-8">
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/signup" element={<SignupPage />} />
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />
            <Route path="/reset-password" element={<ResetPasswordPage />} />
            <Route path="/" element={<ProtectedRoute><ProjectsView /></ProtectedRoute>} />
            <Route path="/projects/:projectId" element={<ProtectedRoute><ProjectDetail /></ProtectedRoute>} />
            <Route path="/documents/:documentId/processing" element={<ProtectedRoute><DocumentProcessing /></ProtectedRoute>} />
            <Route path="/documents/:documentId" element={<ProtectedRoute><DocumentDetail /></ProtectedRoute>} />
          </Routes>

        </main>
      </div>
    </AuthProvider>
  );
}
