let adminDealers = [];
let pendingSensitiveAction = null;

document.addEventListener("DOMContentLoaded", () => {
  checkSessionExpiredUrl();
  document.getElementById("adminLoginForm")?.addEventListener("submit", login);
  document.getElementById("refreshDealers")?.addEventListener("click", loadDealers);
  document.getElementById("adminLogout")?.addEventListener("click", () => window.GasQAuth.logoutAdmin());

  // Setup reauth modal listeners
  document.getElementById("reauthCancelBtn")?.addEventListener("click", () => {
    closeReauthModal();
  });

  document.getElementById("reauthForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    await handleReauthConfirm();
  });

  initAdminPage();
});

function checkSessionExpiredUrl() {
  const urlParams = new URLSearchParams(window.location.search);
  const alertEl = document.getElementById("sessionExpiredAlert");
  if (urlParams.get("expired") === "1" && alertEl) {
    alertEl.style.display = "block";
  }
}

function setAdminMessage(text, success = false) {
  const message = document.getElementById("adminMessage");
  if (!message) return;
  message.textContent = text || "";
  message.className = success ? "message success-text" : "message";
}

function setAdminView(isAuthenticated) {
  const loginPanel = document.getElementById("adminLoginPanel");
  const adminPanel = document.getElementById("adminPanel");
  const logoutBtn = document.getElementById("adminLogout");

  if (loginPanel) loginPanel.hidden = isAuthenticated;
  if (adminPanel) adminPanel.hidden = !isAuthenticated;
  if (logoutBtn) logoutBtn.hidden = !isAuthenticated;

  if (isAuthenticated) {
    window.GasQSessionGuard?.init("admin");
    const alertEl = document.getElementById("sessionExpiredAlert");
    if (alertEl) alertEl.style.display = "none";
  }
}

async function initAdminPage() {
  const session = window.GasQAuth.getAdminSession();
  setAdminView(Boolean(session?.access_token));
  if (session?.access_token) {
    await loadDealers();
  }
}

async function login(event) {
  event.preventDefault();
  setAdminMessage("");

  const email = document.getElementById("adminEmail")?.value.trim();
  const password = document.getElementById("adminPassword")?.value;
  const totpCode = document.getElementById("adminTotp")?.value.trim();

  const button = document.getElementById("adminLoginBtn");
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "Signing in...";

  try {
    const result = await window.GasQAuth.loginAdmin(email, password, totpCode || null);

    if (result?.requires_2fa) {
      const totpSection = document.getElementById("totpSection");
      if (totpSection) totpSection.style.display = "block";
      document.getElementById("adminTotp")?.focus();
      setAdminMessage("Two-factor authentication required. Please enter your 6-digit authenticator code.");
      return;
    }

    setAdminView(true);
    await loadDealers();
  } catch (error) {
    setAdminMessage(error.message || "Invalid credentials.");
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
}

async function loadDealers() {
  setAdminMessage("");
  try {
    adminDealers = await window.GasQApi.get("/admin/dealers");
    renderDealers();
  } catch (error) {
    if (error.status === 401) {
      window.GasQAuth.clearAdminSession();
      setAdminView(false);
      window.location.replace("/admin.html?expired=1");
      return;
    }
    setAdminMessage(error.message);
  }
}

function renderDealers() {
  const list = document.getElementById("adminDealerList");
  if (!list) return;
  if (!adminDealers.length) {
    list.innerHTML = '<p class="muted">No dealer accounts found.</p>';
    return;
  }

  list.innerHTML = adminDealers.map((dealer) => {
    const isApproved = dealer.status === "APPROVED" && dealer.is_active;
    const action = isApproved ? "Suspend" : "Approve";
    const actionClass = isApproved ? "danger" : "primary";
    return `
      <article class="queue-row">
        <div>
          <strong>${window.GasQApi.escapeHtml(dealer.name)}</strong>
          <div class="queue-meta">ID: ${dealer.id} · ${window.GasQApi.escapeHtml(dealer.username || "No username")}</div>
        </div>
        <div class="queue-meta">
          <span>${window.GasQApi.escapeHtml(dealer.email || "No email")}</span>
          <span class="badge ${isApproved ? "" : "warning"}">${window.GasQApi.escapeHtml(dealer.status)}</span>
        </div>
        <button class="button small ${actionClass}" type="button" data-dealer-id="${dealer.id}" data-action="${action}">
          ${action}
        </button>
      </article>
    `;
  }).join("");

  list.querySelectorAll("[data-dealer-id]").forEach((button) => {
    button.addEventListener("click", () => {
      openReauthModal(Number(button.dataset.dealerId), button.dataset.action);
    });
  });
}

function openReauthModal(dealerId, action) {
  pendingSensitiveAction = { dealerId, action };
  const modal = document.getElementById("reauthModal");
  const input = document.getElementById("reauthPasswordInput");
  if (modal) modal.classList.add("open");
  if (input) {
    input.value = "";
    input.focus();
  }
}

function closeReauthModal() {
  pendingSensitiveAction = null;
  const modal = document.getElementById("reauthModal");
  if (modal) modal.classList.remove("open");
}

async function handleReauthConfirm() {
  if (!pendingSensitiveAction) return;

  const passwordInput = document.getElementById("reauthPasswordInput");
  const password = passwordInput?.value;
  if (!password) return;

  const { dealerId, action } = pendingSensitiveAction;
  const verb = action.toLowerCase();
  const confirmBtn = document.getElementById("reauthConfirmBtn");
  confirmBtn.disabled = true;

  setAdminMessage("");
  try {
    // Send sensitive action with admin password confirmation header
    await window.GasQApi.post(
      `/admin/dealers/${dealerId}/${verb}`,
      {},
      { headers: { "X-Admin-Password": password } }
    );
    closeReauthModal();
    setAdminMessage(`Dealer ${dealerId} ${verb}d successfully.`, true);
    await loadDealers();
  } catch (error) {
    setAdminMessage(error.message || "Invalid confirmation password.");
  } finally {
    confirmBtn.disabled = false;
  }
}
