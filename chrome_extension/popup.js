// Facebook Group Scanner - Apify Integration
// v6.0.0

// DOM Elements
const apifyTokenInput = document.getElementById('apifyToken');
const postsLimitSelect = document.getElementById('postsLimit');
const sortOrderSelect = document.getElementById('sortOrder');
const groupUrlDiv = document.getElementById('groupUrl');
const groupUrlValue = document.getElementById('groupUrlValue');
const progressDiv = document.getElementById('progress');
const progressText = document.getElementById('progressText');
const progressFill = document.getElementById('progressFill');
const resultsDiv = document.getElementById('results');
const resultsCount = document.getElementById('resultsCount');
const btnScrape = document.getElementById('btnScrape');
const btnDownload = document.getElementById('btnDownload');
const settingsContent = document.getElementById('settingsContent');
const settingsArrow = document.getElementById('settingsArrow');

// State
let currentGroupUrl = null;
let scrapedData = null;

// Apify Actor ID 
// Format: either "username~actor-name" or the Actor ID from the console URL
const APIFY_ACTOR_ID = '2chN8UQcH1CfxLRNE';

// Initialize
async function init() {
  // Load saved settings
  const settings = await chrome.storage.sync.get(['apifyToken', 'postsLimit', 'sortOrder']);
  
  if (settings.apifyToken) {
    apifyTokenInput.value = settings.apifyToken;
  } else {
    // Show settings if no token saved
    settingsContent.classList.add('show');
    settingsArrow.textContent = '▲';
  }
  
  if (settings.postsLimit) {
    postsLimitSelect.value = settings.postsLimit;
  }
  
  if (settings.sortOrder) {
    sortOrderSelect.value = settings.sortOrder;
  }
  
  // Detect current page
  await detectGroupUrl();
}

// Toggle settings visibility
function toggleSettings() {
  console.log('Toggle settings clicked');
  settingsContent.classList.toggle('show');
  settingsArrow.textContent = settingsContent.classList.contains('show') ? '▲' : '▼';
}

// Save settings
async function saveSettings() {
  const btn = document.getElementById('btnSaveSettings');
  
  try {
    await chrome.storage.sync.set({
      apifyToken: apifyTokenInput.value,
      postsLimit: postsLimitSelect.value,
      sortOrder: sortOrderSelect.value
    });
    
    // Visual feedback
    btn.textContent = '✅ Sauvegardé!';
    btn.style.background = 'rgba(0, 210, 106, 0.3)';
    
    setTimeout(() => {
      btn.textContent = '💾 Sauvegarder';
      btn.style.background = '';
    }, 2000);
    
    // Re-check if we can enable the scrape button
    await detectGroupUrl();
    
    console.log('Settings saved!', apifyTokenInput.value ? 'Token: ****' + apifyTokenInput.value.slice(-4) : 'No token');
    
  } catch (error) {
    console.error('Error saving settings:', error);
    btn.textContent = '❌ Erreur!';
    setTimeout(() => {
      btn.textContent = '💾 Sauvegarder';
    }, 2000);
  }
}

// Detect Facebook group URL
async function detectGroupUrl() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    
    if (tab.url && tab.url.includes('facebook.com/groups/')) {
      // Extract clean group URL
      const match = tab.url.match(/(https:\/\/www\.facebook\.com\/groups\/[^\/\?]+)/);
      if (match) {
        currentGroupUrl = match[1];
        groupUrlValue.textContent = currentGroupUrl;
        groupUrlDiv.classList.remove('error');
        
        // Enable button if we have a token
        const settings = await chrome.storage.sync.get(['apifyToken']);
        btnScrape.disabled = !settings.apifyToken;
        
        if (!settings.apifyToken) {
          groupUrlValue.textContent += '\n⚠️ Configure ton token Apify ci-dessus';
        }
        
        return true;
      }
    }
    
    // Not on a Facebook group
    currentGroupUrl = null;
    groupUrlDiv.classList.add('error');
    groupUrlValue.textContent = '❌ Ouvre un groupe Facebook pour scraper';
    btnScrape.disabled = true;
    return false;
    
  } catch (error) {
    groupUrlDiv.classList.add('error');
    groupUrlValue.textContent = '❌ Erreur: ' + error.message;
    btnScrape.disabled = true;
    return false;
  }
}

// Start scraping with Apify
async function startScraping() {
  const token = apifyTokenInput.value || (await chrome.storage.sync.get(['apifyToken'])).apifyToken;
  
  if (!token) {
    showError('Token Apify manquant! Configure-le dans les paramètres.');
    return;
  }
  
  if (!currentGroupUrl) {
    showError('Aucun groupe Facebook détecté.');
    return;
  }
  
  // Update UI
  btnScrape.disabled = true;
  btnScrape.textContent = '⏳ Scraping...';
  progressDiv.classList.add('show');
  resultsDiv.classList.remove('show');
  btnDownload.style.display = 'none';
  
  try {
    // Step 1: Start the Apify run
    updateProgress('Lancement du scraper Apify...', 10);
    
    const runInput = {
      startUrls: [{ url: currentGroupUrl }],
      resultsLimit: parseInt(postsLimitSelect.value),
      sort: sortOrderSelect.value,
      maxComments: 5
    };
    
    const startResponse = await fetch(`https://api.apify.com/v2/acts/${APIFY_ACTOR_ID}/runs?token=${token}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(runInput)
    });
    
    if (!startResponse.ok) {
      const error = await startResponse.json();
      throw new Error(error.error?.message || 'Erreur Apify: ' + startResponse.status);
    }
    
    const runData = await startResponse.json();
    const runId = runData.data.id;
    
    console.log('Apify run started:', runId);
    updateProgress('Scraper démarré, extraction en cours...', 20);
    
    // Step 2: Poll for completion
    let status = 'RUNNING';
    let pollCount = 0;
    const maxPolls = 120; // 10 minutes max (5s * 120)
    
    while (status === 'RUNNING' || status === 'READY') {
      await sleep(5000); // Wait 5 seconds
      pollCount++;
      
      if (pollCount > maxPolls) {
        throw new Error('Timeout: le scraping prend trop de temps');
      }
      
      const statusResponse = await fetch(`https://api.apify.com/v2/actor-runs/${runId}?token=${token}`);
      const statusData = await statusResponse.json();
      status = statusData.data.status;
      
      // Update progress
      const progress = Math.min(20 + (pollCount * 2), 80);
      updateProgress(`Extraction en cours... (${Math.floor(pollCount * 5)}s)`, progress);
      
      console.log('Poll', pollCount, 'status:', status);
    }
    
    if (status !== 'SUCCEEDED') {
      throw new Error(`Scraping échoué: ${status}`);
    }
    
    updateProgress('Récupération des résultats...', 90);
    
    // Step 3: Get the results
    const datasetId = (await (await fetch(`https://api.apify.com/v2/actor-runs/${runId}?token=${token}`)).json()).data.defaultDatasetId;
    
    const resultsResponse = await fetch(`https://api.apify.com/v2/datasets/${datasetId}/items?token=${token}`);
    const posts = await resultsResponse.json();
    
    console.log('Posts retrieved:', posts.length);
    
    // Convert to our standard format
    scrapedData = convertToStandardFormat(posts, currentGroupUrl);
    
    // Show success
    showSuccess(scrapedData.posts.length);
    
  } catch (error) {
    console.error('Scraping error:', error);
    showError(error.message);
  }
  
  // Reset button
  btnScrape.disabled = false;
  btnScrape.textContent = '🚀 Scraper avec Apify';
}

// Convert Apify data to our standard format
function convertToStandardFormat(apifyPosts, groupUrl) {
  const posts = apifyPosts.map(item => ({
    id: `apify_${item.postId || item.id || Math.random().toString(36).substr(2, 9)}`,
    postId: item.postId || item.id || '',
    author: item.profileName || item.authorName || 'Inconnu',
    authorProfileUrl: item.profileUrl || '',
    timestamp: item.timestamp || '',
    text: item.postText || item.text || '',
    postUrl: item.postUrl || item.url || '',
    hasMedia: !!(item.media || item.imageUrls || item.videoUrl),
    mediaType: item.videoUrl ? 'video' : (item.imageUrls?.length ? 'image' : null),
    source: 'apify',
    capturedAt: new Date().toISOString(),
    // Extra Apify data
    likesCount: parseInt(item.likesCount) || 0,
    commentsCount: parseInt(item.commentsCount) || 0,
    sharesCount: parseInt(item.sharesCount) || 0,
    topComments: item.topComments || []
  })).filter(post => post.text && post.text.length > 10);
  
  // Extract group name from URL
  let groupName = 'Unknown Group';
  const match = groupUrl.match(/\/groups\/([^\/\?]+)/);
  if (match) {
    groupName = decodeURIComponent(match[1]).replace(/-/g, ' ');
  }
  
  return {
    extractedAt: new Date().toISOString(),
    groupUrl: groupUrl,
    groupName: groupName,
    postsCount: posts.length,
    source: 'apify',
    posts: posts
  };
}

// Update progress UI
function updateProgress(text, percent) {
  progressText.textContent = text;
  progressFill.style.width = percent + '%';
}

// Show success
function showSuccess(count) {
  progressDiv.classList.remove('show');
  resultsDiv.classList.remove('error');
  resultsDiv.classList.add('show');
  resultsCount.textContent = count;
  btnDownload.style.display = 'block';
}

// Show error
function showError(message) {
  progressDiv.classList.remove('show');
  resultsDiv.classList.add('show', 'error');
  resultsCount.textContent = '❌ ' + message;
  document.querySelector('.results-icon').textContent = '❌';
  document.querySelector('.results-label').textContent = '';
}

// Download JSON
function downloadJSON() {
  if (!scrapedData) return;
  
  const blob = new Blob([JSON.stringify(scrapedData, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  const filename = `facebook_posts_apify_${timestamp}.json`;
  
  chrome.downloads.download({
    url: url,
    filename: filename,
    saveAs: false
  });
}

// Helper: sleep
function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// Event listeners
btnScrape.addEventListener('click', startScraping);
btnDownload.addEventListener('click', downloadJSON);
document.getElementById('btnSaveSettings').addEventListener('click', saveSettings);
document.getElementById('settingsHeader').addEventListener('click', toggleSettings);

console.log('FB Group Scanner v6.0.3 loaded');

// Initialize on load
init();
