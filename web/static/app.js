/**
 * Spec Agent — Frontend
 *
 * Chat moderno com WebSocket, markdown rico, code blocks com copy,
 * theme toggle, sidebar colapsavel, e typing indicator animado.
 */

let ws = null;
let isConnected = false;

// ============================================================
// WebSocket
// ============================================================

function connect() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${location.host}/ws/chat`;

    ws = new WebSocket(url);

    ws.onopen = () => {
        isConnected = true;
        updateConnectionStatus(true);
    };

    ws.onclose = () => {
        isConnected = false;
        updateConnectionStatus(false);
        setTimeout(connect, 3000);
    };

    ws.onerror = () => {};

    ws.onmessage = (event) => {
        handleServerMessage(JSON.parse(event.data));
    };
}

function handleServerMessage(data) {
    switch (data.type) {
        case 'response':
            removeThinking();
            addMessage('agent', data.content);
            break;
        case 'thinking':
            showThinking(data.content);
            break;
        case 'status':
            updateStatus(data.data);
            break;
        case 'card_generated':
            addCardToSidebar(data.data);
            break;
        case 'error':
            removeThinking();
            addMessage('error', data.content);
            break;
    }
}

// ============================================================
// Enviar mensagens
// ============================================================

function sendMessage() {
    const input = document.getElementById('chat-input');
    const text = input.value.trim();
    if (!text || !isConnected) return;

    hideWelcome();
    addMessage('user', text);
    ws.send(JSON.stringify({ type: 'message', content: text }));
    input.value = '';
    input.style.height = 'auto';
    updateSendBtn();
}

function sendCommand(cmd) {
    if (!isConnected) return;
    ws.send(JSON.stringify({ type: 'command', command: cmd }));
}

function useChip(el) {
    const input = document.getElementById('chat-input');
    input.value = el.textContent;
    updateSendBtn();
    sendMessage();
}

// ============================================================
// Mensagens
// ============================================================

function addMessage(type, content) {
    hideWelcome();
    const container = document.getElementById('chat-messages');

    const row = document.createElement('div');
    const rowClass = type === 'user' ? 'user-row' : type === 'error' ? 'error-row' : 'agent-row';
    row.className = `msg-row ${rowClass}`;

    const inner = document.createElement('div');
    inner.className = 'msg-inner';

    // Avatar
    const avatar = document.createElement('div');
    const avatarClass = type === 'user' ? 'user-avatar' : type === 'error' ? 'error-avatar' : 'agent-avatar';
    avatar.className = `msg-avatar ${avatarClass}`;
    avatar.textContent = type === 'user' ? 'U' : type === 'error' ? '!' : 'S';

    // Content
    const contentDiv = document.createElement('div');
    contentDiv.className = 'msg-content';

    const sender = document.createElement('div');
    sender.className = 'msg-sender';
    sender.textContent = type === 'user' ? 'Voce' : type === 'error' ? 'Erro' : 'Spec Agent';

    const body = document.createElement('div');
    body.className = `msg-body ${type === 'user' ? 'user-body' : ''}`;

    if (type === 'user') {
        body.textContent = content;
    } else {
        body.innerHTML = renderMarkdown(content || '');
    }

    contentDiv.appendChild(sender);
    contentDiv.appendChild(body);
    inner.appendChild(avatar);
    inner.appendChild(contentDiv);
    row.appendChild(inner);
    container.appendChild(row);

    scrollToBottom();
}

function showThinking() {
    removeThinking();
    hideWelcome();
    const container = document.getElementById('chat-messages');

    const row = document.createElement('div');
    row.className = 'thinking-row';
    row.id = 'thinking-indicator';

    const inner = document.createElement('div');
    inner.className = 'thinking-inner';

    const avatar = document.createElement('div');
    avatar.className = 'msg-avatar agent-avatar';
    avatar.textContent = 'S';

    const bubble = document.createElement('div');
    bubble.className = 'thinking-bubble';

    const dots = document.createElement('div');
    dots.className = 'thinking-dots';
    dots.innerHTML = '<span></span><span></span><span></span>';

    const label = document.createElement('span');
    label.textContent = 'Pensando...';

    bubble.appendChild(dots);
    bubble.appendChild(label);
    inner.appendChild(avatar);
    inner.appendChild(bubble);
    row.appendChild(inner);
    container.appendChild(row);

    scrollToBottom();
}

function removeThinking() {
    const el = document.getElementById('thinking-indicator');
    if (el) el.remove();
}

function hideWelcome() {
    const el = document.getElementById('welcome-screen');
    if (el) el.remove();
}

function scrollToBottom() {
    const container = document.getElementById('chat-messages');
    requestAnimationFrame(() => {
        container.scrollTop = container.scrollHeight;
    });
}

// ============================================================
// Markdown renderer
// ============================================================

function renderMarkdown(text) {
    if (!text) return '';

    // Preserve code blocks
    const codeBlocks = [];
    text = text.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
        const idx = codeBlocks.length;
        codeBlocks.push({ lang: lang || '', code: code.replace(/\n$/, '') });
        return `%%CODEBLOCK_${idx}%%`;
    });

    // Escape HTML
    text = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

    // Headers
    text = text.replace(/^#### (.+)$/gm, '<h4>$1</h4>');
    text = text.replace(/^### (.+)$/gm, '<h3>$1</h3>');
    text = text.replace(/^## (.+)$/gm, '<h2>$1</h2>');
    text = text.replace(/^# (.+)$/gm, '<h1>$1</h1>');

    // Horizontal rule
    text = text.replace(/^---$/gm, '<hr>');

    // Blockquote
    text = text.replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>');

    // Bold & italic
    text = text.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
    text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    text = text.replace(/\*(.+?)\*/g, '<em>$1</em>');

    // Inline code (not inside code blocks)
    text = text.replace(/`([^`]+?)`/g, '<code>$1</code>');

    // Tables
    text = text.replace(/^(\|.+\|)\n(\|[-| :]+\|)\n((?:\|.+\|\n?)*)/gm, (_, header, sep, body) => {
        const ths = header.split('|').filter(c => c.trim()).map(c => `<th>${c.trim()}</th>`).join('');
        const rows = body.trim().split('\n').map(row => {
            const tds = row.split('|').filter(c => c.trim()).map(c => `<td>${c.trim()}</td>`).join('');
            return `<tr>${tds}</tr>`;
        }).join('');
        return `<table><thead><tr>${ths}</tr></thead><tbody>${rows}</tbody></table>`;
    });

    // Unordered lists
    text = text.replace(/(^[\t ]*- .+(\n|$))+/gm, (block) => {
        const items = block.trim().split('\n').map(line => {
            return `<li>${line.replace(/^[\t ]*- /, '')}</li>`;
        }).join('');
        return `<ul>${items}</ul>`;
    });

    // Ordered lists
    text = text.replace(/(^\d+\. .+(\n|$))+/gm, (block) => {
        const items = block.trim().split('\n').map(line => {
            return `<li>${line.replace(/^\d+\. /, '')}</li>`;
        }).join('');
        return `<ol>${items}</ol>`;
    });

    // Paragraphs — wrap remaining plain text lines
    text = text.replace(/^(?!<[houpbtal]|%%CODEBLOCK)(.+)$/gm, '<p>$1</p>');

    // Clean up empty paragraphs and double breaks
    text = text.replace(/<p>\s*<\/p>/g, '');
    text = text.replace(/\n{2,}/g, '');
    text = text.replace(/\n/g, '');

    // Restore code blocks
    text = text.replace(/%%CODEBLOCK_(\d+)%%/g, (_, idx) => {
        const block = codeBlocks[parseInt(idx)];
        const id = `code-${Date.now()}-${idx}`;
        const escaped = block.code
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
        return `<div class="code-block">` +
            `<div class="code-header">` +
                `<span class="code-lang">${block.lang || 'code'}</span>` +
                `<button class="copy-btn" onclick="copyCode('${id}', this)">` +
                    `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>` +
                    `Copiar` +
                `</button>` +
            `</div>` +
            `<pre class="code-body" id="${id}">${escaped}</pre>` +
        `</div>`;
    });

    return text;
}

function copyCode(id, btn) {
    const el = document.getElementById(id);
    if (!el) return;
    navigator.clipboard.writeText(el.textContent).then(() => {
        btn.classList.add('copied');
        btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>Copiado!`;
        setTimeout(() => {
            btn.classList.remove('copied');
            btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>Copiar`;
        }, 2000);
    });
}

// ============================================================
// Sidebar / Status
// ============================================================

function updateStatus(status) {
    if (status.checklist) {
        const items = document.querySelectorAll('.check-item');
        let filled = 0;
        const total = items.length;

        items.forEach(item => {
            const field = item.dataset.field;
            const done = status.checklist[field] || false;
            item.classList.toggle('done', done);
            if (done) filled++;
        });

        const pct = (filled / total) * 100;
        document.getElementById('progress-fill').style.width = `${pct}%`;
        document.getElementById('checklist-count').textContent = `${filled}/${total}`;
    }

    if (status.phase) {
        document.getElementById('phase').textContent = status.phase;
    }
    if (status.estimated_context_tokens !== undefined) {
        const el = document.getElementById('context-tokens');
        el.innerHTML = `${Math.round(status.estimated_context_tokens).toLocaleString()} <small>tokens</small>`;
    }
    if (status.knowledge_refs !== undefined) {
        document.getElementById('knowledge-refs').textContent = status.knowledge_refs;
    }
    if (status.observations !== undefined) {
        document.getElementById('observations').textContent = status.observations;
    }
}

function updateConnectionStatus(connected) {
    const el = document.getElementById('connection-status');
    el.querySelector('.conn-text').textContent = connected ? 'Conectado' : 'Desconectado';
    el.className = `conn-indicator ${connected ? 'connected' : 'disconnected'}`;
}

function addCardToSidebar(data) {
    const container = document.getElementById('cards-list');
    const empty = container.querySelector('.empty-state');
    if (empty) empty.remove();

    if (container.querySelector(`[data-filename="${data.filename}"]`)) return;

    const link = document.createElement('a');
    link.className = 'card-link';
    link.href = data.url;
    link.target = '_blank';
    link.dataset.filename = data.filename;
    link.textContent = data.filename;
    container.appendChild(link);
}

// ============================================================
// Theme toggle
// ============================================================

function toggleTheme() {
    const html = document.documentElement;
    const current = html.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
    updateThemeIcon(next);
}

function updateThemeIcon(theme) {
    document.getElementById('theme-icon-light').style.display = theme === 'light' ? '' : 'none';
    document.getElementById('theme-icon-dark').style.display = theme === 'dark' ? '' : 'none';
}

function initTheme() {
    const saved = localStorage.getItem('theme');
    if (saved) {
        document.documentElement.setAttribute('data-theme', saved);
        updateThemeIcon(saved);
    } else if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
        document.documentElement.setAttribute('data-theme', 'dark');
        updateThemeIcon('dark');
    }
}

// ============================================================
// Sidebar toggle
// ============================================================

function initSidebar() {
    const sidebar = document.getElementById('sidebar');
    const toggleBtn = document.getElementById('toggle-sidebar');
    const openBtn = document.getElementById('open-sidebar');

    toggleBtn.addEventListener('click', () => {
        sidebar.classList.add('collapsed');
        openBtn.style.display = '';
    });

    openBtn.addEventListener('click', () => {
        sidebar.classList.remove('collapsed');
        openBtn.style.display = 'none';
    });
}

// ============================================================
// Send button state
// ============================================================

function updateSendBtn() {
    const input = document.getElementById('chat-input');
    const btn = document.getElementById('send-btn');
    btn.disabled = !input.value.trim() || !isConnected;
}

// ============================================================
// Event listeners
// ============================================================

document.getElementById('chat-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

document.getElementById('chat-input').addEventListener('input', function () {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 160) + 'px';
    updateSendBtn();
});

document.getElementById('theme-toggle').addEventListener('click', toggleTheme);

// ============================================================
// Init
// ============================================================

initTheme();
initSidebar();
connect();
