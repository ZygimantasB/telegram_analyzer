/**
 * Telegram Analyzer - Theme Switcher
 * Handles light/dark theme toggle with localStorage persistence
 */

(function() {
    'use strict';

    const THEME_KEY = 'telegram-analyzer-theme';
    const DARK_THEME = 'dark';
    const LIGHT_THEME = 'light';

    /**
     * Get the current theme from localStorage or system preference
     */
    function getStoredTheme() {
        const storedTheme = localStorage.getItem(THEME_KEY);
        if (storedTheme) {
            return storedTheme;
        }
        // Check system preference
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
            return DARK_THEME;
        }
        return LIGHT_THEME;
    }

    /**
     * Apply theme to the document
     */
    function applyTheme(theme) {
        document.documentElement.setAttribute('data-bs-theme', theme);
        localStorage.setItem(THEME_KEY, theme);
        updateToggleButton(theme);
    }

    /**
     * Toggle between light and dark themes
     */
    function toggleTheme() {
        const currentTheme = document.documentElement.getAttribute('data-bs-theme') || LIGHT_THEME;
        const newTheme = currentTheme === DARK_THEME ? LIGHT_THEME : DARK_THEME;
        applyTheme(newTheme);
    }

    /**
     * Update the toggle button icons
     */
    function updateToggleButton(theme) {
        const sunIcon = document.getElementById('theme-icon-sun');
        const moonIcon = document.getElementById('theme-icon-moon');

        if (sunIcon && moonIcon) {
            if (theme === DARK_THEME) {
                sunIcon.classList.remove('active');
                moonIcon.classList.add('active');
            } else {
                sunIcon.classList.add('active');
                moonIcon.classList.remove('active');
            }
        }

        // Also update simple toggle if exists
        const simpleToggle = document.getElementById('theme-toggle-icon');
        if (simpleToggle) {
            simpleToggle.className = theme === DARK_THEME ? 'bi bi-sun-fill' : 'bi bi-moon-fill';
        }
    }

    /**
     * Initialize theme on page load
     */
    function initTheme() {
        const theme = getStoredTheme();
        applyTheme(theme);

        // Listen for system theme changes
        if (window.matchMedia) {
            window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
                if (!localStorage.getItem(THEME_KEY)) {
                    applyTheme(e.matches ? DARK_THEME : LIGHT_THEME);
                }
            });
        }
    }

    // Apply theme immediately to prevent flash
    initTheme();

    // Set up event listeners when DOM is ready
    document.addEventListener('DOMContentLoaded', function() {
        // Update button state
        updateToggleButton(getStoredTheme());

        // Add click handlers to theme toggle buttons
        const toggleButtons = document.querySelectorAll('[data-theme-toggle]');
        toggleButtons.forEach(button => {
            button.addEventListener('click', function(e) {
                e.preventDefault();
                toggleTheme();
            });
        });

        // Handle keyboard accessibility
        toggleButtons.forEach(button => {
            button.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    toggleTheme();
                }
            });
        });
    });

    // Expose functions globally for inline handlers
    window.ThemeSwitcher = {
        toggle: toggleTheme,
        set: applyTheme,
        get: getStoredTheme,
        DARK: DARK_THEME,
        LIGHT: LIGHT_THEME
    };
})();
