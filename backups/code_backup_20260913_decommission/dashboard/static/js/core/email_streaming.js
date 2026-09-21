/**
 * dashboard/static/js/core/email_streaming.js
 * Streaming IA pour la génération d'emails (effet typewriter)
 */

async function regenerateEmailWithStreaming() {
    const leadId = document.getElementById('edit-email-nom')?.value || getSelectedLeadId();
    if (!leadId) {
        showToast('Aucun lead sélectionné', 'error');
        return;
    }

    const loader = document.getElementById('email-streaming-loader');
    const textContainer = document.getElementById('email-streaming-text');
    const objetInput = document.getElementById('edit-email-objet');
    const corpsInput = document.getElementById('edit-email-corps');

    loader.style.display = 'block';
    textContainer.innerHTML = '';

    try {
        const response = await fetch(`/api/leads/${leadId}/regenerate-email-stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        if (!response.ok) throw new Error('Erreur génération');

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            
            // Parser les chunks JSON
            const lines = buffer.split('\n');
            buffer = lines.pop(); // Garder le dernier chunk incomplet

            for (const line of lines) {
                if (line.trim().startsWith('data:')) {
                    try {
                        const data = JSON.parse(line.replace('data:', '').trim());
                        if (data.objet && objetInput) {
                            objetInput.value = data.objet;
                        }
                        if (data.corps) {
                            // Effet typewriter
                            textContainer.innerHTML = data.corps;
                        }
                        if (data.done) {
                            corpsInput.value = data.corps || textContainer.innerHTML;
                        }
                    } catch (e) {
                        // Pas JSON, treat as text chunk
                        textContainer.innerHTML += line;
                    }
                }
            }
        }

        showToast('Email régénéré', 'success');
    } catch (e) {
        console.error('Streaming error:', e);
        showToast('Erreur: ' + e.message, 'error');
    } finally {
        loader.style.display = 'none';
    }
}

function getSelectedLeadId() {
    // Fallback: chercher dans l'URL ou autre source
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get('lead_id') || document.querySelector('[data-lead-id]')?.dataset.leadId;
}