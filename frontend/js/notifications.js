/**
 * GasQ Real-Time Notifications Module
 * Handles Server-Sent Events (SSE) stream, fallback polling, unread badges,
 * notification panel drawer, and audio alert on call.
 */

const GasQNotifications = (() => {
  let eventSource = null;
  let pollInterval = null;
  let isPanelOpen = false;

  function playAlertChime() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(587.33, ctx.currentTime); // D5
      osc.frequency.setValueAtTime(880.00, ctx.currentTime + 0.15); // A5
      gain.gain.setValueAtTime(0.2, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.6);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.65);
    } catch (_) {}
  }

  function getSession() {
    return window.GasQAuth?.getCustomerSession();
  }

  async function fetchUnreadCount() {
    const session = getSession();
    if (!session?.access_token) return 0;
    try {
      const data = await window.GasQApi.get("/customer/notifications/unread-count");
      updateBadgeUI(data.unread_count || 0);
      return data.unread_count || 0;
    } catch (_) {
      return 0;
    }
  }

  function updateBadgeUI(count) {
    const badge = document.getElementById("notificationBadge");
    if (!badge) return;
    if (count > 0) {
      badge.textContent = count > 99 ? "99+" : String(count);
      badge.style.display = "inline-flex";
    } else {
      badge.style.display = "none";
    }
  }

  function renderNotificationItem(item) {
    const isUnread = !item.read_at;
    const timeFormatted = item.created_at ? new Date(item.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
    return `
      <div class="notification-item ${isUnread ? "unread" : ""}" data-id="${item.id}">
        <div class="notification-item-header">
          <strong>${window.GasQApi.escapeHtml(item.title)}</strong>
          <span class="muted"><small>${timeFormatted}</small></span>
        </div>
        <p>${window.GasQApi.escapeHtml(item.message)}</p>
        ${isUnread ? `<button class="mark-read-btn" data-id="${item.id}">Mark read</button>` : ""}
      </div>
    `;
  }

  async function openNotificationPanel() {
    let panel = document.getElementById("gasqNotificationPanel");
    if (!panel) return;

    panel.classList.add("open");
    isPanelOpen = true;

    const listContainer = document.getElementById("gasqNotificationList");
    if (!listContainer) return;

    listContainer.innerHTML = '<p class="muted" style="padding:16px;">Loading notifications...</p>';

    try {
      const notifications = await window.GasQApi.get("/customer/notifications");
      if (!notifications || notifications.length === 0) {
        listContainer.innerHTML = '<p class="muted" style="padding:16px;">No notifications yet.</p>';
      } else {
        listContainer.innerHTML = notifications.map(renderNotificationItem).join("");
        // Attach click handlers to mark read buttons
        listContainer.querySelectorAll(".mark-read-btn").forEach((btn) => {
          btn.addEventListener("click", async (e) => {
            const id = e.target.getAttribute("data-id");
            try {
              await window.GasQApi.post(`/customer/notifications/${id}/read`);
              const parent = e.target.closest(".notification-item");
              if (parent) {
                parent.classList.remove("unread");
                e.target.remove();
              }
              await fetchUnreadCount();
            } catch (_) {}
          });
        });
      }
    } catch (err) {
      listContainer.innerHTML = `<p class="message" style="padding:16px;">${window.GasQApi.escapeHtml(err.message)}</p>`;
    }
  }

  function closeNotificationPanel() {
    const panel = document.getElementById("gasqNotificationPanel");
    if (panel) panel.classList.remove("open");
    isPanelOpen = false;
  }

  function injectNotificationUi() {
    // Inject bell icon into topbar if container exists or attach to topbar
    const topbar = document.querySelector(".topbar");
    if (topbar && !document.getElementById("notificationBell")) {
      const bellContainer = document.createElement("div");
      bellContainer.className = "notification-bell-container";
      bellContainer.innerHTML = `
        <button id="notificationBell" class="bell-button" type="button" aria-label="Notifications">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"></path>
            <path d="M13.73 21a2 2 0 0 1-3.46 0"></path>
          </svg>
          <span id="notificationBadge" class="notification-badge" style="display:none;">0</span>
        </button>
      `;

      // Insert before profile or at the right
      topbar.appendChild(bellContainer);

      document.getElementById("notificationBell")?.addEventListener("click", () => {
        if (isPanelOpen) {
          closeNotificationPanel();
        } else {
          openNotificationPanel();
        }
      });
    }

    // Inject drawer panel into body if not already present
    if (!document.getElementById("gasqNotificationPanel")) {
      const panel = document.createElement("aside");
      panel.id = "gasqNotificationPanel";
      panel.className = "notification-drawer";
      panel.innerHTML = `
        <div class="notification-drawer-header">
          <h3>Notifications</h3>
          <button id="closeNotificationDrawer" class="close-btn" type="button" aria-label="Close">&times;</button>
        </div>
        <div id="gasqNotificationList" class="notification-drawer-body"></div>
      `;
      document.body.appendChild(panel);

      document.getElementById("closeNotificationDrawer")?.addEventListener("click", closeNotificationPanel);

      // Close when clicking outside
      document.addEventListener("click", (e) => {
        if (isPanelOpen && !panel.contains(e.target) && !e.target.closest("#notificationBell")) {
          closeNotificationPanel();
        }
      });
    }
  }

  function startStream() {
    const session = getSession();
    if (!session?.access_token) return;

    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }

    try {
      const sseUrl = `/customer/notifications/stream?token=${encodeURIComponent(session.access_token)}`;
      eventSource = new EventSource(sseUrl);

      eventSource.addEventListener("notification", (event) => {
        try {
          const data = JSON.parse(event.data);
          fetchUnreadCount();

          // Play sound if token called
          if (data.type === "TOKEN_CALLED") {
            playAlertChime();
          }

          // Emit global window event
          window.dispatchEvent(new CustomEvent("gasq:notification", { detail: data }));
        } catch (_) {}
      });

      eventSource.addEventListener("error", () => {
        if (eventSource) {
          eventSource.close();
          eventSource = null;
        }
        // Will retry automatically on next interval or page focus
      });
    } catch (_) {}

    // Fallback unread count polling every 20 seconds
    if (!pollInterval) {
      pollInterval = setInterval(fetchUnreadCount, 20000);
    }
  }

  function init() {
    const session = getSession();
    if (!session) return;

    injectNotificationUi();
    fetchUnreadCount();
    startStream();
  }

  function destroy() {
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
    if (pollInterval) {
      clearInterval(pollInterval);
      pollInterval = null;
    }
  }

  return {
    init,
    destroy,
    fetchUnreadCount,
    openNotificationPanel,
    closeNotificationPanel,
    playAlertChime,
  };
})();

if (typeof window !== "undefined") {
  window.GasQNotifications = GasQNotifications;
}
