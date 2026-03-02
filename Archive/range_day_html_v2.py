RANGE_DAY_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ range.name }} - {{ date.strftime('%d %b %Y') }}</title>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&family=Barlow+Condensed:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root { --bg:#0c1e2b; --bg2:#122a3a; --bg-row:#153040; --gold:#f4c566; --blue:#54b8db; --green:#5cc9a7; --text:#f0ece4; --text2:#8ab4c8; --muted:#5a8899; --border:#1e3d50; }
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--bg); color:var(--text); font-family:"Barlow Condensed",sans-serif; min-height:100vh; padding:20px; }
.container { max-width:1200px; margin:0 auto; }
.header { display:flex; justify-content:space-between; align-items:center; padding:20px 0; border-bottom:1px solid var(--border); margin-bottom:20px; flex-wrap:wrap; gap:12px; }
.header h1 { font-family:"Oswald",sans-serif; font-size:1.6rem; color:var(--gold); }
.nav-link { color:var(--gold); text-decoration:none; border:1px solid var(--gold); padding:8px 16px; border-radius:4px; }
.nav-link:hover { background:var(--gold); color:var(--bg); }

/* Filter Bar */
.filter-bar { display:flex; flex-direction:column; gap:16px; margin-bottom:20px; padding:16px; background:var(--bg2); border-radius:8px; border:1px solid var(--border); }
.filter-row { display:flex; flex-wrap:wrap; gap:12px; align-items:flex-end; }
.filter-group { display:flex; flex-direction:column; gap:4px; }
.filter-group label { font-size:0.8rem; color:var(--text2); text-transform:uppercase; }
.filter-group input { font-size:0.9rem; color:var(--text); background:var(--bg); border:1px solid var(--border); padding:8px 12px; border-radius:4px; min-width:160px; }
.filter-group input:focus { outline:none; border-color:var(--gold); }

/* Toggle Buttons */
.toggle-group { display:flex; flex-wrap:wrap; gap:6px; }
.toggle-btn { padding:6px 12px; border:1px solid var(--border); background:var(--bg); color:var(--muted); border-radius:4px; cursor:pointer; font-size:0.85rem; transition:all 0.2s; }
.toggle-btn:hover { border-color:var(--text2); color:var(--text2); }
.toggle-btn.active { border-color:var(--gold); background:var(--gold); color:var(--bg); }
.toggle-btn.distance { min-width:50px; text-align:center; font-family:"JetBrains Mono",monospace; }
.toggle-btn.target-btn { font-family:"JetBrains Mono",monospace; font-size:0.8rem; }

.filter-actions { display:flex; gap:8px; align-items:flex-end; }
.filter-clear { background:transparent; border:1px solid var(--muted); color:var(--muted); padding:8px 16px; border-radius:4px; cursor:pointer; }
.filter-clear:hover { border-color:var(--gold); color:var(--gold); }
.select-all-btn { background:transparent; border:1px solid var(--blue); color:var(--blue); padding:4px 10px; border-radius:4px; cursor:pointer; font-size:0.8rem; }
.select-all-btn:hover { background:var(--blue); color:var(--bg); }

.result-count { color:var(--text2); font-size:0.9rem; margin-bottom:12px; }

table { width:100%; border-collapse:collapse; }
th, td { padding:12px; text-align:left; border-bottom:1px solid var(--border); }
th { background:var(--bg2); color:var(--gold); font-family:"Oswald",sans-serif; cursor:pointer; user-select:none; }
th:hover { color:var(--text); }
th.sorted-asc::after { content:" ▲"; font-size:0.7rem; }
th.sorted-desc::after { content:" ▼"; font-size:0.7rem; }
tr:hover { background:var(--bg-row); }
tr.hidden { display:none; }
.score-cell { display:flex; flex-direction:column; gap:4px; }
.score { font-family:"JetBrains Mono",monospace; color:var(--gold); font-size:1.1rem; }
.target { font-family:"JetBrains Mono",monospace; color:var(--blue); font-size:0.85rem; }
.shooter { font-family:"Oswald",sans-serif; }
.distance-cell { font-family:"JetBrains Mono",monospace; color:var(--text2); font-size:0.9rem; }

/* Shot badges */
.shot-badges { display:flex; flex-wrap:wrap; gap:3px; margin-top:4px; }
.shot-badge { display:inline-flex; align-items:center; justify-content:center; min-width:22px; height:20px; padding:0 4px; border-radius:3px; font-family:"JetBrains Mono",monospace; font-size:0.7rem; font-weight:600; }
.shot-badge.sighter { background:var(--bg); color:var(--muted); border:1px solid var(--border); font-style:italic; }
.shot-badge.score-X { background:#f4c566; color:#0c1e2b; }
.shot-badge.score-V { background:#5cc9a7; color:#0c1e2b; }
.shot-badge.score-6 { background:#54b8db; color:#0c1e2b; }
.shot-badge.score-5 { background:#8ab4c8; color:#0c1e2b; }
.shot-badge.score-4 { background:#d4cdb8; color:#0c1e2b; }
.shot-badge.score-3 { background:#e8985a; color:#0c1e2b; }
.shot-badge.score-2 { background:#e8706a; color:#0c1e2b; }
.shot-badge.score-1 { background:#ff5555; color:#0c1e2b; }
.shot-badge.score-0 { background:#ff3333; color:#fff; }

.plot-btn { background:transparent; border:1px solid var(--blue); color:var(--blue); padding:4px 10px; border-radius:4px; cursor:pointer; font-size:0.8rem; }
.plot-btn:hover { background:var(--blue); color:var(--bg); }
.no-data { text-align:center; padding:60px; color:var(--muted); }

/* Plot Modal */
.plot-modal { display:none; position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,0.9); z-index:1000; }
.plot-modal.active { display:flex; flex-direction:column; }
.plot-modal-bar { display:flex; justify-content:space-between; align-items:center; padding:16px 20px; background:var(--bg2); border-bottom:1px solid var(--border); }
.pm-title { font-family:"Oswald",sans-serif; font-size:1.2rem; color:var(--gold); }
.pm-sub { font-family:"JetBrains Mono",monospace; font-size:0.85rem; color:var(--text2); margin-left:16px; }
.pm-close { background:transparent; border:1px solid var(--gold); color:var(--gold); padding:8px 16px; border-radius:4px; cursor:pointer; }
.pm-close:hover { background:var(--gold); color:var(--bg); }
.plot-modal-body { flex:1; display:flex; padding:20px; gap:20px; overflow:hidden; }
#pmCanvasWrap { flex:1; background:#0a1820; border-radius:8px; overflow:hidden; position:relative; }
#pmCanvas { display:block; width:100%; height:100%; }
.pm-stats { width:200px; background:var(--bg2); border-radius:8px; padding:16px; overflow-y:auto; }
.pm-stats h3 { font-family:"Oswald",sans-serif; color:var(--gold); margin-bottom:12px; }
.pm-shot-list { list-style:none; }
.pm-shot-list li { padding:6px 0; border-bottom:1px solid var(--border); font-family:"JetBrains Mono",monospace; font-size:0.85rem; display:flex; justify-content:space-between; }
.pm-shot-list li.sighter { color:var(--muted); font-style:italic; }
.pm-controls { display:flex; gap:8px; margin-top:12px; }
.pm-btn { background:var(--bg); border:1px solid var(--border); color:var(--text2); padding:6px 12px; border-radius:4px; cursor:pointer; }
.pm-btn:hover { border-color:var(--gold); color:var(--gold); }
footer { margin-top:60px; padding:20px; border-top:1px solid var(--border); text-align:center; font-size:0.9rem; }
footer a { color:var(--text2); text-decoration:none; margin:0 12px; }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>{{ range.name }} — {{ date.strftime("%d %B %Y") }}</h1>
    <a href="/range/{{ range.id }}" class="nav-link">← Calendar</a>
  </div>
  
  <!-- Filter Bar -->
  <div class="filter-bar">
    <div class="filter-row">
      <div class="filter-group">
        <label>Shooter</label>
        <input type="text" id="filterShooter" placeholder="Search name..." oninput="applyFilters()">
      </div>
      <div class="filter-actions">
        <button class="filter-clear" onclick="clearFilters()">Clear All Filters</button>
      </div>
    </div>
    
    <div class="filter-group">
      <label>Distance <button class="select-all-btn" onclick="toggleAllDistances()">Toggle All</button></label>
      <div class="toggle-group" id="distanceFilters">
        <button class="toggle-btn distance active" data-dist="300" onclick="toggleDistance(this)">300</button>
        <button class="toggle-btn distance active" data-dist="400" onclick="toggleDistance(this)">400</button>
        <button class="toggle-btn distance active" data-dist="500" onclick="toggleDistance(this)">500</button>
        <button class="toggle-btn distance active" data-dist="600" onclick="toggleDistance(this)">600</button>
        <button class="toggle-btn distance active" data-dist="700" onclick="toggleDistance(this)">700</button>
        <button class="toggle-btn distance active" data-dist="800" onclick="toggleDistance(this)">800</button>
        <button class="toggle-btn distance active" data-dist="900" onclick="toggleDistance(this)">900</button>
        <button class="toggle-btn distance active" data-dist="1000" onclick="toggleDistance(this)">1000</button>
      </div>
    </div>
    
    <div class="filter-group">
      <label>Target <button class="select-all-btn" onclick="toggleAllTargets()">Toggle All</button></label>
      <div class="toggle-group" id="targetFilters"></div>
    </div>
  </div>
  
  <div class="result-count" id="resultCount"></div>
  
  <table id="resultsTable">
    <thead>
      <tr>
        <th data-sort="target" onclick="sortTable('target')">Target</th>
        <th data-sort="shooter" onclick="sortTable('shooter')">Shooter</th>
        <th data-sort="distance" onclick="sortTable('distance')">Distance</th>
        <th data-sort="score" onclick="sortTable('score')">Score</th>
        <th></th>
      </tr>
    </thead>
    <tbody>
      {% for s in strings %}
      <tr data-idx="{{ loop.index0 }}" data-target="{{ s.target }}" data-shooter="{{ s.shooter_name }}" data-match="{{ s.match_name }}">
        <td class="target">{{ s.target }}</td>
        <td class="shooter">{{ s.shooter_name }}</td>
        <td class="distance-cell" id="dist-{{ loop.index0 }}">-</td>
        <td>
          <div class="score-cell">
            <span class="score" id="score-{{ loop.index0 }}">--</span>
            <div class="shot-badges" id="badges-{{ loop.index0 }}"></div>
          </div>
        </td>
        <td><button class="plot-btn" onclick="showPlot({{ loop.index0 }})">Plot</button></td>
      </tr>
      {% endfor %}
      {% if not strings %}<tr><td colspan="5" class="no-data">No data for this date</td></tr>{% endif %}
    </tbody>
  </table>
</div>

<div class="plot-modal" id="plotModal">
  <div class="plot-modal-bar">
    <div><span class="pm-title" id="pmTitle">Shooter</span><span class="pm-sub" id="pmSub"></span></div>
    <button class="pm-close" onclick="closePlot()">✕ Close</button>
  </div>
  <div class="plot-modal-body">
    <div id="pmCanvasWrap"><canvas id="pmCanvas"></canvas></div>
    <div class="pm-stats">
      <h3>Shots</h3>
      <ul class="pm-shot-list" id="pmShotList"></ul>
      <div class="pm-controls">
        <button class="pm-btn" onclick="pmResetZoom()">Reset</button>
        <button class="pm-btn" onclick="pmFitShots()">Fit</button>
        <button class="pm-btn" onclick="pmZoomIn()">+</button>
        <button class="pm-btn" onclick="pmZoomOut()">-</button>
      </div>
    </div>
  </div>
</div>

<footer><a href="/">Home</a><a href="/about">About</a><a href="/contact">Contact</a></footer>

<script>
var stringData = [
{% for s in strings %}
{target:"{{ s.target }}",name:"{{ s.shooter_name }}",match:"{{ s.match_name or '' }}",shots:{{ s.shot_data | tojson if s.shot_data else "[]" }}},
{% endfor %}
];

// Extract distance from match name (e.g., "800m F-Class" -> 800)
function extractDistance(match) {
  if (!match) return null;
  var m = match.match(/(\d{3,4})m?/);
  return m ? parseInt(m[1]) : null;
}

// Calculate score and render badges
function calcScore(shots) {
  var t = 0, xv = 0;
  shots.forEach(function(s) {
    if (s.isSighter) return;
    var sc = String(s.score).toUpperCase();
    if (sc === "X" || sc === "V") { t += 6; xv++; }
    else if (sc === "6") { t += 6; }
    else { t += parseInt(sc) || 0; }
  });
  return { total: t, xv: xv, display: t + "." + xv };
}

function renderBadges(shots) {
  var html = '';
  shots.forEach(function(s) {
    var sc = String(s.score).toUpperCase();
    if (s.isSighter) {
      html += '<span class="shot-badge sighter">' + sc + '</span>';
    } else {
      var cls = 'score-' + sc;
      html += '<span class="shot-badge ' + cls + '">' + sc + '</span>';
    }
  });
  return html;
}

// Initialize scores, badges, and distances
var targetSet = new Set();
stringData.forEach(function(s, i) {
  var scoreEl = document.getElementById("score-" + i);
  var badgeEl = document.getElementById("badges-" + i);
  var distEl = document.getElementById("dist-" + i);
  
  // Extract distance
  s.distance = extractDistance(s.match);
  if (distEl && s.distance) distEl.textContent = s.distance + 'm';
  
  // Collect targets
  if (s.target) targetSet.add(s.target);
  
  if (s.shots && s.shots.length) {
    var result = calcScore(s.shots);
    if (scoreEl) scoreEl.textContent = result.display;
    if (badgeEl) badgeEl.innerHTML = renderBadges(s.shots);
    stringData[i].numericScore = result.total + result.xv / 100;
  } else {
    stringData[i].numericScore = 0;
  }
});

// Build target filter buttons
var targetContainer = document.getElementById('targetFilters');
Array.from(targetSet).sort().forEach(function(t) {
  var btn = document.createElement('button');
  btn.className = 'toggle-btn target-btn active';
  btn.dataset.target = t;
  btn.textContent = t;
  btn.onclick = function() { toggleTarget(this); };
  targetContainer.appendChild(btn);
});

// Filter state
var activeDistances = new Set(['300','400','500','600','700','800','900','1000']);
var activeTargets = new Set(targetSet);

function toggleDistance(btn) {
  var dist = btn.dataset.dist;
  btn.classList.toggle('active');
  if (activeDistances.has(dist)) {
    activeDistances.delete(dist);
  } else {
    activeDistances.add(dist);
  }
  applyFilters();
}

function toggleTarget(btn) {
  var target = btn.dataset.target;
  btn.classList.toggle('active');
  if (activeTargets.has(target)) {
    activeTargets.delete(target);
  } else {
    activeTargets.add(target);
  }
  applyFilters();
}

function toggleAllDistances() {
  var btns = document.querySelectorAll('#distanceFilters .toggle-btn');
  var allActive = activeDistances.size === 8;
  btns.forEach(function(btn) {
    if (allActive) {
      btn.classList.remove('active');
      activeDistances.delete(btn.dataset.dist);
    } else {
      btn.classList.add('active');
      activeDistances.add(btn.dataset.dist);
    }
  });
  applyFilters();
}

function toggleAllTargets() {
  var btns = document.querySelectorAll('#targetFilters .toggle-btn');
  var allActive = activeTargets.size === targetSet.size;
  btns.forEach(function(btn) {
    if (allActive) {
      btn.classList.remove('active');
      activeTargets.delete(btn.dataset.target);
    } else {
      btn.classList.add('active');
      activeTargets.add(btn.dataset.target);
    }
  });
  applyFilters();
}

function applyFilters() {
  var shooter = document.getElementById('filterShooter').value.toLowerCase();
  var rows = document.querySelectorAll('#resultsTable tbody tr');
  var visible = 0;
  
  rows.forEach(function(row) {
    if (!row.dataset.idx) return;
    var idx = parseInt(row.dataset.idx);
    var s = stringData[idx];
    
    var rowShooter = (s.name || '').toLowerCase();
    var rowTarget = s.target || '';
    var rowDist = s.distance ? String(s.distance) : '';
    
    var show = true;
    if (shooter && !rowShooter.includes(shooter)) show = false;
    if (rowTarget && !activeTargets.has(rowTarget)) show = false;
    if (rowDist && !activeDistances.has(rowDist)) show = false;
    
    row.classList.toggle('hidden', !show);
    if (show) visible++;
  });
  
  document.getElementById('resultCount').textContent = visible + ' of ' + stringData.length + ' strings shown';
}

function clearFilters() {
  document.getElementById('filterShooter').value = '';
  
  // Reset all distances
  document.querySelectorAll('#distanceFilters .toggle-btn').forEach(function(btn) {
    btn.classList.add('active');
    activeDistances.add(btn.dataset.dist);
  });
  
  // Reset all targets
  document.querySelectorAll('#targetFilters .toggle-btn').forEach(function(btn) {
    btn.classList.add('active');
    activeTargets.add(btn.dataset.target);
  });
  
  applyFilters();
}

// Sorting
var currentSort = { col: null, asc: true };
function sortTable(col) {
  var tbody = document.querySelector('#resultsTable tbody');
  var rows = Array.from(tbody.querySelectorAll('tr[data-idx]'));
  
  if (currentSort.col === col) {
    currentSort.asc = !currentSort.asc;
  } else {
    currentSort.col = col;
    currentSort.asc = true;
  }
  
  document.querySelectorAll('th').forEach(function(th) {
    th.classList.remove('sorted-asc', 'sorted-desc');
  });
  var th = document.querySelector('th[data-sort="' + col + '"]');
  if (th) th.classList.add(currentSort.asc ? 'sorted-asc' : 'sorted-desc');
  
  rows.sort(function(a, b) {
    var aIdx = parseInt(a.dataset.idx);
    var bIdx = parseInt(b.dataset.idx);
    var aVal, bVal;
    
    if (col === 'score') {
      aVal = stringData[aIdx].numericScore;
      bVal = stringData[bIdx].numericScore;
    } else if (col === 'shooter') {
      aVal = (stringData[aIdx].name || '').toLowerCase();
      bVal = (stringData[bIdx].name || '').toLowerCase();
    } else if (col === 'target') {
      aVal = (stringData[aIdx].target || '').toLowerCase();
      bVal = (stringData[bIdx].target || '').toLowerCase();
    } else if (col === 'distance') {
      aVal = stringData[aIdx].distance || 0;
      bVal = stringData[bIdx].distance || 0;
    }
    
    if (aVal < bVal) return currentSort.asc ? -1 : 1;
    if (aVal > bVal) return currentSort.asc ? 1 : -1;
    return 0;
  });
  
  rows.forEach(function(row) { tbody.appendChild(row); });
}

// Initialize
applyFilters();

// Plot modal code
var ICFRA={300:{aim:600,X:35,V:70,5:140,4:280,3:420,2:600,tw:1200,th:1200},400:{aim:800,X:46,V:93,5:186,4:373,3:560,2:800,tw:1200,th:1200},500:{aim:1000,X:72,V:145,5:290,4:660,3:1000,2:1320,tw:1800,th:1800},600:{aim:1000,X:80,V:160,5:320,4:660,3:1000,2:1320,tw:1800,th:1800},700:{aim:1120,X:127,V:255,5:510,4:815,3:1120,2:1830,tw:1800,th:1800},800:{aim:1120,X:127,V:255,5:510,4:815,3:1120,2:1830,tw:2400,th:1800},900:{aim:1120,X:127,V:255,5:510,4:815,3:1120,2:1830,tw:2400,th:1800}};
var SHOT_COLORS={"X":"#f4c566","V":"#5cc9a7","6":"#54b8db","5":"#8ab4c8","4":"#d4cdb8","3":"#e8985a","2":"#e8706a","1":"#ff5555","0":"#ff3333"};
var pmShots=[],pmFace=null,pmViewX=0,pmViewY=0,pmViewScale=1,pmCanvasW=600,pmCanvasH=600,pmDragging=false,pmDragSX,pmDragSY,pmDragVX,pmDragVY;
function parseFace(str){var m=str.match(/(\d+)m/);var dist=m?parseInt(m[1]):800;var isTR=/Target Rifle/i.test(str);var d=ICFRA[dist]||ICFRA[800];var aimR=d.aim/2;var rings=isTR?[{label:"V",r:d.X/2},{label:"V",r:d.V/2},{label:"5",r:d[5]/2},{label:"4",r:d[4]/2},{label:"3",r:d[3]/2},{label:"2",r:d[2]/2}]:[{label:"X",r:d.X/2},{label:"6",r:d.V/2},{label:"5",r:d[5]/2},{label:"4",r:d[4]/2},{label:"3",r:d[3]/2},{label:"2",r:d[2]/2}];return{dist:dist,d:d,rings:rings,isTR:isTR,aimR:aimR,tw:d.tw,th:d.th};}
function showPlot(idx){var s=stringData[idx];if(!s||!s.shots||!s.shots.length){alert("No shot data");return;}pmShots=s.shots;pmFace=parseFace(s.match||"800m");pmViewX=0;pmViewY=0;pmViewScale=1;document.getElementById("pmTitle").textContent=s.name;document.getElementById("pmSub").textContent=calcScore(s.shots).display+" • "+(s.match||"");var html="";pmShots.forEach(function(shot){var cls=shot.isSighter?" class=\\"sighter\\"":"";var lbl=shot.isSighter?"S"+shot.id.replace("S",""):shot.id;html+="<li"+cls+"><span>"+lbl+"</span><span>"+shot.score+"</span></li>";});document.getElementById("pmShotList").innerHTML=html;document.getElementById("plotModal").classList.add("active");document.body.style.overflow="hidden";setTimeout(function(){pmDraw();pmFitShots();},50);}
function closePlot(){document.getElementById("plotModal").classList.remove("active");document.body.style.overflow="";}
function pmDraw(){var wrap=document.getElementById("pmCanvasWrap");var canvas=document.getElementById("pmCanvas");var ctx=canvas.getContext("2d");var dpr=window.devicePixelRatio||1;var rect=wrap.getBoundingClientRect();pmCanvasW=rect.width;pmCanvasH=rect.height;canvas.width=pmCanvasW*dpr;canvas.height=pmCanvasH*dpr;canvas.style.width=pmCanvasW+"px";canvas.style.height=pmCanvasH+"px";ctx.setTransform(dpr,0,0,dpr,0,0);if(!pmFace)return;var f=pmFace;var maxDim=Math.max(f.tw,f.th)/2*1.08;var baseScale=Math.min(pmCanvasW,pmCanvasH)/2/maxDim;var scale=baseScale*pmViewScale;var cx=pmCanvasW/2+pmViewX,cy=pmCanvasH/2+pmViewY;var mm2px=function(mx,my){return[cx+mx*scale,cy-my*scale];};var mm2r=function(mm){return mm*scale;};ctx.fillStyle="#0a1820";ctx.fillRect(0,0,pmCanvasW,pmCanvasH);var tl=mm2px(-f.tw/2,f.th/2);ctx.fillStyle="#e8e4da";ctx.fillRect(tl[0],tl[1],mm2r(f.tw),mm2r(f.th));for(var i=f.rings.length-1;i>=0;i--){var ring=f.rings[i];if(ring.r>f.aimR){ctx.beginPath();ctx.arc(cx,cy,mm2r(ring.r),0,Math.PI*2);ctx.strokeStyle="#222";ctx.lineWidth=Math.max(1.5,mm2r(3));ctx.stroke();}}ctx.beginPath();ctx.arc(cx,cy,mm2r(f.aimR),0,Math.PI*2);ctx.fillStyle="#1a1a1a";ctx.fill();for(var i=f.rings.length-1;i>=0;i--){var ring=f.rings[i];if(ring.r<=f.aimR&&ring.r>0){ctx.beginPath();ctx.arc(cx,cy,mm2r(ring.r),0,Math.PI*2);ctx.strokeStyle="rgba(255,255,255,0.55)";ctx.lineWidth=Math.max(0.8,mm2r(2));ctx.stroke();}}pmShots.forEach(function(shot){var sp=mm2px(shot.x,shot.y);var baseR=shot.isSighter?4:5.5;var dotR=baseR*Math.max(0.7,Math.min(2.5,1/Math.sqrt(pmViewScale)*1.8));var sc=String(shot.score).toUpperCase();var color=shot.isSighter?"rgba(200,200,200,0.5)":(SHOT_COLORS[sc]||"#888");if(!shot.isSighter){ctx.beginPath();ctx.arc(sp[0],sp[1],dotR+3,0,Math.PI*2);ctx.fillStyle="rgba(0,0,0,0.25)";ctx.fill();}ctx.beginPath();ctx.arc(sp[0],sp[1],dotR,0,Math.PI*2);ctx.fillStyle=color;ctx.fill();ctx.strokeStyle=shot.isSighter?"rgba(255,255,255,0.2)":"rgba(0,0,0,0.5)";ctx.lineWidth=0.8;ctx.stroke();if(!shot.isSighter){var fs=Math.max(7,Math.min(12,10/Math.sqrt(pmViewScale)*1.5));ctx.fillStyle=color;ctx.globalAlpha=0.85;ctx.font="bold "+fs+"px JetBrains Mono";ctx.textAlign="left";ctx.textBaseline="middle";ctx.fillText(shot.id,sp[0]+dotR+3,sp[1]+1);ctx.globalAlpha=1;}});}
function pmResetZoom(){pmViewX=0;pmViewY=0;pmViewScale=1;pmDraw();}
function pmFitShots(){if(!pmShots.length||!pmFace)return;var minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity;pmShots.forEach(function(s){if(s.x<minX)minX=s.x;if(s.x>maxX)maxX=s.x;if(s.y<minY)minY=s.y;if(s.y>maxY)maxY=s.y;});var span=Math.max((maxX-minX)||100,(maxY-minY)||100)*1.5;var maxDim=Math.max(pmFace.tw,pmFace.th)/2*1.08;pmViewScale=Math.min((maxDim*2)/span,40);var centX=(minX+maxX)/2,centY=(minY+maxY)/2;var baseScale=Math.min(pmCanvasW,pmCanvasH)/2/maxDim;pmViewX=-centX*baseScale*pmViewScale;pmViewY=centY*baseScale*pmViewScale;pmDraw();}
function pmZoomIn(){pmViewScale=Math.min(100,pmViewScale*1.5);pmDraw();}
function pmZoomOut(){pmViewScale=Math.max(0.3,pmViewScale/1.5);pmDraw();}
(function(){var wrap=document.getElementById("pmCanvasWrap");wrap.addEventListener("wheel",function(e){e.preventDefault();pmViewScale=Math.max(0.3,Math.min(100,pmViewScale*(e.deltaY<0?1.15:1/1.15)));pmDraw();},{passive:false});wrap.addEventListener("mousedown",function(e){pmDragging=true;pmDragSX=e.clientX;pmDragSY=e.clientY;pmDragVX=pmViewX;pmDragVY=pmViewY;});window.addEventListener("mousemove",function(e){if(pmDragging){pmViewX=pmDragVX+(e.clientX-pmDragSX);pmViewY=pmDragVY+(e.clientY-pmDragSY);pmDraw();}});window.addEventListener("mouseup",function(){pmDragging=false;});})();
</script>
</body>
</html>
'''
