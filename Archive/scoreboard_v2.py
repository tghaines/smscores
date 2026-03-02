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
.controls { display:flex; flex-wrap:wrap; gap:16px; margin:20px 0; align-items:center; }
.search-box input { padding:8px 12px; background:var(--bg2); border:1px solid var(--border); border-radius:4px; color:var(--text); font-size:0.9rem; width:200px; }
.search-box input:focus { outline:none; border-color:var(--gold); }
.toggle-btns { display:flex; gap:6px; }
.toggle-btn { padding:6px 14px; border:1px solid var(--border); background:var(--bg); color:var(--muted); border-radius:4px; cursor:pointer; font-size:0.85rem; }
.toggle-btn:hover { border-color:var(--text2); color:var(--text2); }
.toggle-btn.active { border-color:var(--gold); background:var(--gold); color:var(--bg); }
.update-time { margin-left:auto; font-family:'JetBrains Mono',monospace; font-size:0.75rem; color:var(--muted); }
.category-section { margin-bottom:40px; }
.category-header { font-family:'Oswald',sans-serif; font-size:1.4rem; color:var(--gold); padding:12px 0; border-bottom:2px solid var(--gold); margin-bottom:16px; display:flex; justify-content:space-between; }
.category-count { font-size:0.9rem; color:var(--text2); font-family:'Barlow Condensed',sans-serif; }
table { width:100%; border-collapse:collapse; }
th, td { padding:10px 12px; text-align:center; border-bottom:1px solid var(--border); }
th { background:var(--bg2); color:var(--gold); font-family:'Oswald',sans-serif; font-weight:600; font-size:0.85rem; }
th:first-child, td:first-child { text-align:center; width:50px; }
th:nth-child(2), td:nth-child(2) { text-align:left; min-width:150px; }
tr:hover { background:var(--bg-row); }
.rank { font-family:'JetBrains Mono',monospace; color:var(--muted); font-size:0.9rem; }
.rank-1 { color:var(--gold); font-weight:bold; }
.rank-2 { color:#c0c0c0; font-weight:bold; }
.rank-3 { color:#cd7f32; font-weight:bold; }
.shooter-name { font-family:'Oswald',sans-serif; font-size:1rem; }
.match-score { font-family:'JetBrains Mono',monospace; font-size:0.95rem; }
.match-score.has-score { color:var(--text); }
.match-score.no-score { color:var(--border); }
.aggregate { font-family:'JetBrains Mono',monospace; font-size:1.1rem; color:var(--gold); font-weight:600; }
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
    <div class="search-box"><input type="text" id="searchInput" placeholder="Search shooter..." oninput="applyFilters()"></div>
    <div class="toggle-btns" id="categoryBtns"></div>
    <div class="update-time" id="updateTime">Loading...</div>
  </div>
  <div id="scoreboards"></div>
</div>
<footer><a href="/">Home</a><a href="/about">About</a><a href="/contact">Contact</a></footer>
<script>
var defined_matches = [];
var defined_categories = [];
var competitors = [];
var scores = [];
var activeCategories = new Set();

async function loadCompetitors() {
  try {
    var resp = await fetch('/{{ competition.route }}/competitors.json?_t=' + Date.now());
    var data = await resp.json();
    competitors = data.competitors || [];
    var matchSet = new Set();
    var catSet = new Set();
    competitors.forEach(function(c) {
      if (c.match) matchSet.add(c.match);
      if (c.class) catSet.add(c.class);
    });
    defined_matches = Array.from(matchSet).sort(function(a, b) {
      var numA = a.match(/\\d+/) ? parseInt(a.match(/\\d+/)[0]) : 0;
      var numB = b.match(/\\d+/) ? parseInt(b.match(/\\d+/)[0]) : 0;
      if (numA !== numB) return numA - numB;
      return a.localeCompare(b);
    });
    defined_categories = Array.from(catSet).sort();
    activeCategories = new Set(defined_categories);
    buildCategoryButtons();
  } catch (e) { console.error('Load competitors error:', e); }
}

function buildCategoryButtons() {
  var container = document.getElementById('categoryBtns');
  var html = '<button class="toggle-btn active" data-cat="ALL" onclick="toggleCat(this)">All</button>';
  defined_categories.forEach(function(cat) {
    html += '<button class="toggle-btn active" data-cat="' + cat + '" onclick="toggleCat(this)">' + cat + '</button>';
  });
  container.innerHTML = html;
}

function toggleCat(btn) {
  var cat = btn.dataset.cat;
  if (cat === 'ALL') {
    var allActive = activeCategories.size === defined_categories.length;
    document.querySelectorAll('#categoryBtns .toggle-btn').forEach(function(b) {
      if (allActive) { b.classList.remove('active'); activeCategories.clear(); }
      else { b.classList.add('active'); activeCategories = new Set(defined_categories); }
    });
  } else {
    btn.classList.toggle('active');
    if (activeCategories.has(cat)) activeCategories.delete(cat);
    else activeCategories.add(cat);
    var allBtn = document.querySelector('#categoryBtns .toggle-btn[data-cat="ALL"]');
    if (activeCategories.size === defined_categories.length) allBtn.classList.add('active');
    else allBtn.classList.remove('active');
  }
  renderScoreboards();
}

async function loadScores() {
  try {
    var resp = await fetch('/{{ competition.route }}/scores/latest.json?_t=' + Date.now());
    scores = await resp.json() || [];
    renderScoreboards();
    document.getElementById('updateTime').textContent = 'Updated ' + new Date().toLocaleTimeString();
  } catch (e) { console.error('Load scores error:', e); }
}

function renderShotBadges(shots) {
  if (!shots) return '';
  var html = '<div class="shot-badges">';
  shots.split(',').forEach(function(s) {
    var sc = s.trim().toUpperCase();
    html += '<span class="shot-badge score-' + sc + '">' + sc + '</span>';
  });
  return html + '</div>';
}

function renderScoreboards() {
  var container = document.getElementById('scoreboards');
  var search = document.getElementById('searchInput').value.toLowerCase();
  if (!defined_categories.length && !scores.length) {
    container.innerHTML = '<div class="no-data">Loading...</div>';
    return;
  }
  var shooterMap = new Map();
  competitors.forEach(function(c) {
    if (!shooterMap.has(c.name)) shooterMap.set(c.name, { name: c.name, class: c.class });
  });
  scores.forEach(function(s) {
    if (shooterMap.has(s.name)) {
      shooterMap.get(s.name).scoreData = s;
    } else {
      shooterMap.set(s.name, { name: s.name, class: s.class || 'UNCATEGORIZED', scoreData: s });
    }
  });
  var allShooters = Array.from(shooterMap.values());
  var cats = defined_categories.length ? defined_categories : ['UNCATEGORIZED'];
  var html = '';
  cats.forEach(function(category) {
    if (!activeCategories.has(category) && activeCategories.size > 0) return;
    var catShooters = allShooters.filter(function(s) { return s.class === category; });
    if (search) catShooters = catShooters.filter(function(s) { return s.name.toLowerCase().indexOf(search) >= 0; });
    catShooters.forEach(function(s) {
      var total = 0, totalX = 0;
      if (s.scoreData && s.scoreData.matches) {
        s.scoreData.matches.forEach(function(m) { total += m.score || 0; totalX += m.xCount || 0; });
      }
      s.aggregate = total;
      s.aggregateX = totalX;
    });
    catShooters.sort(function(a, b) {
      if (b.aggregate !== a.aggregate) return b.aggregate - a.aggregate;
      return b.aggregateX - a.aggregateX;
    });
    html += '<div class="category-section">';
    html += '<div class="category-header"><span>' + category + '</span><span class="category-count">' + catShooters.length + ' shooters</span></div>';
    if (!catShooters.length) {
      html += '<div class="no-data">No shooters</div>';
    } else {
      html += '<table><thead><tr><th>#</th><th>Shooter</th>';
      defined_matches.forEach(function(m) {
        var short = m.replace('Match ', 'M').replace(' 10+2', '').replace(' Finals', ' F');
        html += '<th>' + short + '</th>';
      });
      html += '<th>Aggregate</th></tr></thead><tbody>';
      catShooters.forEach(function(s, idx) {
        var rank = idx + 1;
        var rankClass = rank <= 3 ? ' rank-' + rank : '';
        html += '<tr><td class="rank' + rankClass + '">' + rank + '</td>';
        html += '<td class="shooter-name">' + s.name + '</td>';
        defined_matches.forEach(function(matchName) {
          var matchData = null;
          if (s.scoreData && s.scoreData.matches) {
            s.scoreData.matches.forEach(function(m) { if (m.match === matchName) matchData = m; });
          }
          if (matchData) {
            html += '<td class="match-score has-score"><div>' + matchData.score + '.' + matchData.xCount + '</div>' + renderShotBadges(matchData.shots) + '</td>';
          } else {
            html += '<td class="match-score no-score">-</td>';
          }
        });
        html += '<td class="aggregate">' + s.aggregate + '.' + s.aggregateX + '</td></tr>';
      });
      html += '</tbody></table>';
    }
    html += '</div>';
  });
  if (!html) html = '<div class="no-data">No categories selected</div>';
  container.innerHTML = html;
}

function applyFilters() { renderScoreboards(); }

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
