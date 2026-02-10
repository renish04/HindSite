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
let hsOverlayInput = null;
let hsOverlayVisible = false;

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
    
    const urlExists = savedPages.some(page => page.url === pageData.url);
    
    if (urlExists) {
      console.log('⚠️ Page already saved, skipping duplicate');
      return;
    }
    
    savedPages.push(pageData);
    
    chrome.storage.local.set({ savedPages: savedPages }, () => {
      console.log('✅ Page saved to storage!');
      console.log(`   Total pages saved: ${savedPages.length}`);
      
      showNotification();
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
  hsOverlayRoot.style.cssText = `
    position: fixed;
    left: 50%;
    bottom: 32px;
    transform: translateX(-50%);
    z-index: 2147483647;
    pointer-events: none;
    display: none;
  `;

  const panel = document.createElement('div');
  panel.style.cssText = `
    pointer-events: auto;
    min-width: 420px;
    max-width: 560px;
    width: 46vw;
    box-sizing: border-box;
    padding: 10px 12px;
    border-radius: 999px;
    background: radial-gradient(circle at top left, rgba(15,23,42,0.92), rgba(15,23,42,0.86));
    box-shadow:
      0 18px 45px rgba(15,23,42,0.85),
      0 0 0 1px rgba(148,163,184,0.45);
    backdrop-filter: blur(18px);
    display: flex;
    align-items: center;
    gap: 10px;
    border: 1px solid rgba(148,163,184,0.65);
    color: #e5e7eb;
    font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;
  `;

  const hint = document.createElement('div');
  hint.textContent = 'HindSite quick search';
  hint.style.cssText = `
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    color: #9ca3af;
    margin-right: 4px;
  `;

  const input = document.createElement('input');
  input.type = 'text';
  input.placeholder = 'Type to search (no action yet)...';
  input.style.cssText = `
    flex: 1;
    border: none;
    outline: none;
    background: transparent;
    color: #f9fafb;
    font-size: 14px;
    font-weight: 400;
    padding: 3px 0;
  `;

  const kbd = document.createElement('div');
  kbd.textContent = '➤';
  kbd.title = 'Send';
  kbd.style.cssText = `
    font-size: 11px;
    padding: 4px 8px;
    border-radius: 999px;
    border: 1px solid rgba(148,163,184,0.6);
    background: rgba(15,23,42,0.9);
    color: #e5e7eb;
    cursor: default;
  `;

  panel.appendChild(hint);
  panel.appendChild(input);
  panel.appendChild(kbd);
  hsOverlayRoot.appendChild(panel);
  document.documentElement.appendChild(hsOverlayRoot);

  hsOverlayInput = input;

  // ESC closes overlay
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      hideOverlay();
    }
  });
}

function showOverlay() {
  createOverlayIfNeeded();
  if (!hsOverlayRoot) return;

  hsOverlayRoot.style.display = 'block';
  hsOverlayVisible = true;

  // Focus input with minimal delay to avoid layout races
  setTimeout(() => {
    hsOverlayInput && hsOverlayInput.focus();
  }, 0);
}

function hideOverlay() {
  if (!hsOverlayRoot) return;
  hsOverlayRoot.style.display = 'none';
  hsOverlayVisible = false;
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