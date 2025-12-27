// Facebook Group Post Extractor v5.0.0
// FIXED: Capture posts initiaux + bon endpoint GraphQL

(function() {
  'use strict';

  const VERSION = '5.0.0';
  
  // État global
  if (!window.fbScanner) {
    window.fbScanner = {
      posts: new Map(),
      isScanning: false,
      mode: 'passive',
      observer: null,
      startTime: null,
      interceptorsInstalled: false,
      initialPostsCaptured: false
    };
  }

  console.log(`🔍 [FB Scanner v${VERSION}] Content script chargé`);

  // ============================================
  // 1. CAPTURE DES POSTS INITIAUX (dans le HTML)
  // ============================================
  function captureInitialPosts() {
    if (window.fbScanner.initialPostsCaptured) return;
    
    console.log('📦 [FB Scanner] Recherche des posts initiaux dans le HTML...');
    
    // Facebook stocke les données dans des balises <script type="application/json">
    const scripts = document.querySelectorAll('script[type="application/json"]');
    let foundCount = 0;
    
    scripts.forEach(script => {
      try {
        const data = JSON.parse(script.textContent);
        const count = parseRelayData(data);
        foundCount += count;
      } catch (e) {
        // Pas du JSON valide, ignorer
      }
    });
    
    // Aussi chercher dans les scripts avec data-sjs
    const sjsScripts = document.querySelectorAll('script[data-sjs]');
    sjsScripts.forEach(script => {
      try {
        const data = JSON.parse(script.textContent);
        const count = parseRelayData(data);
        foundCount += count;
      } catch (e) {}
    });
    
    window.fbScanner.initialPostsCaptured = true;
    
    if (foundCount > 0) {
      console.log(`✅ [FB Scanner] ${foundCount} posts initiaux capturés depuis le HTML!`);
    } else {
      console.log('⚠️ [FB Scanner] Aucun post initial trouvé dans le HTML');
    }
  }

  // Parser les données Relay de Facebook
  function parseRelayData(data) {
    let count = 0;
    
    if (!data) return count;
    
    // Format 1: require array (RelayPrefetchedStreamCache)
    if (Array.isArray(data.require)) {
      data.require.forEach(req => {
        if (Array.isArray(req) && req[0] === 'RelayPrefetchedStreamCache') {
          const relayData = req[3];
          if (Array.isArray(relayData)) {
            relayData.forEach(item => {
              count += extractPostsFromObject(item);
            });
          }
        }
      });
    }
    
    // Format 2: direct data object
    count += extractPostsFromObject(data);
    
    return count;
  }

  // Extraction récursive des posts depuis un objet
  function extractPostsFromObject(obj, depth = 0) {
    if (!obj || typeof obj !== 'object' || depth > 15) return 0;
    
    let count = 0;
    
    // Chercher group_feed.edges
    if (obj.group_feed?.edges && Array.isArray(obj.group_feed.edges)) {
      obj.group_feed.edges.forEach(edge => {
        if (edge.node) {
          if (addPostFromGraphQL(edge.node)) count++;
        }
      });
    }
    
    // Chercher edges directement
    if (Array.isArray(obj.edges)) {
      obj.edges.forEach(edge => {
        if (edge.node) {
          if (addPostFromGraphQL(edge.node)) count++;
        }
      });
    }
    
    // Chercher story
    if (obj.story && obj.story.message) {
      if (addPostFromGraphQL(obj.story)) count++;
    }
    
    // Chercher node avec message
    if (obj.node && obj.node.message) {
      if (addPostFromGraphQL(obj.node)) count++;
    }
    
    // Récursion sur les propriétés
    for (const key of Object.keys(obj)) {
      if (typeof obj[key] === 'object' && obj[key] !== null) {
        count += extractPostsFromObject(obj[key], depth + 1);
      }
    }
    
    return count;
  }

  // Ajouter un post depuis les données GraphQL
  function addPostFromGraphQL(node) {
    if (!node) return false;
    
    const postId = node.id || node.post_id || node.story_id;
    if (!postId) return false;
    if (window.fbScanner.posts.has(postId)) return false;
    
    // Extraire le texte
    let text = '';
    if (node.message?.text) {
      text = node.message.text;
    } else if (node.comet_sections?.content?.story?.message?.text) {
      text = node.comet_sections.content.story.message.text;
    }
    
    if (!text || text.length < 5) return false;
    
    // Extraire l'auteur
    let author = null;
    let authorUrl = null;
    
    // Plusieurs chemins possibles pour l'auteur
    const actorPaths = [
      node.actors?.[0],
      node.author,
      node.comet_sections?.context_layout?.story?.comet_sections?.actor_photo?.story?.actors?.[0],
      node.comet_sections?.content?.story?.actors?.[0]
    ];
    
    for (const actor of actorPaths) {
      if (actor?.name) {
        author = actor.name;
        authorUrl = actor.url || actor.profile_url;
        break;
      }
    }
    
    // Extraire le timestamp
    const timestamp = node.creation_time || node.created_time || null;
    
    // Extraire l'URL du post
    let postUrl = node.url || node.wwwURL || null;
    if (!postUrl && postId) {
      // Construire l'URL si on a le group ID
      const groupMatch = window.location.pathname.match(/\/groups\/([^\/]+)/);
      if (groupMatch) {
        postUrl = `https://www.facebook.com/groups/${groupMatch[1]}/posts/${postId}/`;
      }
    }
    
    const post = {
      id: `graphql_${postId}`,
      postId: postId,
      author: author,
      authorProfileUrl: authorUrl,
      timestamp: timestamp,
      text: text.slice(0, 3000),
      postUrl: postUrl,
      hasMedia: !!(node.attachments?.length || node.photo || node.video),
      mediaType: node.video ? 'video' : (node.photo ? 'image' : null),
      source: 'graphql',
      capturedAt: new Date().toISOString()
    };
    
    window.fbScanner.posts.set(postId, post);
    console.log(`📥 [GraphQL] "${author || '?'}" - ${text.slice(0, 50)}...`);
    
    // Notifier le popup
    chrome.runtime.sendMessage({
      action: 'newPost',
      postCount: window.fbScanner.posts.size
    }).catch(() => {});
    
    return true;
  }

  // ============================================
  // 2. INTERCEPTEURS (bon endpoint!)
  // ============================================
  function installInterceptors() {
    if (window.fbScanner.interceptorsInstalled) return;
    window.fbScanner.interceptorsInstalled = true;
    
    console.log('🔌 [FB Scanner] Installation des intercepteurs...');
    
    // Intercepter fetch()
    const originalFetch = window.fetch;
    window.fetch = async function(...args) {
      const response = await originalFetch.apply(this, args);
      
      try {
        const url = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';
        
        // ✅ FIX: Bon endpoint - /graphql (pas /api/graphql/)
        if (url.includes('/graphql')) {
          const clone = response.clone();
          clone.text().then(text => {
            parseGraphQLResponse(text);
          }).catch(() => {});
        }
      } catch (e) {}
      
      return response;
    };
    
    // Intercepter XMLHttpRequest
    const originalXHROpen = XMLHttpRequest.prototype.open;
    const originalXHRSend = XMLHttpRequest.prototype.send;
    
    XMLHttpRequest.prototype.open = function(method, url, ...rest) {
      this._fbUrl = url;
      return originalXHROpen.apply(this, [method, url, ...rest]);
    };
    
    XMLHttpRequest.prototype.send = function(...args) {
      this.addEventListener('load', function() {
        try {
          // ✅ FIX: Bon endpoint
          if (this._fbUrl && this._fbUrl.includes('/graphql')) {
            parseGraphQLResponse(this.responseText);
          }
        } catch (e) {}
      });
      return originalXHRSend.apply(this, args);
    };
    
    console.log('✅ [FB Scanner] Intercepteurs installés (endpoint: /graphql)');
  }

  function parseGraphQLResponse(text) {
    if (!text) return;
    
    try {
      // Facebook peut renvoyer plusieurs JSON concaténés par ligne
      const lines = text.split('\n');
      
      lines.forEach(line => {
        if (!line.trim().startsWith('{')) return;
        
        try {
          const data = JSON.parse(line);
          extractPostsFromObject(data);
        } catch (e) {}
      });
    } catch (e) {}
  }

  // ============================================
  // 3. MESSAGE HANDLER
  // ============================================
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    
    if (request.action === 'startPassive') {
      window.fbScanner.isScanning = true;
      window.fbScanner.mode = 'passive';
      window.fbScanner.startTime = Date.now();
      
      // Capturer les posts initiaux
      captureInitialPosts();
      
      // Setup observers
      setupMutationObserver();
      captureVisiblePosts();
      
      console.log('🛡️ [FB Scanner] Mode PASSIF activé - scrolle naturellement!');
      sendResponse({ success: true, postCount: window.fbScanner.posts.size });
    }
    
    if (request.action === 'startAuto') {
      window.fbScanner.isScanning = true;
      window.fbScanner.mode = 'auto';
      window.fbScanner.startTime = Date.now();
      
      captureInitialPosts();
      setupMutationObserver();
      captureVisiblePosts();
      startHumanizedScroll(request.duration || 30);
      
      console.log(`⚡ [FB Scanner] Mode AUTO activé (${request.duration}s)`);
      sendResponse({ success: true });
    }
    
    if (request.action === 'stopAndExport') {
      stopScanning();
      const data = exportData();
      sendResponse({ 
        success: true, 
        count: window.fbScanner.posts.size,
        data: data
      });
    }
    
    if (request.action === 'getStatus') {
      sendResponse({
        isScanning: window.fbScanner.isScanning,
        mode: window.fbScanner.mode,
        postCount: window.fbScanner.posts.size,
        elapsed: window.fbScanner.startTime ? 
          Math.floor((Date.now() - window.fbScanner.startTime) / 1000) : 0
      });
    }
    
    if (request.action === 'clearCache') {
      window.fbScanner.posts.clear();
      window.fbScanner.initialPostsCaptured = false;
      console.log('🗑️ [FB Scanner] Cache vidé');
      sendResponse({ success: true, postCount: 0 });
    }
    
    return true;
  });

  // ============================================
  // 4. SCROLL HUMANISÉ
  // ============================================
  function startHumanizedScroll(durationSeconds) {
    let elapsed = 0;
    
    function doScroll() {
      if (!window.fbScanner.isScanning || window.fbScanner.mode !== 'auto') return;
      
      elapsed += 1;
      if (elapsed >= durationSeconds) {
        console.log('⏰ [FB Scanner] Durée écoulée');
        stopScanning();
        chrome.runtime.sendMessage({
          action: 'scanComplete',
          postCount: window.fbScanner.posts.size,
          data: exportData()
        }).catch(() => {});
        return;
      }
      
      // Scroll humanisé
      const baseScroll = 300 + Math.random() * 400;
      window.scrollBy({ top: baseScroll, behavior: 'smooth' });
      
      const nextDelay = 800 + Math.random() * 1200;
      const actualDelay = Math.random() < 0.15 ? nextDelay + 2000 : nextDelay;
      
      setTimeout(() => {
        captureVisiblePosts();
        doScroll();
      }, actualDelay);
      
      chrome.runtime.sendMessage({
        action: 'scanProgress',
        postCount: window.fbScanner.posts.size,
        elapsed: elapsed,
        duration: durationSeconds
      }).catch(() => {});
    }
    
    setTimeout(doScroll, 500);
  }

  function stopScanning() {
    console.log(`🛑 [FB Scanner] Arrêt - ${window.fbScanner.posts.size} posts capturés`);
    window.fbScanner.isScanning = false;
    
    if (window.fbScanner.observer) {
      window.fbScanner.observer.disconnect();
      window.fbScanner.observer = null;
    }
  }

  // ============================================
  // 5. MUTATION OBSERVER
  // ============================================
  function setupMutationObserver() {
    if (window.fbScanner.observer) {
      window.fbScanner.observer.disconnect();
    }
    
    const feed = document.querySelector('[role="feed"]') || document.body;
    
    window.fbScanner.observer = new MutationObserver((mutations) => {
      mutations.forEach(mutation => {
        mutation.addedNodes.forEach(node => {
          if (node.nodeType === Node.ELEMENT_NODE) {
            // Chercher les nouveaux scripts avec données JSON
            if (node.tagName === 'SCRIPT' && node.type === 'application/json') {
              try {
                const data = JSON.parse(node.textContent);
                parseRelayData(data);
              } catch (e) {}
            }
            
            // Chercher les liens de posts
            const links = node.querySelectorAll ? 
              node.querySelectorAll('a[href*="/posts/"]') : [];
            
            links.forEach(link => {
              const href = link.getAttribute('href') || '';
              if (href.includes('comment_id')) return;
              
              const match = href.match(/\/posts\/(\d+)/);
              if (match && !window.fbScanner.posts.has(match[1])) {
                extractPostFromDOM(link, match[1]);
              }
            });
          }
        });
      });
    });
    
    window.fbScanner.observer.observe(document.documentElement, {
      childList: true,
      subtree: true
    });
    
    console.log('👁️ [FB Scanner] MutationObserver activé');
  }

  // ============================================
  // 6. CAPTURE DOM (backup)
  // ============================================
  function captureVisiblePosts() {
    const allLinks = document.querySelectorAll('a[href*="/posts/"], a[href*="/permalink/"]');
    let newCount = 0;
    
    allLinks.forEach(link => {
      const href = link.getAttribute('href') || '';
      if (href.includes('comment_id')) return;
      
      const match = href.match(/\/posts\/(\d+)/);
      if (match) {
        const postId = match[1];
        if (!window.fbScanner.posts.has(postId)) {
          const post = extractPostFromDOM(link, postId);
          if (post && post.text && post.text.length > 15) {
            window.fbScanner.posts.set(postId, post);
            newCount++;
          }
        }
      }
    });
    
    if (newCount > 0) {
      console.log(`➕ [DOM] +${newCount} posts (Total: ${window.fbScanner.posts.size})`);
    }
  }

  function extractPostFromDOM(link, postId) {
    const container = findPostContainer(link);
    if (!container) return null;
    
    const post = {
      id: `dom_${postId}`,
      postId: postId,
      author: null,
      authorProfileUrl: null,
      timestamp: null,
      text: null,
      postUrl: cleanUrl(link.getAttribute('href')),
      hasMedia: false,
      mediaType: null,
      source: 'dom',
      capturedAt: new Date().toISOString()
    };
    
    // Auteur
    const userLinks = container.querySelectorAll('a[href*="/user/"], a[href*="profile.php"]');
    for (const userLink of userLinks) {
      if (userLink.closest('[role="article"]')) continue;
      const nameEl = userLink.querySelector('strong, span');
      const name = (nameEl || userLink).textContent?.trim();
      if (name && name.length > 1 && name.length < 60 && !name.match(/^[\d\s]+$/)) {
        post.author = name;
        post.authorProfileUrl = cleanUrl(userLink.getAttribute('href'));
        break;
      }
    }
    
    // Texte
    post.text = extractPostText(container);
    
    // Médias
    const images = [...container.querySelectorAll('img[src*="scontent"]')]
      .filter(img => !img.closest('[role="article"]'));
    const videos = [...container.querySelectorAll('video')]
      .filter(vid => !vid.closest('[role="article"]'));
    
    post.hasMedia = images.length > 0 || videos.length > 0;
    post.mediaType = videos.length > 0 ? 'video' : (images.length > 0 ? 'image' : null);
    
    return post;
  }

  function findPostContainer(link) {
    let current = link.parentElement;
    let bestCandidate = null;
    let depth = 0;
    
    while (current && depth < 20) {
      const rect = current.getBoundingClientRect();
      if (rect.height > 100 && rect.height < 2000) {
        const textLength = current.textContent?.length || 0;
        if (textLength > 50) {
          bestCandidate = current;
        }
      }
      
      const role = current.getAttribute('role');
      if (role === 'main' || role === 'feed' || current.id?.startsWith('mount_')) {
        break;
      }
      
      current = current.parentElement;
      depth++;
    }
    
    return bestCandidate;
  }

  function extractPostText(container) {
    const candidates = [];
    const textElements = container.querySelectorAll('div[dir="auto"], span[dir="auto"]');
    
    textElements.forEach(el => {
      if (el.closest('[role="article"]')) return;
      const text = el.textContent?.trim();
      if (!text || text.length < 15) return;
      
      const ignorePatterns = [
        /^(Like|Comment|Share|J'aime|Commenter|Partager|Répondre)$/i,
        /^(See more|Voir plus|Afficher plus|Afficher la suite)$/i,
        /^\d+\s*(comments?|shares?|j'aime|commentaires?|partages?)$/i,
        /^\d+\s*(h|m|d|w|j|s|sem)\.?$/i,
        /^https?:\/\//i,
        /^(Contribution remarquée|Top contributor|Compte vérifié)$/i,
        /^Afficher/i,
        /^S'abonner$/i,
      ];
      
      for (const pattern of ignorePatterns) {
        if (pattern.test(text)) return;
      }
      
      candidates.push({ text, length: text.length });
    });
    
    candidates.sort((a, b) => b.length - a.length);
    
    for (const candidate of candidates) {
      if (candidate.length < 2000) {
        return candidate.text.replace(/\s+/g, ' ').trim().slice(0, 3000);
      }
    }
    
    return '';
  }

  function cleanUrl(url) {
    if (!url) return null;
    if (!url.startsWith('http')) {
      url = 'https://www.facebook.com' + url;
    }
    try {
      const urlObj = new URL(url);
      ['__cft__', '__tn__', '__eep__', 'ref', 'fref', 'mibextid'].forEach(p => 
        urlObj.searchParams.delete(p)
      );
      return urlObj.toString();
    } catch {
      return url;
    }
  }

  // ============================================
  // 7. EXPORT
  // ============================================
  function exportData() {
    const posts = [...window.fbScanner.posts.values()];
    
    let groupName = document.title || '';
    groupName = groupName
      .replace(/^\(\d+\)\s*/, '')
      .replace(/\s*[|\-–]\s*Facebook.*$/i, '')
      .trim() || 'Unknown Group';
    
    const fromGraphQL = posts.filter(p => p.source === 'graphql').length;
    const fromDOM = posts.filter(p => p.source === 'dom').length;
    
    console.log(`📊 [Export] ${posts.length} posts (${fromGraphQL} GraphQL, ${fromDOM} DOM)`);
    
    return {
      extractedAt: new Date().toISOString(),
      groupUrl: window.location.href,
      groupName: groupName,
      postsCount: posts.length,
      scanDuration: window.fbScanner.startTime ? 
        Math.floor((Date.now() - window.fbScanner.startTime) / 1000) : 0,
      stats: { fromGraphQL, fromDOM },
      posts: posts
    };
  }

  // ============================================
  // INITIALISATION
  // ============================================
  
  // Installer les intercepteurs IMMÉDIATEMENT
  installInterceptors();
  
  // Capturer les posts initiaux quand le DOM est prêt
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      setTimeout(captureInitialPosts, 500);
    });
  } else {
    setTimeout(captureInitialPosts, 500);
  }
  
  console.log(`✅ [FB Scanner v${VERSION}] Prêt!`);
  console.log('   📦 Posts initiaux: capture auto au chargement');
  console.log('   📡 GraphQL: endpoint /graphql');

})();
