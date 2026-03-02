SCOREBOARD_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ competition.name }} - Live Scores</title>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&family=Barlow+Condensed:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root { --bg:#0c1e2b; --bg2:#122a3a; --bg-row:#153040; --gold:#f4c566; --green:#5cc9a7; --blue:#54b8db; --text:#f0ece4; --text2:#8ab4c8; --muted:#5a8899; --border:#1e3d50; }
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--bg); color:var(--text); font-family:'Barlow Condensed',sans-serif; min-height:100vh; }
.container { max-width:1400px; margin:0 auto; padding:20px; }
.header { display:flex; justify-content:space-between; align-items:center; padding:20px 0; border-bottom:1px solid var(--border); margin-bottom:20px; flex-wrap:wrap; gap:12px; }
.header h1 { font-family:'Oswald',sans-serif; font-size:1.8rem; color:var(--gold); }
.header .subtitle { color:var(--text2); font-size:0.95rem; }
.nav-links { display:flex; gap:12px; }
.nav-link { color:var(--gold); text-decoration:none; border:1px solid var(--gold); padding:8px 16px; border-radius:4px; font-size:0.9rem; }
.nav-link:hover { background:var(--gold); color:var(--bg); }
.live-badge { display:inline-flex; align-items:center; gap:8px; background:rgba(92,201,167,0.1); border:1px solid rgba(92,201,167,0.3); padding:6px 14px; border-radius:4px; color:var(--green); font-family:'JetBrains Mono',monospace; font-size:0.75rem; }
.live-dot { width:8px; height:8px; background:var(--green); border-radius:50%; animation:pulse 2s infinite; }
@keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.5; } }

/* Controls */
.controls { display:flex; flex-wrap:wrap; gap:16px; margin:20px 0; align-items:center; }
.search-box { display:flex; flex-direction:column; gap:4px; }
.search-box label { font-size:0.75rem; color:var(--text2); text-transform:uppercase; }
.search-box input { padding:8px 12px; background:var(--bg2); border:1px solid var(--border); border-radius:4px; color:var(--text); font-size:0.9rem; width:200px; }
.search-box input:focus { outline:none; border-color:var(--gold); }
.filter-group { display:flex; flex-direction:column; gap:4px; }
.filter-group label { font-size:0.75rem; color:var(--text2); text-transform:uppercase; }
.toggle-btns { display:flex; gap:6px; }
.toggle-btn { padding:6px 14px; border:1px solid var(--border); background:var(--bg); color:var(--muted); border-radius:4px; cursor:pointer; font-size:0.85rem; transition:all 0.2s; }
.toggle-btn:hover { border-color:var(--text2); color:var(--text2); }
.toggle-btn.active { border-color:var(--gold); background:var(--gold); color:var(--bg); }
.update-info { margin-left:auto; text-align:right; }
.update-time { font-family:'JetBrains Mono',monospace; font-size:0.75rem; color:var(--muted); }

/* Category Section */
.category-section { margin-bottom:40px; }
.category-header { font-family:'Oswald',sans-serif; font-size:1.4rem; color:var(--gold); padding:12px 0; border-bottom:2px solid var(--gold); margin-bottom:16px; display:flex; justify-content:space-between; align-items:center; }
.category-count { font-size:0.9rem; color:var(--text2); font-family:'Barlow Condensed',sans-serif; }

/* Table */
table { width:100%; border-collapse:collapse; }
th, td { padding:10px 12px; text-align:center; border-bottom:1px solid var(--border); }
th { background:var(--bg2); color:var(--gold); font-family:'Oswald',sans-serif; font-weight:600; font-size:0.85rem; letter-spacing:0.5px; position:sticky; top:0; }
th:first-child, td:first-child { text-align:left; width:50px; }
th:nth-child(2), td:nth-child(2) { text-align:left; min-width:150px; }
tr:hover { background:var(--bg-row); }
tr.hidden { display:none; }
.rank { font-family:'JetBrains Mono',monospace; color:var(--muted); font-size:0.9rem; }
.rank-1 { color:var(--gold); font-weight:bold; }
.rank-2 { color:#c0c0c0; font-weight:bold; }
.rank-3 { color:#cd7f32; font-weight:bold; }
.shooter-name { font-family:'Oswald',sans-serif; font-size:1rem; }
.match-score { font-family:'JetBrains Mono',monospace; font-size:0.95rem; }
.match-score.has-score { color:var(--text); }
.match-score.no-score { color:var(--border); }
.aggregate { font-family:'JetBrains Mono',monospace; font-size:1.1rem; color:var(--gold); font-weight:600; }

/* Shot badges */
.shot-badges { display:flex; flex-wrap:wrap; gap:2px; justify-content:center; margin-top:4px; }
.shot-badge { display:inline-flex; align-items:center; justify-content:center; min-width:18px; height:16px; padding:0 3px; border-radius:2px; font-family:'JetBrains Mono',monospace; font-size:0.6rem; font-weight:600; }
.shot-badge.score-X { background:#f4c566; color:#0c1e2b; }
.shot-badge.score-V { background:#5cc9a7; color:#0c1e2b; }
.shot-badge.score-6 { background:#54b8db; color:#0c1e2b; }
.shot-badge.score-5 { background:#8ab4c8; color:#0c1e2b; }
.shot-badge.score-4 { background:#d4cdb8; color:#0c1e2b; }
.shot-badge.score-3 { background:#e8985a; color:#0c1e2b; }
.shot-badge.score-2 { background:#e8706a; color:#0c1e2b; }
.shot-badge.score-1 { background:#ff5555; color:#0c1e2b; }
.shot-badge.score-0 { background:#ff3333; color:#fff; }

.no-data { text-align:center; padding:60px; color:var(--muted); }
footer { margin-top:60px; padding:20px; border-top:1px solid var(--border); text-align:center; font-size:0.9rem; }
footer a { color:var(--text2); text-decoration:none; margin:0 12px; }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div>
      <h1>🏆 {{ competition.name }}</h1>
      <div class="subtitle">{{ competition.description or '' }}</div>
    </div>
    <div class="nav-links">
      <a href="/" class="nav-link">← Home</a>
      <a href="/{{ competition.route }}/squadding" class="nav-link">Squadding</a>
    </div>
  </div>
  
  <div class="controls">
    <div class="live-badge"><div class="live-dot"></div> Live Scores</div>
    <div class="search-box">
      <label>Search</label>
      <input type="text" id="searchInput" placeholder="Shooter name..." oninput="applyFilters()">
    </div>
    <div class="filter-group">
      <label>Category</label>
      <div class="toggle-btns" id="categoryBtns"></div>
    </div>
    <div class="update-info">
      <div class="update-time" id="updateTime">Loading...</div>
    </div>
  </div>
  
  <div id="scoreboards"></div>
</div>

<footer>
  <a href="/">Home</a>
  <a href="/about">About</a>
  <a href="/contact">Contact</a>
</footer>

<script>
const COMP_ROUTE = '{{ competition.route }}';
let allMatches = [];
let allCategories = [];
let competitors = [];
let scores = [];
let activeCategories = new Set();

// Load competitors to get match list and categories
async function loadCompetitors() {
  try {
    const resp = await fetch('/' + COMP_ROUTE + '/competitors.json?_t=' + Date.now());
    const data = await resp.json();
    competitors = data.competitors || [];
    
    // Extract unique matches and categories
    const matchSet = new Set();
    const catSet = new Set();
    competitors.forEach(c => {
      if (c.match) matchSet.add(c.match);
      if (c.class) catSet.add(c.class);
    });
    
    // Sort matches (assuming they have numbers or order)
    allMatches = Array.from(matchSet).sort((a, b) => {
      const numA = a.match(/\d+/) ? parseInt(a.match(/\d+/)[0]) : 0;
      const numB = b.match(/\d+/) ? parseInt(b.match(/\d+/)[0]) : 0;
      if (numA !== numB) return numA - numB;
      return a.localeCompare(b);
    });
    
    allCategories = Array.from(catSet).sort();
    activeCategories = new Set(allCategories);
    
    // Build category filter buttons
    buildCategoryButtons();
    
  } catch (e) {
    console.error('Load competitors error:', e);
  }
}

function buildCategoryButtons() {
  const container = document.getElementById('categoryBtns');
  let html = '<button class="toggle-btn active" data-cat="ALL" onclick="toggleCategory(\'ALL\')">All</button>';
  allCategories.forEach(cat => {
    html += '<button class="toggle-btn active" data-cat="' + cat + '" onclick="toggleCategory(\'' + cat + '\')">' + cat + '</button>';
  });
  container.innerHTML = html;
}

function toggleCategory(cat) {
  const btns = document.querySelectorAll('#categoryBtns .toggle-btn');
  
  if (cat === 'ALL') {
    // Toggle all
    const allActive = activeCategories.size === allCategories.length;
    if (allActive) {
      activeCategories.clear();
      btns.forEach(b => b.classList.remove('active'));
    } else {
      activeCategories = new Set(allCategories);
      btns.forEach(b => b.classList.add('active'));
    }
  } else {
    // Toggle specific category
    const btn = document.querySelector('#categoryBtns .toggle-btn[data-cat="' + cat + '"]');
    if (activeCategories.has(cat)) {
      activeCategories.delete(cat);
      btn.classList.remove('active');
    } else {
      activeCategories.add(cat);
      btn.classList.add('active');
    }
    // Update ALL button
    const allBtn = document.querySelector('#categoryBtns .toggle-btn[data-cat="ALL"]');
    allBtn.classList.toggle('active', activeCategories.size === allCategories.length);
  }
  
  renderScoreboards();
}

async function loadScores() {
  try {
    const resp = await fetch('/' + COMP_ROUTE + '/scores/latest.json?_t=' + Date.now());
    scores = await resp.json() || [];
    renderScoreboards();
    document.getElementById('updateTime').textContent = 'Updated ' + new Date().toLocaleTimeString();
  } catch (e) {
    console.error('Load scores error:', e);
  }
}

function renderShotBadges(shots) {
  if (!shots) return '';
  const shotList = shots.split(',');
  let html = '<div class="shot-badges">';
  shotList.forEach(s => {
    const sc = s.trim().toUpperCase();
    html += '<span class="shot-badge score-' + sc + '">' + sc + '</span>';
  });
  html += '</div>';
  return html;
}

function getScoreDisplay(matchData) {
  if (!matchData || matchData.score === undefined || matchData.score === null) {
    return { display: '-', hasScore: false, shots: '' };
  }
  const xCount = matchData.xCount || 0;
  return { 
    display: matchData.score + '.' + xCount, 
    hasScore: true,
    shots: matchData.shots || ''
  };
}

function renderScoreboards() {
  const container = document.getElementById('scoreboards');
  const search = document.getElementById('searchInput').value.toLowerCase();
  
  if (!allCategories.length) {
    container.innerHTML = '<div class="no-data">Loading competition data...</div>';
    return;
  }
  
  // Get unique shooters from competitors (grouped by name)
  const shooterMap = new Map();
  competitors.forEach(c => {
    if (!shooterMap.has(c.name)) {
      shooterMap.set(c.name, { name: c.name, class: c.class });
    }
  });
  
  // Merge with scores
  scores.forEach(s => {
    if (shooterMap.has(s.name)) {
      shooterMap.get(s.name).scoreData = s;
    } else {
      shooterMap.set(s.name, { name: s.name, class: s.class || '', scoreData: s });
    }
  });
  
  const allShooters = Array.from(shooterMap.values());
  
  let html = '';
  
  // Render each category separately
  allCategories.forEach(category => {
    if (!activeCategories.has(category)) return;
    
    // Filter shooters by category and search
    let categoryShooters = allShooters.filter(s => s.class === category);
    if (search) {
      categoryShooters = categoryShooters.filter(s => s.name.toLowerCase().includes(search));
    }
    
    // Calculate aggregates and sort
    categoryShooters.forEach(s => {
      let totalScore = 0;
      let totalX = 0;
      if (s.scoreData && s.scoreData.matches) {
        s.scoreData.matches.forEach(m => {
          totalScore += m.score || 0;
          totalX += m.xCount || 0;
        });
      }
      s.aggregate = totalScore;
      s.aggregateX = totalX;
    });
    
    // Sort by aggregate (descending), then by X count
    categoryShooters.sort((a, b) => {
      if (b.aggregate !== a.aggregate) return b.aggregate - a.aggregate;
      return b.aggregateX - a.aggregateX;
    });
    
    html += '<div class="category-section">';
    html += '<div class="category-header"><span>' + category + '</span><span class="category-count">' + categoryShooters.length + ' shooters</span></div>';
    
    if (categoryShooters.length === 0) {
      html += '<div class="no-data">No shooters' + (search ? ' matching "' + search + '"' : '') + '</div>';
    } else {
      html += '<table><thead><tr>';
      html += '<th>#</th><th>Shooter</th>';
      allMatches.forEach(m => {
        // Shorten match name for header
        const shortName = m.replace('Match ', 'M').replace(' 10+2', '').replace(' Finals', ' F');
        html += '<th>' + shortName + '</th>';
      });
      html += '<th>Aggregate</th>';
      html += '</tr></thead><tbody>';
      
      categoryShooters.forEach((s, idx) => {
        const rank = idx + 1;
        const rankClass = rank <= 3 ? ' rank-' + rank : '';
        
        html += '<tr>';
        html += '<td class="rank' + rankClass + '">' + rank + '</td>';
        html += '<td class="shooter-name">' + s.name + '</td>';
        
        // Match columns
        allMatches.forEach(matchName => {
          const matchData = s.scoreData?.matches?.find(m => m.match === matchName);
          const scoreInfo = getScoreDisplay(matchData);
          
          html += '<td class="match-score ' + (scoreInfo.hasScore ? 'has-score' : 'no-score') + '">';
          html += '<div>' + scoreInfo.display + '</div>';
          if (scoreInfo.hasScore && scoreInfo.shots) {
            html += renderShotBadges(scoreInfo.shots);
          }
          html += '</td>';
        });
        
        // Aggregate
        html += '<td class="aggregate">' + s.aggregate + '.' + s.aggregateX + '</td>';
        html += '</tr>';
      });
      
      html += '</tbody></table>';
    }
    
    html += '</div>';
  });
  
  if (!html) {
    html = '<div class="no-data">No categories selected</div>';
  }
  
  container.innerHTML = html;
}

function applyFilters() {
  renderScoreboards();
}

// Initialize
async function init() {
  await loadCompetitors();
  await loadScores();
  setInterval(loadScores, 15000);
}

init();
</script>
</body>
</html>
'''
