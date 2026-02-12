// HindSite Quick Search Window
// Focus input, ESC closes window, voice input, and backend search (tab switch / semantic).

const API_BASE = 'http://localhost:8000';

let qsRecognition = null;
let qsRecognizing = false;
let qsSpeechBaseText = '';
let qsSpeechSupported = null;

(function () {
  if (window.self === window.top) document.body.classList.add('standalone');
})();

async function performSearch(query) {
  if (!query.trim()) return;

  // In-out press animation on send button (Enter or click)
  const sendChip = document.querySelector('.send-chip');
  if (sendChip) {
    sendChip.classList.add('press');
    setTimeout(() => sendChip.classList.remove('press'), 180);
  }

  const tabs = await chrome.tabs.query({});
  const openTabs = tabs.map((t) => ({
    tab_id: t.id,
    window_id: t.windowId,
    url: t.url || '',
    title: t.title || ''
  }));

  try {
    const response = await fetch(`${API_BASE}/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: query.trim(),
        limit: 3,
        open_tabs: openTabs
      })
    });

    const contentType = response.headers.get('content-type') || '';
    const isJson = contentType.includes('application/json');
    const text = await response.text();

    if (!response.ok) {
      let msg = text;
      if (isJson) {
        try {
          const body = JSON.parse(text);
          msg = body.detail ?? body.message ?? text;
        } catch (_) {
          msg = text || `Server error (${response.status})`;
        }
      }
      displayError(typeof msg === 'string' ? msg : `Server error (${response.status})`);
      return;
    }
    if (!isJson) {
      displayError('Invalid response from server.');
      return;
    }

    const data = JSON.parse(text);

    if (data.query_type === 'tab_switch' && data.matched_tab) {
      await chrome.tabs.update(data.matched_tab.tab_id, { active: true });
      await chrome.windows.update(data.matched_tab.window_id, { focused: true });
      window.close();
    } else if (data.query_type === 'semantic_search' && data.results) {
      displaySearchResults(data.results);
    } else {
      displayNoResults();
    }
  } catch (error) {
    console.error('Search failed:', error);
    displayError(error.message || 'Search failed. Is the backend running?');
  }
}

function displaySearchResults(results) {
  let container = document.getElementById('resultsContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'resultsContainer';
    container.style.cssText = `
      position: absolute;
      bottom: 100%;
      left: 0;
      right: 0;
      max-height: 300px;
      overflow-y: auto;
      background: rgba(20, 20, 35, 0.98);
      border-radius: 12px 12px 0 0;
      padding: 10px;
      margin-bottom: 5px;
    `;
    const shell = document.querySelector('.shell');
    if (shell && shell.parentElement) {
      shell.parentElement.insertBefore(container, shell);
    } else {
      document.body.appendChild(container);
    }
  }

  if (results.length === 0) {
    container.innerHTML = `
      <div style="color: #888; text-align: center; padding: 20px;">
        No matching pages found
      </div>
    `;
    return;
  }

  container.innerHTML = results
    .map(
      (r) => `
    <div class="result-card" data-url="${escapeHtml(r.url)}" style="
      background: rgba(255,255,255,0.05);
      padding: 12px;
      margin-bottom: 8px;
      border-radius: 8px;
      cursor: pointer;
      transition: background 0.2s;
    ">
      <div style="color: #fff; font-weight: 500; margin-bottom: 4px; font-size: 14px;">
        ${escapeHtml(r.title || r.domain || '')}
      </div>
      <div style="color: #888; font-size: 11px; margin-bottom: 6px;">
        ${escapeHtml(r.domain)} • ${Math.round((r.similarity || 0) * 100)}% match
      </div>
      <div style="color: #aaa; font-size: 12px; line-height: 1.4;">
        ${escapeHtml(r.snippet || '')}
      </div>
    </div>
  `
    )
    .join('');

  container.querySelectorAll('.result-card').forEach((card) => {
    card.addEventListener('click', () => {
      chrome.tabs.create({ url: card.dataset.url });
      window.close();
    });
    card.addEventListener('mouseenter', () => {
      card.style.background = 'rgba(255,255,255,0.1)';
    });
    card.addEventListener('mouseleave', () => {
      card.style.background = 'rgba(255,255,255,0.05)';
    });
  });
}

function escapeHtml(text) {
  if (text == null) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function displayNoResults() {
  displaySearchResults([]);
}

function displayError(message) {
  let container = document.getElementById('resultsContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'resultsContainer';
    container.style.cssText = `
      position: absolute;
      bottom: 100%;
      left: 0;
      right: 0;
      max-height: 300px;
      overflow-y: auto;
      padding: 10px;
      margin-bottom: 5px;
    `;
    const shell = document.querySelector('.shell');
    if (shell && shell.parentElement) {
      shell.parentElement.insertBefore(container, shell);
    } else {
      document.body.appendChild(container);
    }
  }
  container.innerHTML = `
    <div style="color: #ff6b6b; text-align: center; padding: 20px;">
      ${escapeHtml(message)}
    </div>
  `;
}

document.addEventListener('DOMContentLoaded', () => {
  const input = document.getElementById('quickSearchInput');
  const micBtn = document.getElementById('quickSearchMicBtn');
  const shell = document.querySelector('.shell');

  if (shell) {
    requestAnimationFrame(() => shell.classList.add('is-open'));
  }

  if (input) {
    input.focus();
    autoResizeQuickInput();

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        window.close();
      }
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        performSearch(input.value);
      }
    });

    input.addEventListener('input', () => {
      autoResizeQuickInput();
    });
  }

  if (micBtn) {
    micBtn.addEventListener('click', () => {
      toggleQuickSearchSpeech();
    });
  }

  const sendChip = document.querySelector('.send-chip');
  if (sendChip) {
    sendChip.addEventListener('click', () => {
      performSearch(input ? input.value : '');
    });
    sendChip.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        performSearch(input ? input.value : '');
      }
    });
  }

  startQuickSearchSpeech();
});

function ensureQuickSearchSpeechSupport() {
  if (qsSpeechSupported !== null) return qsSpeechSupported;
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  qsSpeechSupported = !!SpeechRecognition;
  if (qsSpeechSupported && !qsRecognition) {
    const SR = SpeechRecognition;
    qsRecognition = new SR();
    qsRecognition.lang = navigator.language || 'en-US';
    qsRecognition.continuous = false;
    qsRecognition.interimResults = true;

    qsRecognition.onstart = () => {
      qsRecognizing = true;
      const micBtn = document.getElementById('quickSearchMicBtn');
      if (micBtn) micBtn.classList.add('listening');
      const input = document.getElementById('quickSearchInput');
      qsSpeechBaseText = input && input.value ? input.value : '';
    };

    qsRecognition.onresult = (event) => {
      const input = document.getElementById('quickSearchInput');
      if (!input) return;

      let finalText = '';
      let interimText = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const res = event.results[i];
        if (res.isFinal) {
          finalText += res[0].transcript;
        } else {
          interimText += res[0].transcript;
        }
      }

      const base = qsSpeechBaseText ? qsSpeechBaseText + ' ' : '';
      const combined = (base + finalText + ' ' + interimText).trim();
      input.value = combined;
      autoResizeQuickInput();
    };

    qsRecognition.onerror = () => {
      qsRecognizing = false;
      const micBtn = document.getElementById('quickSearchMicBtn');
      if (micBtn) micBtn.classList.remove('listening');
    };

    qsRecognition.onend = () => {
      qsRecognizing = false;
      const micBtn = document.getElementById('quickSearchMicBtn');
      if (micBtn) micBtn.classList.remove('listening');
    };
  }
  return qsSpeechSupported;
}

function startQuickSearchSpeech() {
  if (!ensureQuickSearchSpeechSupport()) return;
  if (!qsRecognition || qsRecognizing) return;
  try {
    qsRecognition.start();
  } catch (e) {
    // ignore repeated start errors
  }
}

function stopQuickSearchSpeech() {
  if (qsRecognition && qsRecognizing) {
    try {
      qsRecognition.stop();
    } catch (_) {}
  }
}

function toggleQuickSearchSpeech() {
  if (qsRecognizing) {
    stopQuickSearchSpeech();
  } else {
    startQuickSearchSpeech();
  }
}

function autoResizeQuickInput() {
  const input = document.getElementById('quickSearchInput');
  if (!input) return;

  input.style.height = 'auto';
  const maxHeight = 120;
  const nextHeight = Math.min(input.scrollHeight, maxHeight);
  input.style.height = `${nextHeight}px`;
  input.style.overflowY = input.scrollHeight > maxHeight ? 'auto' : 'hidden';
}

