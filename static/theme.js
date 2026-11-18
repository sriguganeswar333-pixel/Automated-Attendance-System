/* ============================================================
   AUTOMATED ATTENDANCE SYSTEM
   UNIFIED LIGHT / DARK THEME MANAGER
   Synchronized across all application pages
   ============================================================ */

(function () {
    const THEME_KEY = "attendance_theme";

    function getStoredTheme() {
        return localStorage.getItem(THEME_KEY) || localStorage.getItem("attendance-theme") || "light";
    }

    function applyTheme(theme) {
        const isDark = theme === "dark";
        const html = document.documentElement;
        const body = document.body;

        if (isDark) {
            html.classList.add("dark-theme");
            if (body) body.classList.add("dark-theme");
        } else {
            html.classList.remove("dark-theme");
            if (body) body.classList.remove("dark-theme");
        }

        localStorage.setItem(THEME_KEY, theme);
        localStorage.setItem("attendance-theme", theme);

        updateThemeButtons(isDark);

        // Notify charts or other page-specific listeners
        window.dispatchEvent(new CustomEvent("themeChange", { detail: { theme: theme, isDark: isDark } }));
        if (typeof window.renderCharts === "function") {
            try { window.renderCharts(); } catch (e) {}
        }
    }

    function updateThemeButtons(isDark) {
        const buttons = document.querySelectorAll(
            "#themeToggle, #theme-toggle, .theme-switch-btn, .dark-mode-button, .theme-btn, .theme-toggle"
        );

        buttons.forEach(button => {
            const iconEl = button.querySelector(".sidebar-icon, #theme-icon, .theme-icon");
            const textEl = button.querySelector("span:last-child, #theme-text, .theme-text");

            if (iconEl && textEl && iconEl !== textEl) {
                iconEl.textContent = isDark ? "☀️" : "🌙";
                textEl.textContent = isDark ? "Light Mode" : "Dark Mode";
            } else if (textEl) {
                textEl.textContent = isDark ? "☀️ Light Mode" : "🌙 Dark Mode";
            } else {
                // Standalone icon button
                button.textContent = isDark ? "☀️" : "🌙";
            }

            button.setAttribute("title", isDark ? "Switch to Light Mode" : "Switch to Dark Mode");
            button.setAttribute("aria-label", isDark ? "Switch to Light Mode" : "Switch to Dark Mode");
        });
    }

    function toggleTheme() {
        const currentTheme = document.documentElement.classList.contains("dark-theme") ? "dark" : "light";
        const nextTheme = currentTheme === "dark" ? "light" : "dark";
        applyTheme(nextTheme);
    }

    // Expose global helpers
    window.toggleGlobalTheme = toggleTheme;
    window.toggleTheme = toggleTheme;
    window.applyDashboardTheme = applyTheme;
    window.applyGlobalTheme = applyTheme;

    // Apply stored theme immediately on script execution to avoid flickering
    const initialTheme = getStoredTheme();
    if (initialTheme === "dark") {
        document.documentElement.classList.add("dark-theme");
    } else {
        document.documentElement.classList.remove("dark-theme");
    }

    // Bind event listeners when DOM is loaded
    document.addEventListener("DOMContentLoaded", function () {
        applyTheme(getStoredTheme());

        // Delegate click for any theme button
        document.addEventListener("click", function (event) {
            const btn = event.target.closest(
                "#themeToggle, #theme-toggle, .theme-switch-btn, .dark-mode-button, .theme-btn, .theme-toggle"
            );
            if (btn) {
                event.preventDefault();
                toggleTheme();
            }
        });
    });
})();
