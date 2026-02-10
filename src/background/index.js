// ============================================
// HindSite - Background Service Worker
// Handles keyboard commands and messaging
// ============================================

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

