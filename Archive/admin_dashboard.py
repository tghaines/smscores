
# ══════════════════════════════════════════════
#  ADMIN DASHBOARD (Password Protected)
# ══════════════════════════════════════════════
ADMIN_PASSWORD = 'Gregory'

ADMIN_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SM Scores Admin</title>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=Barlow+Condensed:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root { --bg:#0c1e2b; --bg2:#122a3a; --bg3:#1a3344; --gold:#f4c566; --blue:#54b8db; --green:#5cc9a7; --red:#e74c3c; --text:#f0ece4; --text2:#8ab4c8; --border:#1e3d50; }
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--bg); color:var(--text); font-family:"Barlow Condensed",sans-serif; min-height:100vh; padding:20px; }
.container { max-width:1200px; margin:0 auto; }
h1 { font-family:"Oswald",sans-serif; color:var(--gold); margin-bottom:20px; font-size:2rem; }
h2 { font-family:"Oswald",sans-serif; color:var(--gold); font-size:1.3rem; margin-bottom:15px; border-bottom:1px solid var(--border); padding-bottom:8px; }
.grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(350px, 1fr)); gap:20px; margin-bottom:20px; }
.card { background:var(--bg2); border:1px solid var(--border); border-radius:8px; padding:20px; }
.status-row { display:flex; justify-content:space-between; padding:10px 0; border-bottom:1px solid var(--border); }
.status-row:last-child { border-bottom:none; }
.status-label { color:var(--text2); }
.status-value { font-weight:600; }
.status-ok { color:var(--green); }
.status-warn { color:var(--gold); }
.status-error { color:var(--red); }
.log-box { background:var(--bg); border:1px solid var(--border); border-radius:4px; padding:12px; font-family:monospace; font-size:0.8rem; max-height:300px; overflow-y:auto; }
.log-entry { padding:4px 0; border-bottom:1px solid var(--border); }
.log-entry:last-child { border-bottom:none; }
.log-time { color:var(--text2); margin-right:10px; }
.log-msg { color:var(--text); }
.log-push { color:var(--green); }
.log-error { color:var(--red); }
.log-warn { color:var(--gold); }
.refresh-btn { background:var(--blue); color:var(--bg); border:none; padding:8px 16px; border-radius:4px; cursor:pointer; font-family:"Oswald",sans-serif; margin-bottom:20px; }
.refresh-btn:hover { opacity:0.9; }
.stat-big { font-size:2.5rem; font-family:"Oswald",sans-serif; color:var(--gold); }
.stat-label { color:var(--text2); font-size:0.9rem; }
table { width:100%; border-collapse:collapse; }
th, td { padding:8px 12px; text-align:left; border-bottom:1px solid var(--border); }
th { color:var(--gold); font-family:"Oswald",sans-serif; }
.back-link { color:var(--gold); text-decoration:none; display:inline-block; margin-bottom:20px; }
</style>
</head>
<body>
<div class="container">
  <a href="/" class="back-link">← Back to Home</a>
  <h1>🔧 SM Scores Admin Dashboard</h1>
  <button class="refresh-btn" onclick="location.reload()">↻ Refresh</button>
  <a href="/admin/logout" class="refresh-btn" style="background:var(--red); margin-left:10px; text-decoration:none;">Logout</a>
  
  <div class="grid">
    <div class="card">
      <h2>System Status</h2>
      <div class="status-row"><span class="status-label">Server</span><span class="status-value status-ok">● Online</span></div>
      <div class="status-row"><span class="status-label">Database</span><span class="status-value status-ok">● Connected</span></div>
      <div class="status-row"><span class="status-label">Last Score Push</span><span class="status-value">{{ last_score_time or "Never" }}</span></div>
      <div class="status-row"><span class="status-label">Last Shotlog Push</span><span class="status-value">{{ last_shotlog_time or "Never" }}</span></div>
    </div>
    
    <div class="card">
      <h2>Database Stats</h2>
      <div class="status-row"><span class="status-label">Competitions</span><span class="status-value">{{ comp_count }}</span></div>
      <div class="status-row"><span class="status-label">Ranges</span><span class="status-value">{{ range_count }}</span></div>
      <div class="status-row"><span class="status-label">Shotlogs</span><span class="status-value">{{ shotlog_count }}</span></div>
      <div class="status-row"><span class="status-label">Competitors</span><span class="status-value">{{ competitor_count }}</span></div>
    </div>
  </div>
  
  <div class="grid">
    <div class="card">
      <h2>Recent Activity</h2>
      <div class="log-box">
        {% for log in activity_logs %}
        <div class="log-entry">
          <span class="log-time">{{ log.time }}</span>
          <span class="log-msg {% if log.type == 'push' %}log-push{% elif log.type == 'error' %}log-error{% elif log.type == 'warn' %}log-warn{% endif %}">{{ log.message }}</span>
        </div>
        {% endfor %}
        {% if not activity_logs %}
        <div class="log-entry"><span class="log-msg">No recent activity</span></div>
        {% endif %}
      </div>
    </div>
    
    <div class="card">
      <h2>Competitions</h2>
      <table>
        <tr><th>Name</th><th>Route</th><th>Scores</th></tr>
        {% for comp in competitions %}
        <tr><td>{{ comp.name }}</td><td>/{{ comp.route }}</td><td>{{ comp.score_count }}</td></tr>
        {% endfor %}
      </table>
    </div>
  </div>
  
  <div class="card">
    <h2>Ranges</h2>
    <table>
      <tr><th>Name</th><th>Route</th><th>Days</th><th>Latest</th></tr>
      {% for r in ranges %}
      <tr><td>{{ r.name }}</td><td>/range/{{ r.route }}</td><td>{{ r.day_count }}</td><td>{{ r.latest or "-" }}</td></tr>
      {% endfor %}
    </table>
  </div>
</div>
</body>
</html>
'''

ADMIN_LOGIN_HTML = '''
<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Admin Login</title>
<style>
body { background:#0c1e2b; color:#f0ece4; font-family:sans-serif; display:flex; justify-content:center; align-items:center; min-height:100vh; }
.login-box { background:#122a3a; padding:40px; border-radius:8px; border:1px solid #1e3d50; }
h1 { color:#f4c566; margin-bottom:20px; }
input { padding:12px; margin:10px 0; width:100%; border:1px solid #1e3d50; background:#0c1e2b; color:#f0ece4; border-radius:4px; }
button { background:#f4c566; color:#0c1e2b; border:none; padding:12px 24px; width:100%; border-radius:4px; cursor:pointer; font-weight:bold; margin-top:10px; }
.error { color:#e74c3c; margin-top:10px; }
</style>
</head><body>
<div class="login-box">
  <h1>🔒 Admin Access</h1>
  <form method="POST">
    <input type="password" name="password" placeholder="Password" autofocus>
    <button type="submit">Login</button>
  </form>
  {% if error %}<div class="error">{{ error }}</div>{% endif %}
</div>
</body></html>
'''

# Activity log storage (in-memory, persists until restart)
activity_log = []

def log_activity(msg, log_type='info'):
    from datetime import datetime
    activity_log.insert(0, {
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'message': msg,
        'type': log_type
    })
    if len(activity_log) > 100:
        activity_log.pop()

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect('/admin/dashboard')
        return render_template_string(ADMIN_LOGIN_HTML, error='Invalid password')
    return render_template_string(ADMIN_LOGIN_HTML, error=None)

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin'):
        return redirect('/admin')
    
    comp_count = Competition.query.count()
    range_count = Range.query.count()
    shotlog_count = Shotlog.query.count()
    competitor_count = Competitor.query.count()
    
    competitions = []
    for comp in Competition.query.all():
        score_count = Score.query.filter_by(competition_id=comp.id).count()
        competitions.append({'name': comp.name, 'route': comp.route, 'score_count': score_count})
    
    ranges = []
    for r in Range.query.all():
        days = db.session.query(db.func.date(Shotlog.timestamp)).filter_by(range_id=r.id).distinct().count()
        latest = db.session.query(db.func.max(db.func.date(Shotlog.timestamp))).filter_by(range_id=r.id).scalar()
        ranges.append({'name': r.name, 'route': r.route, 'day_count': days, 'latest': str(latest) if latest else None})
    
    last_score_time = None
    last_shotlog_time = None
    for log in activity_log:
        if 'score' in log['message'].lower() and 'push' in log['message'].lower() and not last_score_time:
            last_score_time = log['time']
        if 'shotlog' in log['message'].lower() and not last_shotlog_time:
            last_shotlog_time = log['time']
        if last_score_time and last_shotlog_time:
            break
    
    return render_template_string(ADMIN_HTML,
        comp_count=comp_count,
        range_count=range_count,
        shotlog_count=shotlog_count,
        competitor_count=competitor_count,
        competitions=competitions,
        ranges=ranges,
        activity_logs=activity_log[:50],
        last_score_time=last_score_time,
        last_shotlog_time=last_shotlog_time
    )

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect('/admin')
