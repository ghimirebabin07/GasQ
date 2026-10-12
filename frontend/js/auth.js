/**
 * GasQ Auth Module
 * Manages customer and dealer sessions, Google Identity Services, Email OTP,
 * Nepal phone number validation, and route guards.
 */

const GasQAuth = (() => {
  const CUSTOMER_KEY = "lpg_customer";
  const DEALER_KEY = "lpg_dealer_session";
  const ADMIN_KEY = "lpg_admin_session";

  // Nepal Phone Regex: 10 digits starting with 98 or 97, optional +977 prefix
  const NEPAL_PHONE_REGEX = /^(?:\+?977)?[9][78]\d{8}$/;

  function isValidNepalPhone(phone) {
    if (!phone) return false;
    const cleaned = String(phone).replace(/[\s-]/g, "");
    return NEPAL_PHONE_REGEX.test(cleaned);
  }

  function normalizeNepalPhone(phone) {
    if (!phone) return "";
    let cleaned = String(phone).replace(/[\s-]/g, "");
    if (!cleaned.startsWith("+977")) {
      if (cleaned.startsWith("977")) {
        cleaned = `+${cleaned}`;
      } else {
        cleaned = `+977${cleaned}`;
      }
    }
    return cleaned;
  }

  function getCustomerSession() {
    const raw = localStorage.getItem(CUSTOMER_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch (_) {
      return null;
    }
  }

  function setCustomerSession(session) {
    const data = {
      ...(session.customer || session.user || {}),
      access_token: session.access_token,
      refresh_token: session.refresh_token,
      token_type: session.token_type || "bearer",
    };
    localStorage.setItem(CUSTOMER_KEY, JSON.stringify(data));
    return data;
  }

  function clearCustomerSession() {
    localStorage.removeItem(CUSTOMER_KEY);
    localStorage.removeItem("lpg_token_id");
  }

  function getDealerSession() {
    const raw = localStorage.getItem(DEALER_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch (_) {
      return null;
    }
  }

  function setDealerSession(session) {
    const data = {
      ...(session.dealer || session.user || {}),
      access_token: session.access_token,
      refresh_token: session.refresh_token,
      token_type: session.token_type || "bearer",
    };
    localStorage.setItem(DEALER_KEY, JSON.stringify(data));
    window.GasQSessionGuard?.init("dealer");
    return data;
  }

  function clearDealerSession() {
    localStorage.removeItem(DEALER_KEY);
    sessionStorage.removeItem("gasq_dealer_auth_time");
  }

  function getAdminSession() {
    const raw = localStorage.getItem(ADMIN_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch (_) {
      return null;
    }
  }

  function setAdminSession(session) {
    const data = {
      access_token: session.access_token,
      refresh_token: session.refresh_token,
      token_type: session.token_type || "bearer",
    };
    localStorage.setItem(ADMIN_KEY, JSON.stringify(data));
    window.GasQSessionGuard?.init("admin");
    return data;
  }

  function clearAdminSession() {
    localStorage.removeItem(ADMIN_KEY);
    sessionStorage.removeItem("gasq_admin_auth_time");
  }

  async function loginAdmin(email, password, totp_code = null) {
    const payload = { email, password };
    if (totp_code) payload.totp_code = totp_code;
    const session = await window.GasQApi.post("/admin/login", payload);
    if (session.requires_2fa) {
      return { requires_2fa: true };
    }
    const data = setAdminSession(session);
    return data;
  }

  async function logoutAdmin() {
    const session = getAdminSession();
    try {
      await window.GasQApi.post("/auth/logout", { refresh_token: session?.refresh_token });
    } catch (_) {}
    clearAdminSession();
    window.location.href = "/admin.html";
  }

  function requireCustomer(redirectTo = "/customer.html") {
    const session = getCustomerSession();
    if (!session || !session.access_token) {
      window.location.href = redirectTo;
      return null;
    }
    return session;
  }

  function requireDealer(redirectTo = "/dealer-dashboard.html") {
    const session = getDealerSession();
    if (!session || !session.access_token) {
      window.location.href = redirectTo;
      return null;
    }
    return session;
  }

  async function getAuthConfig() {
    try {
      return await window.GasQApi.get("/auth/config");
    } catch (_) {
      return { google_client_id: "", phone_otp_enabled: false };
    }
  }

  function loadGoogleGsiScript() {
    return new Promise((resolve, reject) => {
      if (window.google?.accounts?.id) {
        resolve();
        return;
      }
      const existing = document.querySelector('script[src*="accounts.google.com/gsi/client"]');
      if (existing) {
        existing.addEventListener("load", () => resolve());
        existing.addEventListener("error", () => reject(new Error("Failed to load Google Sign-In script")));
        return;
      }
      const script = document.createElement("script");
      script.src = "https://accounts.google.com/gsi/client";
      script.async = true;
      script.defer = true;
      script.onload = () => resolve();
      script.onerror = () => reject(new Error("Failed to load Google Sign-In script"));
      document.head.appendChild(script);
    });
  }

  async function setupGoogleSignIn(containerElementId, onCredentialReceived) {
    const container = document.getElementById(containerElementId);
    if (!container) return;

    try {
      const config = await getAuthConfig();
      if (!config?.google_client_id) {
        // No client ID configured in env: show graceful placeholder
        container.innerHTML = `
          <div class="google-disabled-note muted">
            <small>Google Sign-In is configured via <code>GASQ_GOOGLE_CLIENT_ID</code> in .env.</small>
          </div>
        `;
        return;
      }

      await loadGoogleGsiScript();
      if (!window.google?.accounts?.id) return;

      window.google.accounts.id.initialize({
        client_id: config.google_client_id,
        callback: (response) => {
          if (response?.credential) {
            onCredentialReceived(response.credential);
          }
        },
      });

      container.innerHTML = "";
      window.google.accounts.id.renderButton(container, {
        theme: "outline",
        size: "large",
        shape: "rectangular",
        width: 320,
        text: "continue_with",
      });
    } catch (err) {
      console.warn("Google Sign-In initialization note:", err.message);
    }
  }

  // Customer Email OTP
  async function sendCustomerEmailOtp(email) {
    return await window.GasQApi.post("/customer/auth/otp/send", { email });
  }

  async function verifyCustomerEmailOtp(email, code) {
    const session = await window.GasQApi.post("/customer/auth/otp/verify", { email, code });
    return setCustomerSession(session);
  }

  // Customer Google Login
  async function loginCustomerWithGoogle(idToken) {
    const session = await window.GasQApi.post("/customer/auth/google", { id_token: idToken });
    return setCustomerSession(session);
  }

  // Customer Password Auth
  async function loginCustomerPassword(phone, password) {
    const session = await window.GasQApi.post("/customer/login", { phone, password });
    return setCustomerSession(session);
  }

  async function registerCustomerPassword(name, phone, password) {
    const session = await window.GasQApi.post("/customer/register", { name, phone, password });
    return setCustomerSession(session);
  }

  // Dealer Google Login
  async function loginDealerWithGoogle(idToken) {
    const session = await window.GasQApi.post("/dealer/auth/google", { id_token: idToken });
    return setDealerSession(session);
  }

  // Dealer Password Auth
  async function loginDealerPassword(username, password) {
    const session = await window.GasQApi.post("/dealer/login", { username, password });
    return setDealerSession(session);
  }

  async function registerDealerAccount(dealerData) {
    const session = await window.GasQApi.post("/dealer/register", dealerData);
    return setDealerSession(session);
  }

  // Update customer phone
  async function updateCustomerPhone(phone) {
    const normalized = normalizeNepalPhone(phone);
    const updated = await window.GasQApi.put("/customer/phone", { phone: normalized });
    const session = getCustomerSession();
    if (session) {
      session.phone = updated.phone;
      session.is_phone_verified = updated.is_phone_verified;
      localStorage.setItem(CUSTOMER_KEY, JSON.stringify(session));
    }
    return updated;
  }

  // Global logout
  async function logoutCustomer() {
    const session = getCustomerSession();
    if (session?.refresh_token) {
      try {
        await window.GasQApi.post("/auth/logout", { refresh_token: session.refresh_token });
      } catch (_) {}
    }
    clearCustomerSession();
    window.location.href = "/customer.html";
  }

  async function logoutDealer() {
    const session = getDealerSession();
    if (session?.refresh_token) {
      try {
        await window.GasQApi.post("/auth/logout", { refresh_token: session.refresh_token });
      } catch (_) {}
    }
    clearDealerSession();
    window.location.href = "/dealer-dashboard.html";
  }

  // Listen for auth expiration
  window.addEventListener("gasq:auth_expired", (event) => {
    if (event.detail?.type === "admin") {
      clearAdminSession();
      window.location.href = "/admin.html?expired=1";
    } else if (event.detail?.type === "customer" && window.location.pathname.includes("queue")) {
      window.location.href = "/customer.html";
    } else if (event.detail?.type === "dealer" && window.location.pathname.includes("dealer-dashboard")) {
      window.location.reload();
    }
  });

  return {
    isValidNepalPhone,
    normalizeNepalPhone,
    getCustomerSession,
    setCustomerSession,
    clearCustomerSession,
    getDealerSession,
    setDealerSession,
    clearDealerSession,
    getAdminSession,
    setAdminSession,
    clearAdminSession,
    loginAdmin,
    logoutAdmin,
    requireCustomer,
    requireDealer,
    getAuthConfig,
    setupGoogleSignIn,
    sendCustomerEmailOtp,
    verifyCustomerEmailOtp,
    loginCustomerWithGoogle,
    loginCustomerPassword,
    registerCustomerPassword,
    loginDealerWithGoogle,
    loginDealerPassword,
    registerDealerAccount,
    updateCustomerPhone,
    logoutCustomer,
    logoutDealer,
  };
})();

if (typeof window !== "undefined") {
  window.GasQAuth = GasQAuth;
}
