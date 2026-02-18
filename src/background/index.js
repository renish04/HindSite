// ============================================
// HindSite - Background Service Worker
// Handles keyboard commands and messaging
// ============================================

const API_BASE = 'http://localhost:8000';

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === 'SEND_TO_BACKEND' && message.pageData) {
    fetch(`${API_BASE}/capture`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url: message.pageData.url,
        content: message.pageData.content,
        title: message.pageData.title,
        domain: message.pageData.domain,
        summary: message.pageData.summary,
        timestamp: message.pageData.timestamp,
        metadata: message.pageData.metadata
      })
    })
      .then((res) => {
        if (res.ok) return res.json();
        return res.text().then((t) => Promise.reject(new Error(`${res.status} ${t}`)));
      })
      .then((result) => {
        console.log('HindSite: Page sent to backend:', result?.status);
        sendResponse({ ok: true });
      })
      .catch((err) => {
        console.log('HindSite: Backend unavailable, saved locally only', err.message);
        sendResponse({ ok: false });
      });
    return true; // keep channel open for async sendResponse
  }

  if (message.type === 'SEARCH' && typeof message.query === 'string') {
    const query = message.query.trim();
    if (!query) {
      sendResponse({ error: 'empty_query' });
      return false;
    }
    chrome.tabs.query({}, (tabs) => {
      const openTabs = (tabs || []).map((t) => ({
        tab_id: t.id,
        window_id: t.windowId,
        url: t.url || '',
        title: t.title || ''
      }));
      fetch(`${API_BASE}/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query,
          limit: 3,
          open_tabs: openTabs
        })
      })
        .then(async (res) => {
          const contentType = res.headers.get('content-type') || '';
          const isJson = contentType.includes('application/json');
          const text = await res.text();
          if (!res.ok) {
            let msg = text;
            if (isJson) {
              try {
                const body = JSON.parse(text);
                msg = body.detail || body.message || text;
              } catch (_) {
                msg = text || `Server error (${res.status})`;
              }
            }
            throw new Error(typeof msg === 'string' ? msg : `Server error (${res.status})`);
          }
          if (!isJson) throw new Error(text || 'Invalid response');
          return JSON.parse(text);
        })
        .then((data) => {
          if (data.query_type === 'tab_switch' && data.matched_tab) {
            chrome.tabs.update(data.matched_tab.tab_id, { active: true }).then(() => {
              return chrome.windows.update(data.matched_tab.window_id, { focused: true });
            }).then(() => {
              sendResponse({ action: 'tab_switch' });
            }).catch((err) => {
              console.error('HindSite: tab switch failed', err);
              sendResponse({ action: 'error', error: err.message });
            });
          } else if (data.query_type === 'semantic_search' && data.results) {
            sendResponse({ action: 'semantic_search', results: data.results });
          } else {
            sendResponse({ action: 'no_results' });
          }
        })
        .catch((err) => {
          console.error('HindSite: search failed', err);
          sendResponse({ action: 'error', error: err.message });
        });
    });
    return true; // async sendResponse
  }

  if (message.type === 'OPEN_URL' && message.url) {
    chrome.tabs.create({ url: message.url }, () => sendResponse({ ok: true }));
    return true;
  }

  if (message.type === 'DELETE_ALL_PAGES') {
    fetch(`${API_BASE}/pages/all`, { method: 'DELETE' })
      .then((res) => (res.ok ? res.json() : res.text().then((t) => Promise.reject(new Error(t)))))
      .then((data) => sendResponse({ ok: true, count: data.count }))
      .catch((err) => {
        console.log('HindSite: Delete all failed', err.message);
        sendResponse({ ok: false, error: err.message });
      });
    return true;
  }

  if (message.type === 'DELETE_PAGE_BY_URL' && typeof message.url === 'string') {
    const encoded = encodeURIComponent(message.url);
    fetch(`${API_BASE}/pages/by-url?url=${encoded}`, { method: 'DELETE' })
      .then((res) => (res.ok ? res.json() : res.text().then((t) => Promise.reject(new Error(t)))))
      .then(() => sendResponse({ ok: true }))
      .catch((err) => {
        console.log('HindSite: Delete page by URL failed', err.message);
        sendResponse({ ok: false, error: err.message });
      });
    return true;
  }
});

function openQuickSearchWindow() {
  const width = 560;
  const height = 160;

  chrome.windows.getCurrent({}, (currentWin) => {
    const createData = {
      url: chrome.runtime.getURL('src/quicksearch/index.html'),
      type: 'popup',
      width,
      height,
      focused: true
    };

    if (
      currentWin &&
      typeof currentWin.left === 'number' &&
      typeof currentWin.top === 'number' &&
      typeof currentWin.width === 'number' &&
      typeof currentWin.height === 'number'
    ) {
      const left = Math.round(currentWin.left + (currentWin.width - width) / 2);
      const top = Math.round(currentWin.top + currentWin.height - height - 40);
      createData.left = left;
      createData.top = top;
    }

    chrome.windows.create(createData);
  });
}

chrome.commands.onCommand.addListener((command) => {
  if (command !== 'toggle_overlay') {
    return;
  }

  // Find the active tab in the current window
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tab = tabs && tabs[0];
    if (!tab || !tab.id) {
      openQuickSearchWindow();
      return;
    }

    const url = tab.url || '';
    const isRestricted =
      url.startsWith('chrome://') ||
      url.startsWith('chrome-extension://') ||
      url.startsWith('devtools://') ||
      url.startsWith('view-source:') ||
      url.startsWith('edge://') ||
      url.startsWith('about:') ||
      url.includes('chrome.google.com/webstore');

    if (isRestricted) {
      openQuickSearchWindow();
      return;
    }

    // Non-restricted page: only toggle in-page overlay
    chrome.tabs.sendMessage(tab.id, { type: 'TOGGLE_OVERLAY' });
  });
});

