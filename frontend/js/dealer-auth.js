/**
 * GasQ Dealer Authentication Helper
 * Manages dedicated dealer-login.html and dealer-register.html pages.
 */

document.addEventListener("DOMContentLoaded", () => {
  // If already logged in, redirect straight to dashboard
  const session = window.GasQAuth?.getDealerSession();
  if (session?.access_token) {
    window.location.href = "/dealer-dashboard.html";
    return;
  }

  initLoginForm();
  initRegisterForm();
});

function showAuthMessage(text, isSuccess = false) {
  const message = document.getElementById("message");
  if (!message) return;
  message.textContent = text || "";
  message.className = isSuccess ? "dealer-toast-msg success-msg" : "dealer-toast-msg";
  if (text) {
    setTimeout(() => {
      message.textContent = "";
      message.className = "dealer-toast-msg";
    }, 4500);
  }
}

function initLoginForm() {
  const loginForm = document.getElementById("loginForm");
  if (!loginForm) return;

  // Toggle Password Visibility
  const toggleBtn = document.getElementById("toggleLoginPassword");
  toggleBtn?.addEventListener("click", () => {
    const passwordInput = document.getElementById("loginPassword");
    if (!passwordInput) return;
    const isPassword = passwordInput.getAttribute("type") === "password";
    passwordInput.setAttribute("type", isPassword ? "text" : "password");

    const eyeIcon = document.getElementById("eyeIcon");
    if (eyeIcon) {
      if (isPassword) {
        eyeIcon.innerHTML = `
          <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path>
          <line x1="1" y1="1" x2="23" y2="23"></line>
        `;
      } else {
        eyeIcon.innerHTML = `
          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
          <circle cx="12" cy="12" r="3"></circle>
        `;
      }
    }
  });

  // Google Sign-In
  window.GasQAuth?.setupGoogleSignIn("dealerGoogleSignInBtn", async (idToken) => {
    showAuthMessage("Verifying Google account...");
    try {
      await window.GasQAuth.loginDealerWithGoogle(idToken);
      window.location.href = "/dealer-dashboard.html";
    } catch (err) {
      showAuthMessage(err.message || "Google sign-in failed.");
    }
  });

  // Login Submit
  loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    showAuthMessage("");

    const username = document.getElementById("loginUsername")?.value.trim();
    const password = document.getElementById("loginPassword")?.value;

    if (!username || !password) {
      showAuthMessage("Please enter your email/dealer ID and password.");
      return;
    }

    const submitBtn = document.getElementById("loginSubmitBtn");
    const originalText = submitBtn.textContent;
    submitBtn.disabled = true;
    submitBtn.textContent = "Logging in...";

    try {
      await window.GasQAuth.loginDealerPassword(username, password);
      window.location.href = "/dealer-dashboard.html";
    } catch (err) {
      showAuthMessage(err.message || "Invalid credentials.");
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = originalText;
    }
  });
}

function initRegisterForm() {
  const registerForm = document.getElementById("registerForm");
  if (!registerForm) return;

  registerForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    showAuthMessage("");

    const name = document.getElementById("registerName")?.value.trim();
    const username = document.getElementById("registerUsername")?.value.trim();
    const email = document.getElementById("registerEmail")?.value.trim();
    const password = document.getElementById("registerPassword")?.value;
    const confirmPassword = document.getElementById("registerConfirmPassword")?.value;
    const address = document.getElementById("registerAddress")?.value.trim();
    const phone = document.getElementById("registerPhone")?.value.trim();
    const stock = Number(document.getElementById("registerStock")?.value);

    if (password !== confirmPassword) {
      showAuthMessage("Passwords do not match. Please re-enter.");
      return;
    }

    const submitBtn = document.getElementById("registerSubmitBtn");
    const originalText = submitBtn.textContent;
    submitBtn.disabled = true;
    submitBtn.textContent = "Submitting...";

    try {
      await window.GasQAuth.registerDealerAccount({
        name,
        username,
        email,
        password,
        address,
        phone,
        available_cylinders: stock,
      });
      window.location.href = "/dealer-dashboard.html";
    } catch (err) {
      showAuthMessage(err.message || "Registration failed.");
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = originalText;
    }
  });
}
