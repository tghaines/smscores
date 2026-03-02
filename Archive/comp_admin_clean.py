
# ══════════════════════════════════════════════
#  COMPETITION ADMIN
# ══════════════════════════════════════════════

@app.route('/admin/competition/<int:comp_id>')
def admin_competition(comp_id):
    if not session.get('admin'):
        return redirect('/admin')
    comp = Competition.query.get_or_404(comp_id)
    return render_template_string(COMP_ADMIN_HTML, competition=comp)

@app.route('/api/admin/competition/<int:comp_id>/shooters')
def api_comp_shooters(comp_id):
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    competitors = Competitor.query.filter_by(competition_id=comp_id).all()
    shooter_map = {}
    for c in competitors:
        if c.name not in shooter_map:
            shooter_map[c.name] = {'name': c.name, 'class': c.class_name, 'matches': []}
        shooter_map[c.name]['matches'].append(c.match)
    return jsonify(list(shooter_map.values()))

@app.route('/api/admin/competition/<int:comp_id>/shooter', methods=['POST'])
def api_add_shooter(comp_id):
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json()
    name = data.get('name', '').strip()
    class_name = data.get('class', '').strip()
    if not name:
        return jsonify({'error': 'Name required'}), 400
    match = data.get('match', '')
    comp = Competitor(competition_id=comp_id, name=name, class_name=class_name, match=match, relay='', target='', position='')
    db.session.add(comp)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Added ' + name})

@app.route('/api/admin/competition/<int:comp_id>/shooter/update', methods=['POST'])
def api_update_shooter(comp_id):
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json()
    old_name = data.get('old_name', '').strip()
    new_name = data.get('new_name', '').strip()
    new_class = data.get('new_class')
    if not old_name:
        return jsonify({'error': 'Old name required'}), 400
    competitors = Competitor.query.filter_by(competition_id=comp_id, name=old_name).all()
    for c in competitors:
        if new_name:
            c.name = new_name
        if new_class is not None:
            c.class_name = new_class
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
    return jsonify({'success': True, 'message': 'Updated shooter'})

@app.route('/api/admin/competition/<int:comp_id>/shooter/delete', methods=['POST'])
def api_delete_shooter(comp_id):
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Name required'}), 400
    Competitor.query.filter_by(competition_id=comp_id, name=name).delete()
    scores = Score.query.filter_by(competition_id=comp_id).all()
    for score in scores:
        if score.data:
            score.data = [s for s in score.data if s.get('name') != name]
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(score, 'data')
    db.session.commit()
    return jsonify({'success': True, 'message': 'Deleted ' + name})

@app.route('/api/admin/competition/<int:comp_id>/matches')
def api_comp_matches(comp_id):
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    competitors = Competitor.query.filter_by(competition_id=comp_id).all()
    matches = set(c.match for c in competitors if c.match)
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
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json()
    old_name = data.get('old_name', '').strip()
    new_name = data.get('new_name', '').strip()
    if not old_name or not new_name:
        return jsonify({'error': 'Both names required'}), 400
    competitors = Competitor.query.filter_by(competition_id=comp_id, match=old_name).all()
    for c in competitors:
        c.match = new_name
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
    return jsonify({'success': True, 'message': 'Renamed match'})

@app.route('/api/admin/competition/<int:comp_id>/scores')
def api_comp_scores(comp_id):
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    latest = Score.query.filter_by(competition_id=comp_id).order_by(Score.created_at.desc()).first()
    if not latest or not latest.data:
        return jsonify([])
    return jsonify(latest.data)

@app.route('/api/admin/competition/<int:comp_id>/score/add', methods=['POST'])
def api_add_score(comp_id):
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json()
    shooter_name = data.get('name', '').strip()
    match_name = data.get('match', '').strip()
    shots = data.get('shots', '').strip()
    if not shooter_name or not match_name:
        return jsonify({'error': 'Name and match required'}), 400
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
    latest = Score.query.filter_by(competition_id=comp_id).order_by(Score.created_at.desc()).first()
    if not latest:
        latest = Score(competition_id=comp_id, data=[])
        db.session.add(latest)
    shooter_data = None
    for s in latest.data:
        if s.get('name') == shooter_name:
            shooter_data = s
            break
    if not shooter_data:
        shooter_data = {'name': shooter_name, 'class': '', 'matches': [], 'total': 0, 'vCount': 0}
        latest.data.append(shooter_data)
    match_data = None
    for m in shooter_data.get('matches', []):
        if m.get('match') == match_name:
            match_data = m
            break
    if match_data:
        old_score = match_data.get('score', 0)
        old_x = match_data.get('xCount', 0)
        match_data['shots'] = shots
        match_data['score'] = score
        match_data['xCount'] = x_count
        shooter_data['total'] = shooter_data.get('total', 0) - old_score + score
        shooter_data['vCount'] = shooter_data.get('vCount', 0) - old_x + x_count
    else:
        if 'matches' not in shooter_data:
            shooter_data['matches'] = []
        shooter_data['matches'].append({'match': match_name, 'shots': shots, 'score': score, 'xCount': x_count})
        shooter_data['total'] = shooter_data.get('total', 0) + score
        shooter_data['vCount'] = shooter_data.get('vCount', 0) + x_count
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(latest, 'data')
    db.session.commit()
    return jsonify({'success': True, 'message': 'Added score'})

@app.route('/api/admin/competition/<int:comp_id>/score/delete', methods=['POST'])
def api_delete_score(comp_id):
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
                old_matches = shooter.get('matches', [])
                for m in old_matches:
                    if m.get('match') == match_name:
                        shooter['total'] = shooter.get('total', 0) - m.get('score', 0)
                        shooter['vCount'] = shooter.get('vCount', 0) - m.get('xCount', 0)
                shooter['matches'] = [m for m in old_matches if m.get('match') != match_name]
            else:
                latest.data = [s for s in latest.data if s.get('name') != shooter_name]
            break
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(latest, 'data')
    db.session.commit()
    return jsonify({'success': True, 'message': 'Deleted score'})

@app.route('/api/admin/competition/<int:comp_id>/clear-scores', methods=['POST'])
def api_clear_scores(comp_id):
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    Score.query.filter_by(competition_id=comp_id).delete()
    db.session.commit()
    return jsonify({'success': True, 'message': 'All scores cleared'})

@app.route('/api/admin/competition/<int:comp_id>/clear-competitors', methods=['POST'])
def api_clear_competitors(comp_id):
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    Competitor.query.filter_by(competition_id=comp_id).delete()
    db.session.commit()
    return jsonify({'success': True, 'message': 'All competitors cleared'})

COMP_ADMIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Admin - {{ competition.name }}</title>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&family=Barlow+Condensed:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root { --bg:#0c1e2b; --bg2:#122a3a; --bg3:#1a3a4a; --gold:#f4c566; --green:#5cc9a7; --blue:#54b8db; --red:#e85a5a; --text:#f0ece4; --text2:#8ab4c8; --border:#1e3d50; }
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--bg); color:var(--text); font-family:Barlow Condensed,sans-serif; min-height:100vh; }
.container { max-width:1200px; margin:0 auto; padding:20px; }
.header { display:flex; justify-content:space-between; align-items:center; padding:20px 0; border-bottom:1px solid var(--border); margin-bottom:20px; }
.header h1 { font-family:Oswald,sans-serif; font-size:1.6rem; color:var(--gold); }
.nav-links { display:flex; gap:12px; }
.nav-link { color:var(--gold); text-decoration:none; border:1px solid var(--gold); padding:8px 16px; border-radius:4px; font-size:0.9rem; }
.nav-link:hover { background:var(--gold); color:var(--bg); }
.tabs { display:flex; gap:4px; margin-bottom:20px; border-bottom:2px solid var(--border); }
.tab { padding:12px 24px; background:transparent; border:none; color:var(--text2); font-family:Oswald,sans-serif; font-size:1rem; cursor:pointer; border-bottom:2px solid transparent; margin-bottom:-2px; }
.tab:hover { color:var(--text); }
.tab.active { color:var(--gold); border-bottom-color:var(--gold); }
.tab-content { display:none; }
.tab-content.active { display:block; }
.action-bar { display:flex; gap:12px; margin-bottom:16px; flex-wrap:wrap; align-items:center; }
.action-btn { padding:8px 16px; border:1px solid var(--border); background:var(--bg2); color:var(--text); border-radius:4px; cursor:pointer; font-size:0.9rem; }
.action-btn:hover { border-color:var(--gold); color:var(--gold); }
.action-btn.primary { background:var(--gold); color:var(--bg); border-color:var(--gold); }
.action-btn.danger { background:var(--red); color:var(--text); border-color:var(--red); }
.search-input { padding:8px 12px; background:var(--bg); border:1px solid var(--border); border-radius:4px; color:var(--text); width:200px; }
.search-input:focus { outline:none; border-color:var(--gold); }
table { width:100%; border-collapse:collapse; }
th, td { padding:10px 12px; text-align:left; border-bottom:1px solid var(--border); }
th { background:var(--bg2); color:var(--gold); font-family:Oswald,sans-serif; font-size:0.9rem; }
tr:hover { background:var(--bg3); }
.edit-btn { padding:4px 10px; background:var(--blue); color:var(--bg); border:none; border-radius:3px; cursor:pointer; font-size:0.8rem; margin-right:4px; }
.delete-btn { padding:4px 10px; background:var(--red); color:var(--text); border:none; border-radius:3px; cursor:pointer; font-size:0.8rem; }
.edit-btn:hover, .delete-btn:hover { opacity:0.8; }
.form-row { display:flex; gap:12px; margin-bottom:12px; flex-wrap:wrap; }
.form-group { display:flex; flex-direction:column; gap:4px; }
.form-group label { font-size:0.8rem; color:var(--text2); text-transform:uppercase; }
.form-group input, .form-group select { padding:8px 12px; background:var(--bg); border:1px solid var(--border); border-radius:4px; color:var(--text); font-size:0.9rem; }
.form-group input:focus, .form-group select:focus { outline:none; border-color:var(--gold); }
.modal { display:none; position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,0.8); z-index:1000; align-items:center; justify-content:center; }
.modal.active { display:flex; }
.modal-content { background:var(--bg2); border:1px solid var(--border); border-radius:8px; padding:24px; min-width:400px; max-width:90%; }
.modal-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; }
.modal-header h2 { font-family:Oswald,sans-serif; color:var(--gold); }
.modal-close { background:none; border:none; color:var(--text2); font-size:1.5rem; cursor:pointer; }
.message { padding:12px 16px; border-radius:4px; margin-bottom:16px; font-family:JetBrains Mono,monospace; font-size:0.85rem; }
.message.success { background:rgba(92,201,167,0.2); border:1px solid var(--green); color:var(--green); }
.message.error { background:rgba(232,90,90,0.2); border:1px solid var(--red); color:var(--red); }
.match-card { background:var(--bg2); border:1px solid var(--border); border-radius:4px; padding:12px 16px; margin-bottom:8px; }
.match-card input { background:transparent; border:none; color:var(--text); font-family:Oswald,sans-serif; font-size:1.1rem; width:100%; }
.match-card input:focus { outline:none; border-bottom:1px solid var(--gold); }
.shot-badges { display:flex; flex-wrap:wrap; gap:2px; }
.shot-badge { display:inline-flex; align-items:center; justify-content:center; min-width:20px; height:18px; padding:0 4px; border-radius:2px; font-family:JetBrains Mono,monospace; font-size:0.7rem; font-weight:600; }
.shot-badge.score-X { background:#f4c566; color:#0c1e2b; }
.shot-badge.score-V { background:#5cc9a7; color:#0c1e2b; }
.shot-badge.score-6 { background:#54b8db; color:#0c1e2b; }
.shot-badge.score-5 { background:#8ab4c8; color:#0c1e2b; }
.shot-badge.score-4 { background:#d4cdb8; color:#0c1e2b; }
.shot-badge.score-low { background:#e85a5a; color:#0c1e2b; }
.danger-zone { margin-top:40px; padding:20px; border:1px solid var(--red); border-radius:8px; background:rgba(232,90,90,0.1); }
.danger-zone h3 { color:var(--red); margin-bottom:16px; font-family:Oswald,sans-serif; }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>Admin: {{ competition.name }}</h1>
    <div class="nav-links">
      <a href="/{{ competition.route }}" class="nav-link">View Scoreboard</a>
      <a href="/admin/dashboard" class="nav-link">Dashboard</a>
    </div>
  </div>
  <div id="message"></div>
  <div class="tabs">
    <button class="tab active" id="tab-shooters">Shooters</button>
    <button class="tab" id="tab-scores">Scores</button>
    <button class="tab" id="tab-matches">Matches</button>
    <button class="tab" id="tab-settings">Settings</button>
  </div>
  <div id="shooters-tab" class="tab-content active">
    <div class="action-bar">
      <button class="action-btn primary" id="btn-add-shooter">+ Add Shooter</button>
      <input type="text" class="search-input" id="search-shooters" placeholder="Search shooters...">
    </div>
    <table><thead><tr><th>Name</th><th>Class</th><th>Actions</th></tr></thead><tbody id="shooters-body"></tbody></table>
  </div>
  <div id="scores-tab" class="tab-content">
    <div class="action-bar">
      <button class="action-btn primary" id="btn-add-score">+ Add Score</button>
      <input type="text" class="search-input" id="search-scores" placeholder="Search scores...">
    </div>
    <table><thead><tr><th>Shooter</th><th>Match</th><th>Shots</th><th>Score</th><th>Actions</th></tr></thead><tbody id="scores-body"></tbody></table>
  </div>
  <div id="matches-tab" class="tab-content">
    <p style="color:var(--text2); margin-bottom:16px;">Edit match names - changes apply to squadding and scores.</p>
    <div id="matches-list"></div>
  </div>
  <div id="settings-tab" class="tab-content">
    <div class="danger-zone">
      <h3>Danger Zone</h3>
      <p style="color:var(--text2); margin-bottom:16px;">These actions cannot be undone.</p>
      <div class="action-bar">
        <button class="action-btn danger" id="btn-clear-scores">Clear All Scores</button>
        <button class="action-btn danger" id="btn-clear-competitors">Clear All Competitors</button>
      </div>
    </div>
  </div>
</div>
<div class="modal" id="modal-add-shooter">
  <div class="modal-content">
    <div class="modal-header"><h2>Add Shooter</h2><button class="modal-close" data-close="modal-add-shooter">x</button></div>
    <div class="form-row">
      <div class="form-group"><label>Name</label><input type="text" id="new-shooter-name" style="width:250px;"></div>
      <div class="form-group"><label>Class</label><select id="new-shooter-class"><option value="F-Open">F-Open</option><option value="FTR">FTR</option><option value="">Other</option></select></div>
    </div>
    <div class="form-row" style="margin-top:20px;"><button class="action-btn primary" id="btn-save-shooter">Add Shooter</button></div>
  </div>
</div>
<div class="modal" id="modal-edit-shooter">
  <div class="modal-content">
    <div class="modal-header"><h2>Edit Shooter</h2><button class="modal-close" data-close="modal-edit-shooter">x</button></div>
    <input type="hidden" id="edit-shooter-old-name">
    <div class="form-row">
      <div class="form-group"><label>Name</label><input type="text" id="edit-shooter-name" style="width:250px;"></div>
      <div class="form-group"><label>Class</label><select id="edit-shooter-class"><option value="F-Open">F-Open</option><option value="FTR">FTR</option><option value="">Other</option></select></div>
    </div>
    <div class="form-row" style="margin-top:20px;"><button class="action-btn primary" id="btn-update-shooter">Save Changes</button></div>
  </div>
</div>
<div class="modal" id="modal-add-score">
  <div class="modal-content">
    <div class="modal-header"><h2>Add Score</h2><button class="modal-close" data-close="modal-add-score">x</button></div>
    <div class="form-row">
      <div class="form-group"><label>Shooter</label><select id="score-shooter" style="width:200px;"></select></div>
      <div class="form-group"><label>Match</label><select id="score-match" style="width:200px;"></select></div>
    </div>
    <div class="form-row">
      <div class="form-group"><label>Shots (comma separated)</label><input type="text" id="score-shots" style="width:400px;" placeholder="X,6,5,V,6,6,5,6,X,6"></div>
    </div>
    <div class="form-row" style="margin-top:20px;"><button class="action-btn primary" id="btn-save-score">Add Score</button></div>
  </div>
</div>
<script>
var COMP_ID = {{ competition.id }};
var shooters = [];
var scores = [];
var matches = [];
var currentEditName = '';

document.querySelectorAll('.tab').forEach(function(tab) {
  tab.addEventListener('click', function() {
    document.querySelectorAll('.tab').forEach(function(t) { t.classList.remove('active'); });
    document.querySelectorAll('.tab-content').forEach(function(t) { t.classList.remove('active'); });
    tab.classList.add('active');
    document.getElementById(tab.id.replace('tab-', '') + '-tab').classList.add('active');
  });
});

document.querySelectorAll('.modal-close').forEach(function(btn) {
  btn.addEventListener('click', function() {
    document.getElementById(btn.dataset.close).classList.remove('active');
  });
});

document.getElementById('btn-add-shooter').addEventListener('click', function() {
  document.getElementById('new-shooter-name').value = '';
  document.getElementById('modal-add-shooter').classList.add('active');
});

document.getElementById('btn-add-score').addEventListener('click', function() {
  var sel = document.getElementById('score-shooter');
  sel.innerHTML = shooters.map(function(s) { return '<option value="' + s.name + '">' + s.name + '</option>'; }).join('');
  var msel = document.getElementById('score-match');
  msel.innerHTML = matches.map(function(m) { return '<option value="' + m + '">' + m + '</option>'; }).join('');
  document.getElementById('score-shots').value = '';
  document.getElementById('modal-add-score').classList.add('active');
});

document.getElementById('btn-save-shooter').addEventListener('click', addShooter);
document.getElementById('btn-update-shooter').addEventListener('click', updateShooter);
document.getElementById('btn-save-score').addEventListener('click', addScore);
document.getElementById('btn-clear-scores').addEventListener('click', clearScores);
document.getElementById('btn-clear-competitors').addEventListener('click', clearCompetitors);

document.getElementById('search-shooters').addEventListener('input', function() { renderShooters(this.value); });
document.getElementById('search-scores').addEventListener('input', function() { renderScores(this.value); });

function showMessage(msg, isError) {
  var el = document.getElementById('message');
  el.innerHTML = msg;
  el.className = 'message ' + (isError ? 'error' : 'success');
  setTimeout(function() { el.innerHTML = ''; }, 5000);
}

function loadShooters() {
  fetch('/api/admin/competition/' + COMP_ID + '/shooters')
    .then(function(r) { return r.json(); })
    .then(function(data) { shooters = data; renderShooters(); });
}

function loadScores() {
  fetch('/api/admin/competition/' + COMP_ID + '/scores')
    .then(function(r) { return r.json(); })
    .then(function(data) { scores = data; renderScores(); });
}

function loadMatches() {
  fetch('/api/admin/competition/' + COMP_ID + '/matches')
    .then(function(r) { return r.json(); })
    .then(function(data) { matches = data; renderMatches(); });
}

function renderShooters(filter) {
  filter = (filter || '').toLowerCase();
  var tbody = document.getElementById('shooters-body');
  var filtered = shooters.filter(function(s) { return s.name.toLowerCase().indexOf(filter) >= 0; });
  var html = '';
  filtered.forEach(function(s) {
    html += '<tr>';
    html += '<td>' + s.name + '</td>';
    html += '<td>' + (s.class || '-') + '</td>';
    html += '<td>';
    html += '<button class="edit-btn" data-name="' + s.name + '" data-class="' + (s.class || '') + '">Edit</button>';
    html += '<button class="delete-btn" data-name="' + s.name + '">Delete</button>';
    html += '</td></tr>';
  });
  tbody.innerHTML = html;
  tbody.querySelectorAll('.edit-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      document.getElementById('edit-shooter-old-name').value = btn.dataset.name;
      document.getElementById('edit-shooter-name').value = btn.dataset.name;
      document.getElementById('edit-shooter-class').value = btn.dataset.class;
      document.getElementById('modal-edit-shooter').classList.add('active');
    });
  });
  tbody.querySelectorAll('.delete-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      if (confirm('Delete ' + btn.dataset.name + '?')) deleteShooter(btn.dataset.name);
    });
  });
}

function renderScores(filter) {
  filter = (filter || '').toLowerCase();
  var tbody = document.getElementById('scores-body');
  var html = '';
  scores.forEach(function(shooter) {
    if (filter && shooter.name.toLowerCase().indexOf(filter) < 0) return;
    (shooter.matches || []).forEach(function(m) {
      var shots = (m.shots || '').split(',').map(function(s) {
        var sc = s.trim().toUpperCase();
        var cls = (sc === 'X' || sc === 'V' || sc === '6' || sc === '5' || sc === '4') ? 'score-' + sc : 'score-low';
        return '<span class="shot-badge ' + cls + '">' + sc + '</span>';
      }).join('');
      html += '<tr>';
      html += '<td>' + shooter.name + '</td>';
      html += '<td>' + m.match + '</td>';
      html += '<td><div class="shot-badges">' + shots + '</div></td>';
      html += '<td>' + m.score + '.' + m.xCount + '</td>';
      html += '<td><button class="delete-btn" data-name="' + shooter.name + '" data-match="' + m.match + '">Delete</button></td>';
      html += '</tr>';
    });
  });
  tbody.innerHTML = html;
  tbody.querySelectorAll('.delete-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      if (confirm('Delete score?')) deleteScore(btn.dataset.name, btn.dataset.match);
    });
  });
}

function renderMatches() {
  var container = document.getElementById('matches-list');
  var html = '';
  matches.forEach(function(m) {
    html += '<div class="match-card"><input type="text" value="' + m + '" data-original="' + m + '"></div>';
  });
  container.innerHTML = html;
  container.querySelectorAll('input').forEach(function(inp) {
    inp.addEventListener('change', function() {
      if (inp.value !== inp.dataset.original) renameMatch(inp.dataset.original, inp.value);
    });
  });
}

function addShooter() {
  var name = document.getElementById('new-shooter-name').value.trim();
  var cls = document.getElementById('new-shooter-class').value;
  if (!name) { showMessage('Name required', true); return; }
  fetch('/api/admin/competition/' + COMP_ID + '/shooter', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ name: name, class: cls })
  }).then(function(r) { return r.json(); }).then(function(result) {
    if (result.success) { showMessage(result.message); document.getElementById('modal-add-shooter').classList.remove('active'); loadShooters(); }
    else showMessage(result.error, true);
  });
}

function updateShooter() {
  var oldName = document.getElementById('edit-shooter-old-name').value;
  var newName = document.getElementById('edit-shooter-name').value.trim();
  var newClass = document.getElementById('edit-shooter-class').value;
  fetch('/api/admin/competition/' + COMP_ID + '/shooter/update', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ old_name: oldName, new_name: newName, new_class: newClass })
  }).then(function(r) { return r.json(); }).then(function(result) {
    if (result.success) { showMessage(result.message); document.getElementById('modal-edit-shooter').classList.remove('active'); loadShooters(); loadScores(); }
    else showMessage(result.error, true);
  });
}

function deleteShooter(name) {
  fetch('/api/admin/competition/' + COMP_ID + '/shooter/delete', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ name: name })
  }).then(function(r) { return r.json(); }).then(function(result) {
    if (result.success) { showMessage(result.message); loadShooters(); loadScores(); }
    else showMessage(result.error, true);
  });
}

function addScore() {
  var name = document.getElementById('score-shooter').value;
  var match = document.getElementById('score-match').value;
  var shots = document.getElementById('score-shots').value.trim();
  if (!name || !match || !shots) { showMessage('All fields required', true); return; }
  fetch('/api/admin/competition/' + COMP_ID + '/score/add', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ name: name, match: match, shots: shots })
  }).then(function(r) { return r.json(); }).then(function(result) {
    if (result.success) { showMessage(result.message); document.getElementById('modal-add-score').classList.remove('active'); loadScores(); }
    else showMessage(result.error, true);
  });
}

function deleteScore(name, match) {
  fetch('/api/admin/competition/' + COMP_ID + '/score/delete', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ name: name, match: match })
  }).then(function(r) { return r.json(); }).then(function(result) {
    if (result.success) { showMessage(result.message); loadScores(); }
    else showMessage(result.error, true);
  });
}

function renameMatch(oldName, newName) {
  fetch('/api/admin/competition/' + COMP_ID + '/match/rename', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ old_name: oldName, new_name: newName })
  }).then(function(r) { return r.json(); }).then(function(result) {
    if (result.success) { showMessage(result.message); loadMatches(); }
    else showMessage(result.error, true);
  });
}

function clearScores() {
  if (!confirm('Are you sure you want to delete ALL scores? This cannot be undone.')) return;
  fetch('/api/admin/competition/' + COMP_ID + '/clear-scores', { method: 'POST' })
    .then(function(r) { return r.json(); }).then(function(result) {
      if (result.success) { showMessage(result.message); loadScores(); }
      else showMessage(result.error, true);
    });
}

function clearCompetitors() {
  if (!confirm('Are you sure you want to delete ALL competitors? This cannot be undone.')) return;
  fetch('/api/admin/competition/' + COMP_ID + '/clear-competitors', { method: 'POST' })
    .then(function(r) { return r.json(); }).then(function(result) {
      if (result.success) { showMessage(result.message); loadShooters(); }
      else showMessage(result.error, true);
    });
}

loadShooters();
loadScores();
loadMatches();
</script>
</body>
</html>
"""
