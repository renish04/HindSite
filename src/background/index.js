// ============================================
// HindSite - Background Service Worker
// Handles keyboard commands and messaging
// ============================================

chrome.commands.onCommand.addListener((command) => {
  if (command !== 'toggle_overlay') {
    return;
  }

  // Find the active tab in the current window
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tab = tabs && tabs[0];
    if (!tab || !tab.id) return;

    // Ask the content script in that tab to toggle the overlay
    chrome.tabs.sendMessage(tab.id, { type: 'TOGGLE_OVERLAY' });
  });
});

