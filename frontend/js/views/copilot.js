/* AI Copilot — natural-language decision support over live context */

window.Views = window.Views || {};

const QUICK_SLOTS = [
  'Summarize today’s attendance',
  'Any unresolved CRITICAL alerts right now?',
  'Who was phone-distracted most today?',
  'Which assets are at theft risk?',
];

Views.copilot = {
  render: async (container) => {
    container.innerHTML = `
      <div class="glass-card rounded-2xl p-5 flex flex-col h-[calc(100vh-220px)]">
        <div class="flex items-center justify-between pb-4 border-b border-white/5 mb-4">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-xl bg-gradient-to-tr from-purple-600 to-indigo-600 grid place-items-center text-lg">🤖</div>
            <div>
              <h2 class="text-sm font-bold text-white">Gemini AI Decision Copilot</h2>
              <p class="text-[11px] text-gray-400">Rule-fallback when no API key is configured</p>
            </div>
          </div>
          <span class="px-2.5 py-1 rounded-lg bg-purple-500/20 text-purple-300 border border-purple-500/30 text-[10px] font-mono">MODEL: GEMINI-2.5-FLASH</span>
        </div>

        <div class="flex flex-wrap gap-2 mb-4">
          ${QUICK_SLOTS.map((q) => `<button data-quick class="px-3 py-1.5 rounded-lg bg-ink-800 hover:bg-ink-700 border border-white/10 text-[11px] text-gray-300">${esc(q)}</button>`).join('')}
        </div>

        <div id="chat" class="flex-1 overflow-y-auto space-y-3 pr-1 mb-4"></div>

        <form id="copilot-form" class="flex gap-2 pt-3 border-t border-white/5">
          <input id="copilot-input" placeholder="Ask: 'Show today’s gate activity', 'Theft alerts?'…"
            class="flex-1 px-4 py-2.5 rounded-xl bg-ink-800 border border-white/10 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-purple-400/50" />
          <button class="px-5 py-2.5 rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 hover:opacity-90 text-white text-sm font-semibold">Ask</button>
        </form>
      </div>`;

    const chat = container.querySelector('#chat');
    function append(sender, text) {
      chat.appendChild(el(`
        <div class="flex ${sender === 'user' ? 'justify-end' : 'justify-start'}">
          <div class="max-w-[80%] px-4 py-3 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap ${sender === 'user'
            ? 'bg-gradient-to-r from-cyan-600 to-blue-600 text-white rounded-br-none'
            : 'bg-ink-800 border border-white/10 text-gray-200 rounded-bl-none'}">${esc(text)}</div>
        </div>`));
      chat.scrollTop = chat.scrollHeight;
    }

    chat.appendChild(el(`<div class="text-xs text-gray-400">Welcome! The copilot queries the live database for attendance, alerts, assets, productivity and health. Ask anything.</div>`));

    async function send(text) {
      const q = text.trim();
      if (!q) return;
      append('user', q);
      const input = container.querySelector('#copilot-input');
      input.value = '';
      input.disabled = true;
      const thinking = el(`<div class="flex justify-start"><div class="bg-ink-800 border border-white/10 text-gray-400 px-4 py-3 rounded-2xl text-xs">Reasoning over live context<span class="dots-loading"></span></div></div>`);
      chat.appendChild(thinking);
      try {
        const res = await api('/api/copilot/query', { method: 'POST', body: JSON.stringify({ query: q }) });
        thinking.remove();
        append('ai', res.response || 'No response returned.');
      } catch (err) {
        thinking.remove();
        append('ai', 'Error: ' + err.message);
      } finally {
        input.disabled = false;
        input.focus();
      }
    }

    container.querySelector('#copilot-form').onsubmit = (e) => {
      e.preventDefault();
      send(container.querySelector('#copilot-input').value);
    };
    container.querySelectorAll('[data-quick]').forEach((b) => (b.onclick = () => send(b.textContent)));
  },
};