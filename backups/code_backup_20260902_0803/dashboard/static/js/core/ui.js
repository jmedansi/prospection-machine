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
        const { title = 'Information', buttonText = 'OK' } = options;
        return new Promise(resolve => {
            let modal = document.getElementById('_alert-modal');
            if (!modal) {
                modal = document.createElement('div');
                modal.id = '_alert-modal';
                modal.className = 'modal-backdrop';
                modal.innerHTML = `
                    <div class="modal-content" style="max-width:480px">
                        <div class="mh">
                            <div class="mh-t" id="_alert-title"></div>
                        </div>
                        <div class="mb">
                            <div id="_alert-msg" style="color:var(--ink2); font-size:14px; line-height:1.6"></div>
                        </div>
                        <div class="mf">
                            <button id="_alert-ok" class="btn btn-primary"></button>
                        </div>
                    </div>`;
                document.body.appendChild(modal);
            }

            modal.querySelector('#_alert-title').textContent = title;
            modal.querySelector('#_alert-msg').innerHTML = message;
            
            const okBtn = modal.querySelector('#_alert-ok');
            okBtn.textContent = buttonText;

            modal.style.display = 'flex';
            setTimeout(() => modal.classList.add('active'), 10);

            const onOk = () => {
                modal.classList.remove('active');
                setTimeout(() => modal.style.display = 'none', 300);
                okBtn.removeEventListener('click', onOk);
                resolve();
            };

            okBtn.addEventListener('click', onOk);
        });
    }

    /**
     * Custom confirm dialog
     */
    static confirm(message, options = {}) {
        const {
            title = 'Confirmation',
            confirmText = 'Confirmer',
            cancelText = 'Annuler',
            danger = false
        } = options;

        return new Promise(resolve => {
            let modal = document.getElementById('_confirm-modal');
            if (!modal) {
                modal = document.createElement('div');
                modal.id = '_confirm-modal';
                modal.className = 'modal-backdrop';
                modal.innerHTML = `
                    <div class="modal-content" style="max-width:440px">
                        <div class="mh">
                            <div class="mh-t" id="_confirm-title"></div>
                        </div>
                        <div class="mb">
                            <p id="_confirm-msg" style="color:var(--ink2); font-size:14px; line-height:1.6"></p>
                        </div>
                        <div class="mf">
                            <button id="_confirm-cancel" class="btn btn-ghost"></button>
                            <button id="_confirm-ok" class="btn"></button>
                        </div>
                    </div>`;
                document.body.appendChild(modal);
            }

            modal.querySelector('#_confirm-title').textContent = title;
            modal.querySelector('#_confirm-msg').textContent = message;
            
            const cancelBtn = modal.querySelector('#_confirm-cancel');
            const okBtn = modal.querySelector('#_confirm-ok');
            
            cancelBtn.textContent = cancelText;
            okBtn.textContent = confirmText;
            okBtn.className = danger ? 'btn btn-danger' : 'btn btn-primary';

            modal.style.display = 'flex';
            setTimeout(() => modal.classList.add('active'), 10);

            const handleClose = (result) => {
                modal.classList.remove('active');
                setTimeout(() => modal.style.display = 'none', 300);
                okBtn.removeEventListener('click', onOk);
                cancelBtn.removeEventListener('click', onCancel);
                resolve(result);
            };

            const onOk = () => handleClose(true);
            const onCancel = () => handleClose(false);

            okBtn.addEventListener('click', onOk);
            cancelBtn.addEventListener('click', onCancel);
        });
    }
}

// Export globally for non-module scripts
window.UI = UI;
console.log('[UI] Core module loaded and exposed to window.UI');
