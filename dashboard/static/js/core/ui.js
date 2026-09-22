/**
 * dashboard/static/js/core/ui.js
 * Centralized UI utilities (Toasts, Modals, Confirmations)
 */

export class UI {
    static TOAST_ICONS = {
        success: '✅',
        error: '❌',
        warning: '⚠️',
        info: 'ℹ️'
    };

    /**
     * Show a toast notification
     */
    static toast(message, type = 'success') {
        const container = document.getElementById('toast-container');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `
            <span class="t-icon">${this.TOAST_ICONS[type] || '✅'}</span>
            <span class="t-msg">${message}</span>
        `;
        
        container.appendChild(toast);
        
        // Animation
        requestAnimationFrame(() => {
            toast.style.opacity = '1';
            toast.style.transform = 'translateX(0)';
        });

        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(110%)';
            setTimeout(() => toast.remove(), 350);
        }, 4000);
    }

    /**
     * Set innerHTML for an element safely if it exists
     */
    static setHTML(id, html) {
        const el = document.getElementById(id);
        if (el) el.innerHTML = html;
    }

    /**
     * Set textContent for an element and trigger "bump" animation if changed
     */
    static setText(id, text) {
        const el = document.getElementById(id);
        if (!el) return;
        const prev = el.textContent;
        el.textContent = text;
        
        if (prev !== String(text) && (el.classList.contains('mv') || el.classList.contains('pn'))) {
            el.classList.remove('bump');
            void el.offsetWidth;
            el.classList.add('bump');
        }
    }

    /**
     * Toggle a class active/inactive on many elements
     */
    static toggleActive(selector, activeId) {
        document.querySelectorAll(selector).forEach(el => {
            if (el.id === activeId || el.dataset.section === activeId || el.dataset.tab === activeId) {
                el.classList.add('active');
            } else {
                el.classList.remove('active');
            }
        });
    }

    /**
     * Side Panel management
     */
    static openSidePanel(id = 'lead-details-panel') {
        const panel = document.getElementById(id);
        if (panel) panel.classList.add('open');
    }

    static closeSidePanel(id = 'lead-details-panel') {
        const panel = document.getElementById(id);
        if (panel) panel.classList.remove('open');
    }

    /**
     * Custom alert / info modal
     */
    static alert(message, options = {}) {
        if (typeof showAlert === 'function') {
            return showAlert(message, options);
        }
        return Promise.resolve();
    }

    /**
     * Custom confirm dialog
     */
    static confirm(message, options = {}) {
        if (typeof showConfirm === 'function') {
            return showConfirm(message, options);
        }
        return Promise.resolve(window.confirm(message));
    }
}

// Export globally for non-module scripts
window.UI = UI;
console.log('[UI] Core module loaded and exposed to window.UI');
