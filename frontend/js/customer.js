/**
 * GasQ Customer Module
 * Handles customer authentication, dealer discovery & filtering,
 * Nepal phone collection modal, and queue token issuance.
 */

document.addEventListener("DOMContentLoaded", () => {
  // 1. Check which page we are on
  const isAuthPage = document.getElementById("customerAuthSection") || document.getElementById("customerForm");
  const isDealersPage = document.getElementById("dealerGrid");

  if (isAuthPage) {
    initCustomerAuthPage();
  } else if (isDealersPage) {
    initDealersPage();
  }
});

function setMessage(text, isSuccess = false) {
  const message = document.getElementById("message");
  if (!message) return;
  message.textContent = text || "";
  message.className = isSuccess ? "message success-text" : "message";
}

// ========================================================
// CUSTOMER AUTH PAGE (customer.html)
// ========================================================
function initCustomerAuthPage() {
  const session = window.GasQAuth.getCustomerSession();
  if (session?.access_token) {
    // If already logged in, redirect to dealers list
    window.location.href = "/dealers.html";
    return;
  }

  // Phone + password login and registration
  const passwordForm = document.getElementById("customerPasswordForm");
  const registerBtn = document.getElementById("registerCustomerBtn");

  passwordForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    setMessage("");
    const phone = document.getElementById("phone").value.trim();
    const password = document.getElementById("password").value;

    const submitBtn = document.getElementById("loginCustomerBtn");
    submitBtn.disabled = true;
    try {
      await window.GasQAuth.loginCustomerPassword(phone, password);
      window.location.href = "/dealers.html";
    } catch (err) {
      submitBtn.disabled = false;
      setMessage(err.message);
    }
  });

  registerBtn?.addEventListener("click", async () => {
    setMessage("");
    const name = document.getElementById("name").value.trim();
    const phone = document.getElementById("phone").value.trim();
    const password = document.getElementById("password").value;

    if (!name || name.length < 2) {
      setMessage("Please provide your name (at least 2 characters).");
      return;
    }
    if (!phone) {
      setMessage("Please provide your phone number.");
      return;
    }
    if (!password || password.length < 8) {
      setMessage("Password must be at least 8 characters with letters and numbers.");
      return;
    }

    registerBtn.disabled = true;
    try {
      await window.GasQAuth.registerCustomerPassword(name, phone, password);
      window.location.href = "/dealers.html";
    } catch (err) {
      registerBtn.disabled = false;
      setMessage(err.message);
    }
  });
}

// ========================================================
// DEALERS DIRECTORY PAGE (dealers.html)
// ========================================================
async function initDealersPage() {
  const customer = window.GasQAuth.requireCustomer();
  if (!customer) return;

  // Initialize notifications
  window.GasQNotifications.init();

  // Render customer line in header or subtext
  const customerLine = document.getElementById("customerLine");
  if (customerLine) {
    const displayName = customer.name || customer.email || "Customer";
    const displayPhone = customer.phone ? `(${customer.phone})` : "(No phone set)";
    customerLine.innerHTML = `
      <span>Welcome, <strong>${window.GasQApi.escapeHtml(displayName)}</strong> ${displayPhone}</span>
      <button id="customerLogoutBtn" class="button secondary small" type="button" style="margin-left:12px;padding:4px 10px;min-height:auto;">Logout</button>
    `;
    document.getElementById("customerLogoutBtn")?.addEventListener("click", () => {
      window.GasQAuth.logoutCustomer();
    });
  }

  // Check for active token
  await checkActiveToken();

  // Load dealers
  await loadDealers();

  // Setup search and filter listeners
  document.getElementById("dealerSearch")?.addEventListener("input", filterDealers);
  document.getElementById("inStockOnly")?.addEventListener("change", filterDealers);
  document.getElementById("refreshDealers")?.addEventListener("click", loadDealers);
}

let loadedDealers = [];

async function checkActiveToken() {
  const banner = document.getElementById("activeTokenBanner");
  if (!banner) return;

  try {
    const res = await window.GasQApi.get("/customer/tokens/active");
    if (res?.has_active_token && res?.token?.token) {
      const t = res.token.token;
      const dealerName = res.token.dealer_name;
      banner.hidden = false;
      banner.innerHTML = `
        <div class="active-token-alert">
          <div>
            <strong>Active Token #${t.token_number} (${t.status})</strong>
            <p>You are queued at <strong>${window.GasQApi.escapeHtml(dealerName)}</strong>.</p>
          </div>
          <a href="/queue.html?token_id=${t.id}" class="button primary small">View My Token &rarr;</a>
        </div>
      `;
    } else {
      banner.hidden = true;
    }
  } catch (_) {
    banner.hidden = true;
  }
}

async function loadDealers() {
  const grid = document.getElementById("dealerGrid");
  if (!grid) return;

  grid.innerHTML = '<p class="muted">Loading LPG dealers...</p>';
  setMessage("");

  try {
    loadedDealers = await window.GasQApi.get("/dealers");
    filterDealers();
  } catch (err) {
    grid.innerHTML = "";
    setMessage(err.message);
  }
}

function filterDealers() {
  const grid = document.getElementById("dealerGrid");
  if (!grid) return;

  const searchTerm = (document.getElementById("dealerSearch")?.value || "").toLowerCase().trim();
  const inStockOnly = document.getElementById("inStockOnly")?.checked || false;

  const filtered = loadedDealers.filter((d) => {
    const matchesSearch =
      !searchTerm ||
      d.name.toLowerCase().includes(searchTerm) ||
      (d.address && d.address.toLowerCase().includes(searchTerm));
    const matchesStock = !inStockOnly || d.available_cylinders > 0;
    return matchesSearch && matchesStock;
  });

  grid.innerHTML = "";
  if (filtered.length === 0) {
    grid.innerHTML = '<p class="muted">No dealers matching your search criteria.</p>';
    return;
  }

  filtered.forEach((dealer) => {
    grid.appendChild(createDealerCard(dealer));
  });
}

function createDealerCard(dealer) {
  const card = document.createElement("article");
  card.className = "dealer-card";

  const outOfStock = dealer.available_cylinders <= 0;
  const estWaitMin = (dealer.people_waiting || 0) * 6; // ~6 min estimated per turn

  card.innerHTML = `
    <div>
      <h2>${window.GasQApi.escapeHtml(dealer.name)}</h2>
      <p class="muted">${window.GasQApi.escapeHtml(dealer.address)}</p>
      ${dealer.phone ? `<p class="muted"><small>📞 ${window.GasQApi.escapeHtml(dealer.phone)}</small></p>` : ""}
    </div>
    <span class="badge ${outOfStock ? "warning" : ""}">${window.GasQApi.escapeHtml(dealer.stock_message)}</span>
    <div class="dealer-meta">
      <span>People waiting: <strong>${dealer.people_waiting || 0}</strong></span>
      <span>Currently serving: <strong>${dealer.current_serving_token ?? "-"}</strong></span>
      <span>Estimated wait: <strong>~${estWaitMin} mins</strong></span>
    </div>
    <button class="button primary" type="button" ${outOfStock ? "disabled" : ""}>
      ${outOfStock ? "Out of Stock" : "Get Token"}
    </button>
  `;

  if (!outOfStock) {
    const btn = card.querySelector("button");
    btn.addEventListener("click", () => handleTakeToken(dealer, btn));
  }

  return card;
}

async function handleTakeToken(dealer, buttonElement) {
  setMessage("");
  const customer = window.GasQAuth.getCustomerSession();

  // If customer has no phone number, prompt modal first
  if (!customer?.phone) {
    promptNepalPhoneModal(async (phone) => {
      try {
        await window.GasQAuth.updateCustomerPhone(phone);
        await executeJoinQueue(dealer, buttonElement);
      } catch (err) {
        setMessage(err.message);
      }
    });
    return;
  }

  await executeJoinQueue(dealer, buttonElement);
}

async function executeJoinQueue(dealer, buttonElement) {
  if (buttonElement) {
    buttonElement.disabled = true;
    buttonElement.textContent = "Joining Queue...";
  }

  try {
    const status = await window.GasQApi.post("/queue/join", { dealer_id: dealer.id });
    localStorage.setItem("lpg_token_id", status.token.id);
    window.location.href = `/queue.html?token_id=${status.token.id}`;
  } catch (err) {
    if (buttonElement) {
      buttonElement.disabled = false;
      buttonElement.textContent = "Get Token";
    }
    setMessage(err.message);
  }
}

// Modal to collect Nepal phone number
function promptNepalPhoneModal(onConfirmed) {
  let modal = document.getElementById("nepalPhoneModal");
  if (!modal) {
    modal = document.createElement("div");
    modal.id = "nepalPhoneModal";
    modal.className = "modal-overlay";
    modal.innerHTML = `
      <div class="modal-card">
        <h3>Enter Mobile Number</h3>
        <p class="muted">A Nepal mobile number is required before receiving a queue token so the dealer can identify and call you.</p>
        <form id="nepalPhoneForm" class="form">
          <label>
            Nepal Mobile Number
            <input id="modalPhoneInput" type="tel" required placeholder="e.g. 9841234567 or +977 98..." pattern="^(\\+?977)?[9][78]\\d{8}$" title="Must be a valid 10-digit Nepal mobile number starting with 98 or 97.">
          </label>
          <p id="modalPhoneError" class="message"></p>
          <div class="action-row">
            <button id="modalPhoneSubmit" class="button primary" type="submit">Save &amp; Continue</button>
            <button id="modalPhoneCancel" class="button secondary" type="button">Cancel</button>
          </div>
        </form>
      </div>
    `;
    document.body.appendChild(modal);

    document.getElementById("modalPhoneCancel")?.addEventListener("click", () => {
      modal.classList.remove("open");
    });
  }

  const form = document.getElementById("nepalPhoneForm");
  const input = document.getElementById("modalPhoneInput");
  const error = document.getElementById("modalPhoneError");
  error.textContent = "";
  input.value = "";

  form.onsubmit = (e) => {
    e.preventDefault();
    error.textContent = "";
    const phone = input.value.trim();
    if (!window.GasQAuth.isValidNepalPhone(phone)) {
      error.textContent = "Please enter a valid 10-digit Nepal mobile number starting with 98 or 97.";
      return;
    }
    modal.classList.remove("open");
    onConfirmed(phone);
  };

  modal.classList.add("open");
  input.focus();
}
