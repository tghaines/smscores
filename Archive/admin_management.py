
# ══════════════════════════════════════════════
#  ADMIN MANAGEMENT - Ranges & Competitions
# ══════════════════════════════════════════════

import secrets

ADMIN_MANAGE_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SM Scores Admin - Manage</title>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=Barlow+Condensed:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root { --bg:#0c1e2b; --bg2:#122a3a; --gold:#f4c566; --blue:#54b8db; --green:#5cc9a7; --red:#e74c3c; --text:#f0ece4; --text2:#8ab4c8; --border:#1e3d50; }
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--bg); color:var(--text); font-family:"Barlow Condensed",sans-serif; min-height:100vh; padding:20px; }
.container { max-width:1000px; margin:0 auto; }
h1 { font-family:"Oswald",sans-serif; color:var(--gold); margin-bottom:20px; font-size:2rem; }
h2 { font-family:"Oswald",sans-serif; color:var(--gold); font-size:1.3rem; margin-bottom:15px; }
.nav { margin-bottom:20px; }
.nav a { color:var(--gold); text-decoration:none; margin-right:20px; }
.nav a:hover { text-decoration:underline; }
.grid { display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-bottom:20px; }
@media (max-width: 768px) { .grid { grid-template-columns:1fr; } }
.card { background:var(--bg2); border:1px solid var(--border); border-radius:8px; padding:20px; }
.form-group { margin-bottom:15px; }
.form-group label { display:block; color:var(--text2); margin-bottom:5px; font-size:0.9rem; }
.form-group input, .form-group select { width:100%; padding:10px; background:var(--bg); border:1px solid var(--border); border-radius:4px; color:var(--text); font-size:1rem; }
.form-group input:focus, .form-group select:focus { outline:none; border-color:var(--gold); }
.btn { padding:10px 20px; border:none; border-radius:4px; cursor:pointer; font-family:"Oswald",sans-serif; font-size:1rem; margin-right:10px; margin-top:10px; }
.btn-primary { background:var(--gold); color:var(--bg); }
.btn-danger { background:var(--red); color:white; }
.btn-small { padding:5px 10px; font-size:0.85rem; }
.btn:hover { opacity:0.9; }
table { width:100%; border-collapse:collapse; margin-top:15px; }
th, td { padding:10px; text-align:left; border-bottom:1px solid var(--border); }
th { color:var(--gold); font-family:"Oswald",sans-serif; }
.api-key { font-family:monospace; font-size:0.75rem; color:var(--text2); word-break:break-all; }
.flash { padding:15px; border-radius:4px; margin-bottom:20px; }
.flash-success { background:rgba(92,201,167,0.2); border:1px solid var(--green); color:var(--green); }
.flash-error { background:rgba(231,76,60,0.2); border:1px solid var(--red); color:var(--red); }
.confirm-delete { display:none; background:rgba(0,0,0,0.8); position:fixed; top:0; left:0; right:0; bottom:0; justify-content:center; align-items:center; z-index:1000; }
.confirm-box { background:var(--bg2); padding:30px; border-radius:8px; border:1px solid var(--border); text-align:center; }
.confirm-box p { margin-bottom:20px; }
</style>
</head>
<body>
<div class="container">
  <div class="nav">
    <a href="/admin/dashboard">← Dashboard</a>
    <a href="/">Home</a>
  </div>
  
  <h1>🔧 Manage Ranges & Competitions</h1>
  
  {% if flash_message %}
  <div class="flash flash-{{ flash_type }}">{{ flash_message }}</div>
  {% endif %}
  
  <div class="grid">
    <!-- Create Range -->
    <div class="card">
      <h2>➕ Create New Range</h2>
      <form method="POST" action="/admin/manage/range/create">
        <div class="form-group">
          <label>Range ID (short code, e.g., BCRC)</label>
          <input type="text" name="range_id" required pattern="[A-Za-z0-9_-]+" placeholder="ANZAC">
        </div>
        <div class="form-group">
          <label>Range Name</label>
          <input type="text" name="range_name" required placeholder="ANZAC Rifle Range">
        </div>
        <button type="submit" class="btn btn-primary">Create Range</button>
      </form>
    </div>
    
    <!-- Create Competition -->
    <div class="card">
      <h2>➕ Create New Competition</h2>
      <form method="POST" action="/admin/manage/comp/create">
        <div class="form-group">
          <label>Range</label>
          <select name="range_id" required>
            <option value="">-- Select Range --</option>
            {% for r in ranges %}
            <option value="{{ r.id }}">{{ r.name }}</option>
            {% endfor %}
          </select>
        </div>
        <div class="form-group">
          <label>Competition Route (URL path, e.g., CoastalCup)</label>
          <input type="text" name="comp_route" required pattern="[A-Za-z0-9_-]+" placeholder="CoastalCup">
        </div>
        <div class="form-group">
          <label>Competition Name</label>
          <input type="text" name="comp_name" required placeholder="The Coastal Cup 2026">
        </div>
        <button type="submit" class="btn btn-primary">Create Competition</button>
      </form>
    </div>
  </div>
  
  <!-- Existing Ranges -->
  <div class="card">
    <h2>📍 Existing Ranges</h2>
    <table>
      <tr><th>ID</th><th>Name</th><th>API Key</th><th>Actions</th></tr>
      {% for r in ranges %}
      <tr>
        <td>{{ r.id }}</td>
        <td>{{ r.name }}</td>
        <td class="api-key">{{ r.api_key }}</td>
        <td>
          <button class="btn btn-danger btn-small" onclick="confirmDelete('range', '{{ r.id }}', '{{ r.name }}')">Delete</button>
        </td>
      </tr>
      {% endfor %}
      {% if not ranges %}
      <tr><td colspan="4">No ranges yet</td></tr>
      {% endif %}
    </table>
  </div>
  
  <!-- Existing Competitions -->
  <div class="card" style="margin-top:20px;">
    <h2>🏆 Existing Competitions</h2>
    <table>
      <tr><th>Route</th><th>Name</th><th>Range</th><th>Actions</th></tr>
      {% for c in competitions %}
      <tr>
        <td>/{{ c.route }}</td>
        <td>{{ c.name }}</td>
        <td>{{ c.range_id }}</td>
        <td>
          <a href="/{{ c.route }}" class="btn btn-primary btn-small" target="_blank">View</a>
          <button class="btn btn-danger btn-small" onclick="confirmDelete('comp', '{{ c.id }}', '{{ c.name }}')">Delete</button>
        </td>
      </tr>
      {% endfor %}
      {% if not competitions %}
      <tr><td colspan="4">No competitions yet</td></tr>
      {% endif %}
    </table>
  </div>
</div>

<!-- Delete Confirmation Modal -->
<div class="confirm-delete" id="confirmModal">
  <div class="confirm-box">
    <p>Are you sure you want to delete <strong id="deleteName"></strong>?</p>
    <p style="color:var(--red); font-size:0.9rem;">This cannot be undone!</p>
    <form method="POST" id="deleteForm">
      <button type="submit" class="btn btn-danger">Yes, Delete</button>
      <button type="button" class="btn btn-primary" onclick="closeModal()">Cancel</button>
    </form>
  </div>
</div>

<script>
function confirmDelete(type, id, name) {
  document.getElementById('deleteName').textContent = name;
  document.getElementById('deleteForm').action = '/admin/manage/' + type + '/delete/' + id;
  document.getElementById('confirmModal').style.display = 'flex';
}
function closeModal() {
  document.getElementById('confirmModal').style.display = 'none';
}
</script>
</body>
</html>
'''

@app.route('/admin/manage')
def admin_manage():
    if not session.get('admin'):
        return redirect('/admin')
    
    ranges = Range.query.all()
    competitions = Competition.query.all()
    
    flash_message = request.args.get('msg')
    flash_type = request.args.get('type', 'success')
    
    return render_template_string(ADMIN_MANAGE_HTML,
        ranges=ranges,
        competitions=competitions,
        flash_message=flash_message,
        flash_type=flash_type
    )

@app.route('/admin/manage/range/create', methods=['POST'])
def admin_create_range():
    if not session.get('admin'):
        return redirect('/admin')
    
    range_id = request.form.get('range_id', '').strip()
    range_name = request.form.get('range_name', '').strip()
    
    if not range_id or not range_name:
        return redirect('/admin/manage?msg=Range ID and name are required&type=error')
    
    # Check if exists
    if Range.query.get(range_id):
        return redirect(f'/admin/manage?msg=Range {range_id} already exists&type=error')
    
    # Generate API key
    api_key = secrets.token_hex(32)
    
    new_range = Range(id=range_id, name=range_name, api_key=api_key)
    db.session.add(new_range)
    db.session.commit()
    
    log_activity(f'Range created: {range_name} ({range_id})', 'info')
    return redirect(f'/admin/manage?msg=Range {range_name} created successfully&type=success')

@app.route('/admin/manage/range/delete/<range_id>', methods=['POST'])
def admin_delete_range(range_id):
    if not session.get('admin'):
        return redirect('/admin')
    
    range_obj = Range.query.get(range_id)
    if not range_obj:
        return redirect('/admin/manage?msg=Range not found&type=error')
    
    range_name = range_obj.name
    
    # Delete associated competitions, shotlogs, etc.
    for comp in Competition.query.filter_by(range_id=range_id).all():
        Score.query.filter_by(competition_id=comp.id).delete()
        Competitor.query.filter_by(competition_id=comp.id).delete()
        db.session.delete(comp)
    
    for shotlog in Shotlog.query.filter_by(range_id=range_id).all():
        ShotlogString.query.filter_by(shotlog_id=shotlog.id).delete()
        db.session.delete(shotlog)
    
    db.session.delete(range_obj)
    db.session.commit()
    
    log_activity(f'Range deleted: {range_name} ({range_id})', 'warn')
    return redirect(f'/admin/manage?msg=Range {range_name} deleted&type=success')

@app.route('/admin/manage/comp/create', methods=['POST'])
def admin_create_comp():
    if not session.get('admin'):
        return redirect('/admin')
    
    range_id = request.form.get('range_id', '').strip()
    comp_route = request.form.get('comp_route', '').strip()
    comp_name = request.form.get('comp_name', '').strip()
    
    if not range_id or not comp_route or not comp_name:
        return redirect('/admin/manage?msg=All fields are required&type=error')
    
    # Check range exists
    if not Range.query.get(range_id):
        return redirect('/admin/manage?msg=Range not found&type=error')
    
    # Check if route exists
    if Competition.query.filter_by(route=comp_route).first():
        return redirect(f'/admin/manage?msg=Competition route {comp_route} already exists&type=error')
    
    new_comp = Competition(range_id=range_id, route=comp_route, name=comp_name)
    db.session.add(new_comp)
    db.session.commit()
    
    log_activity(f'Competition created: {comp_name} (/{comp_route})', 'info')
    return redirect(f'/admin/manage?msg=Competition {comp_name} created successfully&type=success')

@app.route('/admin/manage/comp/delete/<int:comp_id>', methods=['POST'])
def admin_delete_comp(comp_id):
    if not session.get('admin'):
        return redirect('/admin')
    
    comp = Competition.query.get(comp_id)
    if not comp:
        return redirect('/admin/manage?msg=Competition not found&type=error')
    
    comp_name = comp.name
    
    # Delete associated data
    Score.query.filter_by(competition_id=comp.id).delete()
    Competitor.query.filter_by(competition_id=comp.id).delete()
    db.session.delete(comp)
    db.session.commit()
    
    log_activity(f'Competition deleted: {comp_name}', 'warn')
    return redirect(f'/admin/manage?msg=Competition {comp_name} deleted&type=success')
