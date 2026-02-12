// ============================================
// HindSite - Content Script
// Tracks time, scroll, and extracts content
// ============================================

// ============================================
// INITIALIZATION
// ============================================
let activeTime = 0;
let timerRunning = false;
let timerInterval = null;

let maxScrollPercent = 0;
let scrollHistory = [];
let lastScrollTime = null;

let isShortPage = false;
let hasExtracted = false;

let checkInterval = null;

// Overlay state
let hsOverlayRoot = null;
let hsOverlayPanel = null;
let hsOverlayInput = null;
let hsOverlayVisible = false;
let hsOverlayMicBtn = null;
let hsOverlayHideTimer = null;

// Speech recognition state (overlay)
let hsRecognition = null;
let hsRecognizing = false;
let hsSpeechBaseText = '';
let hsSpeechSupported = null;

console.log('🔍 HindSite: Monitoring started');

// ============================================
// PAGE ANALYSIS
// ============================================
function analyzePageHeight() {
  const pageHeight = document.documentElement.scrollHeight;
  const windowHeight = window.innerHeight;
  const scrollableArea = pageHeight - windowHeight;
  
  if (scrollableArea < 100) {
    isShortPage = true;
    console.log('📄 Short page detected - will use time-only criteria');
  } else {
    isShortPage = false;
    console.log('📜 Normal page detected - will use time + scroll criteria');
  }
}

window.addEventListener('load', () => {
  analyzePageHeight();
});

// ============================================
// ACTIVE TIME TRACKING
// ============================================
function startTimer() {
  if (!timerRunning) {
    timerRunning = true;
    
    timerInterval = setInterval(() => {
      if (timerRunning) {
        activeTime++;
        console.log(`⏱️ Active time: ${activeTime}s`);
      }
    }, 1000);
  }
}

function pauseTimer() {
  timerRunning = false;
  console.log('⏸️ Timer paused');
}

function resumeTimer() {
  timerRunning = true;
  console.log('▶️ Timer resumed');
}

document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    pauseTimer();
  } else {
    resumeTimer();
  }
});

startTimer();

// ============================================
// SCROLL TRACKING
// ============================================
function calculateScrollPercent() {
  const scrollTop = window.scrollY;
  const windowHeight = window.innerHeight;
  const docHeight = document.documentElement.scrollHeight;
  
  const scrollableDistance = docHeight - windowHeight;
  
  if (scrollableDistance <= 0) {
    return 0;
  }
  
  const scrollPercent = (scrollTop / scrollableDistance) * 100;
  return Math.min(Math.round(scrollPercent), 100);
}

function updateScrollTracking() {
  const currentScroll = calculateScrollPercent();
  const currentTime = Date.now();
  
  if (currentScroll > maxScrollPercent) {
    maxScrollPercent = currentScroll;
    
    scrollHistory.push({
      percent: currentScroll,
      timestamp: currentTime
    });
    
    console.log(`📜 Scroll: ${maxScrollPercent}%`);
  }
  
  lastScrollTime = currentTime;
}

window.addEventListener('scroll', updateScrollTracking);
window.addEventListener('load', updateScrollTracking);

// ============================================
// GRADUAL SCROLL DETECTION
// ============================================
function wasScrollGradual() {
  if (maxScrollPercent < 40) {
    return false;
  }
  
  let timeToReach40 = null;
  
  for (let i = 0; i < scrollHistory.length; i++) {
    if (scrollHistory[i].percent >= 40) {
      const firstTime = scrollHistory[0].timestamp;
      const fortyPercentTime = scrollHistory[i].timestamp;
      timeToReach40 = (fortyPercentTime - firstTime) / 1000;
      break;
    }
  }
  
  if (timeToReach40 !== null && timeToReach40 < 10) {
    console.log(`⚠️ Scroll too fast: ${timeToReach40}s to reach 40%`);
    return false;
  }
  
  console.log(`✅ Gradual scroll detected: ${timeToReach40}s to reach 40%`);
  return true;
}

// ============================================
// THRESHOLD CHECKING
// ============================================
function checkThresholds() {
  if (hasExtracted) {
    return;
  }
  
  console.log('🔍 Checking thresholds...');
  console.log(`   Active time: ${activeTime}s / 60s`);
  console.log(`   Max scroll: ${maxScrollPercent}% / 40%`);
  console.log(`   Is short page: ${isShortPage}`);
  
  if (isShortPage) {
    if (activeTime >= 60) {
      console.log('✅ Short page threshold met: 60s active time');
      extractContent();
    }
  } else {
    if (activeTime >= 60 && maxScrollPercent >= 40 && wasScrollGradual()) {
      console.log('✅ Normal page thresholds met: 60s + 40% scroll + gradual');
      extractContent();
    }
  }
}

checkInterval = setInterval(checkThresholds, 5000);

// ============================================
// CONTENT EXTRACTION
// ============================================
function extractContent() {
  console.log('📥 Extracting content...');
  
  hasExtracted = true;
  
  clearInterval(timerInterval);
  clearInterval(checkInterval);
  pauseTimer();
  
  const pageText = document.body.innerText;
  const wordCount = pageText.split(/\s+/).filter(word => word.length > 0).length;
  
  const pageData = {
    url: window.location.href,
    content: pageText,
    metadata: {
      timeSpent: activeTime,
      scrollPercent: maxScrollPercent,
      timestamp: new Date().toISOString(),
      wordCount: wordCount,
      isShortPage: isShortPage
    }
  };
  
  console.log('📦 Content extracted:', pageData);
  
  saveToStorage(pageData);
}

// ============================================
// STORAGE
// ============================================
function saveToStorage(pageData) {
  chrome.storage.local.get(['savedPages'], (result) => {
    const savedPages = result.savedPages || [];

    const urlExists = savedPages.some((page) => page.url === pageData.url);

    if (urlExists) {
      console.log('⚠️ Page already saved, skipping duplicate');
      return;
    }

    savedPages.push(pageData);

    chrome.storage.local.set({ savedPages: savedPages }, () => {
      console.log('✅ Page saved to storage!');
      console.log(`   Total pages saved: ${savedPages.length}`);
      showNotification();

      // Ask background to POST to backend (avoids page-origin permission prompts)
      chrome.runtime.sendMessage({ type: 'SEND_TO_BACKEND', pageData }).catch(() => {});
    });
  });
}

function showNotification() {
  const notification = document.createElement('div');
  notification.textContent = 'Page saved to HindSite';
  notification.style.cssText = `
    position: fixed;
    top: 20px;
    right: 20px;
    background: #4CAF50;
    color: white;
    padding: 15px 20px;
    border-radius: 5px;
    z-index: 10000;
    font-family: Arial, sans-serif;
    box-shadow: 0 2px 5px rgba(0,0,0,0.2);
  `;
  
  document.body.appendChild(notification);
  
  setTimeout(() => {
    notification.remove();
  }, 3000);
}

// ============================================
// OVERLAY SEARCH BAR (TOGGLED BY SHORTCUT)
// ============================================

function createOverlayIfNeeded() {
  if (hsOverlayRoot) return;

  hsOverlayRoot = document.createElement('div');
  hsOverlayRoot.id = 'hindsite-overlay-root';
  hsOverlayRoot.className = 'hs-root';
  hsOverlayRoot.style.cssText = `
    position: fixed;
    left: 50%;
    bottom: 32px;
    transform: translateX(-50%);
    z-index: 2147483647;
    pointer-events: none;
    display: none;
  `;

  // Inject lightweight CSS once (for animations / mic pulse)
  if (!document.getElementById('hindsite-overlay-style')) {
    const style = document.createElement('style');
    style.id = 'hindsite-overlay-style';
    style.textContent = `
      #hindsite-overlay-root .hs-panel {
        opacity: 0;
        transform: translateY(18px) scale(0.985);
        transition: transform 180ms cubic-bezier(.2,.9,.2,1.15), opacity 180ms ease-out;
        will-change: transform, opacity;
      }
      #hindsite-overlay-root.hs-visible .hs-panel {
        opacity: 1;
        transform: translateY(0) scale(1);
      }
      @keyframes hsMicPulse {
        0% { box-shadow: 0 0 0 0 rgba(255,255,255,0.22); }
        70% { box-shadow: 0 0 0 10px rgba(255,255,255,0); }
        100% { box-shadow: 0 0 0 0 rgba(255,255,255,0); }
      }
      #hindsite-overlay-root .hs-mic.listening {
        border-color: rgba(255,255,255,0.6) !important;
        animation: hsMicPulse 1.1s ease-in-out infinite;
      }
      #hindsite-overlay-root .hs-mic,
      #hindsite-overlay-root .hs-send-chip {
        transition: transform 0.18s ease-out;
      }
      #hindsite-overlay-root .hs-mic:hover,
      #hindsite-overlay-root .hs-send-chip:hover {
        transform: scale(1.15);
      }
      #hindsite-overlay-root .hs-mic:active,
      #hindsite-overlay-root .hs-send-chip:active {
        transform: scale(0.92);
      }
      #hindsite-overlay-root .hs-send-chip.hs-press {
        transform: scale(0.88);
      }
    `;
    document.documentElement.appendChild(style);
  }

  const panel = document.createElement('div');
  panel.className = 'hs-panel';
  panel.style.cssText = `
    pointer-events: auto;
    min-width: 420px;
    max-width: 560px;
    width: 46vw;
    box-sizing: border-box;
    padding: 12px 14px;
    border-radius: 999px;
    background: linear-gradient(135deg, rgba(26,50,82,0.96) 0%, rgba(38,62,94,0.94) 50%, rgba(44,56,74,0.92) 100%);
    box-shadow: 0 20px 48px rgba(26,50,82,0.45), 0 0 0 1px rgba(148,163,184,0.35);
    border: 1px solid rgba(148,163,184,0.5);
    backdrop-filter: blur(22px);
    display: flex;
    align-items: center;
    gap: 10px;
    color: #e2e8f0;
    font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;
  `;
  hsOverlayPanel = panel;

  const hint = document.createElement('div');
  hint.textContent = 'HindSite quick search';
  hint.style.cssText = `
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    color: #94a3b8;
    margin-right: 4px;
    flex: 0 0 auto;
    white-space: nowrap;
  `;

  const input = document.createElement('textarea');
  input.placeholder = 'Type to search...';
  input.rows = 1;
  input.style.cssText = `
    flex: 1;
    border: none;
    outline: none;
    background: transparent;
    color: #f1f5f9;
    font-size: 14px;
    font-weight: 400;
    padding: 3px 0;
    resize: none;
    overflow: hidden;
    min-height: 20px;
    max-height: 120px;
    line-height: 1.35;
  `;

  const micBtn = document.createElement('button');
  micBtn.type = 'button';
  micBtn.title = 'Voice input';
  micBtn.className = 'hs-mic';
  micBtn.style.cssText = `
    flex: 0 0 auto;
    width: 26px;
    height: 26px;
    border-radius: 999px;
    border: 1px solid rgba(148,163,184,0.5);
    background: rgba(26,50,82,0.9);
    color: #e2e8f0;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    cursor: pointer;
  `;
  micBtn.innerHTML = '<svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path d="M12 3a2.5 2.5 0 0 1 2.5 2.5v5A2.5 2.5 0 0 1 12 13a2.5 2.5 0 0 1-2.5-2.5v-5A2.5 2.5 0 0 1 12 3Zm0 14a5 5 0 0 0 5-5 .75.75 0 0 1 1.5 0A6.5 6.5 0 0 1 12.75 18.47V21h-1.5v-2.53A6.5 6.5 0 0 1 5.5 12a.75.75 0 0 1 1.5 0 5 5 0 0 0 5 5Z" fill="currentColor"/></svg>';

  const sendChip = document.createElement('div');
  sendChip.className = 'hs-send-chip';
  sendChip.textContent = '➤';
  sendChip.title = 'Send';
  sendChip.style.cssText = `
    flex: 0 0 auto;
    font-size: 12px;
    width: 26px;
    height: 26px;
    border-radius: 999px;
    border: 1px solid rgba(148,163,184,0.6);
    background: rgba(26,50,82,0.9);
    color: #e2e8f0;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    user-select: none;
  `;

  panel.appendChild(hint);
  panel.appendChild(input);
  panel.appendChild(micBtn);
  panel.appendChild(sendChip);
  hsOverlayRoot.appendChild(panel);
  document.documentElement.appendChild(hsOverlayRoot);

  hsOverlayInput = input;
  hsOverlayMicBtn = micBtn;

  // ESC closes overlay
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      hideOverlay();
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      performOverlaySearch(input.value);
    }
  });

  input.addEventListener('input', () => {
    autoResizeOverlayInput();
  });

  micBtn.addEventListener('click', () => {
    toggleOverlaySpeech();
  });

  sendChip.addEventListener('click', () => {
    performOverlaySearch(hsOverlayInput ? hsOverlayInput.value : '');
  });
}

function showOverlay() {
  createOverlayIfNeeded();
  if (!hsOverlayRoot) return;

  hsOverlayRoot.style.display = 'block';
  hsOverlayVisible = true;
  if (hsOverlayHideTimer) {
    clearTimeout(hsOverlayHideTimer);
    hsOverlayHideTimer = null;
  }

  // Trigger pop-in animation
  requestAnimationFrame(() => {
    hsOverlayRoot && hsOverlayRoot.classList.add('hs-visible');
  });

  // Focus input with minimal delay to avoid layout races
  setTimeout(() => {
    hsOverlayInput && hsOverlayInput.focus();
    autoResizeOverlayInput();
  }, 0);

  // Auto-start voice input when overlay opens, if supported
  startOverlaySpeech();
}

function hideOverlay() {
  if (!hsOverlayRoot) return;
  hsOverlayRoot.classList.remove('hs-visible');
  hsOverlayVisible = false;
  stopOverlaySpeech();
  const resultsEl = hsOverlayRoot.querySelector('.hs-overlay-results');
  if (resultsEl) resultsEl.innerHTML = '';

  // Let the exit transition finish, then hide
  hsOverlayHideTimer = setTimeout(() => {
    if (hsOverlayRoot) hsOverlayRoot.style.display = 'none';
  }, 190);
}

function ensureOverlayResultsContainer() {
  if (!hsOverlayRoot) return null;
  let container = hsOverlayRoot.querySelector('.hs-overlay-results');
  if (!container) {
    container = document.createElement('div');
    container.className = 'hs-overlay-results';
    container.style.cssText = `
      pointer-events: auto;
      max-height: 280px;
      overflow-y: auto;
      margin-bottom: 8px;
      padding: 8px;
      background: rgba(15,23,42,0.95);
      border-radius: 12px;
      border: 1px solid rgba(148,163,184,0.3);
    `;
    hsOverlayRoot.insertBefore(container, hsOverlayRoot.firstChild);
  }
  return container;
}

function performOverlaySearch(query) {
  const q = (query || (hsOverlayInput && hsOverlayInput.value) || '').trim();
  if (!q) return;

  // In-out press animation on send button (from Enter or click)
  const sendChip = hsOverlayRoot && hsOverlayRoot.querySelector('.hs-send-chip');
  if (sendChip) {
    sendChip.classList.add('hs-press');
    setTimeout(() => sendChip.classList.remove('hs-press'), 180);
  }

  chrome.runtime.sendMessage({ type: 'SEARCH', query: q }, (response) => {
    if (chrome.runtime.lastError) {
      const resultsEl = ensureOverlayResultsContainer();
      if (resultsEl) {
        resultsEl.innerHTML = '<div style="color:#f87171;text-align:center;padding:12px;">Search failed</div>';
        resultsEl.style.display = 'block';
      }
      return;
    }
    if (response && response.action === 'tab_switch') {
      hideOverlay();
      return;
    }
    if (response && response.action === 'semantic_search' && response.results && response.results.length) {
      showOverlayResults(response.results);
      return;
    }
    const resultsEl = ensureOverlayResultsContainer();
    if (resultsEl) {
      resultsEl.innerHTML = '<div style="color:#94a3b8;text-align:center;padding:12px;">No matching pages found</div>';
      resultsEl.style.display = 'block';
    }
  });
}

function showOverlayResults(results) {
  const container = ensureOverlayResultsContainer();
  if (!container) return;
  container.innerHTML = results
    .map((r) => {
      const title = (r.title || '').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
      const url = (r.url || '').replace(/"/g, '&quot;');
      return `<div class="hs-result-card" data-url="${url}" style="
        padding: 10px 12px;
        margin-bottom: 6px;
        border-radius: 8px;
        background: rgba(255,255,255,0.06);
        cursor: pointer;
        font-size: 13px;
        color: #e2e8f0;
      " title="${url}">${title || 'Untitled'}</div>`;
    })
    .join('');
  container.style.display = 'block';
  container.querySelectorAll('.hs-result-card').forEach((el) => {
    el.addEventListener('click', () => {
      const url = el.getAttribute('data-url');
      if (url) chrome.runtime.sendMessage({ type: 'OPEN_URL', url });
      hideOverlay();
    });
  });
}

function toggleOverlay() {
  if (hsOverlayVisible) {
    hideOverlay();
  } else {
    showOverlay();
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message && message.type === 'TOGGLE_OVERLAY') {
    toggleOverlay();
  }
});

// ============================================
// SPEECH RECOGNITION (OVERLAY)
// ============================================

function ensureSpeechSupport() {
  if (hsSpeechSupported !== null) return hsSpeechSupported;
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  hsSpeechSupported = !!SpeechRecognition;
  if (hsSpeechSupported && !hsRecognition) {
    const SR = SpeechRecognition;
    hsRecognition = new SR();
    hsRecognition.lang = navigator.language || 'en-US';
    hsRecognition.continuous = false;
    hsRecognition.interimResults = true;

    hsRecognition.onstart = () => {
      hsRecognizing = true;
      if (hsOverlayMicBtn) hsOverlayMicBtn.classList.add('listening');
      if (hsOverlayInput) {
        hsSpeechBaseText = hsOverlayInput.value || '';
      }
    };

    hsRecognition.onresult = (event) => {
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
      if (hsOverlayInput) {
        const base = hsSpeechBaseText ? hsSpeechBaseText + ' ' : '';
        const combined = (base + finalText + ' ' + interimText).trim();
        hsOverlayInput.value = combined;
        autoResizeOverlayInput();
      }
    };

    hsRecognition.onerror = () => {
      hsRecognizing = false;
      if (hsOverlayMicBtn) hsOverlayMicBtn.classList.remove('listening');
    };

    hsRecognition.onend = () => {
      hsRecognizing = false;
      if (hsOverlayMicBtn) hsOverlayMicBtn.classList.remove('listening');
    };
  }
  return hsSpeechSupported;
}

function startOverlaySpeech() {
  if (!ensureSpeechSupport()) return;
  if (!hsRecognition || hsRecognizing) return;
  try {
    hsRecognition.start();
  } catch (e) {
    // ignore repeated start errors
  }
}

function stopOverlaySpeech() {
  if (hsRecognition && hsRecognizing) {
    try {
      hsRecognition.stop();
    } catch (e) {
      // ignore
    }
  }
}

function toggleOverlaySpeech() {
  if (hsRecognizing) {
    stopOverlaySpeech();
  } else {
    startOverlaySpeech();
  }
}

function autoResizeOverlayInput() {
  if (!hsOverlayInput) return;
  hsOverlayInput.style.height = 'auto';
  const maxHeight = 120;
  const nextHeight = Math.min(hsOverlayInput.scrollHeight, maxHeight);
  hsOverlayInput.style.height = `${nextHeight}px`;
  hsOverlayInput.style.overflowY = hsOverlayInput.scrollHeight > maxHeight ? 'auto' : 'hidden';
}