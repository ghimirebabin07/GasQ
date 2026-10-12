/**
 * GasQ Queue Tracking Module
 * Real-time queue tracker for customers with SSE listeners,
 * audio chime on call, estimated wait time, and token cancellation.
 */

document.addEventListener("DOMContentLoaded", () => {
  const customer = window.GasQAuth?.requireCustomer();
  if (!customer) return;

  // Initialize notifications
  window.GasQNotifications?.init();

  // Listen to real-time notification events from SSE to instantly update status
  window.addEventListener("gasq:notification", (event) => {
    const data = event.detail;
    if (data?.type === "TOKEN_CALLED" || data?.type === "TOKEN_REMINDER") {
      loadQueueStatus();
    }
  });

  const refreshBtn = document.getElementById("refreshQueue");
  const cancelBtn = document.getElementById("cancelToken");

  refreshBtn?.addEventListener("click", loadQueueStatus);
  cancelBtn?.addEventListener("click", handleCancelToken);

  loadQueueStatus();

  // 10-second polling fallback
  setInterval(loadQueueStatus, 10000);
});

function tokenIdFromPage() {
  const params = new URLSearchParams(window.location.search);
  return params.get("token_id") || localStorage.getItem("lpg_token_id");
}

function setMessage(text, isSuccess = false) {
  const message = document.getElementById("message");
  if (!message) return;
  message.textContent = text || "";
  message.className = isSuccess ? "message success-text" : "message";
}

let currentTokenData = null;

async function loadQueueStatus() {
  let tokenId = tokenIdFromPage();

  // If no tokenId in query or localStorage, check for active token via API
  if (!tokenId) {
    try {
      const active = await window.GasQApi.get("/customer/tokens/active");
      if (active?.has_active_token && active?.token?.token?.id) {
        tokenId = active.token.token.id;
        localStorage.setItem("lpg_token_id", tokenId);
      }
    } catch (_) {}
  }

  if (!tokenId) {
    setMessage("No token selected. Please choose a dealer first.");
    document.getElementById("statusMessage").textContent = "No active queue token found.";
    return;
  }

  try {
    const status = await window.GasQApi.get(`/queue/${tokenId}`);
    currentTokenData = status;

    document.getElementById("tokenTitle").textContent = `Token #${status.token.token_number}`;
    document.getElementById("dealerName").textContent = status.dealer_name;
    document.getElementById("currentServing").textContent = status.current_serving_token ?? "-";
    document.getElementById("peopleAhead").textContent = status.people_ahead;

    const estWaitMin = (status.people_ahead || 0) * 6;
    const estWaitElem = document.getElementById("estimatedWait");
    if (estWaitElem) {
      estWaitElem.textContent = status.token.status === "CALLED" ? "Now!" : `~${estWaitMin} mins`;
    }

    // Format status and message banner
    const statusBadge = document.getElementById("tokenStatus");
    const statusMsg = document.getElementById("statusMessage");
    const cancelBtn = document.getElementById("cancelToken");

    statusBadge.textContent = status.token.status;
    statusBadge.className = `badge status-${status.token.status.toLowerCase()}`;

    statusMsg.textContent = status.message;
    statusMsg.className = `status-message status-banner-${status.token.status.toLowerCase()}`;

    // Enable cancel only if waiting
    if (cancelBtn) {
      cancelBtn.disabled = status.token.status !== "WAITING";
      cancelBtn.style.display = (status.token.status === "WAITING" || status.token.status === "CALLED") ? "inline-flex" : "none";
    }

    // Show find new dealer link if terminal
    const terminalRow = document.getElementById("terminalActionRow");
    if (terminalRow) {
      const isTerminal = ["SERVED", "CANCELLED", "NO_SHOW", "SKIPPED"].includes(status.token.status);
      terminalRow.hidden = !isTerminal;
    }

    setMessage("");
  } catch (err) {
    setMessage(err.message);
  }
}

async function handleCancelToken() {
  const tokenId = tokenIdFromPage();
  if (!tokenId) return;

  if (!confirm("Are you sure you want to cancel this token? You will lose your position in queue.")) {
    return;
  }

  const cancelBtn = document.getElementById("cancelToken");
  if (cancelBtn) cancelBtn.disabled = true;

  try {
    await window.GasQApi.post(`/queue/${tokenId}/cancel`);
    setMessage("Token successfully cancelled.", true);
    localStorage.removeItem("lpg_token_id");
    await loadQueueStatus();
  } catch (err) {
    if (cancelBtn) cancelBtn.disabled = false;
    setMessage(err.message);
  }
}
