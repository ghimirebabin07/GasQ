/**
 * GasQ Dealer Dashboard Portal Module
 * Powers the dedicated dealer-dashboard.html page.
 * Manages live queue calling, serving, no-shows, and stock updates.
 */

let dealerProfile = null;
let pollTimer = null;
let toastTimeout = null;

document.addEventListener("DOMContentLoaded", () => {
  initDealerDashboard();
});

function setMessage(text, isSuccess = false) {
  const message = document.getElementById("message");
  if (!message) return;

  if (toastTimeout) clearTimeout(toastTimeout);

  if (!text) {
    message.textContent = "";
    message.className = "dealer-toast-msg";
    return;
  }

  message.textContent = text;
  message.className = isSuccess ? "dealer-toast-msg success-msg" : "dealer-toast-msg";

  toastTimeout = setTimeout(() => {
    message.textContent = "";
    message.className = "dealer-toast-msg";
  }, 4500);
}

async function initDealerDashboard() {
  const session = window.GasQAuth?.getDealerSession();

  // Auth Guard: If not logged in, redirect to dealer login page
  if (!session?.access_token) {
    window.location.href = "/dealer-login.html";
    return;
  }

  // Initialize session timeout guard for dealer
  window.GasQSessionGuard?.init("dealer");

  // Load dashboard data
  await loadDealerDashboard();

  // Start 15s auto-poll
  if (!pollTimer) {
    pollTimer = setInterval(loadDealerDashboard, 15000);
  }

  // Bind Topbar Actions
  document.getElementById("refreshDashboard")?.addEventListener("click", loadDealerDashboard);
  document.getElementById("logoutButton")?.addEventListener("click", () => {
    if (pollTimer) clearInterval(pollTimer);
    window.GasQAuth?.logoutDealer();
  });
}

async function loadDealerDashboard() {
  setMessage("");
  try {
    // 1. Fetch current dealer profile
    dealerProfile = await window.GasQApi.get("/dealer/me");

    // Update depot name in header
    const title = document.getElementById("dashboardTitle");
    if (title && dealerProfile?.name) {
      title.textContent = dealerProfile.name;
    }

    // 2. Check approval status
    const statusBanner = document.getElementById("dealerApprovalBanner");
    const actionsSection = document.getElementById("dealerActionsSection");

    if (dealerProfile.status === "PENDING") {
      if (statusBanner) {
        statusBanner.hidden = false;
        statusBanner.className = "dealer-alert warning";
        statusBanner.innerHTML = `
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="12" y1="8" x2="12" y2="12"></line>
            <line x1="12" y1="16" x2="12.01" y2="16"></line>
          </svg>
          <div>
            <strong>Shop Status: Pending Approval</strong>
            <p>Your shop registration is under administrative review. Customers will be able to see your shop and join the queue once approved.</p>
          </div>
        `;
      }
      if (actionsSection) actionsSection.style.display = "none";
      return;
    } else if (dealerProfile.status === "SUSPENDED") {
      if (statusBanner) {
        statusBanner.hidden = false;
        statusBanner.className = "dealer-alert danger";
        statusBanner.innerHTML = `
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="15" y1="9" x2="9" y2="15"></line>
            <line x1="9" y1="9" x2="15" y2="15"></line>
          </svg>
          <div>
            <strong>Shop Status: Suspended</strong>
            <p>This shop is currently suspended. Please contact GasQ administration support.</p>
          </div>
        `;
      }
      if (actionsSection) actionsSection.style.display = "none";
      return;
    } else {
      if (statusBanner) statusBanner.hidden = true;
      if (actionsSection) actionsSection.style.display = "block";
    }

    // 3. Fetch dashboard operations data
    const dashboard = await window.GasQApi.get("/dealer/me/dashboard");

    // Populate 4 Stat Cards
    const availCyl = document.getElementById("availableCylinders");
    if (availCyl) availCyl.textContent = dashboard.available_cylinders ?? "-";

    const currServ = document.getElementById("currentServing");
    if (currServ) currServ.textContent = dashboard.current_serving_token ? `#${dashboard.current_serving_token}` : "-";

    const waitCount = document.getElementById("waitingCount");
    if (waitCount) waitCount.textContent = dashboard.waiting_count ?? 0;

    const soldCount = document.getElementById("cylindersSoldToday");
    if (soldCount) soldCount.textContent = dashboard.cylinders_sold_today ?? 0;

    // Current stock banner
    const currentStockDisplay = document.getElementById("currentStockDisplay");
    if (currentStockDisplay) {
      currentStockDisplay.textContent = `${dashboard.available_cylinders ?? 0} Cylinders`;
    }

    // Low stock warning check: ONLY show when stock is strictly less than 10
    const lowStockWarning = document.getElementById("lowStockWarning");
    const lowStockCount = document.getElementById("lowStockCount");
    if (lowStockWarning) {
      const stock = Number(dashboard.available_cylinders);
      if (!isNaN(stock) && stock < 10) {
        lowStockWarning.style.display = "flex";
        lowStockWarning.hidden = false;
        if (lowStockCount) lowStockCount.textContent = String(stock);
      } else {
        lowStockWarning.style.display = "none";
        lowStockWarning.hidden = true;
      }
    }

    // Populate stock form input if user is not currently editing it
    const stockInput = document.getElementById("stockInput");
    if (stockInput && !stockInput.matches(":focus")) {
      stockInput.value = dashboard.available_cylinders;
    }

    // Render Customer Queue Table
    renderQueueList(dashboard.queue, dashboard.dealer_id);

    // Bind stock form and Call Next button
    setupStockForm(dashboard.dealer_id);
    setupCallNextButton(dashboard.dealer_id, dashboard.current_called_token_id);
  } catch (err) {
    setMessage(err.message);
  }
}

function setupStockForm(dealerId) {
  const stockForm = document.getElementById("stockForm");
  const stockInput = document.getElementById("stockInput");

  // Quick Add Chips (+5, +10, +25, +50)
  const quickChips = document.querySelectorAll(".quick-stock-chip");
  quickChips.forEach((chip) => {
    if (!chip.dataset.bound) {
      chip.dataset.bound = "true";
      chip.addEventListener("click", () => {
        const addAmount = Number(chip.getAttribute("data-add")) || 0;
        const currentVal = Number(stockInput.value) || 0;
        stockInput.value = Math.min(10000, currentVal + addAmount);
      });
    }
  });

  if (!stockForm || stockForm.dataset.bound) return;
  stockForm.dataset.bound = "true";

  stockForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    setMessage("");

    const newStock = Number(stockInput.value);
    if (!Number.isInteger(newStock) || newStock < 0 || newStock > 10000) {
      setMessage("Stock must be a whole number between 0 and 10000.");
      return;
    }

    const submitBtn = stockForm.querySelector('button[type="submit"]');
    const originalText = submitBtn.textContent;
    submitBtn.disabled = true;
    submitBtn.textContent = "Updating...";

    try {
      await window.GasQApi.patch(`/dealer/${dealerId}/stock`, {
        available_cylinders: newStock,
      });
      setMessage("Cylinder stock updated successfully.", true);
      await loadDealerDashboard();
    } catch (err) {
      setMessage(err.message);
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = originalText;
    }
  });
}

function setupCallNextButton(dealerId, currentCalledTokenId) {
  const callNextBtn = document.getElementById("callNext");
  if (!callNextBtn || callNextBtn.dataset.bound) return;
  callNextBtn.dataset.bound = "true";

  callNextBtn.addEventListener("click", async () => {
    setMessage("");
    callNextBtn.disabled = true;
    callNextBtn.innerHTML = `
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"></circle>
        <line x1="12" y1="6" x2="12" y2="12"></line>
      </svg>
      <span>Calling...</span>
    `;

    try {
      const called = await window.GasQApi.post(`/dealer/${dealerId}/call-next`);
      setMessage(`Token #${called.token_number} called! Customer notified.`, true);
      await loadDealerDashboard();
    } catch (err) {
      setMessage(err.message);
    } finally {
      callNextBtn.disabled = false;
      callNextBtn.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polygon points="5 3 19 12 5 21 5 3"></polygon>
        </svg>
        <span>Serve Next</span>
      `;
    }
  });
}

function renderQueueList(queue, dealerId) {
  const queueList = document.getElementById("queueList");
  if (!queueList) return;

  if (!queue || queue.length === 0) {
    queueList.innerHTML = `
      <div class="queue-empty-box">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
          <circle cx="9" cy="7" r="4"></circle>
          <path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>
          <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
        </svg>
        <p class="muted" style="margin: 0; font-size: 0.9375rem;">No customers waiting.</p>
      </div>
    `;
    return;
  }

  // Render Table
  let tableHtml = `
    <table class="queue-table">
      <thead>
        <tr>
          <th>Token No.</th>
          <th>Customer Name</th>
          <th>Phone</th>
          <th>Status</th>
          <th style="text-align: right;">Actions</th>
        </tr>
      </thead>
      <tbody>
  `;

  queue.forEach((item) => {
    const isCalled = item.status === "CALLED";
    const customerDisplay = window.GasQApi.escapeHtml(item.customer_name);
    const phoneDisplay = window.GasQApi.escapeHtml(item.customer_phone || "No phone");

    let statusBadge = "";
    if (isCalled) {
      statusBadge = `<span class="queue-status-badge serving">Serving</span>`;
    } else if (item.status === "WAITING") {
      statusBadge = `<span class="queue-status-badge waiting">Waiting</span>`;
    } else {
      statusBadge = `<span class="queue-status-badge">${item.status}</span>`;
    }

    let actionButtons = "";
    if (isCalled) {
      actionButtons = `
        <div class="queue-table-actions">
          <button class="dealer-btn btn-primary btn-sm serve-btn" data-id="${item.id}" type="button">Mark Done</button>
          <button class="dealer-btn btn-secondary btn-sm noshow-btn" data-id="${item.id}" type="button">No-Show</button>
          <button class="dealer-btn btn-secondary btn-sm skip-btn" data-id="${item.id}" type="button">Skip</button>
        </div>
      `;
    } else {
      actionButtons = `
        <div class="queue-table-actions">
          <span style="font-size: 0.8125rem; color: var(--dealer-muted); font-weight: 500;">In Line</span>
        </div>
      `;
    }

    tableHtml += `
      <tr class="${isCalled ? "row-called" : ""}">
        <td>
          <span class="queue-token-pill">#${item.token_number}</span>
        </td>
        <td>
          <strong style="color: var(--dealer-text);">${customerDisplay}</strong>
        </td>
        <td>
          <span style="color: var(--dealer-text-secondary);">${phoneDisplay}</span>
        </td>
        <td>${statusBadge}</td>
        <td>${actionButtons}</td>
      </tr>
    `;
  });

  tableHtml += `
      </tbody>
    </table>
  `;

  queueList.innerHTML = tableHtml;

  // Bind row action listeners for called tokens
  queue.forEach((item) => {
    if (item.status === "CALLED") {
      const row = queueList.querySelector(`.serve-btn[data-id="${item.id}"]`)?.closest("tr");
      if (!row) return;

      row.querySelector(".serve-btn")?.addEventListener("click", async () => {
        try {
          await window.GasQApi.post(`/dealer/${dealerId}/token/${item.id}/serve`);
          setMessage(`Token #${item.token_number} completed. Cylinder handed over.`, true);
          await loadDealerDashboard();
        } catch (err) {
          setMessage(err.message);
        }
      });

      row.querySelector(".noshow-btn")?.addEventListener("click", async () => {
        try {
          await window.GasQApi.post(`/dealer/${dealerId}/token/${item.id}/no-show`);
          setMessage(`Token #${item.token_number} marked No-Show. Cylinder returned to stock.`, true);
          await loadDealerDashboard();
        } catch (err) {
          setMessage(err.message);
        }
      });

      row.querySelector(".skip-btn")?.addEventListener("click", async () => {
        try {
          await window.GasQApi.post(`/dealer/${dealerId}/token/${item.id}/skip`);
          setMessage(`Token #${item.token_number} skipped.`, true);
          await loadDealerDashboard();
        } catch (err) {
          setMessage(err.message);
        }
      });
    }
  });
}
