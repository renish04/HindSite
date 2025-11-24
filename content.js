// ============================================
// RESEARCH ASSISTANT - Content Script
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

console.log('🔍 Research Assistant: Monitoring started');

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
  notification.textContent = '✅ Page saved to Research Assistant';
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