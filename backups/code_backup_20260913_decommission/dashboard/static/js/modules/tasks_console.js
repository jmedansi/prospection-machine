/**
 * dashboard/static/js/modules/tasks_console.js
 * Moteur Frontend de la Console de Tâches en Direct (Task Engine SaaS Ultra)
 */

const TaskConsole = {
    activeTasks: new Map(),
    currentFilter: '',
    selectedTaskIdForLogs: null,

    init() {
        console.log('[TaskConsole] Initialisation...');
        this.bindWebSocket();
        this.refreshTasks();
    },

    bindWebSocket() {
        if (typeof io === 'undefined') {
            console.warn('[TaskConsole] Socket.IO non détecté, mode polling activé');
            return;
        }

        const socket = io();

        socket.on('task_created', (data) => {
            console.log('[TaskConsole] WS task_created:', data);
            this.activeTasks.set(data.id, data);
            this.renderActiveTasks();
            this.refreshTasks();
        });

        socket.on('task_update', (data) => {
            const existing = this.activeTasks.get(data.id) || {};
            this.activeTasks.set(data.id, { ...existing, ...data });
            this.renderActiveTasks();
            this.updateTableRow(data.id, data);
        });

        socket.on('task_log', (data) => {
            if (this.selectedTaskIdForLogs === data.id) {
                this.appendLogEntry(data.log);
            }
        });

        socket.on('task_completed', (data) => {
            console.log('[TaskConsole] WS task_completed:', data);
            this.activeTasks.delete(data.id);
            this.renderActiveTasks();
            this.refreshTasks();
        });
    },

    async refreshTasks() {
        try {
            const url = this.currentFilter ? `/api/tasks?status=${this.currentFilter}` : '/api/tasks';
            const res = await fetch(url);
            const data = await res.json();

            if (data.success) {
                this.renderHistoryTable(data.tasks);
                
                // Mettre à jour la liste des tâches actives
                this.activeTasks.clear();
                data.tasks.filter(t => t.status === 'running' || t.status === 'pending').forEach(t => {
                    this.activeTasks.set(t.id, t);
                });
                this.renderActiveTasks();
            }
        } catch (e) {
            console.error('[TaskConsole] Erreur chargement tâches:', e);
        }
    },

    renderActiveTasks() {
        const container = document.getElementById('active-tasks-container');
        if (!container) return;

        if (this.activeTasks.size === 0) {
            container.innerHTML = '';
            return;
        }

        let html = '';
        this.activeTasks.forEach((task) => {
            const pct = task.progress || 0;
            html += `
                <div class="active-task-card" style="background: linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(15, 23, 42, 0.9)); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 12px; padding: 18px; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3);">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
                        <div>
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <span style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #38bdf8; animation: pulse 1.5s infinite;"></span>
                                <h4 style="font-size: 15px; font-weight: 600; color: #fff; margin: 0;">${task.label || task.task_type}</h4>
                                <span style="font-size: 11px; background: rgba(56, 189, 248, 0.15); color: #38bdf8; padding: 2px 8px; border-radius: 9999px; font-weight: 500;">${task.status}</span>
                            </div>
                            <div style="font-size: 13px; color: #94a3b8; margin-top: 4px;">
                                ${task.current_item_label ? `En cours : <span style="color: #cbd5e1;">${task.current_item_label}</span>` : 'Traitement en cours...'}
                            </div>
                        </div>
                        <div style="display: flex; gap: 8px;">
                            <button class="btn btn-sm" onclick="TaskConsole.viewLogs('${task.id}')" style="background: #1e293b; color: #38bdf8; border: 1px solid #334155; padding: 6px 12px; border-radius: 6px; font-size: 12px; cursor: pointer;">
                                Voir logs
                            </button>
                            <button class="btn btn-sm" onclick="TaskConsole.cancelTask('${task.id}')" style="background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); padding: 6px 12px; border-radius: 6px; font-size: 12px; cursor: pointer;">
                                Annuler
                            </button>
                        </div>
                    </div>

                    <div style="display: flex; align-items: center; gap: 12px;">
                        <div style="flex: 1; height: 8px; background: #0f172a; border-radius: 9999px; overflow: hidden;">
                            <div style="width: ${pct}%; height: 100%; background: linear-gradient(90deg, #38bdf8, #818cf8); border-radius: 9999px; transition: width 0.3s ease;"></div>
                        </div>
                        <span style="font-size: 13px; font-weight: 600; color: #f8fafc; min-width: 45px; text-align: right;">${pct}%</span>
                    </div>

                    ${task.total_items ? `
                        <div style="display: flex; justify-content: space-between; font-size: 12px; color: #64748b; margin-top: 8px;">
                            <span>Progression : ${task.processed_items || 0} / ${task.total_items}</span>
                            <span>ID: ${task.id}</span>
                        </div>
                    ` : ''}
                </div>
            `;
        });

        container.innerHTML = html;
    },

    renderHistoryTable(tasks) {
        const tbody = document.getElementById('task-history-tbody');
        if (!tbody) return;

        if (tasks.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; padding: 24px; color: #64748b;">Aucune tâche trouvée.</td></tr>';
            return;
        }

        tbody.innerHTML = tasks.map(t => {
            let badgeColor = '#64748b';
            let badgeBg = 'rgba(100, 116, 139, 0.15)';
            if (t.status === 'completed') { badgeColor = '#4ade80'; badgeBg = 'rgba(74, 222, 128, 0.15)'; }
            else if (t.status === 'running') { badgeColor = '#38bdf8'; badgeBg = 'rgba(56, 189, 248, 0.15)'; }
            else if (t.status === 'failed') { badgeColor = '#f87171'; badgeBg = 'rgba(239, 68, 68, 0.15)'; }
            else if (t.status === 'cancelled') { badgeColor = '#fbbf24'; badgeBg = 'rgba(251, 191, 36, 0.15)'; }

            const dateStr = t.created_at ? t.created_at.replace('T', ' ').substring(0, 19) : '-';

            return `
                <tr id="task-row-${t.id}" style="border-bottom: 1px solid rgba(255, 255, 255, 0.05); color: #cbd5e1;">
                    <td style="padding: 12px; font-family: monospace; color: #94a3b8;">${t.id}</td>
                    <td style="padding: 12px; font-weight: 500; color: #fff;">${t.label || t.task_type}</td>
                    <td style="padding: 12px;">
                        <span style="display: inline-block; padding: 3px 8px; border-radius: 9999px; font-size: 11px; font-weight: 600; color: ${badgeColor}; background: ${badgeBg};">
                            ${t.status}
                        </span>
                    </td>
                    <td style="padding: 12px;">${t.progress || 0}%</td>
                    <td style="padding: 12px; color: #94a3b8;">${t.processed_items || 0} / ${t.total_items || '-'}</td>
                    <td style="padding: 12px; font-size: 12px; color: #64748b;">${dateStr}</td>
                    <td style="padding: 12px; text-align: right;">
                        <button onclick="TaskConsole.viewLogs('${t.id}')" style="background: none; border: none; color: #38bdf8; cursor: pointer; font-size: 12px; text-decoration: underline; margin-right: 8px;">
                            Logs
                        </button>
                        ${t.status === 'running' ? `
                            <button onclick="TaskConsole.cancelTask('${t.id}')" style="background: none; border: none; color: #f87171; cursor: pointer; font-size: 12px; text-decoration: underline;">
                                Annuler
                            </button>
                        ` : ''}
                    </td>
                </tr>
            `;
        }).join('');
    },

    updateTableRow(taskId, data) {
        const row = document.getElementById(`task-row-${taskId}`);
        if (row && data.progress !== undefined) {
            // Mettre à jour visuellement
        }
    },

    async viewLogs(taskId) {
        this.selectedTaskIdForLogs = taskId;
        const drawer = document.getElementById('task-log-drawer');
        const content = document.getElementById('drawer-log-content');
        const title = document.getElementById('drawer-task-title');
        const subtitle = document.getElementById('drawer-task-subtitle');

        if (!drawer || !content) return;

        drawer.style.display = 'flex';
        content.innerHTML = '<div style="color: #64748b;">Chargement des logs...</div>';
        subtitle.innerText = `ID: ${taskId}`;

        try {
            const res = await fetch(`/api/tasks/${taskId}`);
            const data = await res.json();
            if (data.success && data.task) {
                title.innerText = `Logs : ${data.task.label || data.task.task_type}`;
                content.innerHTML = '';
                (data.task.logs || []).forEach(l => this.appendLogEntry(l));
                content.scrollTop = content.scrollHeight;
            }
        } catch (e) {
            content.innerHTML = `<div style="color: #f87171;">Erreur chargement logs: ${e}</div>`;
        }
    },

    appendLogEntry(log) {
        const content = document.getElementById('drawer-log-content');
        if (!content) return;

        let color = '#94a3b8';
        if (log.level === 'error') color = '#f87171';
        else if (log.level === 'warning') color = '#fbbf24';
        else if (log.level === 'info') color = '#38bdf8';

        const line = document.createElement('div');
        line.style.marginBottom = '4px';
        line.innerHTML = `<span style="color: #64748b;">[${log.time || ''}]</span> <span style="color: ${color}; font-weight: 500;">[${(log.level || 'info').toUpperCase()}]</span> <span style="color: #f8fafc;">${log.msg || ''}</span>`;
        content.appendChild(line);
        content.scrollTop = content.scrollHeight;
    },

    closeLogDrawer() {
        this.selectedTaskIdForLogs = null;
        const drawer = document.getElementById('task-log-drawer');
        if (drawer) drawer.style.display = 'none';
    },

    async cancelTask(taskId) {
        if (!confirm(`Voulez-vous vraiment annuler la tâche ${taskId} ?`)) return;

        try {
            const res = await fetch(`/api/tasks/${taskId}/cancel`, { method: 'POST' });
            const data = await res.json();
            if (data.success) {
                this.refreshTasks();
            }
        } catch (e) {
            alert('Erreur lors de l\'annulation de la tâche');
        }
    },

    openLaunchModal() {
        const modal = document.getElementById('task-launch-modal');
        if (modal) modal.style.display = 'flex';
    },

    closeLaunchModal() {
        const modal = document.getElementById('task-launch-modal');
        if (modal) modal.style.display = 'none';
    },

    async submitLaunch() {
        const action = document.getElementById('launch-task-action').value;
        const limit = parseInt(document.getElementById('launch-task-limit').value || '25', 10);

        try {
            const res = await fetch(`/api/tasks/launch/${action}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ limit: limit })
            });
            const data = await res.json();

            if (data.success) {
                this.closeLaunchModal();
                this.refreshTasks();
            } else {
                alert(`Erreur: ${data.error || 'Impossible de lancer la tâche'}`);
            }
        } catch (e) {
            alert('Erreur réseau lors du lancement de la tâche');
        }
    },

    filterTasks() {
        this.currentFilter = document.getElementById('task-filter-status').value;
        this.refreshTasks();
    }
};

// Auto-démarrage si sur la page dashboard
document.addEventListener('DOMContentLoaded', () => {
    TaskConsole.init();
});
