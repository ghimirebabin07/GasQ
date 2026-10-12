/**
 * GasQ API Client Module
 * Provides unified HTTP fetch handling, token injection, silent refresh on 401,
 * and error extraction.
 */

const GasQApi = (() => {
  const API_BASE = "";
  const refreshInFlight = new Map();

  function removeCredentialQueryParameters() {
    if (!window.location.search) return;
    const url = new URL(window.location.href);
    let changed = false;
    for (const key of ["email", "password", "username", "phone"]) {
      if (url.searchParams.has(key)) {
        url.searchParams.delete(key);
        changed = true;
      }
    }
    if (changed) {
      window.history.replaceState({}, document.title, `${url.pathname}${url.search}${url.hash}`);
    }
  }

  removeCredentialQueryParameters();

  function escapeHtml(value) {
    if (value === null || value === undefined) return "";
    return String(value).replace(/[&<>"']/g, (character) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;",
    }[character]));
  }

  function readSession(type) {
    const keys = {
      admin: "lpg_admin_session",
      dealer: "lpg_dealer_session",
      customer: "lpg_customer",
    };
    const raw = localStorage.getItem(keys[type]);
    if (!raw) return null;
    try {
      const data = JSON.parse(raw);
      return data?.access_token ? { type, data } : null;
    } catch (_) {
      return null;
    }
  }

  function getActiveSession(path = "") {
    // Select the token by API role instead of whichever role was logged in last.
    if (path.startsWith("/admin/")) return readSession("admin");
    if (path.startsWith("/dealer/")) return readSession("dealer");
    if (path === "/dealers" || path.startsWith("/queue/") || path.startsWith("/customer/")) {
      return readSession("customer");
    }
    return readSession("admin") || readSession("dealer") || readSession("customer");
  }

  function updateStoredToken(sessionType, newAccessToken, newRefreshToken) {
    const key = sessionType === "admin"
      ? "lpg_admin_session"
      : sessionType === "dealer"
        ? "lpg_dealer_session"
        : "lpg_customer";
    const raw = localStorage.getItem(key);
    if (!raw) return;
    try {
      const parsed = JSON.parse(raw);
      parsed.access_token = newAccessToken;
      if (newRefreshToken) parsed.refresh_token = newRefreshToken;
      localStorage.setItem(key, JSON.stringify(parsed));
    } catch (_) {}
  }

  async function attemptTokenRefresh(session) {
    const refreshToken = session.data.refresh_token;
    if (!refreshToken) return null;

    const existingRefresh = refreshInFlight.get(session.type);
    if (existingRefresh) return existingRefresh;

    const refreshPromise = refreshSession(session);
    refreshInFlight.set(session.type, refreshPromise);
    try {
      return await refreshPromise;
    } finally {
      refreshInFlight.delete(session.type);
    }
  }

  async function refreshSession(session) {
    try {
      const resp = await fetch(`${API_BASE}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: session.data.refresh_token }),
        credentials: "include",
      });
      if (!resp.ok) return null;
      const data = await resp.json();
      updateStoredToken(session.type, data.access_token, data.refresh_token);
      return data.access_token;
    } catch (_) {
      return null;
    }
  }

  function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(";").shift();
    return null;
  }

  async function request(path, options = {}) {
    window.GasQSessionGuard?.resetIdle();

    const session = getActiveSession(path);
    const headers = {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    };

    if (session?.data?.access_token && !headers.Authorization) {
      headers.Authorization = `Bearer ${session.data.access_token}`;
    }

    const csrfToken = getCookie("gasq_csrf");
    if (csrfToken && !headers["X-CSRF-Token"]) {
      headers["X-CSRF-Token"] = csrfToken;
    }

    const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
    const fetchOptions = {
      ...options,
      headers,
      credentials: "include",
    };
    let response = await fetch(url, fetchOptions);

    // Handle expired token with silent refresh
    const canRefresh = !["/admin/login", "/auth/refresh", "/auth/logout"].includes(path);
    if (response.status === 401 && session && canRefresh) {
      const newAccessToken = session.data.refresh_token
        ? await attemptTokenRefresh(session)
        : null;
      if (newAccessToken) {
        headers.Authorization = `Bearer ${newAccessToken}`;
        response = await fetch(url, { ...options, headers });
      } else {
        // Refresh failed, clear session and dispatch auth expiry event
        if (session.type === "admin") {
          localStorage.removeItem("lpg_admin_session");
        } else if (session.type === "dealer") {
          localStorage.removeItem("lpg_dealer_session");
        } else {
          localStorage.removeItem("lpg_customer");
        }
        window.dispatchEvent(new CustomEvent("gasq:auth_expired", { detail: { type: session.type } }));
      }
    }

    let data = null;
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      data = await response.json();
    } else {
      const text = await response.text();
      try {
        data = JSON.parse(text);
      } catch (_) {
        data = { detail: text };
      }
    }

    if (response.ok && path === "/auth/refresh" && session && data?.access_token) {
      updateStoredToken(session.type, data.access_token, data.refresh_token);
    }

    if (!response.ok) {
      let message = "Request failed";
      if (response.status === 422) {
        message = "The given input is not valid. Please check your details and try again.";
      } else if (typeof data?.detail === "string") {
        message = data.detail;
      } else if (Array.isArray(data?.detail) && data.detail.length > 0) {
        message = data.detail[0]?.msg || "The given input is not valid.";
      } else if (data?.message) {
        message = data.message;
      }
      const error = new Error(message);
      error.status = response.status;
      error.data = data;
      throw error;
    }

    return data;
  }

  return {
    escapeHtml,
    request,
    get: (path, options) => request(path, { method: "GET", ...options }),
    post: (path, body, options) => request(path, { method: "POST", body: JSON.stringify(body), ...options }),
    put: (path, body, options) => request(path, { method: "PUT", body: JSON.stringify(body), ...options }),
    patch: (path, body, options) => request(path, { method: "PATCH", body: JSON.stringify(body), ...options }),
    delete: (path, options) => request(path, { method: "DELETE", ...options }),
  };
})();

if (typeof window !== "undefined") {
  window.GasQApi = GasQApi;
}
