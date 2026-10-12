/**
 * GasQ Session Guard Module
 * Enforces client-side idle timeouts and absolute timeouts.
 * - Admin: 15 minutes idle, 4 hours absolute limit.
 * - Dealer: 30 minutes idle, 8 hours absolute limit.
 * Shows a warning popup 1 minute before expiry with "Stay logged in" and "Logout".
 * Resets idle timer on user activity (clicks, typing, API calls).
 */

(() => {
  const SESSION_CONFIGS = {
    admin: {
      idleTimeoutMs: 15 * 60 * 1000,      // 15 minutes
      absTimeoutMs: 4 * 60 * 60 * 1000,   // 4 hours
      loginUrl: "/admin.html",
      role: "admin",
    },
    dealer: {
      idleTimeoutMs: 30 * 60 * 1000,      // 30 minutes
      absTimeoutMs: 8 * 60 * 60 * 1000,   // 8 hours
      loginUrl: "/dealer-dashboard.html",
      role: "dealer",
    },
  };

  const WARNING_BEFORE_MS = 60 * 1000; // 1 minute warning
  const CHECK_INTERVAL_MS = 1000;      // 1 second tick

  let currentRole = null;
  let loginTimestamp = null;
  let lastActivityTimestamp = null;
  let warningModal = null;
  let isWarningVisible = false;
  let checkTimer = null;

  function initSessionGuard(role) {
    if (!SESSION_CONFIGS[role]) return;
    currentRole = role;

    const storedAuthTime = sessionStorage.getItem(`gasq_${role}_auth_time`);
    const now = Date.now();

    if (!storedAuthTime) {
      sessionStorage.setItem(`gasq_${role}_auth_time`, String(now));
      loginTimestamp = now;
    } else {
      loginTimestamp = Number(storedAuthTime);
    }

    lastActivityTimestamp = now;

    setupActivityListeners();
    createWarningModal();

    if (checkTimer) clearInterval(checkTimer);
    checkTimer = setInterval(checkSessionTimeouts, CHECK_INTERVAL_MS);
  }

  function resetIdleTimer() {
    lastActivityTimestamp = Date.now();
    if (isWarningVisible) {
      hideWarningModal();
    }
  }

  function setupActivityListeners() {
    const activityEvents = ["click", "keydown", "mousemove", "scroll", "touchstart"];
    let throttleTimeout = null;

    const onUserActivity = () => {
      if (!throttleTimeout) {
        throttleTimeout = setTimeout(() => {
          resetIdleTimer();
          throttleTimeout = null;
        }, 1000);
      }
    };

    activityEvents.forEach((evt) => {
      window.addEventListener(evt, onUserActivity, { passive: true });
    });
  }

  function createWarningModal() {
    if (document.getElementById("sessionWarningModal")) return;

    const modal = document.createElement("div");
    modal.id = "sessionWarningModal";
    modal.style.cssText = `
      position: fixed;
      inset: 0;
      background: rgba(17, 24, 39, 0.7);
      backdrop-filter: blur(4px);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 10000;
      padding: 16px;
      font-family: Inter, system-ui, sans-serif;
    `;

    modal.innerHTML = `
      <div style="
        background: #ffffff;
        border-radius: 12px;
        padding: 28px;
        max-width: 440px;
        width: 100%;
        box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.2);
        border: 1px solid #e5e7eb;
        text-align: center;
      ">
        <div style="
          width: 48px;
          height: 48px;
          border-radius: 50%;
          background: #fffbeb;
          color: #d97706;
          display: flex;
          align-items: center;
          justify-content: center;
          margin: 0 auto 16px;
        ">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"></circle>
            <polyline points="12 6 12 12 16 14"></polyline>
          </svg>
        </div>
        <h3 style="margin: 0 0 8px; font-size: 1.25rem; font-weight: 700; color: #111827;">Your session will expire</h3>
        <p style="margin: 0 0 20px; font-size: 0.875rem; color: #6b7280; line-height: 1.5;">
          You will be logged out in <strong id="sessionRemainingSecs" style="color: #d97706;">60</strong> seconds due to inactivity. Stay logged in?
        </p>
        <div style="display: flex; gap: 12px;">
          <button id="stayLoggedInBtn" type="button" style="
            flex: 1;
            height: 44px;
            background: #2563eb;
            color: #ffffff;
            font-weight: 600;
            border-radius: 8px;
            border: none;
            cursor: pointer;
            font-size: 0.9375rem;
          ">Stay Logged In</button>
          <button id="sessionLogoutBtn" type="button" style="
            flex: 1;
            height: 44px;
            background: #ffffff;
            color: #374151;
            border: 1px solid #d1d5db;
            font-weight: 600;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.9375rem;
          ">Logout</button>
        </div>
      </div>
    `;

    document.body.appendChild(modal);
    warningModal = modal;

    modal.querySelector("#stayLoggedInBtn")?.addEventListener("click", async () => {
      hideWarningModal();
      resetIdleTimer();
      // Trigger a refresh call to keep backend session alive
      try {
        if (window.GasQApi) {
          await window.GasQApi.post("/auth/refresh");
        }
      } catch (_) {}
    });

    modal.querySelector("#sessionLogoutBtn")?.addEventListener("click", () => {
      terminateSession(false);
    });
  }

  function showWarningModal(secondsLeft) {
    if (!warningModal) return;
    const remainingEl = warningModal.querySelector("#sessionRemainingSecs");
    if (remainingEl) remainingEl.textContent = String(Math.max(1, secondsLeft));
    warningModal.style.display = "flex";
    isWarningVisible = true;
  }

  function hideWarningModal() {
    if (warningModal) warningModal.style.display = "none";
    isWarningVisible = false;
  }

  function terminateSession(isExpired = true) {
    if (checkTimer) clearInterval(checkTimer);
    sessionStorage.removeItem(`gasq_${currentRole}_auth_time`);

    if (currentRole === "admin") {
      window.GasQAuth?.logoutAdmin();
    } else if (currentRole === "dealer") {
      window.GasQAuth?.logoutDealer();
    }

    const config = SESSION_CONFIGS[currentRole];
    const redirectUrl = config ? `${config.loginUrl}?expired=${isExpired ? "1" : "0"}` : "/";
    window.location.href = redirectUrl;
  }

  function checkSessionTimeouts() {
    if (!currentRole || !loginTimestamp || !lastActivityTimestamp) return;

    const config = SESSION_CONFIGS[currentRole];
    const now = Date.now();

    const idleElapsed = now - lastActivityTimestamp;
    const absElapsed = now - loginTimestamp;

    const idleRemaining = config.idleTimeoutMs - idleElapsed;
    const absRemaining = config.absTimeoutMs - absElapsed;

    const minRemaining = Math.min(idleRemaining, absRemaining);

    // Timeout reached
    if (minRemaining <= 0) {
      terminateSession(true);
      return;
    }

    // 1 minute before expiry warning
    if (minRemaining <= WARNING_BEFORE_MS) {
      showWarningModal(Math.ceil(minRemaining / 1000));
    } else if (isWarningVisible) {
      hideWarningModal();
    }
  }

  window.GasQSessionGuard = {
    init: initSessionGuard,
    resetIdle: resetIdleTimer,
    terminate: terminateSession,
  };
})();
