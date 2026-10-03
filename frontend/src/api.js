const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
export const WS_URL = import.meta.env.VITE_WS_URL || "ws://localhost:8000";

const TOKEN_KEY = "docintel_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

// Fired whenever a request comes back 401 (expired/invalid token), so the
// AuthContext can log the user out and redirect to /login in one place
// instead of every page having to check response status itself.
const unauthorizedListeners = new Set();
export function onUnauthorized(fn) {
  unauthorizedListeners.add(fn);
  return () => unauthorizedListeners.delete(fn);
}

async function request(path, options = {}) {
  const token = getToken();
  const res = await fetch(`${API_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
    ...options,
  });
  const isAuthRoute = path.startsWith("/api/auth/");
  if (res.status === 401 && !isAuthRoute) {
    unauthorizedListeners.forEach((fn) => fn());
  }
  if (!res.ok) {
    const text = await res.text();
    let cleanMessage = text;
    try {
      const json = JSON.parse(text);
      if (json && json.detail) {
        cleanMessage = typeof json.detail === "string" ? json.detail : JSON.stringify(json.detail);
      }
    } catch {
      // fallback to raw text
    }
    throw new Error(cleanMessage);
  }
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : res.text();
}

export const authApi = {
  signup: (email, password, name) =>
    request("/api/auth/signup", { method: "POST", body: JSON.stringify({ email, password, name }) }),
  login: (email, password) =>
    request("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  forgotPassword: (email) =>
    request("/api/auth/forgot-password", { method: "POST", body: JSON.stringify({ email }) }),
  resetPassword: (token, new_password) =>
    request("/api/auth/reset-password", { method: "POST", body: JSON.stringify({ token, new_password }) }),
  me: () => request("/api/auth/me"),
};


export const api = {
  listProjects: () => request("/api/projects"),
  createProject: (name, description) =>
    request("/api/projects", { method: "POST", body: JSON.stringify({ name, description }) }),
  getProject: (id) => request(`/api/projects/${id}`),
  deleteProject: (id) => request(`/api/projects/${id}`, { method: "DELETE" }),
  listProjectDocuments: (id) => request(`/api/projects/${id}/documents`),
  listContradictions: (id) => request(`/api/projects/${id}/contradictions`),

  uploadDocument: async (projectId, file) => {
    const form = new FormData();
    form.append("file", file);
    const token = getToken();
    const res = await fetch(`${API_URL}/api/documents/upload?project_id=${projectId}`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    });
    if (res.status === 401) unauthorizedListeners.forEach((fn) => fn());
    if (!res.ok) {
      const text = await res.text();
      let cleanMessage = text;
      try {
        const json = JSON.parse(text);
        if (json && json.detail) {
          cleanMessage = typeof json.detail === "string" ? json.detail : JSON.stringify(json.detail);
        }
      } catch {}
      throw new Error(cleanMessage);
    }
    return res.json();
  },


  getDocument: (id) => request(`/api/documents/${id}`),
  getDocumentStages: (id) => request(`/api/documents/${id}/stages`),
  getDocumentAnomalies: (id) => request(`/api/documents/${id}/anomalies`),
  getCrmSync: (id) =>
    request(`/api/documents/${id}/crm-sync`).catch(() => null),
  retryCrmSync: (id) => request(`/api/documents/${id}/crm-sync/retry`, { method: "POST" }),
  reprocessDocument: (id) => request(`/api/documents/${id}/reprocess`, { method: "POST" }),
  deleteDocument: (id) => request(`/api/documents/${id}`, { method: "DELETE" }),
};
