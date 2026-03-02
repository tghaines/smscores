
# ══════════════════════════════════════════════
#  COMPETITION ADMIN
# ══════════════════════════════════════════════

@app.route('/admin/competition/<int:comp_id>')
def admin_competition(comp_id):
    """Competition admin page"""
    if not session.get('admin'):
        return redirect('/admin')
    comp = Competition.query.get_or_404(comp_id)
    return render_template_string(COMP_ADMIN_HTML, competition=comp)

@app.route('/api/admin/competition/<int:comp_id>/shooters')
def api_comp_shooters(comp_id):
    """Get all shooters for a competition"""
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    competitors = Competitor.query.filter_by(competition_id=comp_id).all()
    
    # Group by name to get unique shooters
    shooter_map = {}
    for c in competitors:
        if c.name not in shooter_map:
            shooter_map[c.name] = {'name': c.name, 'class': c.class_name, 'matches': []}
        shooter_map[c.name]['matches'].append(c.match)
    
    return jsonify(list(shooter_map.values()))

@app.route('/api/admin/competition/<int:comp_id>/shooter', methods=['POST'])
def api_add_shooter(comp_id):
    """Add a new shooter"""
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    name = data.get('name', '').strip()
    class_name = data.get('class', '').strip()
    
    if not name:
        return jsonify({'error': 'Name required'}), 400
    
    # Add to all matches (or specific match if provided)
    match = data.get('match', '')
    
    comp = Competitor(
        competition_id=comp_id,
        name=name,
        class_name=class_name,
        match=match,
        relay='',
        target='',
        position=''
    )
    db.session.add(comp)
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'Added {name}'})

@app.route('/api/admin/competition/<int:comp_id>/shooter/update', methods=['POST'])
def api_update_shooter(comp_id):
    """Update shooter name or class"""
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    old_name = data.get('old_name', '').strip()
    new_name = data.get('new_name', '').strip()
    new_class = data.get('new_class')
    
    if not old_name:
        return jsonify({'error': 'Old name required'}), 400
    
    # Update in competitors table
    competitors = Competitor.query.filter_by(competition_id=comp_id, name=old_name).all()
    for c in competitors:
        if new_name:
            c.name = new_name
        if new_class is not None:
            c.class_name = new_class
    
    # Also update in scores if name changed
    if new_name and new_name != old_name:
        scores = Score.query.filter_by(competition_id=comp_id).all()
        for score in scores:
            if score.data:
                updated = False
                for shooter in score.data:
                    if shooter.get('name') == old_name:
                        shooter['name'] = new_name
                        updated = True
                if updated:
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(score, 'data')
    
    db.session.commit()
    return jsonify({'success': True, 'message': f'Updated {old_name} → {new_name or old_name}'})

@app.route('/api/admin/competition/<int:comp_id>/shooter/delete', methods=['POST'])
def api_delete_shooter(comp_id):
    """Delete a shooter"""
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    name = data.get('name', '').strip()
    
    if not name:
        return jsonify({'error': 'Name required'}), 400
    
    # Delete from competitors
    Competitor.query.filter_by(competition_id=comp_id, name=name).delete()
    
    # Remove from scores
    scores = Score.query.filter_by(competition_id=comp_id).all()
    for score in scores:
        if score.data:
            score.data = [s for s in score.data if s.get('name') != name]
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(score, 'data')
    
    db.session.commit()
    return jsonify({'success': True, 'message': f'Deleted {name}'})

@app.route('/api/admin/competition/<int:comp_id>/matches')
def api_comp_matches(comp_id):
    """Get all match names for a competition"""
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    competitors = Competitor.query.filter_by(competition_id=comp_id).all()
    matches = set(c.match for c in competitors if c.match)
    
    # Also get from scores
    scores = Score.query.filter_by(competition_id=comp_id).all()
    for score in scores:
        if score.data:
            for shooter in score.data:
                for m in shooter.get('matches', []):
                    if m.get('match'):
                        matches.add(m['match'])
    
    return jsonify(sorted(list(matches)))

@app.route('/api/admin/competition/<int:comp_id>/match/rename', methods=['POST'])
def api_rename_match(comp_id):
    """Rename a match"""
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    old_name = data.get('old_name', '').strip()
    new_name = data.get('new_name', '').strip()
    
    if not old_name or not new_name:
        return jsonify({'error': 'Both names required'}), 400
    
    # Update in competitors
    competitors = Competitor.query.filter_by(competition_id=comp_id, match=old_name).all()
    for c in competitors:
        c.match = new_name
    
    # Update in scores
    scores = Score.query.filter_by(competition_id=comp_id).all()
    for score in scores:
        if score.data:
            updated = False
            for shooter in score.data:
                for m in shooter.get('matches', []):
                    if m.get('match') == old_name:
                        m['match'] = new_name
                        updated = True
            if updated:
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(score, 'data')
    
    db.session.commit()
    return jsonify({'success': True, 'message': f'Renamed {old_name} → {new_name}'})

@app.route('/api/admin/competition/<int:comp_id>/scores')
def api_comp_scores(comp_id):
    """Get all scores for a competition"""
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    latest = Score.query.filter_by(competition_id=comp_id).order_by(Score.created_at.desc()).first()
    if not latest or not latest.data:
        return jsonify([])
    
    return jsonify(latest.data)

@app.route('/api/admin/competition/<int:comp_id>/score/add', methods=['POST'])
def api_add_score(comp_id):
    """Add or update a score for a shooter"""
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    shooter_name = data.get('name', '').strip()
    match_name = data.get('match', '').strip()
    shots = data.get('shots', '').strip()
    
    if not shooter_name or not match_name:
        return jsonify({'error': 'Name and match required'}), 400
    
    # Calculate score from shots
    score = 0
    x_count = 0
    for s in shots.split(','):
        s = s.strip().upper()
        if s == 'X':
            score += 6
            x_count += 1
        elif s == 'V':
            score += 5
            x_count += 1
        elif s.isdigit():
            score += int(s)
    
    # Get or create latest score record
    latest = Score.query.filter_by(competition_id=comp_id).order_by(Score.created_at.desc()).first()
    
    if not latest:
        latest = Score(competition_id=comp_id, data=[])
        db.session.add(latest)
    
    # Find or create shooter in data
    shooter_data = None
    for s in latest.data:
        if s.get('name') == shooter_name:
            shooter_data = s
            break
    
    if not shooter_data:
        shooter_data = {'name': shooter_name, 'class': '', 'matches': [], 'total': 0, 'vCount': 0}
        latest.data.append(shooter_data)
    
    # Find or create match
    match_data = None
    for m in shooter_data.get('matches', []):
        if m.get('match') == match_name:
            match_data = m
            break
    
    if match_data:
        # Update existing
        old_score = match_data.get('score', 0)
        old_x = match_data.get('xCount', 0)
        match_data['shots'] = shots
        match_data['score'] = score
        match_data['xCount'] = x_count
        shooter_data['total'] = shooter_data.get('total', 0) - old_score + score
        shooter_data['vCount'] = shooter_data.get('vCount', 0) - old_x + x_count
    else:
        # Add new
        if 'matches' not in shooter_data:
            shooter_data['matches'] = []
        shooter_data['matches'].append({
            'match': match_name,
            'shots': shots,
            'score': score,
            'xCount': x_count
        })
        shooter_data['total'] = shooter_data.get('total', 0) + score
        shooter_data['vCount'] = shooter_data.get('vCount', 0) + x_count
    
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(latest, 'data')
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'Added score for {shooter_name} in {match_name}: {score}.{x_count}'})

@app.route('/api/admin/competition/<int:comp_id>/score/delete', methods=['POST'])
def api_delete_score(comp_id):
    """Delete a specific score"""
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    shooter_name = data.get('name', '').strip()
    match_name = data.get('match', '').strip()
    
    if not shooter_name:
        return jsonify({'error': 'Name required'}), 400
    
    latest = Score.query.filter_by(competition_id=comp_id).order_by(Score.created_at.desc()).first()
    if not latest or not latest.data:
        return jsonify({'error': 'No scores found'}), 404
    
    for shooter in latest.data:
        if shooter.get('name') == shooter_name:
            if match_name:
                # Delete specific match
                old_matches = shooter.get('matches', [])
                for m in old_matches:
                    if m.get('match') == match_name:
                        shooter['total'] = shooter.get('total', 0) - m.get('score', 0)
                        shooter['vCount'] = shooter.get('vCount', 0) - m.get('xCount', 0)
                shooter['matches'] = [m for m in old_matches if m.get('match') != match_name]
            else:
                # Delete all scores for shooter
                latest.data = [s for s in latest.data if s.get('name') != shooter_name]
            break
    
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(latest, 'data')
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'Deleted score'})

@app.route('/api/admin/competition/<int:comp_id>/archive', methods=['POST'])
def api_archive_competition(comp_id):
    """Archive a competition"""
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    comp = Competition.query.get_or_404(comp_id)
    comp.archived = True
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'Archived {comp.name}'})

COMP_ADMIN_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Admin - {{ competition.name }}</title>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&family=Barlow+Condensed:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root { --bg:#0c1e2b; --bg2:#122a3a; --bg3:#1a3a4a; --gold:#f4c566; --green:#5cc9a7; --blue:#54b8db; --red:#e85a5a; --text:#f0ece4; --text2:#8ab4c8; --muted:#5a8899; --border:#1e3d50; }
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--bg); color:var(--text); font-family:'Barlow Condensed',sans-serif; min-height:100vh; }
.container { max-width:1200px; margin:0 auto; padding:20px; }
.header { display:flex; justify-content:space-between; align-items:center; padding:20px 0; border-bottom:1px solid var(--border); margin-bottom:20px; }
.header h1 { font-family:'Oswald',sans-serif; font-size:1.6rem; color:var(--gold); }
.nav-links { display:flex; gap:12px; }
.nav-link { color:var(--gold); text-decoration:none; border:1px solid var(--gold); padding:8px 16px; border-radius:4px; font-size:0.9rem; }
.nav-link:hover { background:var(--gold); color:var(--bg); }

/* Tabs */
.tabs { display:flex; gap:4px; margin-bottom:20px; border-bottom:2px solid var(--border); }
.tab { padding:12px 24px; background:transparent; border:none; color:var(--text2); font-family:'Oswald',sans-serif; font-size:1rem; cursor:pointer; border-bottom:2px solid transparent; margin-bottom:-2px; }
.tab:hover { color:var(--text); }
.tab.active { color:var(--gold); border-bottom-color:var(--gold); }
.tab-content { display:none; }
.tab-content.active { display:block; }

/* Action Bar */
.action-bar { display:flex; gap:12px; margin-bottom:16px; flex-wrap:wrap; align-items:center; }
.action-btn { padding:8px 16px; border:1px solid var(--border); background:var(--bg2); color:var(--text); border-radius:4px; cursor:pointer; font-size:0.9rem; }
.action-btn:hover { border-color:var(--gold); color:var(--gold); }
.action-btn.primary { background:var(--gold); color:var(--bg); border-color:var(--gold); }
.action-btn.danger { background:var(--red); color:var(--text); border-color:var(--red); }
.search-input { padding:8px 12px; background:var(--bg); border:1px solid var(--border); border-radius:4px; color:var(--text); width:200px; }
.search-input:focus { outline:none; border-color:var(--gold); }

/* Tables */
table { width:100%; border-collapse:collapse; }
th, td { padding:10px 12px; text-align:left; border-bottom:1px solid var(--border); }
th { background:var(--bg2); color:var(--gold); font-family:'Oswald',sans-serif; font-size:0.9rem; }
tr:hover { background:var(--bg3); }
.edit-btn { padding:4px 10px; background:var(--blue); color:var(--bg); border:none; border-radius:3px; cursor:pointer; font-size:0.8rem; margin-right:4px; }
.delete-btn { padding:4px 10px; background:var(--red); color:var(--text); border:none; border-radius:3px; cursor:pointer; font-size:0.8rem; }
.edit-btn:hover, .delete-btn:hover { opacity:0.8; }

/* Forms */
.form-row { display:flex; gap:12px; margin-bottom:12px; flex-wrap:wrap; }
.form-group { display:flex; flex-direction:column; gap:4px; }
.form-group label { font-size:0.8rem; color:var(--text2); text-transform:uppercase; }
.form-group input, .form-group select { padding:8px 12px; background:var(--bg); border:1px solid var(--border); border-radius:4px; color:var(--text); font-size:0.9rem; }
.form-group input:focus, .form-group select:focus { outline:none; border-color:var(--gold); }

/* Modal */
.modal { display:none; position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,0.8); z-index:1000; align-items:center; justify-content:center; }
.modal.active { display:flex; }
.modal-content { background:var(--bg2); border:1px solid var(--border); border-radius:8px; padding:24px; min-width:400px; max-width:90%; max-height:90vh; overflow-y:auto; }
.modal-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; }
.modal-header h2 { font-family:'Oswald',sans-serif; color:var(--gold); }
.modal-close { background:none; border:none; color:var(--text2); font-size:1.5rem; cursor:pointer; }
.modal-close:hover { color:var(--text); }

/* Messages */
.message { padding:12px 16px; border-radius:4px; margin-bottom:16px; font-family:'JetBrains Mono',monospace; font-size:0.85rem; }
.message.success { background:rgba(92,201,167,0.2); border:1px solid var(--green); color:var(--green); }
.message.error { background:rgba(232,90,90,0.2); border:1px solid var(--red); color:var(--red); }

/* Match cards */
.match-card { background:var(--bg2); border:1px solid var(--border); border-radius:4px; padding:12px 16px; margin-bottom:8px; display:flex; justify-content:space-between; align-items:center; }
.match-name { font-family:'Oswald',sans-serif; font-size:1.1rem; }
.match-name input { background:transparent; border:none; color:var(--text); font-family:'Oswald',sans-serif; font-size:1.1rem; width:300px; }
.match-name input:focus { outline:none; border-bottom:1px solid var(--gold); }

/* Shot badges */
.shot-badges { display:flex; flex-wrap:wrap; gap:2px; }
.shot-badge { display:inline-flex; align-items:center; justify-content:center; min-width:20px; height:18px; padding:0 4px; border-radius:2px; font-family:'JetBrains Mono',monospace; font-size:0.7rem; font-weight:600; }
.shot-badge.score-X { background:#f4c566; color:#0c1e2b; }
.shot-badge.score-V { background:#5cc9a7; color:#0c1e2b; }
.shot-badge.score-6 { background:#54b8db; color:#0c1e2b; }
.shot-badge.score-5 { background:#8ab4c8; color:#0c1e2b; }
.shot-badge.score-4 { background:#d4cdb8; color:#0c1e2b; }
.shot-badge.score-3 { background:#e8985a; color:#0c1e2b; }
.shot-badge.score-2 { background:#e8706a; color:#0c1e2b; }
.shot-badge.score-1 { background:#ff5555; color:#0c1e2b; }
.shot-badge.score-0 { background:#ff3333; color:#fff; }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>⚙️ Admin: {{ competition.name }}</h1>
    <div class="nav-links">
      <a href="/{{ competition.route }}" class="nav-link">View Scoreboard</a>
      <a href="/admin/dashboard" class="nav-link">← Dashboard</a>
    </div>
  </div>
  
  <div id="message"></div>
  
  <div class="tabs">
    <button class="tab active" onclick="showTab('shooters')">Shooters</button>
    <button class="tab" onclick="showTab('scores')">Scores</button>
    <button class="tab" onclick="showTab('matches')">Matches</button>
    <button class="tab" onclick="showTab('settings')">Settings</button>
  </div>
  
  <!-- SHOOTERS TAB -->
  <div id="shooters-tab" class="tab-content active">
    <div class="action-bar">
      <button class="action-btn primary" onclick="showAddShooterModal()">+ Add Shooter</button>
      <input type="text" class="search-input" placeholder="Search shooters..." oninput="filterShooters(this.value)">
    </div>
    <table id="shooters-table">
      <thead>
        <tr><th>Name</th><th>Class</th><th>Actions</th></tr>
      </thead>
      <tbody id="shooters-body"></tbody>
    </table>
  </div>
  
  <!-- SCORES TAB -->
  <div id="scores-tab" class="tab-content">
    <div class="action-bar">
      <button class="action-btn primary" onclick="showAddScoreModal()">+ Add Score</button>
      <input type="text" class="search-input" placeholder="Search scores..." oninput="filterScores(this.value)">
    </div>
    <table id="scores-table">
      <thead>
        <tr><th>Shooter</th><th>Match</th><th>Shots</th><th>Score</th><th>Actions</th></tr>
      </thead>
      <tbody id="scores-body"></tbody>
    </table>
  </div>
  
  <!-- MATCHES TAB -->
  <div id="matches-tab" class="tab-content">
    <p style="color:var(--text2); margin-bottom:16px;">Edit match names - changes apply to squadding and scores.</p>
    <div id="matches-list"></div>
  </div>
  
  <!-- SETTINGS TAB -->
  <div id="settings-tab" class="tab-content">
    <div class="form-row">
      <div class="form-group">
        <label>Competition Name</label>
        <input type="text" id="comp-name" value="{{ competition.name }}" style="width:300px;">
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Description</label>
        <input type="text" id="comp-desc" value="{{ competition.description or '' }}" style="width:400px;">
      </div>
    </div>
    <div class="form-row" style="margin-top:30px;">
      <button class="action-btn danger" onclick="archiveCompetition()">Archive Competition</button>
    </div>
  </div>
</div>

<!-- Add Shooter Modal -->
<div class="modal" id="add-shooter-modal">
  <div class="modal-content">
    <div class="modal-header">
      <h2>Add Shooter</h2>
      <button class="modal-close" onclick="closeModal('add-shooter-modal')">&times;</button>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Name</label>
        <input type="text" id="new-shooter-name" style="width:250px;">
      </div>
      <div class="form-group">
        <label>Class</label>
        <select id="new-shooter-class">
          <option value="F-Open">F-Open</option>
          <option value="FTR">FTR</option>
          <option value="">Other</option>
        </select>
      </div>
    </div>
    <div class="form-row" style="margin-top:20px;">
      <button class="action-btn primary" onclick="addShooter()">Add Shooter</button>
    </div>
  </div>
</div>

<!-- Edit Shooter Modal -->
<div class="modal" id="edit-shooter-modal">
  <div class="modal-content">
    <div class="modal-header">
      <h2>Edit Shooter</h2>
      <button class="modal-close" onclick="closeModal('edit-shooter-modal')">&times;</button>
    </div>
    <input type="hidden" id="edit-shooter-old-name">
    <div class="form-row">
      <div class="form-group">
        <label>Name</label>
        <input type="text" id="edit-shooter-name" style="width:250px;">
      </div>
      <div class="form-group">
        <label>Class</label>
        <select id="edit-shooter-class">
          <option value="F-Open">F-Open</option>
          <option value="FTR">FTR</option>
          <option value="">Other</option>
        </select>
      </div>
    </div>
    <div class="form-row" style="margin-top:20px;">
      <button class="action-btn primary" onclick="updateShooter()">Save Changes</button>
    </div>
  </div>
</div>

<!-- Add Score Modal -->
<div class="modal" id="add-score-modal">
  <div class="modal-content">
    <div class="modal-header">
      <h2>Add Score</h2>
      <button class="modal-close" onclick="closeModal('add-score-modal')">&times;</button>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Shooter</label>
        <select id="score-shooter" style="width:200px;"></select>
      </div>
      <div class="form-group">
        <label>Match</label>
        <select id="score-match" style="width:200px;"></select>
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Shots (comma separated: X,6,5,V,6,6,5,6,X,6)</label>
        <input type="text" id="score-shots" style="width:400px;" placeholder="X,6,5,V,6,6,5,6,X,6">
      </div>
    </div>
    <div class="form-row" style="margin-top:20px;">
      <button class="action-btn primary" onclick="addScore()">Add Score</button>
    </div>
  </div>
</div>

<script>
const COMP_ID = {{ competition.id }};
let shooters = [];
let scores = [];
let matches = [];

// Tab switching
function showTab(tab) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelector(`.tab-content#${tab}-tab`).classList.add('active');
  event.target.classList.add('active');
}

// Modal functions
function showModal(id) { document.getElementById(id).classList.add('active'); }
function closeModal(id) { document.getElementById(id).classList.remove('active'); }

function showMessage(msg, isError = false) {
  const el = document.getElementById('message');
  el.innerHTML = msg;
  el.className = 'message ' + (isError ? 'error' : 'success');
  setTimeout(() => el.innerHTML = '', 5000);
}

// Load data
async function loadShooters() {
  const resp = await fetch(`/api/admin/competition/${COMP_ID}/shooters`);
  shooters = await resp.json();
  renderShooters();
}

async function loadScores() {
  const resp = await fetch(`/api/admin/competition/${COMP_ID}/scores`);
  scores = await resp.json();
  renderScores();
}

async function loadMatches() {
  const resp = await fetch(`/api/admin/competition/${COMP_ID}/matches`);
  matches = await resp.json();
  renderMatches();
}

// Render functions
function renderShooters(filter = '') {
  const tbody = document.getElementById('shooters-body');
  const filtered = shooters.filter(s => s.name.toLowerCase().includes(filter.toLowerCase()));
  
  tbody.innerHTML = filtered.map(s => `
    <tr>
      <td>${s.name}</td>
      <td>${s.class || '-'}</td>
      <td>
        <button class="edit-btn" onclick="showEditShooter('${s.name}', '${s.class || ''}')">Edit</button>
        <button class="delete-btn" onclick="deleteShooter('${s.name}')">Delete</button>
      </td>
    </tr>
  `).join('');
}

function renderScores(filter = '') {
  const tbody = document.getElementById('scores-body');
  let rows = [];
  
  scores.forEach(shooter => {
    if (filter && !shooter.name.toLowerCase().includes(filter.toLowerCase())) return;
    
    (shooter.matches || []).forEach(m => {
      const shots = (m.shots || '').split(',').map(s => {
        const sc = s.trim().toUpperCase();
        return `<span class="shot-badge score-${sc}">${sc}</span>`;
      }).join('');
      
      rows.push(`
        <tr>
          <td>${shooter.name}</td>
          <td>${m.match}</td>
          <td><div class="shot-badges">${shots}</div></td>
          <td>${m.score}.${m.xCount}</td>
          <td>
            <button class="delete-btn" onclick="deleteScore('${shooter.name}', '${m.match}')">Delete</button>
          </td>
        </tr>
      `);
    });
  });
  
  tbody.innerHTML = rows.join('');
}

function renderMatches() {
  const container = document.getElementById('matches-list');
  container.innerHTML = matches.map(m => `
    <div class="match-card">
      <div class="match-name">
        <input type="text" value="${m}" data-original="${m}" onchange="renameMatch('${m}', this.value)">
      </div>
    </div>
  `).join('');
}

function filterShooters(val) { renderShooters(val); }
function filterScores(val) { renderScores(val); }

// Shooter actions
function showAddShooterModal() {
  document.getElementById('new-shooter-name').value = '';
  showModal('add-shooter-modal');
}

async function addShooter() {
  const name = document.getElementById('new-shooter-name').value.trim();
  const cls = document.getElementById('new-shooter-class').value;
  
  if (!name) { showMessage('Name required', true); return; }
  
  const resp = await fetch(`/api/admin/competition/${COMP_ID}/shooter`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ name, class: cls })
  });
  const result = await resp.json();
  
  if (result.success) {
    showMessage(result.message);
    closeModal('add-shooter-modal');
    loadShooters();
  } else {
    showMessage(result.error, true);
  }
}

function showEditShooter(name, cls) {
  document.getElementById('edit-shooter-old-name').value = name;
  document.getElementById('edit-shooter-name').value = name;
  document.getElementById('edit-shooter-class').value = cls;
  showModal('edit-shooter-modal');
}

async function updateShooter() {
  const oldName = document.getElementById('edit-shooter-old-name').value;
  const newName = document.getElementById('edit-shooter-name').value.trim();
  const newClass = document.getElementById('edit-shooter-class').value;
  
  const resp = await fetch(`/api/admin/competition/${COMP_ID}/shooter/update`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ old_name: oldName, new_name: newName, new_class: newClass })
  });
  const result = await resp.json();
  
  if (result.success) {
    showMessage(result.message);
    closeModal('edit-shooter-modal');
    loadShooters();
    loadScores();
  } else {
    showMessage(result.error, true);
  }
}

async function deleteShooter(name) {
  if (!confirm(`Delete ${name} and all their scores?`)) return;
  
  const resp = await fetch(`/api/admin/competition/${COMP_ID}/shooter/delete`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ name })
  });
  const result = await resp.json();
  
  if (result.success) {
    showMessage(result.message);
    loadShooters();
    loadScores();
  } else {
    showMessage(result.error, true);
  }
}

// Score actions
function showAddScoreModal() {
  // Populate shooter dropdown
  const shooterSelect = document.getElementById('score-shooter');
  shooterSelect.innerHTML = shooters.map(s => `<option value="${s.name}">${s.name}</option>`).join('');
  
  // Populate match dropdown
  const matchSelect = document.getElementById('score-match');
  matchSelect.innerHTML = matches.map(m => `<option value="${m}">${m}</option>`).join('');
  
  document.getElementById('score-shots').value = '';
  showModal('add-score-modal');
}

async function addScore() {
  const name = document.getElementById('score-shooter').value;
  const match = document.getElementById('score-match').value;
  const shots = document.getElementById('score-shots').value.trim();
  
  if (!name || !match || !shots) { showMessage('All fields required', true); return; }
  
  const resp = await fetch(`/api/admin/competition/${COMP_ID}/score/add`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ name, match, shots })
  });
  const result = await resp.json();
  
  if (result.success) {
    showMessage(result.message);
    closeModal('add-score-modal');
    loadScores();
  } else {
    showMessage(result.error, true);
  }
}

async function deleteScore(name, match) {
  if (!confirm(`Delete score for ${name} in ${match}?`)) return;
  
  const resp = await fetch(`/api/admin/competition/${COMP_ID}/score/delete`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ name, match })
  });
  const result = await resp.json();
  
  if (result.success) {
    showMessage(result.message);
    loadScores();
  } else {
    showMessage(result.error, true);
  }
}

// Match actions
async function renameMatch(oldName, newName) {
  if (!newName.trim() || newName === oldName) return;
  
  const resp = await fetch(`/api/admin/competition/${COMP_ID}/match/rename`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ old_name: oldName, new_name: newName.trim() })
  });
  const result = await resp.json();
  
  if (result.success) {
    showMessage(result.message);
    loadMatches();
  } else {
    showMessage(result.error, true);
  }
}

// Settings
async function archiveCompetition() {
  if (!confirm('Archive this competition? It will be hidden from the main view.')) return;
  
  const resp = await fetch(`/api/admin/competition/${COMP_ID}/archive`, {
    method: 'POST'
  });
  const result = await resp.json();
  
  if (result.success) {
    showMessage(result.message);
    setTimeout(() => window.location.href = '/admin/dashboard', 2000);
  } else {
    showMessage(result.error, true);
  }
}

// Init
loadShooters();
loadScores();
loadMatches();
</script>
</body>
</html>
'''
