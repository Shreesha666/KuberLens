/**
 * Client-Side Application Script
 * Manages HTMX navigation events, progress bar, active sidebar highlighting,
 * and browser history restoration.
 */

document.addEventListener("DOMContentLoaded", function () {
    // 1. Sidebar Active State Updater
    function updateActiveSidebar(currentPath) {
        if (!currentPath) currentPath = window.location.pathname;
        const navLinks = document.querySelectorAll("#sidebar .sidebar-nav .nav-link");
        
        navLinks.forEach((link) => {
            const href = link.getAttribute("hx-get") || link.getAttribute("href");
            if (!href) return;

            // Strict match for dashboard root, startsWith match for submodules
            const isMatch = (href === "/" || href === "/dashboard/")
                ? (currentPath === "/" || currentPath === "/dashboard/")
                : (currentPath.startsWith(href));

            if (isMatch) {
                link.classList.add("active");
            } else {
                link.classList.remove("active");
            }
        });
    }

    // Initialize on page load
    updateActiveSidebar();

    // 2. HTMX Event Handlers
    const progressBar = document.getElementById("htmx-progress-bar");

    document.addEventListener("htmx:configRequest", function () {
        if (progressBar) {
            progressBar.style.opacity = "1";
            progressBar.style.width = "40%";
        }
    });

    document.addEventListener("htmx:afterRequest", function () {
        if (progressBar) {
            progressBar.style.width = "100%";
            setTimeout(() => {
                progressBar.style.opacity = "0";
                setTimeout(() => {
                    progressBar.style.width = "0%";
                }, 200);
            }, 150);
        }
    });

    // Update sidebar after dynamic content swap
    document.addEventListener("htmx:afterOnLoad", function (event) {
        if (event.detail.target && event.detail.target.id === "main-content") {
            updateActiveSidebar(window.location.pathname);
            // Close mobile sidebar if open
            const sidebar = document.getElementById("sidebar");
            if (sidebar && sidebar.classList.contains("show")) {
                sidebar.classList.remove("show");
            }
        }
    });

    // Update sidebar and DOM when user navigates using browser Back / Forward
    document.addEventListener("htmx:historyRestore", function () {
        updateActiveSidebar(window.location.pathname);
    });

    // Handle HTMX Response Errors Gracefully
    document.addEventListener("htmx:responseError", function (event) {
        const status = event.detail.xhr.status;
        showToast("Error", `Request failed with HTTP status ${status}. Please try again.`, "danger");
    });

    // 3. Mobile Sidebar Toggle
    const mobileToggle = document.getElementById("mobile-sidebar-toggle");
    if (mobileToggle) {
        mobileToggle.addEventListener("click", function () {
            const sidebar = document.getElementById("sidebar");
            if (sidebar) {
                sidebar.classList.toggle("show");
            }
        });
    }

    // 4. Accessible Toast Notification Helper
    window.showToast = function (title, message, variant = "info") {
        const container = document.getElementById("toast-container");
        if (!container) return;

        const toast = document.createElement("div");
        toast.className = `toast align-items-center text-bg-${variant} border-0 show mb-2`;
        toast.setAttribute("role", "alert");
        toast.setAttribute("aria-live", "assertive");
        toast.setAttribute("aria-atomic", "true");
        toast.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">
                    <strong>${title}:</strong> ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        `;
        container.appendChild(toast);
        setTimeout(() => {
            toast.remove();
        }, 5000);
    };
});

