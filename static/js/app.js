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

    function isPollingRequest(event) {
        const elt = event?.detail?.elt;
        if (!elt) return false;
        const trigger = elt.getAttribute("hx-trigger") || "";
        return trigger.includes("every") || elt.hasAttribute("data-silent-refresh");
    }

    document.addEventListener("htmx:configRequest", function (event) {
        // Skip progress bar animation for background polling / periodic sync
        if (isPollingRequest(event)) {
            return;
        }
        if (progressBar) {
            progressBar.style.opacity = "1";
            progressBar.style.width = "40%";
        }
    });

    document.addEventListener("htmx:afterRequest", function (event) {
        if (isPollingRequest(event)) {
            return;
        }
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
        if (isPollingRequest(event)) {
            return; // Silent failover for background sync blips
        }
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

    // 4. Accessible SweetAlert2 Toast Notification Engine
    function getToastThemeConfig() {
        const isDark = document.documentElement.getAttribute("data-bs-theme") === "dark";
        return {
            background: isDark ? "rgba(15, 23, 42, 0.96)" : "#ffffff",
            color: isDark ? "#f8fafc" : "#1e293b",
            customClass: {
                popup: "kuberlens-swal-toast"
            }
        };
    }

    function createSwalToastInstance() {
        if (typeof Swal === "undefined") return null;
        return Swal.mixin({
            toast: true,
            position: "top-end",
            showConfirmButton: false,
            timer: 4000,
            timerProgressBar: true,
            didOpen: (toast) => {
                toast.onmouseenter = Swal.stopTimer;
                toast.onmouseleave = Swal.resumeTimer;
            }
        });
    }

    let kuberSwalToast = createSwalToastInstance();

    window.showToast = function (title, message, variant = "info") {
        if (!kuberSwalToast && typeof Swal !== "undefined") {
            kuberSwalToast = createSwalToastInstance();
        }

        // Map variant string to SweetAlert2 standard icons: 'success', 'error', 'warning', 'info'
        let icon = "info";
        const v = (variant || "info").toLowerCase();
        if (v === "danger" || v === "error") icon = "error";
        else if (v === "success") icon = "success";
        else if (v === "warning") icon = "warning";
        else if (v === "info" || v === "primary" || v === "secondary") icon = "info";

        if (kuberSwalToast) {
            const themeCfg = getToastThemeConfig();
            kuberSwalToast.fire({
                icon: icon,
                title: title || undefined,
                html: message,
                background: themeCfg.background,
                color: themeCfg.color,
                customClass: themeCfg.customClass
            });
        } else {
            // DOM Toast Fallback
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
                        <strong>${title || 'Notification'}:</strong> ${message}
                    </div>
                    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
                </div>
            `;
            container.appendChild(toast);
            setTimeout(() => {
                toast.remove();
            }, 4000);
        }
    };

    // Process Django Messages Bridge (Initial Load & HTMX Swaps)
    function processDjangoMessages(rootElement = document) {
        if (!rootElement) return;
        const messageNodes = rootElement.querySelectorAll("[data-django-message]");
        messageNodes.forEach((node, index) => {
            const message = node.getAttribute("data-django-message") || node.innerText.trim();
            const tags = (node.getAttribute("data-tags") || "info").toLowerCase();
            if (message) {
                let variant = "info";
                let title = "";
                if (tags.includes("success")) {
                    variant = "success";
                    title = "Success";
                } else if (tags.includes("error") || tags.includes("danger")) {
                    variant = "error";
                    title = "Error";
                } else if (tags.includes("warning")) {
                    variant = "warning";
                    title = "Notice";
                } else {
                    variant = "info";
                    title = "Information";
                }

                // Stagger sequential toasts by 200ms
                setTimeout(() => {
                    window.showToast(title, message, variant);
                }, index * 200);
            }
            node.remove();
        });
    }

    // Process on initial page render
    processDjangoMessages(document);

    // Process on HTMX content swaps
    document.addEventListener("htmx:afterOnLoad", function (event) {
        const target = event.detail?.target || document;
        processDjangoMessages(target);
    });

    // Inspect HX-Trigger response headers for programmatic toasts
    document.addEventListener("htmx:afterRequest", function (event) {
        const triggerHeader = event.detail?.xhr?.getResponseHeader("HX-Trigger");
        if (triggerHeader) {
            try {
                const parsed = JSON.parse(triggerHeader);
                if (parsed.showToast) {
                    const { title, message, variant } = parsed.showToast;
                    window.showToast(title, message, variant);
                }
            } catch (e) {
                // Non-JSON HX-Trigger header, ignore
            }
        }
    });

    // 5. Close Search Results Dropdowns on Click Outside or Escape
    document.addEventListener("click", function (event) {
        document.querySelectorAll(".search-results-dropdown, #search-results, #ai-search-results").forEach(function (dropdown) {
            const container = dropdown.closest(".header-search-box, .position-relative") || dropdown.parentElement;
            if (container && !container.contains(event.target)) {
                dropdown.innerHTML = "";
            }
        });
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
            document.querySelectorAll(".search-results-dropdown, #search-results, #ai-search-results").forEach(function (dropdown) {
                dropdown.innerHTML = "";
            });
        }
    });
});

