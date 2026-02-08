// ============================================
// HindSite - Popup Script
// Displays saved pages and handles user actions
// ============================================

// ============================================
// LOAD AND DISPLAY SAVED PAGES
// ============================================

document.addEventListener('DOMContentLoaded', () => {
    loadSavedPages();
    
    // Attach event listeners to buttons
    document.getElementById('exportBtn').addEventListener('click', exportAllPages);
    document.getElementById('clearBtn').addEventListener('click', clearAllPages);
  });
  
  function loadSavedPages() {
    chrome.storage.local.get(['savedPages'], (result) => {
      const savedPages = result.savedPages || [];
      
      if (savedPages.length === 0) {
        showEmptyState();
      } else {
        displayPages(savedPages);
        updateStatistics(savedPages);
      }
    });
  }
  
  // ============================================
  // DISPLAY PAGES
  // ============================================
  
  function displayPages(pages) {
    const pagesList = document.getElementById('pagesList');
    pagesList.innerHTML = ''; // Clear existing content
    
    // Show most recent first
    const sortedPages = [...pages].reverse();
    
    sortedPages.forEach((page, index) => {
      const pageCard = createPageCard(page, pages.length - 1 - index);
      pagesList.appendChild(pageCard);
    });
  }
  
  function createPageCard(page, originalIndex) {
    const card = document.createElement('div');
    card.className = 'page-item';
    
    // Extract domain from URL
    const domain = extractDomain(page.url);
    
    // Format timestamp
    const date = new Date(page.metadata.timestamp);
    const formattedDate = formatDate(date);
    
    // Create content preview (first 150 characters)
    const preview = page.content.substring(0, 150).trim() + '...';
    
    // Build card HTML
    card.innerHTML = `
      <div class="page-url" title="${page.url}">${domain}</div>
      <div class="page-preview">${preview}</div>
      <div class="page-meta">
        <div class="meta-item">⏱️ ${page.metadata.timeSpent}s</div>
        <div class="meta-item">📜 ${page.metadata.scrollPercent}%</div>
        <div class="meta-item">📝 ${page.metadata.wordCount.toLocaleString()} words</div>
        <div class="meta-item">📅 ${formattedDate}</div>
      </div>
    `;
    
    // Click to open URL (focus existing tab if already open)
    card.addEventListener('click', () => {
      openPageUrl(page.url);
    });
    
    return card;
  }
  
  // ============================================
  // UPDATE STATISTICS
  // ============================================
  
  function updateStatistics(pages) {
    // Total pages
    const totalPages = pages.length;
    document.getElementById('totalPages').textContent = totalPages;
    
    // Total words
    const totalWords = pages.reduce((sum, page) => sum + page.metadata.wordCount, 0);
    document.getElementById('totalWords').textContent = totalWords.toLocaleString();
    
    // Average time spent
    const totalTime = pages.reduce((sum, page) => sum + page.metadata.timeSpent, 0);
    const avgTime = Math.round(totalTime / totalPages);
    document.getElementById('avgTime').textContent = avgTime + 's';
  }
  
  // ============================================
  // EMPTY STATE
  // ============================================
  
  function showEmptyState() {
    const pagesList = document.getElementById('pagesList');
    pagesList.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">📭</div>
        <div class="empty-state-title">No pages saved yet</div>
        <div class="empty-state-text">
          Browse the web normally and pages will be saved automatically when you:<br>
          • Spend 60+ seconds on a page<br>
          • Scroll through 40%+ of the content<br>
          • Read gradually (not jumping around)
        </div>
      </div>
    `;
    
    // Update stats to 0
    document.getElementById('totalPages').textContent = '0';
    document.getElementById('totalWords').textContent = '0';
    document.getElementById('avgTime').textContent = '0s';
  }
  
  // ============================================
  // EXPORT FUNCTIONALITY
  // ============================================
  
  function exportAllPages() {
    chrome.storage.local.get(['savedPages'], (result) => {
      const savedPages = result.savedPages || [];
      
      if (savedPages.length === 0) {
        alert('No pages to export!');
        return;
      }
      
      // Create JSON file
      const dataStr = JSON.stringify(savedPages, null, 2);
      const dataBlob = new Blob([dataStr], { type: 'application/json' });
      
      // Create download link
      const url = URL.createObjectURL(dataBlob);
      const link = document.createElement('a');
      link.href = url;
      
      // Filename with timestamp
      const timestamp = new Date().toISOString().split('T')[0];
      link.download = `HindSite-export-${timestamp}.json`;
      
      // Trigger download
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      
      // Clean up
      URL.revokeObjectURL(url);
      
      console.log(`✅ Exported ${savedPages.length} pages`);
    });
  }
  
  // ============================================
  // CLEAR ALL FUNCTIONALITY
  // ============================================
  
  function clearAllPages() {
    const confirmed = confirm(
      'Are you sure you want to delete all saved pages?\n\nThis action cannot be undone!'
    );
    
    if (confirmed) {
      chrome.storage.local.set({ savedPages: [] }, () => {
        console.log('🗑️ All pages cleared');
        showEmptyState();
      });
    }
  }
  
  // ============================================
  // OPEN URL (focus existing tab if already open)
  // ============================================
  
  function openPageUrl(url) {
    // Normalize target URL for exact comparison
    const targetUrl = normalizeUrl(url);
    
    // Get base URL (without fragment) for efficient querying
    // Chrome's query ignores fragments, so this will return all tabs with same base URL
    const baseUrl = getBaseUrlWithoutFragment(url);
    
    // Query tabs matching the base URL (Chrome ignores fragments in query)
    chrome.tabs.query({ url: baseUrl }, (tabs) => {
      if (tabs && tabs.length > 0) {
        // Find exact URL match (including fragment) by comparing normalized URLs
        const exactMatch = tabs.find(tab => normalizeUrl(tab.url) === targetUrl);
        
        if (exactMatch) {
          // Focus the exact matching tab
          chrome.tabs.update(exactMatch.id, { active: true });
          chrome.windows.update(exactMatch.windowId, { focused: true });
          return;
        }
      }
      
      // No exact match found, create new tab
      chrome.tabs.create({ url });
    });
  }
  
  // Normalize URL for exact comparison (preserves fragments)
  function normalizeUrl(url) {
    try {
      const urlObj = new URL(url);
      // Return full href including fragment for exact matching
      return urlObj.href;
    } catch (e) {
      return url;
    }
  }
  
  // Get base URL without fragment for querying
  // Chrome's tabs.query ignores fragments, so this efficiently gets candidate tabs
  function getBaseUrlWithoutFragment(url) {
    try {
      const urlObj = new URL(url);
      // Return URL without fragment - Chrome will match tabs with this base regardless of fragment
      return `${urlObj.protocol}//${urlObj.host}${urlObj.pathname}${urlObj.search}`;
    } catch (e) {
      // Fallback: try to remove fragment manually
      const hashIndex = url.indexOf('#');
      return hashIndex !== -1 ? url.substring(0, hashIndex) : url;
    }
  }
  
  // ============================================
  // UTILITY FUNCTIONS
  // ============================================
  
  function extractDomain(url) {
    try {
      const urlObj = new URL(url);
      return urlObj.hostname;
    } catch (e) {
      return url;
    }
  }
  
  function formatDate(date) {
    const now = new Date();
    const diffTime = Math.abs(now - date);
    const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));
    
    if (diffDays === 0) {
      return 'Today';
    } else if (diffDays === 1) {
      return 'Yesterday';
    } else if (diffDays < 7) {
      return `${diffDays} days ago`;
    } else {
      return date.toLocaleDateString();
    }
  }