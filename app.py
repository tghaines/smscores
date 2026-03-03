import csv
import io
from flask import Flask, request, jsonify, render_template_string, redirect, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
import json
import hashlib
import os
import secrets

app = Flask(__name__)
def extract_distance(text):
    """Extract distance like 800m from target face description"""
    import re
    match = re.search(r"(\d+)\s*m", str(text))
    return match.group(1) if match else ""
app.secret_key = 'smscores-secret-key-change-me'
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://smscores:smscores123@localhost/smscores'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ══════════════════════════════════════════════
#  DATABASE MODELS
# ══════════════════════════════════════════════

class Range(db.Model):
    """A shooting range that can host competitions and record shotlogs"""
    id = db.Column(db.String(50), primary_key=True)  # e.g., 'ANZAC', 'BCRC'
    name = db.Column(db.String(100), nullable=False)  # e.g., 'ANZAC Rifle Range'
    api_key = db.Column(db.String(64), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    competitions = db.relationship('Competition', backref='range', lazy=True)
    shotlogs = db.relationship('Shotlog', backref='range', lazy=True)

class Competition(db.Model):
    """A live competition event (e.g., Coastal Cup)"""
    id = db.Column(db.Integer, primary_key=True)
    range_id = db.Column(db.String(50), db.ForeignKey('range.id'), nullable=False)
    route = db.Column(db.String(50), nullable=False, unique=True)  # URL slug
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200))
    event_date = db.Column(db.Date)
    active = db.Column(db.Boolean, default=True)
    sponsors = db.Column(db.JSON, default=list)  # List of sponsor logo URLs
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    logo = db.Column(db.Text)  # Base64 data URI for competition logo
    guide_html = db.Column(db.Text)  # HTML content for competitor guide
    contact_email = db.Column(db.String(200))
    contact_phone = db.Column(db.String(50))
    contact_info = db.Column(db.Text)  # Free-text contact details
    scores = db.relationship('Score', backref='competition', lazy=True)
    competitors = db.relationship('Competitor', backref='competition', lazy=True)

class Score(db.Model):
    """Score snapshot for a competition"""
    id = db.Column(db.Integer, primary_key=True)
    competition_id = db.Column(db.Integer, db.ForeignKey('competition.id'), nullable=False)
    data = db.Column(db.JSON, nullable=False)
    data_hash = db.Column(db.String(32))  # To detect changes
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Competitor(db.Model):
    """Squadding entry for a competition"""
    id = db.Column(db.Integer, primary_key=True)
    competition_id = db.Column(db.Integer, db.ForeignKey('competition.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    class_name = db.Column(db.String(50))
    relay = db.Column(db.String(10))
    target = db.Column(db.String(20))
    match = db.Column(db.String(50))
    position = db.Column(db.String(10))

class Shotlog(db.Model):
    """Daily shotlog for a range (club shooting history)"""
    id = db.Column(db.Integer, primary_key=True)
    range_id = db.Column(db.String(50), db.ForeignKey('range.id'), nullable=False)
    shoot_date = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    strings = db.relationship('ShotlogString', backref='shotlog', lazy=True)

class ShotlogString(db.Model):
    """A single string (10+2 etc) within a shotlog"""
    id = db.Column(db.Integer, primary_key=True)
    shotlog_id = db.Column(db.Integer, db.ForeignKey('shotlog.id'), nullable=False)
    target = db.Column(db.String(50))  # e.g., '82-E6 BCRC'
    shooter_name = db.Column(db.String(100))  # Name saved in ShotMarker
    match_name = db.Column(db.String(50))  # e.g., '10+2 1'
    total_score = db.Column(db.Integer)
    x_count = db.Column(db.Integer)
    shot_data = db.Column(db.JSON)
    distance = db.Column(db.String(20))  # Individual shots with x/y coords

class Photo(db.Model):
    """Photo for a competition gallery"""
    id = db.Column(db.Integer, primary_key=True)
    competition_id = db.Column(db.Integer, db.ForeignKey('competition.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    caption = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ══════════════════════════════════════════════
#  API ENDPOINTS - For Pi scrapers to push data
# ══════════════════════════════════════════════

@app.route('/api/push/scores', methods=['POST'])
def push_scores():
    """Receive competition scores from a Pi scraper (ts_export format)"""
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return jsonify({'error': 'Missing API key'}), 401
    range_obj = Range.query.filter_by(api_key=api_key).first()
    if not range_obj:
        return jsonify({'error': 'Invalid API key'}), 401
    data = request.json
    comp_route = data.get('competition')
    raw_scores = data.get('scores', [])
    comp = Competition.query.filter_by(range_id=range_obj.id, route=comp_route).first()
    if not comp:
        return jsonify({'error': 'Competition not found'}), 404
    # Transform ts_export format to scoreboard format
    # Input: [{"match":"Match One 10+2","user":"Name","shots":"X,6,5...","total":"53-2X"}]
    # Output: [{"name":"Name","class":"F-OPEN","matches":[{"match":"Match One","score":53,"xCount":2,"shots":["X","6"]}]}]
    shooter_map = {}
    for entry in raw_scores:
        name = entry.get('user', '')
        match_name = entry.get('match', '')
        shots_str = entry.get('shots', '')
        total_str = entry.get('total', '')
        if not name:
            continue
        # Parse total (e.g., "53-2X" or "53-2V")
        total_score = 0
        x_count = 0
        if '-' in total_str:
            parts = total_str.split('-')
            try:
                total_score = int(parts[0])
                x_part = parts[1].upper().replace('X', '').replace('V', '')
                x_count = int(x_part) if x_part else 0
            except:
                pass
        # Parse shots into array
        shots = shots_str  # Keep as string
        # Find competitor class from existing competitors
        competitor = Competitor.query.filter_by(competition_id=comp.id, name=name).first()
        shooter_class = competitor.class_name if competitor else 'UNCATEGORIZED'
        # Build shooter entry
        if name not in shooter_map:
            shooter_map[name] = {'name': name, 'class': shooter_class, 'matches': []}
        shooter_map[name]['matches'].append({
            'match': match_name,
            'score': total_score,
            'xCount': x_count,
            'shots': shots
        })
    transformed = list(shooter_map.values())
    # Check if scores have changed
    data_hash = hashlib.md5(json.dumps(transformed, sort_keys=True).encode()).hexdigest()
    latest = Score.query.filter_by(competition_id=comp.id).order_by(Score.created_at.desc()).first()
    if latest and latest.data_hash == data_hash:
        return jsonify({'ok': True, 'message': 'Scores unchanged'})
    # Save transformed scores
    score_entry = Score(competition_id=comp.id, data=transformed, data_hash=data_hash)
    db.session.add(score_entry)
    db.session.commit()
    log_activity(f'Scores pushed: {comp.name} - {len(transformed)} shooters', 'push')
    return jsonify({'ok': True, 'message': f'Saved scores for {len(transformed)} shooters'})

@app.route('/api/push/competitors', methods=['POST'])
def push_competitors():
    """Receive squadding data from a Pi scraper"""
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return jsonify({'error': 'Missing API key'}), 401
    
    range_obj = Range.query.filter_by(api_key=api_key).first()
    if not range_obj:
        return jsonify({'error': 'Invalid API key'}), 401
    
    data = request.json
    comp_route = data.get('competition')
    competitors = data.get('competitors', [])
    
    comp = Competition.query.filter_by(range_id=range_obj.id, route=comp_route).first()
    if not comp:
        return jsonify({'error': 'Competition not found'}), 404
    
    # Clear existing and add new
    Competitor.query.filter_by(competition_id=comp.id).delete()
    for c in competitors:
        entry = Competitor(
            competition_id=comp.id,
            name=c.get('name', ''),
            class_name=c.get('class', ''),
            relay=c.get('relay', ''),
            target=c.get('target', ''),
            match=c.get('match', ''),
            position=c.get('position', '')
        )
        db.session.add(entry)
    db.session.commit()
    
    return jsonify({'ok': True, 'message': f'Saved {len(competitors)} competitors'})

@app.route('/api/push/shotlog', methods=['POST'])
def push_shotlog():
    """Receive shotlog (club history) from a Pi scraper"""
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return jsonify({'error': 'Missing API key'}), 401

    range_obj = Range.query.filter_by(api_key=api_key).first()
    if not range_obj:
        return jsonify({'error': 'Invalid API key'}), 401

    data = request.json
    csv_text = data.get('csv', '')

    if not csv_text:
        return jsonify({'error': 'No CSV data provided'}), 400

    # Parse the raw ShotMarker CSV using the existing parser
    strings = parse_upload_csv(csv_text)

    if not strings:
        return jsonify({'error': 'No valid data found in CSV'}), 400

    # Save using the existing save function
    saved_dates = save_uploaded_shotlog(range_obj.id, strings)

    log_activity(f'Shotlog pushed: {range_obj.name} - {len(strings)} strings, {len(saved_dates)} dates', 'push')
    return jsonify({'ok': True, 'message': f'Saved {len(strings)} strings for {len(saved_dates)} dates', 'dates': saved_dates})


# ══════════════════════════════════════════════
#  ADMIN API - Create ranges, competitions
# ══════════════════════════════════════════════

@app.route('/api/admin/create-range', methods=['POST'])
def create_range():
    """Create a new range (temporary - no auth for now)"""
    data = request.json
    range_id = data.get('id')
    name = data.get('name')
    
    if not range_id or not name:
        return jsonify({'error': 'id and name required'}), 400
    
    if Range.query.get(range_id):
        return jsonify({'error': 'Range already exists'}), 400
    
    api_key = secrets.token_hex(32)
    range_obj = Range(id=range_id, name=name, api_key=api_key)
    db.session.add(range_obj)
    db.session.commit()
    
    return jsonify({'ok': True, 'id': range_id, 'api_key': api_key})

@app.route('/api/admin/create-competition', methods=['POST'])
def create_competition():
    """Create a new competition"""
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return jsonify({'error': 'Missing API key'}), 401
    
    range_obj = Range.query.filter_by(api_key=api_key).first()
    if not range_obj:
        return jsonify({'error': 'Invalid API key'}), 401
    
    data = request.json
    route = data.get('route')
    name = data.get('name')
    description = data.get('description', '')
    
    if not route or not name:
        return jsonify({'error': 'route and name required'}), 400
    
    if Competition.query.filter_by(route=route).first():
        return jsonify({'error': 'Competition route already exists'}), 400
    
    comp = Competition(
        range_id=range_obj.id,
        route=route,
        name=name,
        description=description,
        event_date=date.today()
    )
    db.session.add(comp)
    db.session.commit()
    
    return jsonify({'ok': True, 'route': route, 'id': comp.id})

# ══════════════════════════════════════════════
#  PUBLIC PAGES - Homepage
# ══════════════════════════════════════════════

@app.route('/')
def index():
    """Homepage - list active competitions and ranges"""
    comps = Competition.query.filter_by(active=True).all()
    archived = Competition.query.filter_by(active=False).all()
    ranges = Range.query.all()
    return render_template_string(HOME_HTML, competitions=comps, archived=archived, ranges=ranges)

# ══════════════════════════════════════════════
#  COMPETITION PAGES - Live scores & squadding
# ══════════════════════════════════════════════

@app.route('/<comp_route>')
def competition_page(comp_route):
    """Display live scores for a competition"""
    comp = Competition.query.filter_by(route=comp_route).first()
    if not comp:
        return "Competition not found", 404
    return render_template_string(SCOREBOARD_HTML, competition=comp)

@app.route('/<comp_route>/squadding')
def competition_squadding(comp_route):
    """Display squadding for a competition"""
    comp = Competition.query.filter_by(route=comp_route).first()
    if not comp:
        return "Competition not found", 404
    return render_template_string(SQUADDING_HTML, competition=comp)

@app.route('/<comp_route>/guide')
def competition_guide(comp_route):
    """Display competitors guide"""
    comp = Competition.query.filter_by(route=comp_route).first()
    if not comp:
        return "Competition not found", 404
    if comp.guide_html:
        return comp.guide_html
    guide_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Coastal_Cup_Competitors_Guide.html')
    if os.path.exists(guide_path):
        with open(guide_path, 'r') as f:
            return f.read()
    return "Contact event organisers", 404

@app.route('/<comp_route>/contact')
def competition_contact(comp_route):
    """Display per-competition contact page"""
    comp = Competition.query.filter_by(route=comp_route).first()
    if not comp:
        return "Competition not found", 404
    if not comp.contact_email and not comp.contact_phone and not comp.contact_info:
        return redirect('/contact')
    return render_template_string(COMP_CONTACT_HTML, competition=comp)

# ══════════════════════════════════════════════
#  PHOTO GALLERY
# ══════════════════════════════════════════════

PHOTO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'photos')

@app.route('/<comp_route>/photos')
def competition_photos(comp_route):
    comp = Competition.query.filter_by(route=comp_route).first()
    if not comp:
        return "Competition not found", 404
    return render_template_string(PHOTO_GALLERY_HTML, competition=comp)

@app.route('/<comp_route>/photos/upload', methods=['POST'])
def upload_photo(comp_route):
    try:
        comp = Competition.query.filter_by(route=comp_route).first()
        if not comp:
            return jsonify({'error': 'Competition not found'}), 404
        if 'photo' not in request.files:
            return jsonify({'error': 'No file'}), 400
        file = request.files['photo']
        if not file.filename:
            return jsonify({'error': 'No file selected'}), 400
        # Validate - accept any image type
        ct = (file.content_type or '').lower()
        if ct and not ct.startswith('image/'):
            return jsonify({'error': 'Invalid file type: ' + ct}), 400
        # Generate safe filename - save everything as jpg (canvas sends jpeg)
        ext = 'jpg'
        if 'png' in ct:
            ext = 'png'
        elif 'webp' in ct:
            ext = 'webp'
        import time as _time
        fname = f'{comp.id}_{int(_time.time())}_{secrets.token_hex(4)}.{ext}'
        os.makedirs(PHOTO_DIR, exist_ok=True)
        file.save(os.path.join(PHOTO_DIR, fname))
        caption = request.form.get('caption', '').strip()[:200]
        photo = Photo(competition_id=comp.id, filename=fname, caption=caption)
        db.session.add(photo)
        db.session.commit()
        return jsonify({'ok': True, 'id': photo.id, 'filename': fname})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/photos/<filename>')
def serve_photo(filename):
    """Serve uploaded photo from disk"""
    return send_from_directory(PHOTO_DIR, filename)

@app.route('/<comp_route>/photos/json')
def photos_json(comp_route):
    comp = Competition.query.filter_by(route=comp_route).first()
    if not comp:
        return jsonify([])
    photos = Photo.query.filter_by(competition_id=comp.id).order_by(Photo.created_at.desc()).all()
    return jsonify([{
        'id': p.id, 'filename': p.filename, 'caption': p.caption,
        'url': f'/photos/{p.filename}',
        'date': p.created_at.strftime('%d %b %Y %H:%M') if p.created_at else ''
    } for p in photos])

@app.route('/api/admin/competition/<int:comp_id>/photos/<int:photo_id>/delete', methods=['POST'])
def admin_delete_photo(comp_id, photo_id):
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    photo = Photo.query.filter_by(id=photo_id, competition_id=comp_id).first()
    if not photo:
        return jsonify({'error': 'Photo not found'}), 404
    # Delete file from disk
    fpath = os.path.join(PHOTO_DIR, photo.filename)
    if os.path.exists(fpath):
        os.remove(fpath)
    db.session.delete(photo)
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/api/admin/competition/<int:comp_id>/photos/clear', methods=['POST'])
def admin_clear_photos(comp_id):
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    photos = Photo.query.filter_by(competition_id=comp_id).all()
    count = len(photos)
    for p in photos:
        fpath = os.path.join(PHOTO_DIR, p.filename)
        if os.path.exists(fpath):
            os.remove(fpath)
        db.session.delete(p)
    db.session.commit()
    return jsonify({'ok': True, 'message': f'Deleted {count} photos'})

@app.route('/<comp_route>/scores/latest.json')
def competition_scores_json(comp_route):
    """Return latest scores as JSON"""
    comp = Competition.query.filter_by(route=comp_route).first()
    if not comp:
        return jsonify([])
    
    latest = Score.query.filter_by(competition_id=comp.id).order_by(Score.created_at.desc()).first()
    if not latest:
        return jsonify([])
    return jsonify(latest.data)

@app.route('/<comp_route>/competitors.json')
def competition_competitors_json(comp_route):
    """Return competitors/squadding as JSON"""
    comp = Competition.query.filter_by(route=comp_route).first()
    if not comp:
        return jsonify({'competitors': []})
    
    competitors = Competitor.query.filter_by(competition_id=comp.id).all()
    return jsonify({
        'competitors': [{
            'name': c.name,
            'class': c.class_name,
            'relay': c.relay,
            'target': c.target,
            'match': c.match,
            'position': c.position
        } for c in competitors]
    })

# ══════════════════════════════════════════════
#  RANGE PAGES - Club history / shotlogs
# ══════════════════════════════════════════════

@app.route('/range/<range_id>')
def range_history(range_id):
    """Display range calendar/history"""
    range_obj = Range.query.get(range_id)
    if not range_obj:
        return "Range not found", 404
    
    shotlogs = Shotlog.query.filter_by(range_id=range_id).order_by(Shotlog.shoot_date.desc()).all()
    return render_template_string(RANGE_HISTORY_HTML, range=range_obj, shotlogs=shotlogs)

@app.route('/range/<range_id>/<date_str>')
def range_day(range_id, date_str):
    """Display a specific day's shotlog"""
    range_obj = Range.query.get(range_id)
    if not range_obj:
        return "Range not found", 404
    
    try:
        shoot_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except:
        return "Invalid date", 400
    
    shotlog = Shotlog.query.filter_by(range_id=range_id, shoot_date=shoot_date).first()
    if not shotlog:
        return "No data for this date", 404
    
    strings_raw = ShotlogString.query.filter_by(shotlog_id=shotlog.id).all()
    strings = [{
        "target": s.target,
        "shooter_name": s.shooter_name,
        "match_name": s.match_name,
        "total_score": s.total_score,
        "x_count": s.x_count,
        "shot_data": s.shot_data if s.shot_data else [],
        "distance": s.distance
    } for s in strings_raw]
    return render_template_string(RANGE_DAY_HTML, range=range_obj, date=shoot_date, strings=strings, is_admin=session.get('admin'))

# ══════════════════════════════════════════════
#  HTML TEMPLATES
# ══════════════════════════════════════════════

HOME_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SM Scores - Live Shooting Results</title>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=Barlow+Condensed:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root { --bg:#0c1e2b; --bg2:#122a3a; --gold:#f4c566; --blue:#54b8db; --text:#f0ece4; --text2:#8ab4c8; --border:#1e3d50; }
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--bg); color:var(--text); font-family:'Barlow Condensed',sans-serif; min-height:100vh; padding:40px 20px; }
.container { max-width:900px; margin:0 auto; }
h1 { font-family:'Oswald',sans-serif; font-size:2.5rem; color:var(--gold); margin-bottom:8px; }
.subtitle { color:var(--text2); font-size:1.1rem; margin-bottom:40px; }
h2 { font-family:'Oswald',sans-serif; font-size:1.3rem; color:var(--text); margin:30px 0 16px; letter-spacing:1px; }
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:16px; }
.card { background:var(--bg2); border:1px solid var(--border); border-radius:8px; padding:20px; transition:border-color 0.2s; }
.card:hover { border-color:var(--gold); }
.card h3 { font-family:'Oswald',sans-serif; color:var(--gold); margin:0 0 8px; font-size:1.2rem; }
.card p { color:var(--text2); margin:0 0 12px; font-size:0.95rem; }
.card a { color:var(--blue); text-decoration:none; font-weight:500; }
.card a:hover { text-decoration:underline; }
.empty { color:var(--text2); font-style:italic; }
</style>
</head>
<body>
<div class="container">
  <h1>🎯 SM Scores</h1>
  <p class="subtitle">Live shooting competition results</p>
  
  <h2>Live Competitions</h2>
  <div class="grid">
    {% for comp in competitions %}
    <div class="card">
      <h3>{{ comp.name }}</h3>
      <p>{{ comp.description or 'Live scoring' }}</p>
      <a href="/{{ comp.route }}">View Scores →</a> &nbsp;|&nbsp; <a href="/{{ comp.route }}/squadding">Squadding</a>
    </div>
    {% endfor %}
    {% if not competitions %}
    <p class="empty">No active competitions</p>
    {% endif %}
  </div>
  
  <h2>Range History</h2>
  <div class="grid">
    {% for range in ranges %}
    <div class="card">
      <h3>{{ range.name }}</h3>
      <p>Historical shotlogs and scores</p>
      <a href="/range/{{ range.id }}">View History →</a>
    </div>
    {% endfor %}
    {% if not ranges %}
    <p class="empty">No ranges registered yet</p>
    {% endif %}
  </div>

  {% if archived %}
  <h2>Archived Competitions</h2>
  <div class="grid">
    {% for comp in archived %}
    <div class="card" style="opacity:0.7; border-color:var(--border);">
      <h3 style="color:var(--text2);">{{ comp.name }}</h3>
      <p>{{ comp.description or 'Completed' }}</p>
      <a href="/{{ comp.route }}">View Scores →</a>
    </div>
    {% endfor %}
  </div>
  {% endif %}
</div>
<footer style="margin-top:60px;padding:20px;border-top:1px solid #1e3d50;text-align:center;font-size:0.9rem;"><a href="/" style="color:#8ab4c8;text-decoration:none;margin:0 12px;">Home</a><a href="/about" style="color:#8ab4c8;text-decoration:none;margin:0 12px;">About</a><a href="/contact" style="color:#8ab4c8;text-decoration:none;margin:0 12px;">Contact</a></footer></body>
</html>
'''

SCOREBOARD_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ competition.name }} - Live Scores</title>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&family=Barlow+Condensed:wght@300;400;500;600&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/qrcodejs@1.0.0/qrcode.min.js"></script>
<style>
:root { --bg:#0c1e2b; --bg2:#122a3a; --bg-row:#153040; --gold:#f4c566; --green:#5cc9a7; --blue:#54b8db; --text:#f0ece4; --text2:#8ab4c8; --muted:#5a8899; --border:#1e3d50; }
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--bg); color:var(--text); font-family:'Barlow Condensed',sans-serif; min-height:100vh; }
.container { max-width:1400px; margin:0 auto; padding:0 20px; }
.sticky-top { position:sticky; top:0; z-index:100; background:var(--bg); padding-top:12px; border-bottom:1px solid var(--border); margin-bottom:12px; }
.header { display:flex; justify-content:space-between; align-items:center; padding:8px 0; flex-wrap:wrap; gap:12px; }
.header h1 { font-family:'Oswald',sans-serif; font-size:1.8rem; color:var(--gold); }
.header .subtitle { color:var(--text2); font-size:0.95rem; }
.nav-links { display:flex; gap:12px; }
.nav-link { color:var(--gold); text-decoration:none; border:1px solid var(--gold); padding:8px 16px; border-radius:4px; font-size:0.9rem; }
.nav-link:hover { background:var(--gold); color:var(--bg); }
.live-badge { display:inline-flex; align-items:center; gap:8px; background:rgba(92,201,167,0.1); border:1px solid rgba(92,201,167,0.3); padding:6px 14px; border-radius:4px; color:var(--green); font-family:'JetBrains Mono',monospace; font-size:0.75rem; }
.live-dot { width:8px; height:8px; background:var(--green); border-radius:50%; animation:pulse 2s infinite; }
@keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.5; } }
.live-badge.paused { background:rgba(90,136,153,0.1); border-color:rgba(90,136,153,0.3); color:var(--muted); }
.live-badge.paused .live-dot { background:var(--muted); animation:none; }
.pause-btn { background:none; border:1px solid currentColor; color:inherit; padding:2px 8px; border-radius:3px; cursor:pointer; font-family:'JetBrains Mono',monospace; font-size:0.65rem; margin-left:4px; }
.pause-btn:hover { opacity:0.8; }
.scroll-badge { display:inline-flex; align-items:center; gap:8px; background:rgba(84,184,219,0.1); border:1px solid rgba(84,184,219,0.3); padding:6px 14px; border-radius:4px; color:var(--blue); font-family:'JetBrains Mono',monospace; font-size:0.75rem; }
.scroll-badge.paused { background:rgba(90,136,153,0.1); border-color:rgba(90,136,153,0.3); color:var(--muted); }
.controls { display:flex; flex-wrap:wrap; gap:12px; margin:8px 0; align-items:center; }
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
.sponsor-bar { display:flex; flex-wrap:wrap; gap:12px; align-items:center; justify-content:center; padding:12px 16px; background:rgba(255,255,255,0.05); border-radius:6px; margin-top:12px; }
.sponsor-bar a { display:inline-block; transition:transform 0.2s; }
.sponsor-bar a:hover { transform:scale(1.08); }
.sponsor-bar img { max-height:50px; max-width:120px; object-fit:contain; background:#fff; padding:6px; border-radius:4px; }
@media(max-width:600px) { .sponsor-bar img { max-height:36px; max-width:90px; } }
.cb-badge { font-size:0.6rem; padding:1px 4px; border-radius:2px; margin-left:4px; font-family:'JetBrains Mono',monospace; vertical-align:middle; }
.cb-badge.cb { background:rgba(84,184,219,0.2); color:var(--blue); border:1px solid rgba(84,184,219,0.3); }
.cb-badge.so { background:rgba(232,90,90,0.2); color:#e85a5a; border:1px solid rgba(232,90,90,0.3); }
.prize-label { font-size:0.65rem; font-family:'JetBrains Mono',monospace; padding:1px 5px; border-radius:2px; margin-left:4px; }
.prize-1 { background:rgba(244,197,102,0.2); color:var(--gold); }
.prize-2 { background:rgba(192,192,192,0.2); color:#c0c0c0; }
.prize-3 { background:rgba(205,127,50,0.2); color:#cd7f32; }
.print-btn { color:var(--gold); text-decoration:none; border:1px solid var(--gold); padding:8px 16px; border-radius:4px; font-size:0.9rem; cursor:pointer; background:none; font-family:inherit; }
.print-btn:hover { background:var(--gold); color:var(--bg); }
.qr-btn { color:var(--gold); text-decoration:none; border:1px solid var(--gold); padding:8px 16px; border-radius:4px; font-size:0.9rem; cursor:pointer; background:none; font-family:inherit; }
.qr-btn:hover { background:var(--gold); color:var(--bg); }
.qr-popup { display:none; position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,0.8); z-index:1000; justify-content:center; align-items:center; }
.qr-popup.show { display:flex; }
.qr-box { background:white; padding:24px; border-radius:8px; text-align:center; }
.qr-box p { color:#333; margin-top:12px; font-size:0.85rem; font-family:'JetBrains Mono',monospace; word-break:break-all; max-width:250px; }
.qr-close { margin-top:12px; padding:8px 20px; border:none; border-radius:4px; background:var(--bg); color:var(--gold); cursor:pointer; font-size:0.9rem; }
@media print {
  * { color:#000 !important; background:#fff !important; border-color:#ccc !important; }
  body { font-size:11pt; }
  .controls, footer, .nav-links, .sponsor-bar, .shot-badges, .print-btn, .pause-btn, .live-badge, .scroll-badge, .scroll-controls, .qr-btn, .qr-popup { display:none !important; }
  .sticky-top { position:static; border-bottom:none; }
  .container { max-width:100%; padding:0; }
  .header { border-bottom:2px solid #000; margin-bottom:10px; padding:10px 0; }
  .header h1 { font-size:18pt; color:#000 !important; }
  .category-section { break-inside:avoid; margin-bottom:20px; }
  .category-header { font-size:14pt; border-bottom:2px solid #000; padding:6px 0; }
  table { font-size:9pt; }
  th, td { padding:4px 6px; border-bottom:1px solid #ccc; }
  th { background:#eee !important; color:#000 !important; font-weight:bold; }
  .rank, .shooter-name, .match-score, .aggregate { color:#000 !important; }
  .rank-1, .rank-2, .rank-3 { color:#000 !important; }
  .cb-badge { border:1px solid #666; color:#666 !important; }
  .prize-label { border:1px solid #999; color:#000 !important; background:#eee !important; }
  .no-data { display:none; }
}
</style>
</head>
<body>
<div class="container">
  <div class="sticky-top">
  <div class="header">
    <div style="display:flex;align-items:center;gap:16px;">
      {% if competition.logo %}<img src="{{ competition.logo }}" style="max-height:60px;max-width:150px;" alt="Logo">{% endif %}
      <div>
        <h1>🏆 {{ competition.name }}</h1>
        <div class="subtitle">{{ competition.description or '' }}</div>
      </div>
    </div>
      {% if competition.sponsors %}
      <div class="sponsor-bar">
        {% for s in competition.sponsors %}
          {% if s is mapping %}
        <a href="{{ s.link }}" target="_blank" rel="noopener"><img src="{{ s.logo }}" alt="Sponsor" onerror="this.parentElement.style.display='none'"></a>
          {% else %}
        <img src="{{ s }}" alt="Sponsor" onerror="this.style.display='none'">
          {% endif %}
        {% endfor %}
      </div>
      {% endif %}
    <div class="nav-links">
      <a href="/" class="nav-link">← Home</a>
      <a href="/{{ competition.route }}/squadding" class="nav-link">Squadding</a>
      <a href="/{{ competition.route }}/guide" class="nav-link">Guide</a>
      <a href="/{{ competition.route }}/photos" class="nav-link">Photos</a>
      <a href="/{{ competition.route }}/contact" class="nav-link">Contact</a>
      <button class="print-btn" onclick="window.print()">Print</button>
      <button class="qr-btn" onclick="showQR()">QR</button>
    </div>
  </div>
  <div class="controls">
    <div class="live-badge" id="liveBadge"><div class="live-dot" id="liveDot"></div> <span id="liveText">Live Scores</span> <button class="pause-btn" id="pauseBtn" onclick="toggleAutoRefresh()">Pause</button></div>
    <div class="scroll-badge" id="scrollBadge"><span id="scrollText">Auto-Scroll</span> <button class="pause-btn" id="scrollBtn" onclick="toggleAutoScroll()">Pause</button></div>
    <div class="search-box"><input type="text" id="searchInput" placeholder="Search shooter..." oninput="applyFilters()"></div>
    <div class="toggle-btns" id="categoryBtns"></div>
    <div class="update-time" id="updateTime">Loading...</div>
  </div>
  </div>
  <div id="scoreboards"></div>
</div>
<div class="qr-popup" id="qrPopup" onclick="hideQR()">
  <div class="qr-box" onclick="event.stopPropagation()">
    <div id="qrCode"></div>
    <p id="qrUrl"></p>
    <button class="qr-close" onclick="hideQR()">Close</button>
  </div>
</div>
<footer><a href="/">Home</a><a href="/about">About</a><a href="/contact">Contact</a></footer>
<script>
var defined_matches = [];
var defined_categories = [];
var competitors = [];
var scores = [];
var activeCategories = new Set();
var autoRefresh = true;
var refreshInterval = null;
var scrolling = true;
var scrollSpeed = 0.25;
var scrollPauseAtEnd = 3000;
var scrollPauseTimer = null;
var scrollAccum = 0;

function doAutoScroll() {
  if (!scrolling) { return; }
  var maxScroll = Math.round(document.documentElement.scrollHeight - window.innerHeight);
  if (maxScroll <= 2) { setTimeout(function() { requestAnimationFrame(doAutoScroll); }, 1000); return; }
  if (Math.round(window.scrollY) >= maxScroll - 1) {
    scrollAccum = 0;
    scrollPauseTimer = setTimeout(function() { window.scrollTo(0, 0); scrollPauseTimer = null; requestAnimationFrame(doAutoScroll); }, scrollPauseAtEnd);
    return;
  }
  scrollAccum += scrollSpeed;
  if (scrollAccum >= 1) {
    var px = Math.floor(scrollAccum);
    scrollAccum -= px;
    window.scrollBy(0, px);
  }
  requestAnimationFrame(doAutoScroll);
}

function toggleAutoScroll() {
  scrolling = !scrolling;
  var badge = document.getElementById('scrollBadge');
  var btn = document.getElementById('scrollBtn');
  var txt = document.getElementById('scrollText');
  if (scrolling) {
    badge.classList.remove('paused');
    txt.textContent = 'Auto-Scroll';
    btn.textContent = 'Pause';
    requestAnimationFrame(doAutoScroll);
  } else {
    badge.classList.add('paused');
    txt.textContent = 'Scroll Paused';
    btn.textContent = 'Resume';
    if (scrollPauseTimer) { clearTimeout(scrollPauseTimer); scrollPauseTimer = null; }
  }
}

function toggleAutoRefresh() {
  autoRefresh = !autoRefresh;
  var badge = document.getElementById('liveBadge');
  var btn = document.getElementById('pauseBtn');
  var txt = document.getElementById('liveText');
  if (autoRefresh) {
    badge.classList.remove('paused');
    txt.textContent = 'Live Scores';
    btn.textContent = 'Pause';
    loadScores();
    refreshInterval = setInterval(loadScores, 15000);
  } else {
    badge.classList.add('paused');
    txt.textContent = 'Paused';
    btn.textContent = 'Resume';
    if (refreshInterval) { clearInterval(refreshInterval); refreshInterval = null; }
  }
}

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
    var wordNums = {one:1,two:2,three:3,four:4,five:5,six:6,seven:7,eight:8,nine:9,ten:10};
    function matchNum(s) {
      var w = s.toLowerCase().match(/\\b(one|two|three|four|five|six|seven|eight|nine|ten)\\b/);
      if (w) return wordNums[w[1]];
      var d = s.match(/match\\s*(\\d+)/i);
      if (d) return parseInt(d[1]);
      return 0;
    }
    defined_matches = Array.from(matchSet).sort(function(a, b) {
      var numA = matchNum(a), numB = matchNum(b);
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
    // Fill in match names from score data if competitors didn't define them
    var scoreMatchSet = new Set(defined_matches);
    scores.forEach(function(s) {
      if (s.matches) s.matches.forEach(function(m) { if (m.match) scoreMatchSet.add(m.match); });
    });
    if (scoreMatchSet.size > defined_matches.length) {
      var wordNums = {one:1,two:2,three:3,four:4,five:5,six:6,seven:7,eight:8,nine:9,ten:10};
      function matchNum(s) {
        var w = s.toLowerCase().match(/\b(one|two|three|four|five|six|seven|eight|nine|ten)\b/);
        if (w) return wordNums[w[1]];
        var d = s.match(/match\s*(\d+)/i);
        if (d) return parseInt(d[1]);
        return 0;
      }
      defined_matches = Array.from(scoreMatchSet).sort(function(a, b) {
        var numA = matchNum(a), numB = matchNum(b);
        if (numA !== numB) return numA - numB;
        return a.localeCompare(b);
      });
    }
    renderScoreboards();
    document.getElementById('updateTime').textContent = 'Updated ' + new Date().toLocaleTimeString();
  } catch (e) { console.error('Load scores error:', e); }
}

function countback(a, b) {
  // Compare last match shots in reverse order, looking for latest X
  // Returns: 1 if a wins, -1 if b wins, 0 if shoot-off needed
  var aMatches = (a.scoreData && a.scoreData.matches) ? a.scoreData.matches : [];
  var bMatches = (b.scoreData && b.scoreData.matches) ? b.scoreData.matches : [];
  // Find the last match (by defined_matches order)
  for (var mi = defined_matches.length - 1; mi >= 0; mi--) {
    var matchName = defined_matches[mi];
    var aMatch = null, bMatch = null;
    aMatches.forEach(function(m) { if (m.match === matchName) aMatch = m; });
    bMatches.forEach(function(m) { if (m.match === matchName) bMatch = m; });
    if (!aMatch || !bMatch || !aMatch.shots || !bMatch.shots) continue;
    var aShotsArr = aMatch.shots.split(',').map(function(s) { return s.trim().toUpperCase(); });
    var bShotsArr = bMatch.shots.split(',').map(function(s) { return s.trim().toUpperCase(); });
    // Compare from last shot backwards
    var maxLen = Math.max(aShotsArr.length, bShotsArr.length);
    for (var i = maxLen - 1; i >= 0; i--) {
      var aShot = i < aShotsArr.length ? aShotsArr[i] : '';
      var bShot = i < bShotsArr.length ? bShotsArr[i] : '';
      var aIsX = (aShot === 'X');
      var bIsX = (bShot === 'X');
      if (aIsX && !bIsX) return 1;  // a wins
      if (bIsX && !aIsX) return -1; // b wins
    }
    // All shots identical in this match, try previous match
  }
  return 0; // shoot-off needed
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
      if (b.aggregateX !== a.aggregateX) return b.aggregateX - a.aggregateX;
      var cb = countback(a, b);
      if (cb !== 0) return cb > 0 ? -1 : 1;
      return 0;
    });
    // Mark countback/shoot-off flags
    for (var ci = 0; ci < catShooters.length; ci++) {
      catShooters[ci].tieFlag = '';
      if (ci > 0) {
        var prev = catShooters[ci - 1];
        var curr = catShooters[ci];
        if (prev.aggregate === curr.aggregate && prev.aggregateX === curr.aggregateX) {
          var cbResult = countback(prev, curr);
          if (cbResult > 0) {
            if (!prev.tieFlag) prev.tieFlag = 'cb';
            curr.tieFlag = 'cb';
          } else if (cbResult === 0) {
            prev.tieFlag = 'so';
            curr.tieFlag = 'so';
          }
        }
      }
    }
    html += '<div class="category-section">';
    html += '<div class="category-header"><span>' + category + '</span><span class="category-count">' + catShooters.length + ' shooters</span></div>';
    if (!catShooters.length) {
      html += '<div class="no-data">No shooters</div>';
    } else {
      html += '<table><thead><tr><th>#</th><th>Shooter</th>';
      defined_matches.forEach(function(m) {
        var short = m.replace(' 10+2', '').replace(' Finals', ' F');
        short = short.replace(/\\b(One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten)\\b/i, function(w) {
          return {one:'1',two:'2',three:'3',four:'4',five:'5',six:'6',seven:'7',eight:'8',nine:'9',ten:'10'}[w.toLowerCase()] || w;
        });
        html += '<th>' + short + '</th>';
      });
      html += '<th>Aggregate</th></tr></thead><tbody>';
      var displayRank = 1;
      catShooters.forEach(function(s, idx) {
        // Handle tied ranks for shoot-offs
        if (idx > 0) {
          var prev = catShooters[idx - 1];
          if (s.tieFlag === 'so' && prev.tieFlag === 'so' && s.aggregate === prev.aggregate && s.aggregateX === prev.aggregateX) {
            // Same rank as previous (shoot-off)
          } else {
            displayRank = idx + 1;
          }
        }
        var rankClass = displayRank <= 3 ? ' rank-' + displayRank : '';
        var prizeHtml = '';
        if (displayRank === 1) prizeHtml = '<span class="prize-label prize-1">1st</span>';
        else if (displayRank === 2) prizeHtml = '<span class="prize-label prize-2">2nd</span>';
        else if (displayRank === 3) prizeHtml = '<span class="prize-label prize-3">3rd</span>';
        var tieBadge = '';
        if (s.tieFlag === 'cb') tieBadge = '<span class="cb-badge cb" title="Countback">CB</span>';
        else if (s.tieFlag === 'so') tieBadge = '<span class="cb-badge so" title="Shoot-off required">SO</span>';
        html += '<tr><td class="rank' + rankClass + '">' + displayRank + prizeHtml + tieBadge + '</td>';
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
  refreshInterval = setInterval(loadScores, 15000);
  requestAnimationFrame(doAutoScroll);
}
init();

var qrGenerated = false;
function showQR() {
  if (!qrGenerated) {
    new QRCode(document.getElementById('qrCode'), {
      text: window.location.href,
      width: 200,
      height: 200,
      colorDark: '#000000',
      colorLight: '#ffffff'
    });
    document.getElementById('qrUrl').textContent = window.location.href;
    qrGenerated = true;
  }
  document.getElementById('qrPopup').classList.add('show');
}
function hideQR() {
  document.getElementById('qrPopup').classList.remove('show');
}
</script>
</body>
</html>
'''

SQUADDING_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ competition.name }} - Squadding</title>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&family=Barlow+Condensed:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root { --bg:#0c1e2b; --bg2:#122a3a; --bg-row:#153040; --gold:#f4c566; --green:#5cc9a7; --blue:#54b8db; --text:#f0ece4; --text2:#8ab4c8; --muted:#5a8899; --border:#1e3d50; }
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--bg); color:var(--text); font-family:'Barlow Condensed',sans-serif; min-height:100vh; }
.container { max-width:1200px; margin:0 auto; padding:0 20px; }
.sticky-top { position:sticky; top:0; z-index:100; background:var(--bg); padding-top:12px; border-bottom:1px solid var(--border); margin-bottom:12px; }
.header { display:flex; justify-content:space-between; align-items:center; padding:8px 0; flex-wrap:wrap; gap:12px; }
.header h1 { font-family:'Oswald',sans-serif; font-size:1.8rem; color:var(--gold); }
.nav-link { color:var(--gold); text-decoration:none; border:1px solid var(--gold); padding:8px 16px; border-radius:4px; font-size:0.9rem; }
.nav-link:hover { background:var(--gold); color:var(--bg); }
.filter-bar { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:12px; align-items:center; }
.filter-bar label { font-family:'JetBrains Mono',monospace; font-size:0.7rem; color:var(--muted); letter-spacing:1px; text-transform:uppercase; margin-right:8px; }
.filter-btn { font-size:0.85rem; color:var(--text2); background:var(--bg2); border:1px solid var(--border); padding:8px 16px; border-radius:4px; cursor:pointer; }
.filter-btn:hover { border-color:var(--gold); color:var(--text); }
.filter-btn.active { background:var(--gold); color:var(--bg); border-color:var(--gold); font-weight:600; }
.search-bar { margin-bottom:20px; }
.search-bar input { font-size:0.9rem; color:var(--text); background:var(--bg2); border:1px solid var(--border); padding:8px 14px; border-radius:6px; width:260px; }
.search-bar input:focus { outline:none; border-color:var(--gold); }
.squads-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:16px; }
.squad-card { background:var(--bg2); border:1px solid var(--border); border-radius:8px; overflow:hidden; }
.squad-card.hidden { display:none; }
.squad-card-header { font-family:'Oswald',sans-serif; font-size:1rem; padding:12px 16px; background:rgba(244,197,102,0.08); border-bottom:2px solid var(--gold); display:flex; justify-content:space-between; color:var(--gold); }
.squad-list { padding:0; list-style:none; }
.squad-list li { display:flex; justify-content:space-between; padding:10px 16px; border-bottom:1px solid rgba(30,61,80,0.4); }
.squad-list li:last-child { border:none; }
.squad-list li:hover { background:var(--bg-row); }
.shooter-name { font-family:'Oswald',sans-serif; }
.shooter-class { font-family:'JetBrains Mono',monospace; font-size:0.6rem; color:var(--muted); text-transform:uppercase; }
.relay-badge { font-family:'JetBrains Mono',monospace; font-size:0.7rem; padding:3px 10px; border-radius:4px; background:rgba(84,184,219,0.1); color:var(--blue); border:1px solid rgba(84,184,219,0.2); }
.match-header { font-family:'Oswald',sans-serif; font-size:1.3rem; color:var(--gold); padding:20px 0 12px; border-bottom:2px solid var(--gold); margin:24px 0 16px; }
.no-data { text-align:center; padding:60px; color:var(--muted); }
.scroll-badge { display:inline-flex; align-items:center; gap:8px; background:rgba(84,184,219,0.1); border:1px solid rgba(84,184,219,0.3); padding:6px 14px; border-radius:4px; color:var(--blue); font-family:'JetBrains Mono',monospace; font-size:0.75rem; }
.scroll-badge.paused { background:rgba(90,136,153,0.1); border-color:rgba(90,136,153,0.3); color:var(--muted); }
.pause-btn { background:none; border:1px solid currentColor; color:inherit; padding:2px 8px; border-radius:3px; cursor:pointer; font-family:'JetBrains Mono',monospace; font-size:0.65rem; margin-left:4px; }
.pause-btn:hover { opacity:0.8; }
.scroll-controls { display:flex; gap:16px; margin-bottom:16px; align-items:center; }
</style>
</head>
<body>
<div class="container">
  <div class="sticky-top">
  <div class="header">
    <div><h1>🏆 {{ competition.name }} - Squadding</h1></div>
    <a href="/{{ competition.route }}" class="nav-link">← Scores</a>
  </div>
  <div class="scroll-controls">
    <div class="scroll-badge" id="scrollBadge"><span id="scrollText">Auto-Scroll</span> <button class="pause-btn" id="scrollBtn" onclick="toggleAutoScroll()">Pause</button></div>
  </div>
  <div class="filter-bar" id="matchFilter"><label>Match:</label></div>
  <div class="search-bar"><input type="text" id="searchInput" placeholder="Search shooter..." oninput="filterShooters()"></div>
  </div>
  <div id="content"><div class="no-data">Loading squadding...</div></div>
</div>
<script>
let allCompetitors = [], allMatches = [], matchOrder = [], activeMatch = 'all';
const COMP_ROUTE = '{{ competition.route }}';
const STORAGE_KEY = 'squadding_match_order_' + COMP_ROUTE;

function loadMatchOrder() { try { var s = localStorage.getItem(STORAGE_KEY); if(s) return JSON.parse(s); } catch(e){} return null; }
function saveMatchOrder() { try { localStorage.setItem(STORAGE_KEY, JSON.stringify(matchOrder)); } catch(e){} }

async function loadSquadding() {
  try {
    const resp = await fetch('/' + COMP_ROUTE + '/competitors.json?_t=' + Date.now());
    const data = await resp.json();
    allCompetitors = data.competitors || [];
    if (allCompetitors.length === 0) {
      document.getElementById('content').innerHTML = '<div class="no-data">No squadding data yet</div>';
      document.getElementById('matchFilter').style.display = 'none';
      return;
    }
    const matchSet = new Set();
    allCompetitors.forEach(c => { if(c.match) matchSet.add(c.match); });
    allMatches = [...matchSet].sort();
    var saved = loadMatchOrder();
    if (saved && saved.length > 0) {
      matchOrder = saved.filter(m => allMatches.includes(m));
      allMatches.forEach(m => { if(!matchOrder.includes(m)) matchOrder.push(m); });
    } else { matchOrder = [...allMatches]; }
    buildMatchFilter();
    renderSquads();
  } catch(e) {
    document.getElementById('content').innerHTML = '<div class="no-data">Error loading squadding</div>';
  }
}

function buildMatchFilter() {
  const container = document.getElementById('matchFilter');
  let html = '<label>Match:</label><button class="filter-btn active" data-match="all" onclick="setMatchFilter(\\'all\\')">All</button>';
  matchOrder.forEach(m => {
    html += '<button class="filter-btn" data-match="' + m + '" onclick="setMatchFilter(&#39;' + m.replace(/'/g, "&#39;") + '&#39;)">' + m + '</button>';
  });
  container.innerHTML = html;
}

function setMatchFilter(match) {
  activeMatch = match;
  document.querySelectorAll('.filter-btn').forEach(btn => { btn.classList.toggle('active', btn.dataset.match === match); });
  renderSquads();
}

function sortTargets(targets) {
  return targets.sort((a,b) => {
    const na = a.replace(/[^0-9]/g,''), nb = b.replace(/[^0-9]/g,'');
    const pa = a.replace(/[0-9]/g,''), pb = b.replace(/[0-9]/g,'');
    if (pa !== pb) return pa.localeCompare(pb);
    return parseInt(na) - parseInt(nb);
  });
}

function renderSquads(search) {
  const searchLower = (search || document.getElementById('searchInput').value || '').toLowerCase().trim();
  let html = '';
  
  if (activeMatch === 'all') {
    matchOrder.forEach(match => {
      let filtered = allCompetitors.filter(c => c.match === match);
      if (filtered.length === 0) return;
      const targetSet = new Set();
      filtered.forEach(c => { if(c.target) targetSet.add(c.target); });
      const targets = sortTargets([...targetSet]);
      html += '<div class="match-header">' + match + '</div><div class="squads-grid">';
      targets.forEach(target => {
        let shooters = filtered.filter(c => c.target === target);
        shooters.sort((a,b) => (parseInt(a.relay)||0) - (parseInt(b.relay)||0));
        const hasMatch = !searchLower || shooters.some(s => s.name.toLowerCase().includes(searchLower));
        html += '<div class="squad-card' + (hasMatch ? '' : ' hidden') + '">';
        html += '<div class="squad-card-header"><span>🎯 ' + target + '</span><span>' + shooters.length + '</span></div><ul class="squad-list">';
        shooters.forEach(s => {
          const nameMatch = searchLower && s.name.toLowerCase().includes(searchLower);
          html += '<li><div><div class="shooter-name' + (nameMatch ? ' highlight' : '') + '">' + s.name + '</div>';
          html += '<div class="shooter-class">' + (s.class || '') + '</div></div>';
          html += '<span class="relay-badge">R' + (s.relay || '-') + '</span></li>';
        });
        html += '</ul></div>';
      });
      html += '</div>';
    });
  } else {
    let filtered = allCompetitors.filter(c => c.match === activeMatch);
    const targetSet = new Set();
    filtered.forEach(c => { if(c.target) targetSet.add(c.target); });
    const targets = sortTargets([...targetSet]);
    html = '<div class="squads-grid">';
    targets.forEach(target => {
      let shooters = filtered.filter(c => c.target === target);
      shooters.sort((a,b) => (parseInt(a.relay)||0) - (parseInt(b.relay)||0));
      const hasMatch = !searchLower || shooters.some(s => s.name.toLowerCase().includes(searchLower));
      html += '<div class="squad-card' + (hasMatch ? '' : ' hidden') + '">';
      html += '<div class="squad-card-header"><span>🎯 ' + target + '</span><span>' + shooters.length + '</span></div><ul class="squad-list">';
      shooters.forEach(s => {
        const nameMatch = searchLower && s.name.toLowerCase().includes(searchLower);
        html += '<li><div><div class="shooter-name' + (nameMatch ? ' highlight' : '') + '">' + s.name + '</div>';
        html += '<div class="shooter-class">' + (s.class || '') + '</div></div>';
        html += '<span class="relay-badge">R' + (s.relay || '-') + '</span></li>';
      });
      html += '</ul></div>';
    });
    html += '</div>';
  }
  document.getElementById('content').innerHTML = html;
}

function filterShooters() { renderSquads(document.getElementById('searchInput').value); }

var scrolling = true;
var scrollSpeed = 0.25;
var scrollPauseAtEnd = 3000;
var scrollPauseTimer = null;
var scrollAccum = 0;

function doAutoScroll() {
  if (!scrolling) { return; }
  var maxScroll = Math.round(document.documentElement.scrollHeight - window.innerHeight);
  if (maxScroll <= 2) { setTimeout(function() { requestAnimationFrame(doAutoScroll); }, 1000); return; }
  if (Math.round(window.scrollY) >= maxScroll - 1) {
    scrollAccum = 0;
    scrollPauseTimer = setTimeout(function() { window.scrollTo(0, 0); scrollPauseTimer = null; requestAnimationFrame(doAutoScroll); }, scrollPauseAtEnd);
    return;
  }
  scrollAccum += scrollSpeed;
  if (scrollAccum >= 1) {
    var px = Math.floor(scrollAccum);
    scrollAccum -= px;
    window.scrollBy(0, px);
  }
  requestAnimationFrame(doAutoScroll);
}

function toggleAutoScroll() {
  scrolling = !scrolling;
  var badge = document.getElementById('scrollBadge');
  var btn = document.getElementById('scrollBtn');
  var txt = document.getElementById('scrollText');
  if (scrolling) {
    badge.classList.remove('paused');
    txt.textContent = 'Auto-Scroll';
    btn.textContent = 'Pause';
    requestAnimationFrame(doAutoScroll);
  } else {
    badge.classList.add('paused');
    txt.textContent = 'Scroll Paused';
    btn.textContent = 'Resume';
    if (scrollPauseTimer) { clearTimeout(scrollPauseTimer); scrollPauseTimer = null; }
  }
}

loadSquadding().then(function() { requestAnimationFrame(doAutoScroll); });
</script>
<footer style="margin-top:60px;padding:20px;border-top:1px solid #1e3d50;text-align:center;font-size:0.9rem;"><a href="/" style="color:#8ab4c8;text-decoration:none;margin:0 12px;">Home</a><a href="/about" style="color:#8ab4c8;text-decoration:none;margin:0 12px;">About</a><a href="/contact" style="color:#8ab4c8;text-decoration:none;margin:0 12px;">Contact</a></footer></body>
</html>
'''

RANGE_HISTORY_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ range.name }} - History</title>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&family=Barlow+Condensed:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root { --bg:#0c1e2b; --bg2:#122a3a; --gold:#f4c566; --blue:#54b8db; --text:#f0ece4; --text2:#8ab4c8; --muted:#5a8899; --border:#1e3d50; }
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--bg); color:var(--text); font-family:'Barlow Condensed',sans-serif; min-height:100vh; padding:20px; }
.container { max-width:900px; margin:0 auto; }
.header { display:flex; justify-content:space-between; align-items:center; padding:20px 0; border-bottom:1px solid var(--border); margin-bottom:30px; }
.header h1 { font-family:'Oswald',sans-serif; font-size:1.8rem; color:var(--gold); }
.nav-link { color:var(--gold); text-decoration:none; border:1px solid var(--gold); padding:8px 16px; border-radius:4px; }
.nav-link:hover { background:var(--gold); color:var(--bg); }
.calendar { display:grid; grid-template-columns:repeat(auto-fill,minmax(140px,1fr)); gap:12px; }
.date-card { background:var(--bg2); border:1px solid var(--border); border-radius:8px; padding:16px; text-align:center; transition:border-color 0.2s; }
.date-card:hover { border-color:var(--gold); }
.date-card a { color:var(--text); text-decoration:none; display:block; }
.date-card .day { font-family:'Oswald',sans-serif; font-size:1.4rem; color:var(--gold); }
.date-card .month { font-size:0.9rem; color:var(--text2); }
.no-data { text-align:center; padding:60px; color:var(--muted); }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>📅 {{ range.name }}</h1>
    <a href="/" class="nav-link">← Home</a>
  </div>
  <div class="calendar">
    {% for log in shotlogs %}
    <div class="date-card">
      <a href="/range/{{ range.id }}/{{ log.shoot_date.strftime('%Y-%m-%d') }}">
        <div class="day">{{ log.shoot_date.strftime('%d') }}</div>
        <div class="month">{{ log.shoot_date.strftime('%b %Y') }}</div>
      </a>
    </div>
    {% endfor %}
    {% if not shotlogs %}
    <div class="no-data">No shooting history yet</div>
    {% endif %}
  </div>
</div>
<footer style="margin-top:60px;padding:20px;border-top:1px solid #1e3d50;text-align:center;font-size:0.9rem;"><a href="/" style="color:#8ab4c8;text-decoration:none;margin:0 12px;">Home</a><a href="/about" style="color:#8ab4c8;text-decoration:none;margin:0 12px;">About</a><a href="/contact" style="color:#8ab4c8;text-decoration:none;margin:0 12px;">Contact</a></footer></body>
</html>
'''

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
.pm-stat-section { margin-top:16px; padding-top:12px; border-top:1px solid var(--border); }
.pm-stat-section h4 { font-family:"Oswald",sans-serif; color:var(--blue); font-size:0.9rem; margin-bottom:8px; }
.pm-stat-row { display:flex; justify-content:space-between; padding:3px 0; font-family:"JetBrains Mono",monospace; font-size:0.8rem; }
.pm-stat-row .pm-stat-label { color:var(--muted); }
.pm-stat-row .pm-stat-value { color:var(--text); }
.pm-face-info { font-family:"JetBrains Mono",monospace; font-size:0.8rem; color:var(--blue); margin-top:4px; padding:6px 8px; background:rgba(84,184,219,0.1); border:1px solid rgba(84,184,219,0.2); border-radius:4px; text-align:center; }
footer { margin-top:60px; padding:20px; border-top:1px solid var(--border); text-align:center; font-size:0.9rem; }
footer a { color:var(--text2); text-decoration:none; margin:0 12px; }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>{{ range.name }} — {{ date.strftime("%d %B %Y") }}</h1>
    <div style="display:flex;gap:12px;align-items:center;">
      <a href="/range/{{ range.id }}" class="nav-link">← Calendar</a>
      {% if is_admin %}
      <button onclick="clearShotlog()" style="background:#c0392b;color:#fff;border:none;padding:6px 14px;border-radius:4px;cursor:pointer;font-size:0.85rem;">Clear Day</button>
      {% endif %}
    </div>
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
      <tr data-idx="{{ loop.index0 }}" data-target="{{ s.target }}" data-shooter="{{ s.shooter_name }}">
        <td class="target">{{ s.target }}</td>
        <td class="shooter">{{ s.shooter_name }}</td>
        <td class="distance-cell" id="dist-{{ loop.index0 }}">-</td>
        <td>
          <div class="score-cell">
            <span class="score" id="score-{{ loop.index0 }}">--</span>
            <div class="shot-badges" id="badges-{{ loop.index0 }}"></div>
          </div>
        </td>
        <td>
          <button class="plot-btn" onclick="showPlot({{ loop.index0 }})">Plot</button>
          {% if is_admin %}<button class="plot-btn" style="background:#c0392b;color:#fff;margin-left:4px;" onclick="deleteString('{{ s.target }}','{{ s.shooter_name }}',this)">X</button>{% endif %}
        </td>
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
      <div class="pm-face-info" id="pmFaceInfo"></div>
      <div id="pmStatsPanel"></div>
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
{target:"{{ s.target }}",name:"{{ s.shooter_name }}",match:"{{ s.match_name or '' }}",distance:"{{ s.distance or '' }}",shots:{{ s.shot_data | tojson if s.shot_data else "[]" }}},
{% endfor %}
];

function extractDistance(match) {
  if (!match) return null;
  var m = match.match(/(\d{3,4})m?/);
  return m ? parseInt(m[1]) : null;
}

function calcScore(shots) {
  var t = 0, xv = 0;
  shots.forEach(function(s) {
    if (s.isSighter) return;
    var sc = String(s.score).toUpperCase();
    if (sc === "X") { t += 6; xv++; }
    else if (sc === "V") { t += 5; xv++; }
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
      html += '<span class="shot-badge score-' + sc + '">' + sc + '</span>';
    }
  });
  return html;
}

var targetSet = new Set();
stringData.forEach(function(s, i) {
  var scoreEl = document.getElementById("score-" + i);
  var badgeEl = document.getElementById("badges-" + i);
  var distEl = document.getElementById("dist-" + i);
  
  s.distance = s.distance || extractDistance(s.match);
  if (distEl && s.distance) distEl.textContent = s.distance + 'm';
  
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

var targetContainer = document.getElementById('targetFilters');
Array.from(targetSet).sort().forEach(function(t) {
  var btn = document.createElement('button');
  btn.className = 'toggle-btn target-btn active';
  btn.dataset.target = t;
  btn.textContent = t;
  btn.onclick = function() { toggleTarget(this); };
  targetContainer.appendChild(btn);
});

var activeDistances = new Set(['300','400','500','600','700','800','900','1000']);
var activeTargets = new Set(targetSet);

function toggleDistance(btn) {
  var dist = btn.dataset.dist;
  btn.classList.toggle('active');
  if (activeDistances.has(dist)) activeDistances.delete(dist);
  else activeDistances.add(dist);
  applyFilters();
}

function toggleTarget(btn) {
  var target = btn.dataset.target;
  btn.classList.toggle('active');
  if (activeTargets.has(target)) activeTargets.delete(target);
  else activeTargets.add(target);
  applyFilters();
}

function toggleAllDistances() {
  var btns = document.querySelectorAll('#distanceFilters .toggle-btn');
  var allActive = activeDistances.size === 8;
  btns.forEach(function(btn) {
    if (allActive) { btn.classList.remove('active'); activeDistances.delete(btn.dataset.dist); }
    else { btn.classList.add('active'); activeDistances.add(btn.dataset.dist); }
  });
  applyFilters();
}

function toggleAllTargets() {
  var btns = document.querySelectorAll('#targetFilters .toggle-btn');
  var allActive = activeTargets.size === targetSet.size;
  btns.forEach(function(btn) {
    if (allActive) { btn.classList.remove('active'); activeTargets.delete(btn.dataset.target); }
    else { btn.classList.add('active'); activeTargets.add(btn.dataset.target); }
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
    if (shooter && rowShooter.indexOf(shooter) < 0) show = false;
    if (rowTarget && !activeTargets.has(rowTarget)) show = false;
    if (rowDist && !activeDistances.has(rowDist)) show = false;
    
    row.classList.toggle('hidden', !show);
    if (show) visible++;
  });
  
  document.getElementById('resultCount').textContent = visible + ' of ' + stringData.length + ' strings shown';
}

function clearFilters() {
  document.getElementById('filterShooter').value = '';
  document.querySelectorAll('#distanceFilters .toggle-btn').forEach(function(btn) {
    btn.classList.add('active');
    activeDistances.add(btn.dataset.dist);
  });
  document.querySelectorAll('#targetFilters .toggle-btn').forEach(function(btn) {
    btn.classList.add('active');
    activeTargets.add(btn.dataset.target);
  });
  applyFilters();
}

var currentSort = { col: null, asc: true };
function sortTable(col) {
  var tbody = document.querySelector('#resultsTable tbody');
  var rows = Array.from(tbody.querySelectorAll('tr[data-idx]'));
  
  if (currentSort.col === col) currentSort.asc = !currentSort.asc;
  else { currentSort.col = col; currentSort.asc = true; }
  
  document.querySelectorAll('th').forEach(function(th) { th.classList.remove('sorted-asc', 'sorted-desc'); });
  var th = document.querySelector('th[data-sort="' + col + '"]');
  if (th) th.classList.add(currentSort.asc ? 'sorted-asc' : 'sorted-desc');
  
  rows.sort(function(a, b) {
    var aIdx = parseInt(a.dataset.idx), bIdx = parseInt(b.dataset.idx);
    var aVal, bVal;
    if (col === 'score') { aVal = stringData[aIdx].numericScore; bVal = stringData[bIdx].numericScore; }
    else if (col === 'shooter') { aVal = (stringData[aIdx].name || '').toLowerCase(); bVal = (stringData[bIdx].name || '').toLowerCase(); }
    else if (col === 'target') { aVal = (stringData[aIdx].target || '').toLowerCase(); bVal = (stringData[bIdx].target || '').toLowerCase(); }
    else if (col === 'distance') { aVal = stringData[aIdx].distance || 0; bVal = stringData[bIdx].distance || 0; }
    if (aVal < bVal) return currentSort.asc ? -1 : 1;
    if (aVal > bVal) return currentSort.asc ? 1 : -1;
    return 0;
  });
  rows.forEach(function(row) { tbody.appendChild(row); });
}

applyFilters();

var ICFRA={300:{aim:600,X:35,V:70,5:140,4:280,3:420,2:600,tw:1200,th:1200},400:{aim:800,X:46,V:93,5:186,4:373,3:560,2:800,tw:1200,th:1200},500:{aim:1000,X:72,V:145,5:290,4:660,3:1000,2:1320,tw:1800,th:1800},600:{aim:1000,X:80,V:160,5:320,4:660,3:1000,2:1320,tw:1800,th:1800},700:{aim:1120,X:127,V:255,5:510,4:815,3:1120,2:1830,tw:1800,th:1800},800:{aim:1120,X:127,V:255,5:510,4:815,3:1120,2:1830,tw:2400,th:1800},900:{aim:1120,X:127,V:255,5:510,4:815,3:1120,2:1830,tw:2400,th:1800}};
var SHOT_COLORS={"X":"#f4c566","V":"#5cc9a7","6":"#54b8db","5":"#8ab4c8","4":"#d4cdb8","3":"#e8985a","2":"#e8706a","1":"#ff5555","0":"#ff3333"};
var pmShots=[],pmFace=null,pmViewX=0,pmViewY=0,pmViewScale=1,pmCanvasW=600,pmCanvasH=600,pmDragging=false,pmDragSX,pmDragSY,pmDragVX,pmDragVY;

function calcStats(shots, distance) {
  var scoring = shots.filter(function(s) { return !s.isSighter; });
  var result = { hasVelocity: false, hasGroup: false };
  // Velocity stats
  var velocities = [];
  scoring.forEach(function(s) {
    var v = parseFloat(s.v);
    if (!isNaN(v) && v > 0) velocities.push(v);
  });
  if (velocities.length >= 2) {
    result.hasVelocity = true;
    var vMin = Math.min.apply(null, velocities);
    var vMax = Math.max.apply(null, velocities);
    var vSum = velocities.reduce(function(a, b) { return a + b; }, 0);
    var vAvg = vSum / velocities.length;
    var vVariance = velocities.reduce(function(a, b) { return a + (b - vAvg) * (b - vAvg); }, 0) / velocities.length;
    result.vMin = vMin.toFixed(0);
    result.vMax = vMax.toFixed(0);
    result.vAvg = vAvg.toFixed(0);
    result.vES = (vMax - vMin).toFixed(0);
    result.vSD = Math.sqrt(vVariance).toFixed(1);
  }
  // Group stats (x,y in mm)
  var xyShots = scoring.filter(function(s) { return s.x !== undefined && s.y !== undefined; });
  if (xyShots.length >= 2) {
    result.hasGroup = true;
    var cx = 0, cy = 0;
    xyShots.forEach(function(s) { cx += s.x; cy += s.y; });
    cx /= xyShots.length; cy /= xyShots.length;
    // Mean radius
    var totalDist = 0;
    xyShots.forEach(function(s) {
      totalDist += Math.sqrt((s.x - cx) * (s.x - cx) + (s.y - cy) * (s.y - cy));
    });
    var meanR = totalDist / xyShots.length;
    result.meanRadiusMM = meanR.toFixed(1);
    // Extreme spread (max distance between any two shots)
    var maxDist = 0;
    for (var i = 0; i < xyShots.length; i++) {
      for (var j = i + 1; j < xyShots.length; j++) {
        var d = Math.sqrt((xyShots[i].x - xyShots[j].x) * (xyShots[i].x - xyShots[j].x) + (xyShots[i].y - xyShots[j].y) * (xyShots[i].y - xyShots[j].y));
        if (d > maxDist) maxDist = d;
      }
    }
    result.groupSpreadMM = maxDist.toFixed(1);
    // MOA conversion
    var distM = parseInt(distance) || 800;
    result.meanRadiusMOA = (meanR / distM * 3.438).toFixed(2);
    result.groupSpreadMOA = (maxDist / distM * 3.438).toFixed(2);
  }
  return result;
}

function renderStats(stats) {
  var html = '';
  if (stats.hasGroup) {
    html += '<div class="pm-stat-section"><h4>Group</h4>';
    html += '<div class="pm-stat-row"><span class="pm-stat-label">Mean Radius</span><span class="pm-stat-value">' + stats.meanRadiusMM + ' mm</span></div>';
    html += '<div class="pm-stat-row"><span class="pm-stat-label"></span><span class="pm-stat-value">' + stats.meanRadiusMOA + ' MOA</span></div>';
    html += '<div class="pm-stat-row"><span class="pm-stat-label">Ext. Spread</span><span class="pm-stat-value">' + stats.groupSpreadMM + ' mm</span></div>';
    html += '<div class="pm-stat-row"><span class="pm-stat-label"></span><span class="pm-stat-value">' + stats.groupSpreadMOA + ' MOA</span></div>';
    html += '</div>';
  }
  if (stats.hasVelocity) {
    html += '<div class="pm-stat-section"><h4>Velocity</h4>';
    html += '<div class="pm-stat-row"><span class="pm-stat-label">Avg</span><span class="pm-stat-value">' + stats.vAvg + '</span></div>';
    html += '<div class="pm-stat-row"><span class="pm-stat-label">Min / Max</span><span class="pm-stat-value">' + stats.vMin + ' / ' + stats.vMax + '</span></div>';
    html += '<div class="pm-stat-row"><span class="pm-stat-label">ES</span><span class="pm-stat-value">' + stats.vES + '</span></div>';
    html += '<div class="pm-stat-row"><span class="pm-stat-label">SD</span><span class="pm-stat-value">' + stats.vSD + '</span></div>';
    html += '</div>';
  }
  return html;
}
function parseFace(str){var m=str.match(/(\d+)m/);var dist=m?parseInt(m[1]):800;var isTR=/Target Rifle/i.test(str);var d=ICFRA[dist]||ICFRA[800];var aimR=d.aim/2;var rings=isTR?[{label:"V",r:d.X/2},{label:"V",r:d.V/2},{label:"5",r:d[5]/2},{label:"4",r:d[4]/2},{label:"3",r:d[3]/2},{label:"2",r:d[2]/2}]:[{label:"X",r:d.X/2},{label:"6",r:d.V/2},{label:"5",r:d[5]/2},{label:"4",r:d[4]/2},{label:"3",r:d[3]/2},{label:"2",r:d[2]/2}];return{dist:dist,d:d,rings:rings,isTR:isTR,aimR:aimR,tw:d.tw,th:d.th};}
function showPlot(idx){var s=stringData[idx];if(!s||!s.shots||!s.shots.length){alert("No shot data");return;}pmShots=s.shots;pmFace=parseFace(s.match||"800m");pmViewX=0;pmViewY=0;pmViewScale=1;document.getElementById("pmTitle").textContent=s.name;var faceType=pmFace.isTR?"Target Rifle":"F-Class";var faceLabel=pmFace.dist+"m "+faceType;document.getElementById("pmSub").textContent=calcScore(s.shots).display+" \u2022 "+faceLabel;document.getElementById("pmFaceInfo").textContent=faceLabel;var stats=calcStats(s.shots,pmFace.dist);document.getElementById("pmStatsPanel").innerHTML=renderStats(stats);var html="";pmShots.forEach(function(shot){var cls=shot.isSighter?" class='sighter'":"";var lbl=shot.isSighter?"S"+shot.id.replace("S",""):shot.id;html+="<li"+cls+"><span>"+lbl+"</span><span>"+shot.score+"</span></li>";});document.getElementById("pmShotList").innerHTML=html;document.getElementById("plotModal").classList.add("active");document.body.style.overflow="hidden";setTimeout(function(){pmDraw();pmFitShots();},50);}
function closePlot(){document.getElementById("plotModal").classList.remove("active");document.body.style.overflow="";}
function pmDraw(){var wrap=document.getElementById("pmCanvasWrap");var canvas=document.getElementById("pmCanvas");var ctx=canvas.getContext("2d");var dpr=window.devicePixelRatio||1;var rect=wrap.getBoundingClientRect();pmCanvasW=rect.width;pmCanvasH=rect.height;canvas.width=pmCanvasW*dpr;canvas.height=pmCanvasH*dpr;canvas.style.width=pmCanvasW+"px";canvas.style.height=pmCanvasH+"px";ctx.setTransform(dpr,0,0,dpr,0,0);if(!pmFace)return;var f=pmFace;var maxDim=Math.max(f.tw,f.th)/2*1.08;var baseScale=Math.min(pmCanvasW,pmCanvasH)/2/maxDim;var scale=baseScale*pmViewScale;var cx=pmCanvasW/2+pmViewX,cy=pmCanvasH/2+pmViewY;var mm2px=function(mx,my){return[cx+mx*scale,cy-my*scale];};var mm2r=function(mm){return mm*scale;};ctx.fillStyle="#0a1820";ctx.fillRect(0,0,pmCanvasW,pmCanvasH);var tl=mm2px(-f.tw/2,f.th/2);ctx.fillStyle="#e8e4da";ctx.fillRect(tl[0],tl[1],mm2r(f.tw),mm2r(f.th));for(var i=f.rings.length-1;i>=0;i--){var ring=f.rings[i];if(ring.r>f.aimR){ctx.beginPath();ctx.arc(cx,cy,mm2r(ring.r),0,Math.PI*2);ctx.strokeStyle="#222";ctx.lineWidth=Math.max(1.5,mm2r(3));ctx.stroke();}}ctx.beginPath();ctx.arc(cx,cy,mm2r(f.aimR),0,Math.PI*2);ctx.fillStyle="#1a1a1a";ctx.fill();for(var i=f.rings.length-1;i>=0;i--){var ring=f.rings[i];if(ring.r<=f.aimR&&ring.r>0){ctx.beginPath();ctx.arc(cx,cy,mm2r(ring.r),0,Math.PI*2);ctx.strokeStyle="rgba(255,255,255,0.55)";ctx.lineWidth=Math.max(0.8,mm2r(2));ctx.stroke();}}for(var ri=0;ri<f.rings.length;ri++){var rng=f.rings[ri];if(rng.r>0){var lblY=cy-mm2r(rng.r);var fs2=Math.max(9,Math.min(14,mm2r(rng.r*0.18)));ctx.font="bold "+fs2+"px JetBrains Mono";ctx.textAlign="center";ctx.textBaseline="bottom";if(rng.r<=f.aimR){ctx.fillStyle="rgba(255,255,255,0.6)";}else{ctx.fillStyle="rgba(0,0,0,0.5)";}ctx.fillText(rng.label,cx,lblY-2);}}pmShots.forEach(function(shot){var sp=mm2px(shot.x,shot.y);var baseR=shot.isSighter?4:5.5;var dotR=baseR*Math.max(0.7,Math.min(2.5,1/Math.sqrt(pmViewScale)*1.8));var sc=String(shot.score).toUpperCase();var color=shot.isSighter?"rgba(200,200,200,0.5)":(SHOT_COLORS[sc]||"#888");if(!shot.isSighter){ctx.beginPath();ctx.arc(sp[0],sp[1],dotR+3,0,Math.PI*2);ctx.fillStyle="rgba(0,0,0,0.25)";ctx.fill();}ctx.beginPath();ctx.arc(sp[0],sp[1],dotR,0,Math.PI*2);ctx.fillStyle=color;ctx.fill();ctx.strokeStyle=shot.isSighter?"rgba(255,255,255,0.2)":"rgba(0,0,0,0.5)";ctx.lineWidth=0.8;ctx.stroke();if(!shot.isSighter){var fs=Math.max(7,Math.min(12,10/Math.sqrt(pmViewScale)*1.5));ctx.fillStyle=color;ctx.globalAlpha=0.85;ctx.font="bold "+fs+"px JetBrains Mono";ctx.textAlign="left";ctx.textBaseline="middle";ctx.fillText(shot.id,sp[0]+dotR+3,sp[1]+1);ctx.globalAlpha=1;}});}
function pmResetZoom(){pmViewX=0;pmViewY=0;pmViewScale=1;pmDraw();}
function pmFitShots(){if(!pmShots.length||!pmFace)return;var minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity;pmShots.forEach(function(s){if(s.x<minX)minX=s.x;if(s.x>maxX)maxX=s.x;if(s.y<minY)minY=s.y;if(s.y>maxY)maxY=s.y;});var span=Math.max((maxX-minX)||100,(maxY-minY)||100)*1.5;var maxDim=Math.max(pmFace.tw,pmFace.th)/2*1.08;pmViewScale=Math.min((maxDim*2)/span,40);var centX=(minX+maxX)/2,centY=(minY+maxY)/2;var baseScale=Math.min(pmCanvasW,pmCanvasH)/2/maxDim;pmViewX=-centX*baseScale*pmViewScale;pmViewY=centY*baseScale*pmViewScale;pmDraw();}
function pmZoomIn(){pmViewScale=Math.min(100,pmViewScale*1.5);pmDraw();}
function pmZoomOut(){pmViewScale=Math.max(0.3,pmViewScale/1.5);pmDraw();}
(function(){var wrap=document.getElementById("pmCanvasWrap");wrap.addEventListener("wheel",function(e){e.preventDefault();pmViewScale=Math.max(0.3,Math.min(100,pmViewScale*(e.deltaY<0?1.15:1/1.15)));pmDraw();},{passive:false});wrap.addEventListener("mousedown",function(e){pmDragging=true;pmDragSX=e.clientX;pmDragSY=e.clientY;pmDragVX=pmViewX;pmDragVY=pmViewY;});window.addEventListener("mousemove",function(e){if(pmDragging){pmViewX=pmDragVX+(e.clientX-pmDragSX);pmViewY=pmDragVY+(e.clientY-pmDragSY);pmDraw();}});window.addEventListener("mouseup",function(){pmDragging=false;});})();
function clearShotlog() {
  if (!confirm('Delete ALL club scores for this day?')) return;
  if (!confirm('FINAL WARNING: This will permanently delete all strings. Click OK to proceed.')) return;
  fetch('/api/admin/range/{{ range.id }}/{{ date.strftime("%Y-%m-%d") }}/clear-shotlog', {method:'POST'})
    .then(function(r){return r.json();}).then(function(d){
      if(d.success){alert(d.message);location.reload();}else{alert(d.error||'Failed');}
    });
}
function deleteString(target, shooter, btn) {
  if (!confirm('Delete ' + shooter + ' on ' + target + '?')) return;
  fetch('/api/admin/range/{{ range.id }}/{{ date.strftime("%Y-%m-%d") }}/delete-string', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({target:target, shooter:shooter})
  }).then(function(r){return r.json();}).then(function(d){
    if(d.success){btn.closest('tr').remove();}else{alert(d.error||'Failed');}
  });
}
</script>
</body>
</html>
'''



# ══════════════════════════════════════════════
#  ABOUT & CONTACT PAGES
# ══════════════════════════════════════════════

@app.route('/about')
def about_page():
    return render_template_string(ABOUT_HTML)

@app.route('/contact')
def contact_page():
    return render_template_string(CONTACT_HTML)

ABOUT_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>About - SM Scores</title>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=Barlow+Condensed:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root { --bg:#0c1e2b; --bg2:#122a3a; --gold:#f4c566; --blue:#54b8db; --text:#f0ece4; --text2:#8ab4c8; --border:#1e3d50; }
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--bg); color:var(--text); font-family:"Barlow Condensed",sans-serif; min-height:100vh; padding:40px 20px; }
.container { max-width:800px; margin:0 auto; }
h1 { font-family:"Oswald",sans-serif; color:var(--gold); margin-bottom:24px; font-size:2rem; }
h2 { font-family:"Oswald",sans-serif; color:var(--gold); margin:32px 0 16px; font-size:1.4rem; }
p { color:var(--text2); line-height:1.7; margin-bottom:16px; font-size:1.05rem; }
.back { color:var(--gold); text-decoration:none; display:inline-block; margin-bottom:24px; border:1px solid var(--gold); padding:8px 16px; border-radius:4px; }
.back:hover { background:var(--gold); color:var(--bg); }
.feature-box { background:var(--bg2); border:1px solid var(--border); border-radius:8px; padding:20px; margin:16px 0; }
.feature-box h3 { color:var(--gold); margin-bottom:8px; font-family:"Oswald",sans-serif; }
ul { color:var(--text2); margin-left:24px; line-height:1.8; }
</style>
</head>
<body>
<div class="container">
  <a href="/" class="back">← Home</a>
  <h1>🎯 About SM Scores</h1>
  
  <p>SM Scores is a free, open-source live scoring system for precision rifle competitions using ShotMarker electronic targets.</p>
  
  <h2>How It Works</h2>
  
  <div class="feature-box">
    <h3>1. At the Range</h3>
    <p>A Raspberry Pi connects to your ShotMarker wireless network and automatically scrapes scores every 15-30 seconds.</p>
  </div>
  
  <div class="feature-box">
    <h3>2. To the Cloud</h3>
    <p>The Pi pushes score data to this cloud server via mobile hotspot or range WiFi, making scores available to anyone with internet.</p>
  </div>
  
  <div class="feature-box">
    <h3>3. Live Display</h3>
    <p>Spectators, competitors, and coaches can view live scores on any device - phones, tablets, or big screens at the range.</p>
  </div>
  
  <h2>Features</h2>
  <ul>
    <li>Live competition scoreboards with auto-refresh</li>
    <li>Squadding displays showing target assignments</li>
    <li>Historical shotlog archive by range and date</li>
    <li>Support for multiple ShotMarker units</li>
    <li>Works with F-Class, F/TR, and other disciplines</li>
  </ul>
  
</div>
<footer style="margin-top:60px;padding:20px;border-top:1px solid #1e3d50;text-align:center;font-size:0.9rem;"><a href="/" style="color:#8ab4c8;text-decoration:none;margin:0 12px;">Home</a><a href="/about" style="color:#8ab4c8;text-decoration:none;margin:0 12px;">About</a><a href="/contact" style="color:#8ab4c8;text-decoration:none;margin:0 12px;">Contact</a></footer></body>
</html>
'''

CONTACT_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Contact - SM Scores</title>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=Barlow+Condensed:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root { --bg:#0c1e2b; --bg2:#122a3a; --gold:#f4c566; --blue:#54b8db; --green:#5cc9a7; --text:#f0ece4; --text2:#8ab4c8; --border:#1e3d50; }
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--bg); color:var(--text); font-family:"Barlow Condensed",sans-serif; min-height:100vh; padding:40px 20px; }
.container { max-width:500px; margin:0 auto; }
h1 { font-family:"Oswald",sans-serif; color:var(--gold); margin-bottom:24px; font-size:2rem; }
p { color:var(--text2); line-height:1.7; margin-bottom:20px; font-size:1.05rem; }
.back { color:var(--gold); text-decoration:none; display:inline-block; margin-bottom:24px; border:1px solid var(--gold); padding:8px 16px; border-radius:4px; }
.back:hover { background:var(--gold); color:var(--bg); }
.contact-box { background:var(--bg2); border:1px solid var(--border); border-radius:8px; padding:24px; margin:20px 0; }
.contact-box h3 { color:var(--gold); margin-bottom:12px; font-family:"Oswald",sans-serif; }
.contact-box a { color:var(--blue); text-decoration:none; font-size:1.1rem; }
.contact-box a:hover { text-decoration:underline; }
.email-btn { display:inline-block; background:var(--gold); color:var(--bg); padding:14px 28px; border-radius:4px; text-decoration:none; font-weight:600; font-size:1.1rem; margin-top:16px; }
.email-btn:hover { opacity:0.9; }
</style>
</head>
<body>
<div class="container">
  <a href="/" class="back">← Home</a>
  <h1>📬 Contact Us</h1>
  
  <p>Have questions about SM Scores? Want to set up live scoring at your range? We would love to hear from you.</p>
  
  <div class="contact-box">
    <h3>Email</h3>
    <a href="mailto:trent@smscores.com">trent@smscores.com</a>
    <br>
    <a href="mailto:trent@smscores.com" class="email-btn">Send Email</a>
  </div>
  
  <p>We typically respond within 24-48 hours. Please include details about your range and what you are looking to achieve.</p>
  
  <div class="contact-box">
    <h3>For Technical Issues</h3>
    <p style="color:var(--text2); margin:0;">If you are experiencing problems with live scoring during a competition, please include:</p>
    <ul style="color:var(--text2); margin:12px 0 0 20px; line-height:1.8;">
      <li>Competition name</li>
      <li>Time the issue occurred</li>
      <li>Description of the problem</li>
    </ul>
  </div>
</div>
<footer style="margin-top:60px;padding:20px;border-top:1px solid #1e3d50;text-align:center;font-size:0.9rem;"><a href="/" style="color:#8ab4c8;text-decoration:none;margin:0 12px;">Home</a><a href="/about" style="color:#8ab4c8;text-decoration:none;margin:0 12px;">About</a><a href="/contact" style="color:#8ab4c8;text-decoration:none;margin:0 12px;">Contact</a></footer></body>
</html>
'''


COMP_CONTACT_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Contact - {{ competition.name }}</title>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=Barlow+Condensed:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root { --bg:#0c1e2b; --bg2:#122a3a; --gold:#f4c566; --blue:#54b8db; --text:#f0ece4; --text2:#8ab4c8; --border:#1e3d50; }
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--bg); color:var(--text); font-family:"Barlow Condensed",sans-serif; min-height:100vh; padding:40px 20px; }
.container { max-width:500px; margin:0 auto; }
h1 { font-family:"Oswald",sans-serif; color:var(--gold); margin-bottom:24px; font-size:2rem; }
p { color:var(--text2); line-height:1.7; margin-bottom:20px; font-size:1.05rem; white-space:pre-line; }
.back { color:var(--gold); text-decoration:none; display:inline-block; margin-bottom:24px; border:1px solid var(--gold); padding:8px 16px; border-radius:4px; }
.back:hover { background:var(--gold); color:var(--bg); }
.contact-box { background:var(--bg2); border:1px solid var(--border); border-radius:8px; padding:24px; margin:20px 0; }
.contact-box h3 { color:var(--gold); margin-bottom:12px; font-family:"Oswald",sans-serif; }
.contact-box a { color:var(--blue); text-decoration:none; font-size:1.1rem; }
.contact-box a:hover { text-decoration:underline; }
.email-btn { display:inline-block; background:var(--gold); color:var(--bg); padding:14px 28px; border-radius:4px; text-decoration:none; font-weight:600; font-size:1.1rem; margin-top:16px; }
.email-btn:hover { opacity:0.9; }
</style>
</head>
<body>
<div class="container">
  <a href="/{{ competition.route }}" class="back">Back to {{ competition.name }}</a>
  <h1>Contact - {{ competition.name }}</h1>
  {% if competition.contact_info %}
  <p>{{ competition.contact_info }}</p>
  {% endif %}
  {% if competition.contact_email %}
  <div class="contact-box">
    <h3>Email</h3>
    <a href="mailto:{{ competition.contact_email }}">{{ competition.contact_email }}</a>
    <br>
    <a href="mailto:{{ competition.contact_email }}" class="email-btn">Send Email</a>
  </div>
  {% endif %}
  {% if competition.contact_phone %}
  <div class="contact-box">
    <h3>Phone</h3>
    <a href="tel:{{ competition.contact_phone }}">{{ competition.contact_phone }}</a>
  </div>
  {% endif %}
</div>
</body>
</html>
'''

@app.route('/contact-thanks')
def contact_thanks():
    return render_template_string(THANKS_HTML)

THANKS_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Thank You - SM Scores</title>
<style>
:root { --bg:#0c1e2b; --gold:#f4c566; --text:#f0ece4; --text2:#8ab4c8; }
body { background:var(--bg); color:var(--text); font-family:sans-serif; min-height:100vh; display:flex; align-items:center; justify-content:center; text-align:center; padding:20px; }
h1 { color:var(--gold); margin-bottom:16px; }
p { color:var(--text2); margin-bottom:24px; }
a { color:var(--gold); }
</style>
</head>
<body>
<div>
  <h1>✓ Message Sent!</h1>
  <p>Thank you for contacting us. We will get back to you soon.</p>
  <a href="/">← Back to Home</a>
</div>
<footer style="margin-top:60px;padding:20px;border-top:1px solid #1e3d50;text-align:center;font-size:0.9rem;"><a href="/" style="color:#8ab4c8;text-decoration:none;margin:0 12px;">Home</a><a href="/about" style="color:#8ab4c8;text-decoration:none;margin:0 12px;">About</a><a href="/contact" style="color:#8ab4c8;text-decoration:none;margin:0 12px;">Contact</a></footer></body>
</html>
'''


# ══════════════════════════════════════════════
#  PHOTO GALLERY HTML
# ══════════════════════════════════════════════

PHOTO_GALLERY_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Photos - {{ competition.name }}</title>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=Barlow+Condensed:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root { --bg:#0c1e2b; --bg2:#122a3a; --gold:#f4c566; --blue:#54b8db; --green:#5cc9a7; --red:#e74c3c; --text:#f0ece4; --text2:#8ab4c8; --muted:#5a8899; --border:#1e3d50; }
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--bg); color:var(--text); font-family:"Barlow Condensed",sans-serif; min-height:100vh; }
.header { background:var(--bg2); border-bottom:2px solid var(--gold); padding:16px 20px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; }
.header h1 { font-family:"Oswald",sans-serif; color:var(--gold); font-size:1.5rem; }
.nav-links { display:flex; gap:10px; flex-wrap:wrap; }
.nav-link { color:var(--gold); text-decoration:none; border:1px solid var(--gold); padding:6px 14px; border-radius:4px; font-size:0.85rem; }
.nav-link:hover { background:var(--gold); color:var(--bg); }
.container { max-width:1200px; margin:0 auto; padding:20px; }
.upload-bar { display:flex; gap:12px; align-items:center; margin-bottom:24px; flex-wrap:wrap; }
.upload-btn { background:var(--gold); color:var(--bg); border:none; padding:12px 24px; border-radius:4px; font-size:1rem; cursor:pointer; font-family:"Oswald",sans-serif; }
.upload-btn:hover { opacity:0.9; }
.upload-btn:disabled { opacity:0.4; cursor:not-allowed; }
.photo-count { color:var(--text2); font-size:0.9rem; }
.progress-bar { width:200px; height:6px; background:var(--bg2); border-radius:3px; overflow:hidden; display:none; }
.progress-fill { height:100%; background:var(--green); width:0%; transition:width 0.2s; }
.status-msg { color:var(--green); font-size:0.85rem; display:none; }

/* Photo Grid */
.photo-grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(250px, 1fr)); gap:12px; }
.photo-card { position:relative; border-radius:6px; overflow:hidden; cursor:pointer; aspect-ratio:4/3; background:var(--bg2); }
.photo-card img { width:100%; height:100%; object-fit:cover; transition:transform 0.2s; }
.photo-card:hover img { transform:scale(1.03); }
.photo-caption { position:absolute; bottom:0; left:0; right:0; background:linear-gradient(transparent, rgba(0,0,0,0.8)); padding:8px 12px; font-size:0.8rem; color:#fff; }
.no-photos { text-align:center; padding:80px 20px; color:var(--muted); }
.no-photos h2 { font-family:"Oswald",sans-serif; color:var(--text2); margin-bottom:12px; }

/* Lightbox */
.lightbox { display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.95); z-index:1000; justify-content:center; align-items:center; }
.lightbox.active { display:flex; }
.lightbox img { max-width:90vw; max-height:85vh; object-fit:contain; border-radius:4px; }
.lb-close { position:absolute; top:16px; right:20px; color:#fff; font-size:32px; cursor:pointer; background:none; border:none; z-index:1001; }
.lb-nav { position:absolute; top:50%; transform:translateY(-50%); color:#fff; font-size:48px; cursor:pointer; background:none; border:none; padding:20px; opacity:0.6; z-index:1001; }
.lb-nav:hover { opacity:1; }
.lb-prev { left:10px; }
.lb-next { right:10px; }
.lb-caption { position:absolute; bottom:20px; left:0; right:0; text-align:center; color:#ccc; font-size:0.9rem; }
.lb-counter { position:absolute; top:20px; left:20px; color:#888; font-size:0.85rem; }

@media (max-width:600px) {
  .photo-grid { grid-template-columns:repeat(2, 1fr); gap:8px; }
  .lb-nav { font-size:32px; padding:10px; }
  .header h1 { font-size:1.2rem; }
}
</style>
</head>
<body>
<div class="header">
  <h1>{{ competition.name }} &mdash; Photos</h1>
  <div class="nav-links">
    <a href="/{{ competition.route }}" class="nav-link">&larr; Scoreboard</a>
    <a href="/" class="nav-link">Home</a>
  </div>
</div>

<div class="container">
  <div class="upload-bar">
    <button class="upload-btn" onclick="document.getElementById(\'fileInput\').click()">Upload Photos</button>
    <input type="file" id="fileInput" accept="image/*" multiple style="display:none;" onchange="handleFiles(this.files)">
    <span class="photo-count" id="photoCount"></span>
    <div class="progress-bar" id="progressBar"><div class="progress-fill" id="progressFill"></div></div>
    <span class="status-msg" id="statusMsg"></span>
  </div>

  <div class="photo-grid" id="photoGrid"></div>
  <div class="no-photos" id="noPhotos" style="display:none;">
    <h2>No photos yet</h2>
    <p>Be the first to upload photos from the day!</p>
  </div>
</div>

<!-- Lightbox -->
<div class="lightbox" id="lightbox" onclick="closeLightbox(event)">
  <button class="lb-close" onclick="closeLightbox()">&times;</button>
  <button class="lb-nav lb-prev" onclick="navPhoto(-1, event)">&lsaquo;</button>
  <img id="lbImage" src="" alt="">
  <button class="lb-nav lb-next" onclick="navPhoto(1, event)">&rsaquo;</button>
  <div class="lb-caption" id="lbCaption"></div>
  <div class="lb-counter" id="lbCounter"></div>
</div>

<script>
var photos = [];
var currentPhoto = 0;
var compRoute = \'{{ competition.route }}\';

function loadPhotos() {
  fetch(\'/\' + compRoute + \'/photos/json?_t=\' + Date.now())
    .then(function(r) { return r.json(); })
    .then(function(data) {
      photos = data;
      renderGrid();
    });
}

function renderGrid() {
  var grid = document.getElementById(\'photoGrid\');
  var noPhotos = document.getElementById(\'noPhotos\');
  var countEl = document.getElementById(\'photoCount\');

  if (!photos.length) {
    grid.innerHTML = \'\';
    noPhotos.style.display = \'block\';
    countEl.textContent = \'\';
    return;
  }
  noPhotos.style.display = \'none\';
  countEl.textContent = photos.length + \' photo\' + (photos.length !== 1 ? \'s\' : \'\');

  var html = \'\';
  photos.forEach(function(p, i) {
    html += \'<div class="photo-card" onclick="openLightbox(\' + i + \')">\';
    html += \'<img src="\' + p.url + \'" loading="lazy" alt="">\';
    if (p.caption) html += \'<div class="photo-caption">\' + p.caption + \'</div>\';
    html += \'</div>\';
  });
  grid.innerHTML = html;
}

// --- Lightbox ---
function openLightbox(index) {
  currentPhoto = index;
  showLightboxPhoto();
  document.getElementById(\'lightbox\').classList.add(\'active\');
  document.body.style.overflow = \'hidden\';
}

function closeLightbox(e) {
  if (e && e.target !== e.currentTarget && !e.target.classList.contains(\'lb-close\')) return;
  document.getElementById(\'lightbox\').classList.remove(\'active\');
  document.body.style.overflow = \'\';
}

function navPhoto(dir, e) {
  if (e) e.stopPropagation();
  currentPhoto = (currentPhoto + dir + photos.length) % photos.length;
  showLightboxPhoto();
}

function showLightboxPhoto() {
  var p = photos[currentPhoto];
  document.getElementById(\'lbImage\').src = p.url;
  document.getElementById(\'lbCaption\').textContent = p.caption || \'\';
  document.getElementById(\'lbCounter\').textContent = (currentPhoto + 1) + \' / \' + photos.length;
}

// Keyboard nav
document.addEventListener(\'keydown\', function(e) {
  if (!document.getElementById(\'lightbox\').classList.contains(\'active\')) return;
  if (e.key === \'Escape\') closeLightbox();
  if (e.key === \'ArrowLeft\') navPhoto(-1);
  if (e.key === \'ArrowRight\') navPhoto(1);
});

// Swipe support
var touchStartX = 0;
document.getElementById(\'lightbox\').addEventListener(\'touchstart\', function(e) {
  touchStartX = e.changedTouches[0].screenX;
});
document.getElementById(\'lightbox\').addEventListener(\'touchend\', function(e) {
  var diff = e.changedTouches[0].screenX - touchStartX;
  if (Math.abs(diff) > 50) {
    navPhoto(diff > 0 ? -1 : 1);
  }
});

// --- Upload with client-side resize ---
var MAX_SIZE = 800;
var QUALITY = 0.70;

function handleFiles(files) {
  if (!files.length) return;
  var total = files.length;
  var done = 0;
  var bar = document.getElementById(\'progressBar\');
  var fill = document.getElementById(\'progressFill\');
  var status = document.getElementById(\'statusMsg\');
  bar.style.display = \'block\';
  fill.style.width = \'0%\';
  status.style.display = \'inline\';
  status.textContent = \'Uploading...\';

  Array.from(files).forEach(function(file) {
    resizeAndUpload(file, function() {
      done++;
      fill.style.width = Math.round(done / total * 100) + \'%\';
      if (done === total) {
        status.textContent = done + \' photo\' + (done > 1 ? \'s\' : \'\') + \' uploaded!\';
        setTimeout(function() {
          bar.style.display = \'none\';
          status.style.display = \'none\';
        }, 3000);
        loadPhotos();
      }
    });
  });
  // Reset file input so same files can be selected again
  document.getElementById(\'fileInput\').value = \'\';
}

function resizeAndUpload(file, callback) {
  var reader = new FileReader();
  reader.onload = function(e) {
    var img = new Image();
    img.onload = function() {
      var w = img.width, h = img.height;
      if (w > MAX_SIZE || h > MAX_SIZE) {
        if (w > h) { h = Math.round(h * MAX_SIZE / w); w = MAX_SIZE; }
        else { w = Math.round(w * MAX_SIZE / h); h = MAX_SIZE; }
      }
      var canvas = document.createElement(\'canvas\');
      canvas.width = w;
      canvas.height = h;
      canvas.getContext(\'2d\').drawImage(img, 0, 0, w, h);
      canvas.toBlob(function(blob) {
        var fd = new FormData();
        fd.append(\'photo\', blob, \'photo.jpg\');
        fetch(\'/\' + compRoute + \'/photos/upload\', { method: \'POST\', body: fd })
          .then(function(r) {
            if (!r.ok) return r.json().then(function(d) { throw new Error(d.error || \'Upload failed: \' + r.status); });
            return r.json();
          })
          .then(function(data) {
            if (data.error) { alert(\'Upload error: \' + data.error); }
            callback();
          })
          .catch(function(err) { alert(\'Upload failed: \' + err.message); callback(); });
      }, \'image/jpeg\', QUALITY);
    };
    img.src = e.target.result;
  };
  reader.readAsDataURL(file);
}

loadPhotos();
</script>
</body>
</html>
'''

# ══════════════════════════════════════════════
#  SQUADDING UPLOAD
# ══════════════════════════════════════════════

@app.route('/<comp_route>/upload-squadding', methods=['GET', 'POST'])
def upload_squadding(comp_route):
    """Upload squadding CSV or JSON for a competition"""
    comp = Competition.query.filter_by(route=comp_route).first()
    if not comp:
        return "Competition not found", 404
    
    if request.method == 'GET':
        return render_template_string(SQUADDING_UPLOAD_HTML, comp=comp)
    
    # Check for pasted JSON first
    pasted_json = request.form.get('pasted_json', '').strip()
    if pasted_json:
        try:
            import json as json_mod
            data = json_mod.loads(pasted_json)
            competitors_list = data.get('competitors', [])
            if not competitors_list:
                return "No competitors in JSON", 400
            
            Competitor.query.filter_by(competition_id=comp.id).delete()
            
            count = 0
            for c in competitors_list:
                name = c.get('name', '').strip()
                if not name:
                    continue
                competitor = Competitor(
                    competition_id=comp.id,
                    name=name,
                    class_name=c.get('class', '').strip(),
                    match=c.get('match', '').strip(),
                    relay=c.get('relay', '').strip(),
                    target=c.get('target', '').strip(),
                    position=c.get('position', '').strip()
                )
                db.session.add(competitor)
                count += 1
            
            db.session.commit()
            return redirect(f'/{comp_route}/squadding')
        except Exception as e:
            db.session.rollback()
            return f"JSON error: {e}", 400
    
    # Handle file upload (CSV)
    if 'file' not in request.files or not request.files['file'].filename:
        return "No file or JSON provided", 400
    
    file = request.files['file']
    try:
        file_content = file.read().decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(file_content))
        Competitor.query.filter_by(competition_id=comp.id).delete()
        count = 0
        current_match = ''
        for row in reader:
            name = row.get('user', '').strip()
            if not name:
                continue
            row_match = row.get('match', '').strip()
            if row_match:
                current_match = row_match
            competitor = Competitor(
                competition_id=comp.id,
                name=name,
                class_name=row.get('class', '').strip(),
                match=current_match,
                relay=row.get('relay', '').strip(),
                target=row.get('target', '').strip()
            )
            db.session.add(competitor)
            count += 1
        db.session.commit()
        return redirect(f'/{comp_route}/squadding')
    except Exception as e:
        db.session.rollback()
        return f"CSV parse error: {e}", 400


SQUADDING_UPLOAD_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Upload Squadding - {{ comp.name }}</title>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=Barlow+Condensed:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root { --bg:#0c1e2b; --bg2:#122a3a; --gold:#f4c566; --blue:#54b8db; --green:#5cc9a7; --red:#e74c3c; --text:#f0ece4; --text2:#8ab4c8; --muted:#5a8899; --border:#1e3d50; }
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--bg); color:var(--text); font-family:"Barlow Condensed",sans-serif; min-height:100vh; padding:40px 20px; }
.container { max-width:900px; margin:0 auto; }
h1 { font-family:"Oswald",sans-serif; color:var(--gold); margin-bottom:20px; }
h2 { font-family:"Oswald",sans-serif; color:var(--gold); font-size:1.2rem; margin:0 0 15px; }
.upload-box { background:var(--bg2); border:1px solid var(--border); border-radius:8px; padding:24px; margin-bottom:20px; }
textarea { width:100%; background:var(--bg); border:1px solid var(--border); border-radius:4px; color:var(--text); padding:12px; font-family:monospace; font-size:0.85rem; resize:vertical; }
textarea:focus { outline:none; border-color:var(--gold); }
textarea.script { height:60px; font-size:0.72rem; }
textarea.paste { height:120px; }
input[type="file"] { margin:15px 0; }
button { background:var(--gold); color:var(--bg); border:none; padding:10px 20px; border-radius:4px; font-size:0.95rem; cursor:pointer; font-family:"Oswald",sans-serif; }
button:hover { opacity:0.9; }
.btn-copy { background:var(--blue); padding:8px 16px; font-size:0.85rem; }
.btn-clear { background:var(--red); padding:8px 16px; font-size:0.85rem; }
.btn-add { background:var(--green); }
.btn-upload { background:var(--gold); font-size:1.1rem; padding:14px 32px; }
.btn-upload:disabled { opacity:0.4; cursor:not-allowed; }
.back { color:var(--gold); text-decoration:none; display:inline-block; margin-bottom:20px; border:1px solid var(--gold); padding:8px 16px; border-radius:4px; }
.back:hover { background:var(--gold); color:var(--bg); }
p { color:var(--text2); margin-bottom:12px; font-size:0.9rem; }
code { background:var(--bg); padding:2px 6px; border-radius:3px; color:var(--blue); font-size:0.85rem; }
.steps { background:var(--bg); padding:16px; border-radius:4px; margin-bottom:16px; }
.steps ol { margin-left:20px; }
.steps li { margin-bottom:8px; color:var(--text2); }
.copy-msg { color:var(--green); font-size:0.85rem; margin-left:12px; display:none; }
.divider { border-top:1px solid var(--border); margin:30px 0; text-align:center; position:relative; }
.divider span { background:var(--bg); padding:0 15px; position:relative; top:-10px; color:var(--muted); font-size:0.8rem; }
.match-badges { display:flex; flex-wrap:wrap; gap:8px; margin:15px 0; }
.match-badge { background:var(--bg); border:1px solid var(--green); border-radius:20px; padding:6px 14px; font-size:0.85rem; color:var(--green); }
.match-badge .count { font-weight:600; color:var(--gold); margin-left:4px; }
.preview-table { width:100%; border-collapse:collapse; margin-top:12px; font-size:0.85rem; }
.preview-table th { text-align:left; padding:8px 10px; border-bottom:2px solid var(--border); color:var(--gold); font-family:"Oswald",sans-serif; font-size:0.8rem; text-transform:uppercase; }
.preview-table td { padding:6px 10px; border-bottom:1px solid var(--border); color:var(--text2); }
.preview-table tr:hover td { background:var(--bg); }
.preview-summary { display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; }
.total-count { font-family:"Oswald",sans-serif; color:var(--gold); font-size:1.1rem; }
.status-msg { padding:10px 16px; border-radius:4px; margin:10px 0; font-size:0.9rem; display:none; }
.status-msg.success { display:block; background:#5cc9a722; border:1px solid var(--green); color:var(--green); }
.status-msg.error { display:block; background:#e74c3c22; border:1px solid var(--red); color:var(--red); }
.btn-row { display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
</style>
</head>
<body>
<div class="container">
  <a href="/{{ comp.route }}/squadding" class="back">&larr; Back to Squadding</a>
  <h1>Upload Squadding &mdash; {{ comp.name }}</h1>

  <!-- STEP 1: CONSOLE SCRIPT -->
  <div class="upload-box">
    <h2>Step 1: Export from ShotMarker</h2>
    <div class="steps">
      <ol>
        <li>Open ShotMarker web interface (<code>192.168.100.1</code>)</li>
        <li>Navigate to <strong>Match 1</strong></li>
        <li>Press <strong>F12</strong> &rarr; Console tab</li>
        <li>Paste the script below and press Enter</li>
        <li>Navigate to <strong>Match 2</strong>, paste the script again (it accumulates!)</li>
        <li>Repeat for all matches &mdash; each run adds new competitors</li>
        <li>After the last match, right-click the console output and <strong>Copy string contents</strong></li>
      </ol>
    </div>
    <p>
      <strong>Export Script:</strong>
      <button class="btn-copy" onclick="copyScript()">Copy Script</button>
      <button class="btn-copy" onclick="copyReset()" style="background:var(--red);">Copy Reset</button>
      <span class="copy-msg" id="copyMsg"></span>
    </p>
    <textarea class="script" id="exportScript" readonly>(function(){if(typeof data===\'undefined\'||!data.users||!data.squadding){alert(\'ShotMarker data not found!\');return;}var c=[];Object.entries(data.squadding).forEach(function([key,squad]){var parts=key.split(\',\');if(parts.length!==2)return;var user=data.users[parts[1]]||{};if(!user.name||user.name===\'Unknown\')return;var match=data.matches[parts[0]]||{};var classInfo=data.classes?data.classes[user.class]||{}:{};if(typeof squad!==\'object\'||squad===null)squad={};var frameInfo=data.frames[squad.frame_id]||{};c.push({name:user.name,class:classInfo.name||user.class||\'\',relay:String(squad.relay||\'\'),target:frameInfo.name||String(squad.frame_id||\'\'),match:match.name||\'\',position:String(squad.position||\'\')});});var stored=JSON.parse(localStorage.getItem(\'sm_export\')||\'[]\');var existing={};stored.forEach(function(e){existing[e.name+\'|\'+e.match]=true;});var added=0;c.forEach(function(e){if(!existing[e.name+\'|\'+e.match]){stored.push(e);added++;}});localStorage.setItem(\'sm_export\',JSON.stringify(stored));var matches={};stored.forEach(function(e){matches[e.match]=(matches[e.match]||0)+1;});var summary=Object.entries(matches).map(function([m,n]){return m+\': \'+n;}).join(\', \');console.log(JSON.stringify({competitors:stored}));alert(\'Added \'+added+\' from this match.\\nTotal: \'+stored.length+\' competitors (\'+summary+\')\\n\\nNavigate to next match and run again, or copy from console.\');})();</textarea>
    <p style="margin-top:10px; font-size:0.8rem; color:var(--muted);">
      The script remembers previous matches. Use <strong>Copy Reset</strong> to get a command that clears the memory before starting fresh.
    </p>
  </div>

  <!-- STEP 2: PASTE & ACCUMULATE -->
  <div class="upload-box">
    <h2>Step 2: Paste &amp; Build Squadding</h2>
    <p>Paste the JSON output below. You can paste <strong>multiple times</strong> (once per match) &mdash; competitors accumulate. Duplicates are ignored.</p>
    <textarea class="paste" id="pasteArea" placeholder="Paste JSON here"></textarea>
    <div style="margin-top:12px;" class="btn-row">
      <button class="btn-add" onclick="addFromPaste()">+ Add Competitors</button>
      <button class="btn-clear" onclick="clearAll()">Clear All</button>
    </div>
    <div class="status-msg" id="statusMsg"></div>
  </div>

  <!-- PREVIEW -->
  <div class="upload-box" id="previewBox" style="display:none;">
    <div class="preview-summary">
      <span class="total-count" id="totalCount">0 competitors</span>
      <button class="btn-upload" id="uploadBtn" onclick="uploadAll()">Upload All</button>
    </div>
    <div class="match-badges" id="matchBadges"></div>
    <div style="max-height:400px; overflow-y:auto;">
      <table class="preview-table">
        <thead><tr><th>#</th><th>Name</th><th>Class</th><th>Match</th><th>Relay</th><th>Target</th></tr></thead>
        <tbody id="previewBody"></tbody>
      </table>
    </div>
  </div>

  <!-- HIDDEN FORM FOR FINAL SUBMIT -->
  <form method="POST" id="uploadForm" style="display:none;">
    <textarea name="pasted_json" id="hiddenJson"></textarea>
  </form>

  <div class="divider"><span>OR UPLOAD CSV</span></div>

  <div class="upload-box">
    <h2>Upload CSV File</h2>
    <p>Upload a CSV with columns: <code>name,class,match,relay,target</code></p>
    <form method="POST" enctype="multipart/form-data">
      <input type="file" name="file" accept=".csv">
      <br>
      <button type="submit">Upload CSV</button>
    </form>
  </div>
</div>

<script>
var accumulated = [];
var existingKeys = {};

function copyScript() {
  var t = document.getElementById(\'exportScript\');
  t.select();
  t.setSelectionRange(0, 99999);
  document.execCommand(\'copy\');
  showCopyMsg(\'Script copied!\');
}

function copyReset() {
  var resetCmd = "localStorage.removeItem(\'sm_export\'); alert(\'ShotMarker export memory cleared!\');";
  if (navigator.clipboard) {
    navigator.clipboard.writeText(resetCmd);
  } else {
    var ta = document.createElement(\'textarea\');
    ta.value = resetCmd;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand(\'copy\');
    document.body.removeChild(ta);
  }
  showCopyMsg(\'Reset command copied!\');
}

function showCopyMsg(text) {
  var m = document.getElementById(\'copyMsg\');
  m.textContent = text;
  m.style.display = \'inline\';
  setTimeout(function(){ m.style.display = \'none\'; }, 2000);
}

function showStatus(msg, type) {
  var el = document.getElementById(\'statusMsg\');
  el.textContent = msg;
  el.className = \'status-msg \' + type;
  if (type === \'success\') {
    setTimeout(function(){ el.className = \'status-msg\'; }, 3000);
  }
}

function addFromPaste() {
  var raw = document.getElementById(\'pasteArea\').value.trim();
  if (!raw) { showStatus(\'Nothing to paste\', \'error\'); return; }

  var competitors;
  try {
    var parsed = JSON.parse(raw);
    competitors = parsed.competitors || parsed;
    if (!Array.isArray(competitors)) throw new Error(\'not array\');
  } catch (e) {
    showStatus(\'Invalid JSON. Make sure you copied the full output from the console.\', \'error\');
    return;
  }

  var added = 0;
  competitors.forEach(function(c) {
    if (!c.name) return;
    var key = c.name + \'|\' + (c.match || \'\');
    if (existingKeys[key]) return;
    existingKeys[key] = true;
    accumulated.push({
      name: c.name || \'\',
      class: c.class || c.class_name || \'\',
      match: c.match || \'\',
      relay: String(c.relay || \'\'),
      target: String(c.target || \'\'),
      position: String(c.position || \'\')
    });
    added++;
  });

  document.getElementById(\'pasteArea\').value = \'\';
  showStatus(\'Added \' + added + \' competitors (\' + accumulated.length + \' total). Paste next match or Upload All.\', \'success\');
  renderPreview();
}

function clearAll() {
  accumulated = [];
  existingKeys = {};
  renderPreview();
  showStatus(\'Cleared all competitors\', \'success\');
}

function renderPreview() {
  var box = document.getElementById(\'previewBox\');
  if (accumulated.length === 0) {
    box.style.display = \'none\';
    return;
  }
  box.style.display = \'block\';

  // Match badges
  var matches = {};
  accumulated.forEach(function(c) { matches[c.match || \'(no match)\'] = (matches[c.match || \'(no match)\'] || 0) + 1; });
  var badgeHtml = \'\';
  Object.entries(matches).sort().forEach(function([m, n]) {
    badgeHtml += \'<span class="match-badge">\' + m + \'<span class="count">\' + n + \'</span></span>\';
  });
  document.getElementById(\'matchBadges\').innerHTML = badgeHtml;
  document.getElementById(\'totalCount\').textContent = accumulated.length + \' competitors across \' + Object.keys(matches).length + \' matches\';

  // Table
  var html = \'\';
  accumulated.forEach(function(c, i) {
    html += \'<tr><td>\' + (i+1) + \'</td><td>\' + c.name + \'</td><td>\' + c.class + \'</td><td>\' + c.match + \'</td><td>\' + c.relay + \'</td><td>\' + c.target + \'</td></tr>\';
  });
  document.getElementById(\'previewBody\').innerHTML = html;
}

function uploadAll() {
  if (accumulated.length === 0) return;
  document.getElementById(\'hiddenJson\').value = JSON.stringify({competitors: accumulated});
  document.getElementById(\'uploadForm\').submit();
}
</script>
</body>
</html>
'''

# ══════════════════════════════════════════════
#  MANUAL CSV UPLOAD
# ══════════════════════════════════════════════

@app.route('/range/<range_id>/upload', methods=['GET', 'POST'])
def upload_shotlog(range_id):
    """Upload CSV shotlog manually"""
    range_obj = Range.query.get(range_id)
    if not range_obj:
        return "Range not found", 404
    
    if request.method == 'GET':
        return render_template_string(UPLOAD_HTML, range=range_obj)
    
    # POST - handle file upload
    if 'file' not in request.files:
        return "No file uploaded", 400
    
    file = request.files['file']
    if not file.filename:
        return "No file selected", 400
    
    csv_text = file.read().decode('utf-8')
    strings = parse_upload_csv(csv_text)
    
    if not strings:
        return "No valid data found in CSV", 400
    
    # Save to database
    saved_dates = save_uploaded_shotlog(range_id, strings)
    
    return redirect(f'/range/{range_id}')

def parse_upload_csv(csv_text):
    """Parse uploaded ShotMarker CSV"""
    import re
    lines = csv_text.strip().split('\n')
    strings = []
    current = None
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        if re.match(r'^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)', line):
            parts = line.split(',')
            current = {
                'date': parts[0].strip() if parts else '',
                'name': parts[1].strip() if len(parts) > 1 else '',
                'target': parts[2].strip() if len(parts) > 2 else '',
                'dims': parts[3].strip() if len(parts) > 3 else '',
                'face': parts[4].strip() if len(parts) > 4 else '',
                'distance': extract_distance(parts[4]) if len(parts) > 4 else '',
                'shots': []
            }
            strings.append(current)
        elif line.startswith(',') and current and not line.startswith(',time,'):
            parts = line.split(',')
            if len(parts) >= 8:
                try:
                    x = float(parts[6])
                    y = float(parts[7])
                    shot = {
                        'id': parts[3].strip(),
                        'score': parts[4].strip(),
                        'temp': parts[5].strip(),
                        'x': x, 'y': y,
                        'v': parts[8].strip() if len(parts) > 8 else '',
                        'isSighter': 'sighter' in (parts[2] or '').lower()
                    }
                    current['shots'].append(shot)
                except (ValueError, IndexError):
                    pass
    return strings

def save_uploaded_shotlog(range_id, strings):
    """Save parsed CSV strings to database"""
    saved_dates = []
    
    for s in strings:
        date_text = s.get('date', '')
        try:
            dt = datetime.strptime(date_text, '%b %d %Y')
            shoot_date = dt.date()
            date_str = dt.strftime('%Y-%m-%d')
        except ValueError:
            continue
        
        # Calculate totals
        total_score = 0
        x_count = 0
        for shot in s.get('shots', []):
            if shot.get('isSighter'):
                continue
            try:
                score_val = int(shot.get('score', 0))
                total_score += score_val
                if shot.get('v', '').upper() in ['V', 'X']:
                    x_count += 1
            except:
                pass
        
        # Find or create shotlog
        shotlog = Shotlog.query.filter_by(range_id=range_id, shoot_date=shoot_date).first()
        if not shotlog:
            shotlog = Shotlog(range_id=range_id, shoot_date=shoot_date)
            db.session.add(shotlog)
            db.session.flush()
        # Check for existing string for this shooter/target combo
        existing = ShotlogString.query.filter_by(
            shotlog_id=shotlog.id,
            shooter_name=s.get('name', ''),
            target=s.get('target', '')
        ).first()
        if existing:
            db.session.delete(existing)
        
        # Add string entry
        entry = ShotlogString(
            shotlog_id=shotlog.id,
            target=s.get('target', ''),
            shooter_name=s.get('name', ''),
            match_name=s.get('dims', ''),
            total_score=total_score,
            x_count=x_count,
            shot_data=s.get('shots', []),
                distance=extract_distance(s.get('face', ''))
        )
        db.session.add(entry)
        
        if date_str not in saved_dates:
            saved_dates.append(date_str)
    
    db.session.commit()
    return saved_dates

UPLOAD_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Upload Shotlog - {{ range.name }}</title>
<style>
:root { --bg:#0c1e2b; --bg2:#122a3a; --gold:#f4c566; --blue:#54b8db; --text:#f0ece4; --text2:#8ab4c8; --border:#1e3d50; }
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--bg); color:var(--text); font-family:sans-serif; min-height:100vh; padding:40px 20px; }
.container { max-width:500px; margin:0 auto; }
h1 { color:var(--gold); margin-bottom:20px; }
.upload-box { background:var(--bg2); border:2px dashed var(--border); border-radius:8px; padding:40px; text-align:center; }
.upload-box:hover { border-color:var(--gold); }
input[type="file"] { margin:20px 0; }
button { background:var(--gold); color:var(--bg); border:none; padding:12px 24px; border-radius:4px; font-size:1rem; cursor:pointer; }
button:hover { opacity:0.9; }
.back { color:var(--gold); text-decoration:none; display:inline-block; margin-bottom:20px; }
p { color:var(--text2); margin-top:12px; font-size:0.9rem; }
</style>
</head>
<body>
<div class="container">
  <a href="/range/{{ range.id }}" class="back">← Back to {{ range.name }}</a>
  <h1>Upload Shotlog CSV</h1>
  <div class="upload-box">
    <form method="POST" enctype="multipart/form-data">
      <p>Select a ShotMarker CSV export file</p>
      <input type="file" name="file" accept=".csv" required>
      <br><br>
      <button type="submit">Upload</button>
    </form>
    <p>Export from ShotMarker: Menu → Export → CSV</p>
  </div>
</div>
<footer style="margin-top:60px;padding:20px;border-top:1px solid #1e3d50;text-align:center;font-size:0.9rem;"><a href="/" style="color:#8ab4c8;text-decoration:none;margin:0 12px;">Home</a><a href="/about" style="color:#8ab4c8;text-decoration:none;margin:0 12px;">About</a><a href="/contact" style="color:#8ab4c8;text-decoration:none;margin:0 12px;">Contact</a></footer></body>
</html>
'''

# ══════════════════════════════════════════════
#  INIT DATABASE
# ══════════════════════════════════════════════

with app.app_context():
    db.create_all()


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

@app.route('/api/admin/competition/<int:comp_id>/shooter/merge', methods=['POST'])
def api_merge_shooters(comp_id):
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json()
    keep_name = data.get('keep', '').strip()
    merge_names = data.get('merge', [])
    if not keep_name or not merge_names:
        return jsonify({'error': 'Keep name and merge names required'}), 400
    # Get the keeper competitor
    keeper = Competitor.query.filter_by(competition_id=comp_id, name=keep_name).first()
    if not keeper:
        return jsonify({'error': 'Keeper not found'}), 404
    # Update scores data - merge entries
    scores = Score.query.filter_by(competition_id=comp_id).all()
    for score in scores:
        if score.data:
            merged_matches = []
            keeper_entry = None
            for s in score.data:
                if s.get('name') == keep_name:
                    keeper_entry = s
                elif s.get('name') in merge_names:
                    # Add matches from merged shooters to keeper
                    if keeper_entry is None:
                        keeper_entry = {'name': keep_name, 'class': keeper.class_name, 'matches': []}
                    keeper_entry['matches'] = keeper_entry.get('matches', []) + s.get('matches', [])
                else:
                    merged_matches.append(s)
            if keeper_entry:
                merged_matches.append(keeper_entry)
            score.data = merged_matches
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(score, 'data')
    # Delete merged competitors
    for name in merge_names:
        Competitor.query.filter_by(competition_id=comp_id, name=name).delete()
    db.session.commit()
    return jsonify({'ok': True, 'message': f'Merged {len(merge_names)} shooter(s) into {keep_name}'})

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

@app.route('/api/admin/competition/<int:comp_id>/score/update', methods=['POST'])
def api_update_score(comp_id):
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
    latest = Score.query.filter_by(competition_id=comp_id).order_by(Score.created_at.desc()).first()
    if not latest or not latest.data:
        return jsonify({'error': 'No scores found'}), 404
    for shooter in latest.data:
        if shooter.get('name') == shooter_name:
            for m in shooter.get('matches', []):
                if m.get('match') == match_name:
                    # Update totals
                    old_score = m.get('score', 0)
                    old_x = m.get('xCount', 0)
                    shooter['total'] = shooter.get('total', 0) - old_score + score
                    shooter['vCount'] = shooter.get('vCount', 0) - old_x + x_count
                    # Update the match
                    m['shots'] = shots
                    m['score'] = score
                    m['xCount'] = x_count
                    break
            break
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(latest, 'data')
    db.session.commit()
    return jsonify({'success': True, 'message': 'Score updated'})

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

@app.route('/api/admin/range/<range_id>/<date_str>/clear-shotlog', methods=['POST'])
def api_clear_shotlog(range_id, date_str):
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        shoot_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except:
        return jsonify({'error': 'Invalid date'}), 400
    shotlog = Shotlog.query.filter_by(range_id=range_id, shoot_date=shoot_date).first()
    if not shotlog:
        return jsonify({'error': 'No shotlog found for this date'}), 404
    count = ShotlogString.query.filter_by(shotlog_id=shotlog.id).delete()
    db.session.delete(shotlog)
    db.session.commit()
    return jsonify({'success': True, 'message': f'{count} strings cleared'})

@app.route('/api/admin/range/<range_id>/<date_str>/delete-string', methods=['POST'])
def api_delete_string(range_id, date_str):
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        shoot_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except:
        return jsonify({'error': 'Invalid date'}), 400
    shotlog = Shotlog.query.filter_by(range_id=range_id, shoot_date=shoot_date).first()
    if not shotlog:
        return jsonify({'error': 'No shotlog found'}), 404
    data = request.json
    target = data.get('target', '')
    shooter = data.get('shooter', '')
    entry = ShotlogString.query.filter_by(shotlog_id=shotlog.id, target=target, shooter_name=shooter).first()
    if not entry:
        return jsonify({'error': 'String not found'}), 404
    db.session.delete(entry)
    db.session.commit()
    return jsonify({'success': True, 'message': f'Deleted {shooter} on {target}'})

@app.route("/api/admin/competition/<int:comp_id>/sponsors")
def api_get_sponsors(comp_id):
    comp = Competition.query.get(comp_id)
    if not comp:
        return jsonify({"error": "Competition not found"}), 404
    return jsonify({"sponsors": comp.sponsors or []})

@app.route("/api/admin/competition/<int:comp_id>/sponsors", methods=["POST"])
def api_save_sponsors(comp_id):
    if not session.get("admin"):
        return jsonify({"error": "Unauthorized"}), 401
    comp = Competition.query.get(comp_id)
    if not comp:
        return jsonify({"error": "Competition not found"}), 404
    data = request.get_json()
    sponsors = data.get("sponsors", [])
    if len(sponsors) > 8:
        return jsonify({"error": "Maximum 8 sponsors allowed"}), 400
    comp.sponsors = sponsors
    db.session.commit()
    return jsonify({"ok": True, "message": f"Saved {len(sponsors)} sponsor(s)"})

@app.route('/api/admin/competition/<int:comp_id>/settings', methods=['POST'])
def api_save_comp_settings(comp_id):
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    comp = Competition.query.get(comp_id)
    if not comp:
        return jsonify({'error': 'Not found'}), 404
    data = request.get_json()
    if 'name' in data:
        new_name = data['name'].strip()
        if not new_name:
            return jsonify({'error': 'Name cannot be empty'}), 400
        comp.name = new_name
    if 'route' in data:
        import re
        new_route = data['route'].strip()
        if not new_route:
            return jsonify({'error': 'Route cannot be empty'}), 400
        if not re.match(r'^[A-Za-z0-9_-]+$', new_route):
            return jsonify({'error': 'Route can only contain letters, numbers, hyphens and underscores'}), 400
        reserved = {'admin', 'about', 'contact', 'api', 'photos', 'range', 'static', 'login', 'logout'}
        if new_route.lower() in reserved:
            return jsonify({'error': f'"{new_route}" is a reserved name'}), 400
        existing = Competition.query.filter_by(route=new_route).first()
        if existing and existing.id != comp_id:
            return jsonify({'error': f'Route "{new_route}" is already in use'}), 400
        comp.route = new_route
    if 'contact_email' in data:
        comp.contact_email = (data['contact_email'] or '').strip()[:200]
    if 'contact_phone' in data:
        comp.contact_phone = (data['contact_phone'] or '').strip()[:50]
    if 'contact_info' in data:
        comp.contact_info = (data['contact_info'] or '').strip()
    db.session.commit()
    return jsonify({'ok': True, 'message': 'Settings saved', 'name': comp.name, 'route': comp.route})

@app.route('/api/admin/competition/<int:comp_id>/logo', methods=['POST'])
def api_save_logo(comp_id):
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    comp = Competition.query.get(comp_id)
    if not comp:
        return jsonify({'error': 'Not found'}), 404
    if 'logo' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    file = request.files['logo']
    if not file.filename:
        return jsonify({'error': 'No file selected'}), 400
    ct = (file.content_type or '').lower()
    if not ct.startswith('image/'):
        return jsonify({'error': 'Must be an image file'}), 400
    import base64
    img_data = file.read()
    if len(img_data) > 500000:
        return jsonify({'error': 'Image too large (max 500KB)'}), 400
    data_uri = f'data:{ct};base64,' + base64.b64encode(img_data).decode('utf-8')
    comp.logo = data_uri
    db.session.commit()
    return jsonify({'ok': True, 'message': 'Logo uploaded', 'logo': data_uri})

@app.route('/api/admin/competition/<int:comp_id>/logo/delete', methods=['POST'])
def api_delete_logo(comp_id):
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    comp = Competition.query.get(comp_id)
    if not comp:
        return jsonify({'error': 'Not found'}), 404
    comp.logo = None
    db.session.commit()
    return jsonify({'ok': True, 'message': 'Logo removed'})

@app.route('/api/admin/competition/<int:comp_id>/guide', methods=['GET'])
def api_get_guide(comp_id):
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    comp = Competition.query.get(comp_id)
    if not comp:
        return jsonify({'error': 'Not found'}), 404
    return jsonify({'guide_html': comp.guide_html or ''})

@app.route('/api/admin/competition/<int:comp_id>/guide', methods=['POST'])
def api_save_guide(comp_id):
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    comp = Competition.query.get(comp_id)
    if not comp:
        return jsonify({'error': 'Not found'}), 404
    data = request.get_json()
    comp.guide_html = data.get('guide_html', '')
    db.session.commit()
    return jsonify({'ok': True, 'message': 'Guide saved'})

@app.route('/api/admin/competition/<int:comp_id>/export-csv')
def api_export_csv(comp_id):
    if not session.get('admin'):
        return "Unauthorized", 401
    comp = Competition.query.get_or_404(comp_id)
    latest = Score.query.filter_by(competition_id=comp.id).order_by(Score.created_at.desc()).first()
    scores = latest.data if latest else []
    competitors = Competitor.query.filter_by(competition_id=comp.id).all()
    comp_map = {c.name: c.class_name for c in competitors}
    # Build match list from score data
    match_names = []
    match_set = set()
    for s in scores:
        for m in (s.get('matches') or []):
            mn = m.get('match', '')
            if mn and mn not in match_set:
                match_set.add(mn)
                match_names.append(mn)
    # Group by class, sort by aggregate desc
    class_groups = {}
    for s in scores:
        cls = s.get('class') or comp_map.get(s.get('name')) or 'UNCATEGORIZED'
        if cls not in class_groups:
            class_groups[cls] = []
        total = sum(m.get('score', 0) for m in (s.get('matches') or []))
        total_x = sum(m.get('xCount', 0) for m in (s.get('matches') or []))
        class_groups[cls].append({'name': s.get('name', ''), 'class': cls, 'matches': s.get('matches') or [], 'total': total, 'totalX': total_x})
    for cls in class_groups:
        class_groups[cls].sort(key=lambda x: (-x['total'], -x['totalX']))
    import io, csv
    output = io.StringIO()
    writer = csv.writer(output)
    header = ['Rank', 'Name', 'Class']
    for mn in match_names:
        header.extend([mn + ' Score', mn + ' X'])
    header.extend(['Aggregate', 'Total X'])
    writer.writerow(header)
    for cls in class_groups:
        rank = 1
        for s in class_groups[cls]:
            row = [rank, s['name'], s['class']]
            match_lookup = {m.get('match'): m for m in s['matches']}
            for mn in match_names:
                m = match_lookup.get(mn, {})
                row.append(m.get('score', ''))
                row.append(m.get('xCount', ''))
            row.extend([s['total'], s['totalX']])
            writer.writerow(row)
            rank += 1
        writer.writerow([])  # Blank row between classes
    from flask import Response
    csv_content = output.getvalue()
    safe_name = comp.route or 'results'
    return Response(csv_content, mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename={safe_name}-results.csv'})

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
    <button class="tab" id="tab-photos">Photos</button>
    <button class="tab" id="tab-settings">Settings</button>
  </div>
  <div id="shooters-tab" class="tab-content active">
    <div class="action-bar">
      <button class="action-btn primary" id="btn-add-shooter">+ Add Shooter</button>
      <button class="action-btn" id="btn-merge-shooters">🔀 Merge Duplicates</button>
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
  <div id="photos-tab" class="tab-content">
    <div class="action-bar">
      <span style="color:var(--text2);" id="admin-photo-count"></span>
      <a href="/{{ competition.route }}/photos" class="action-btn" style="text-decoration:none;">View Gallery</a>
      <button class="action-btn danger" onclick="clearAllPhotos()">Clear All Photos</button>
    </div>
    <div id="admin-photo-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px;margin-top:16px;"></div>
  </div>
  <div id="settings-tab" class="tab-content">
    <div class="card" style="background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:20px;margin-bottom:20px;">
      <h3 style="color:var(--gold);font-family:Oswald,sans-serif;margin-bottom:16px;">General Settings</h3>
      <div style="margin-bottom:16px;">
        <label style="display:block;color:var(--text2);margin-bottom:4px;font-size:0.9rem;">Competition Name</label>
        <input type="text" id="setting-name" value="{{ competition.name }}" class="search-input" style="width:100%;max-width:400px;">
      </div>
      <div style="margin-bottom:16px;">
        <label style="display:block;color:var(--text2);margin-bottom:4px;font-size:0.9rem;">URL Route (slug)</label>
        <input type="text" id="setting-route" value="{{ competition.route }}" class="search-input" style="width:100%;max-width:400px;">
        <span style="font-size:0.8rem;color:var(--text2);display:block;margin-top:4px;">Current URL: /{{ competition.route }}</span>
      </div>
      <h4 style="color:var(--gold);font-family:Oswald,sans-serif;margin:20px 0 12px;">Contact Information</h4>
      <p style="color:var(--text2);margin-bottom:12px;font-size:0.85rem;">Shown on the competition contact page at /{{ competition.route }}/contact</p>
      <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px;">
        <div style="flex:1;min-width:200px;">
          <label style="display:block;color:var(--text2);margin-bottom:4px;font-size:0.9rem;">Contact Email</label>
          <input type="email" id="setting-email" value="{{ competition.contact_email or '' }}" class="search-input" style="width:100%;">
        </div>
        <div style="flex:1;min-width:200px;">
          <label style="display:block;color:var(--text2);margin-bottom:4px;font-size:0.9rem;">Contact Phone</label>
          <input type="text" id="setting-phone" value="{{ competition.contact_phone or '' }}" class="search-input" style="width:100%;">
        </div>
      </div>
      <div style="margin-bottom:16px;">
        <label style="display:block;color:var(--text2);margin-bottom:4px;font-size:0.9rem;">Additional Contact Info</label>
        <textarea id="setting-info" rows="3" class="search-input" style="width:100%;max-width:500px;resize:vertical;">{{ competition.contact_info or '' }}</textarea>
      </div>
      <button class="action-btn primary" onclick="saveSettings()">Save Settings</button>
      <span id="settings-status" style="margin-left:12px;color:var(--green);font-size:0.9rem;"></span>
    </div>
    <div class="card" style="background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:20px;margin-bottom:20px;">
      <h3 style="color:var(--gold);font-family:Oswald,sans-serif;margin-bottom:16px;">Competition Logo</h3>
      <p style="color:var(--text2);margin-bottom:12px;font-size:0.85rem;">Upload a logo image (PNG, JPG, max 500KB). Displayed on the scoreboard header.</p>
      <div id="logo-preview" style="margin-bottom:12px;">
        {% if competition.logo %}
        <img src="{{ competition.logo }}" style="max-height:80px;max-width:200px;background:#fff;padding:8px;border-radius:4px;">
        {% else %}
        <span style="color:var(--text2);">No logo uploaded</span>
        {% endif %}
      </div>
      <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;">
        <input type="file" id="logo-file" accept="image/*" style="color:var(--text);">
        <button class="action-btn primary" onclick="uploadLogo()">Upload Logo</button>
        <button class="action-btn danger" onclick="deleteLogo()">Remove</button>
      </div>
    </div>
    <div class="card" style="background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:20px;margin-bottom:20px;">
      <h3 style="color:var(--gold);font-family:Oswald,sans-serif;margin-bottom:16px;">Event Guide</h3>
      <p style="color:var(--text2);margin-bottom:12px;font-size:0.85rem;">Upload an HTML file as the competitor guide for this competition.</p>
      <div id="guide-status" style="margin-bottom:12px;color:var(--text2);font-size:0.9rem;">
        {% if competition.guide_html %}Guide uploaded (custom){% else %}Using default guide{% endif %}
      </div>
      <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;">
        <input type="file" id="guide-file" accept=".html,.htm" style="color:var(--text);">
        <button class="action-btn primary" onclick="uploadGuide()">Upload Guide</button>
        <button class="action-btn danger" onclick="clearGuide()">Clear Guide</button>
      </div>
    </div>
    <div class="card" style="background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:20px;margin-bottom:20px;">
      <h3 style="color:var(--gold);font-family:Oswald,sans-serif;margin-bottom:16px;">Sponsor Logos</h3>
      <p style="color:var(--text2);margin-bottom:16px;">Add sponsor logos (max 8). Click logo to visit sponsor website.</p>
      <div id="sponsor-list" style="margin-bottom:16px;"></div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        <input type="text" id="new-sponsor-logo" class="search-input" placeholder="Logo image URL..." style="flex:2;min-width:200px;width:auto;">
        <input type="text" id="new-sponsor-link" class="search-input" placeholder="Sponsor website URL..." style="flex:2;min-width:200px;width:auto;">
        <button class="action-btn primary" onclick="addSponsor()">+ Add</button>
      </div>
      <div id="sponsor-preview" style="display:flex;flex-wrap:wrap;gap:16px;margin-top:16px;"></div>
    </div>
    <div class="card" style="background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:20px;margin-bottom:20px;">
      <h3 style="color:var(--gold);font-family:Oswald,sans-serif;margin-bottom:16px;">Export Results</h3>
      <p style="color:var(--text2);margin-bottom:16px;font-size:0.85rem;">Download final scores as a CSV file (opens in Excel).</p>
      <button class="action-btn primary" onclick="exportCSV()">Download CSV</button>
    </div>
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
<div class="modal" id="modal-merge">
  <div class="modal-content" style="max-width:600px;">
    <div class="modal-header"><h2>🔀 Merge Duplicate Shooters</h2><button class="modal-close" onclick="document.getElementById('modal-merge').classList.remove('active')">×</button></div>
    <p style="color:var(--text2);margin-bottom:16px;">Select shooters to merge. Their scores will be combined under the kept name.</p>
    <div class="form-group" style="margin-bottom:16px;"><label>Keep This Shooter (Primary)</label><select id="merge-keep" style="width:100%;"></select></div>
    <div class="form-group" style="margin-bottom:16px;"><label>Merge These Into Primary (Select Multiple)</label><select id="merge-from" multiple style="width:100%;height:150px;"></select></div>
    <div style="display:flex;gap:12px;"><button class="action-btn primary" onclick="doMerge()">Merge Selected</button><button class="action-btn" onclick="document.getElementById('modal-merge').classList.remove('active')">Cancel</button></div>
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
<div class="modal" id="modal-edit-score">
  <div class="modal-content" style="min-width:450px;">
    <div class="modal-header"><h2>Edit Score</h2><button class="modal-close" data-close="modal-edit-score">x</button></div>
    <input type="hidden" id="edit-score-name">
    <input type="hidden" id="edit-score-match">
    <input type="hidden" id="edit-score-shots">
    <div class="form-row">
      <div class="form-group"><label>Shooter</label><div id="edit-score-name-display" style="padding:8px 0;font-family:Oswald,sans-serif;"></div></div>
      <div class="form-group"><label>Match</label><div id="edit-score-match-display" style="padding:8px 0;"></div></div>
    </div>
    <div class="form-group" style="margin-top:12px;">
      <label>Shots (click to edit, x to remove)</label>
      <div id="edit-shots-container" style="display:flex;flex-direction:column;gap:4px;margin-top:8px;max-height:300px;overflow-y:auto;"></div>
    </div>
    <div class="form-row" style="margin-top:20px;"><button class="action-btn primary" id="btn-update-score">Save Changes</button></div>
  </div>
</div>
<style>
.shot-edit-row { display:flex; align-items:center; gap:10px; background:var(--bg); padding:6px 10px; border-radius:4px; border:1px solid var(--border); }
.shot-num { font-family:JetBrains Mono,monospace; font-size:0.85rem; color:var(--text2); width:30px; }
.shot-input { width:50px; height:30px; text-align:center; padding:4px; background:var(--bg2); border:1px solid var(--border); color:var(--gold); font-family:JetBrains Mono,monospace; font-weight:bold; font-size:1rem; border-radius:4px; text-transform:uppercase; }
.shot-input:focus { outline:none; border-color:var(--gold); }
.shot-remove { background:var(--red); color:white; border:none; width:24px; height:24px; border-radius:50%; cursor:pointer; font-size:0.8rem; line-height:24px; }
.shot-remove:hover { opacity:0.8; }
</style>
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

document.getElementById('btn-update-score').addEventListener('click', updateScore);

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
      html += '<td><button class="edit-btn" data-name="' + shooter.name + '" data-match="' + m.match + '" data-shots="' + (m.shots || '') + '">Edit</button> <button class="delete-btn" data-name="' + shooter.name + '" data-match="' + m.match + '">Delete</button></td>';
      html += '</tr>';
    });
  });
  tbody.innerHTML = html;
  tbody.querySelectorAll('.delete-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      if (confirm('Delete score?')) deleteScore(btn.dataset.name, btn.dataset.match);
    });
  });
  tbody.querySelectorAll('.edit-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      showEditScore(btn.dataset.name, btn.dataset.match, btn.dataset.shots);
    });
  });
}

function showEditScore(name, match, shots) {
  document.getElementById('edit-score-name').value = name;
  document.getElementById('edit-score-match').value = match;
  document.getElementById('edit-score-shots').value = shots || '';
  document.getElementById('edit-score-name-display').textContent = name;
  document.getElementById('edit-score-match-display').textContent = match;
  renderEditShots(shots || '');
  document.getElementById('modal-edit-score').classList.add('active');
}

function renderEditShots(shotsStr) {
  var container = document.getElementById('edit-shots-container');
  var shots = shotsStr ? shotsStr.split(',') : [];
  var html = '';
  shots.forEach(function(s, i) {
    html += '<div class="shot-edit-row">';
    html += '<span class="shot-num">' + (i + 1) + '</span>';
    html += '<input type="text" class="shot-input" value="' + s.trim() + '" maxlength="1">';
    html += '<button type="button" class="shot-remove" data-idx="' + i + '">x</button>';
    html += '</div>';
  });
  html += '<button type="button" class="action-btn" id="btn-add-shot" style="margin-top:8px;">+ Add Shot</button>';
  container.innerHTML = html;
  
  container.querySelectorAll('.shot-remove').forEach(function(btn) {
    btn.addEventListener('click', function() {
      var currentShots = getEditShots();
      currentShots.splice(parseInt(btn.dataset.idx), 1);
      document.getElementById('edit-score-shots').value = currentShots.join(',');
      renderEditShots(currentShots.join(','));
    });
  });
  
  document.getElementById('btn-add-shot').addEventListener('click', function() {
    var currentShots = getEditShots();
    currentShots.push('6');
    document.getElementById('edit-score-shots').value = currentShots.join(',');
    renderEditShots(currentShots.join(','));
  });
  
  container.querySelectorAll('.shot-input').forEach(function(inp) {
    inp.addEventListener('change', function() {
      document.getElementById('edit-score-shots').value = getEditShots().join(',');
    });
  });
}

function getEditShots() {
  var inputs = document.querySelectorAll('#edit-shots-container .shot-input');
  var shots = [];
  inputs.forEach(function(inp) { shots.push(inp.value.trim().toUpperCase()); });
  return shots;
}

function updateScore() {
  var name = document.getElementById('edit-score-name').value;
  var match = document.getElementById('edit-score-match').value;
  var shots = getEditShots().join(',');
  fetch('/api/admin/competition/' + COMP_ID + '/score/update', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ name: name, match: match, shots: shots })
  }).then(function(r) { return r.json(); }).then(function(result) {
    if (result.success) { showMessage(result.message); document.getElementById('modal-edit-score').classList.remove('active'); loadScores(); }
    else showMessage(result.error, true);
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
  if (!confirm('Are you sure you want to delete ALL scores?')) return; if (!confirm('FINAL WARNING: This will permanently delete all scores. Click OK to proceed.')) return;
  fetch('/api/admin/competition/' + COMP_ID + '/clear-scores', { method: 'POST' })
    .then(function(r) { return r.json(); }).then(function(result) {
      if (result.success) { showMessage(result.message); loadScores(); }
      else showMessage(result.error, true);
    });
}

function clearCompetitors() {
  if (!confirm('Are you sure you want to delete ALL competitors?')) return; if (!confirm('FINAL WARNING: This will permanently delete all competitors. Click OK to proceed.')) return;
  fetch('/api/admin/competition/' + COMP_ID + '/clear-competitors', { method: 'POST' })
    .then(function(r) { return r.json(); }).then(function(result) {
      if (result.success) { showMessage(result.message); loadShooters(); }
      else showMessage(result.error, true);
    });
}

loadShooters();
loadScores();
loadMatches();

document.getElementById('btn-merge-shooters').addEventListener('click', function() {
  var keepSelect = document.getElementById('merge-keep');
  var fromSelect = document.getElementById('merge-from');
  keepSelect.innerHTML = '';
  fromSelect.innerHTML = '';
  shooters.forEach(function(s) {
    keepSelect.innerHTML += '<option value="' + s.name + '">' + s.name + ' (' + (s.class || 'No class') + ')</option>';
    fromSelect.innerHTML += '<option value="' + s.name + '">' + s.name + ' (' + (s.class || 'No class') + ')</option>';
  });
  document.getElementById('modal-merge').classList.add('active');
});

function doMerge() {
  var keepName = document.getElementById('merge-keep').value;
  var fromSelect = document.getElementById('merge-from');
  var fromNames = Array.from(fromSelect.selectedOptions).map(function(o) { return o.value; });
  if (!keepName || fromNames.length === 0) { alert('Select a shooter to keep and at least one to merge'); return; }
  if (fromNames.indexOf(keepName) >= 0) { alert('Cannot merge a shooter into themselves'); return; }
  if (!confirm('Merge ' + fromNames.join(', ') + ' into ' + keepName + '? This cannot be undone.')) return;
  fetch('/api/admin/competition/' + COMP_ID + '/shooter/merge', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({keep: keepName, merge: fromNames})
  })
  .then(function(r) { return r.json(); })
  .then(function(data) {
    if (data.ok) { showMessage(data.message); document.getElementById('modal-merge').classList.remove('active'); loadShooters(); loadScores(); }
    else { showMessage(data.error || 'Merge failed', true); }
  });
}

var sponsors = [];

function loadSponsors() {
  fetch("/api/admin/competition/" + COMP_ID + "/sponsors")
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var raw = data.sponsors || [];
      sponsors = raw.map(function(s) {
        if (typeof s === "string") return {logo: s, link: ""};
        return s;
      });
      renderSponsors();
    });
}

function renderSponsors() {
  var list = document.getElementById("sponsor-list");
  var preview = document.getElementById("sponsor-preview");
  if (!sponsors.length) {
    list.innerHTML = "<p style=\\"color:var(--text2);\\">No sponsors added yet.</p>";
    preview.innerHTML = "";
    return;
  }
  var html = "";
  sponsors.forEach(function(s, i) {
    html += "<div style=\\"display:flex;align-items:center;gap:8px;margin-bottom:8px;padding:8px;background:var(--bg);border-radius:4px;flex-wrap:wrap;\\">";
    html += "<img src=\\"" + s.logo + "\\" style=\\"max-height:32px;max-width:80px;object-fit:contain;background:#fff;padding:4px;border-radius:3px;\\" onerror=\\"this.style.display=\\'none\\'\\">";
    html += "<span style=\\"flex:1;color:var(--text);font-size:0.85rem;word-break:break-all;min-width:150px;\\">" + s.logo + "</span>";
    if (s.link) html += "<a href=\\"" + s.link + "\\" target=\\"_blank\\" style=\\"color:var(--blue);font-size:0.8rem;\\">Link &#8599;</a>";
    html += "<button class=\\"delete-btn\\" onclick=\\"removeSponsor(" + i + ")\\">Remove</button>";
    html += "</div>";
  });
  list.innerHTML = html;
  var phtml = "";
  sponsors.forEach(function(s) {
    if (s.link) {
      phtml += "<a href=\\"" + s.link + "\\" target=\\"_blank\\" style=\\"display:inline-block;\\"><img src=\\"" + s.logo + "\\" style=\\"max-height:50px;max-width:120px;object-fit:contain;background:#fff;padding:6px;border-radius:4px;\\" onerror=\\"this.parentElement.style.display=\\'none\\'\\"></a>";
    } else {
      phtml += "<img src=\\"" + s.logo + "\\" style=\\"max-height:50px;max-width:120px;object-fit:contain;background:#fff;padding:6px;border-radius:4px;\\" onerror=\\"this.style.display=\\'none\\'\\">";
    }
  });
  preview.innerHTML = phtml;
}

function addSponsor() {
  var logo = document.getElementById("new-sponsor-logo").value.trim();
  var link = document.getElementById("new-sponsor-link").value.trim();
  if (!logo) { alert("Enter a logo URL"); return; }
  if (sponsors.length >= 8) { alert("Maximum 8 sponsors"); return; }
  sponsors.push({logo: logo, link: link});
  saveSponsors();
  document.getElementById("new-sponsor-logo").value = "";
  document.getElementById("new-sponsor-link").value = "";
}

function removeSponsor(index) {
  sponsors.splice(index, 1);
  saveSponsors();
}

function saveSponsors() {
  fetch("/api/admin/competition/" + COMP_ID + "/sponsors", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({sponsors: sponsors})
  })
  .then(function(r) { return r.json(); })
  .then(function(data) {
    if (data.ok) { renderSponsors(); showMessage("Sponsors saved"); }
    else { showMessage(data.error || "Save failed", true); }
  });
}

loadSponsors();

// --- Photos tab ---
function loadAdminPhotos() {
  fetch("/{{ competition.route }}/photos/json")
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var grid = document.getElementById("admin-photo-grid");
      var count = document.getElementById("admin-photo-count");
      count.textContent = data.length + " photo" + (data.length !== 1 ? "s" : "");
      if (!data.length) { grid.innerHTML = '<p style="color:var(--text2);">No photos uploaded yet.</p>'; return; }
      var html = "";
      data.forEach(function(p) {
        html += '<div style="position:relative;border-radius:6px;overflow:hidden;aspect-ratio:4/3;background:var(--bg);">';
        html += '<img src="' + p.url + '" style="width:100%;height:100%;object-fit:cover;" loading="lazy">';
        html += '<button onclick="deletePhoto(' + p.id + ')" style="position:absolute;top:6px;right:6px;background:var(--red);color:#fff;border:none;border-radius:50%;width:28px;height:28px;cursor:pointer;font-size:16px;line-height:28px;">&times;</button>';
        if (p.caption) html += '<div style="position:absolute;bottom:0;left:0;right:0;background:rgba(0,0,0,0.7);padding:4px 8px;font-size:0.75rem;color:#fff;">' + p.caption + '</div>';
        html += '</div>';
      });
      grid.innerHTML = html;
    });
}

function deletePhoto(photoId) {
  if (!confirm("Delete this photo?")) return;
  fetch("/api/admin/competition/" + COMP_ID + "/photos/" + photoId + "/delete", { method: "POST" })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.ok) { showMessage("Photo deleted"); loadAdminPhotos(); }
      else showMessage(data.error || "Delete failed", true);
    });
}

function clearAllPhotos() {
  if (!confirm("Delete ALL photos for this competition?")) return;
  if (!confirm("FINAL WARNING: This will permanently delete all photos. Click OK to proceed.")) return;
  fetch("/api/admin/competition/" + COMP_ID + "/photos/clear", { method: "POST" })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.ok) { showMessage(data.message); loadAdminPhotos(); }
      else showMessage(data.error || "Clear failed", true);
    });
}

loadAdminPhotos();

// ── Competition Settings ──
function saveSettings() {
  var name = document.getElementById('setting-name').value.trim();
  var route = document.getElementById('setting-route').value.trim();
  var email = document.getElementById('setting-email').value.trim();
  var phone = document.getElementById('setting-phone').value.trim();
  var info = document.getElementById('setting-info').value.trim();
  if (!name) { showMessage('Name is required', true); return; }
  if (!route) { showMessage('Route is required', true); return; }
  fetch('/api/admin/competition/' + COMP_ID + '/settings', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({name: name, route: route, contact_email: email, contact_phone: phone, contact_info: info})
  }).then(function(r) { return r.json(); }).then(function(data) {
    if (data.ok) {
      showMessage(data.message);
      var h1 = document.querySelector('h1');
      if (h1) h1.textContent = 'Admin: ' + data.name;
      document.getElementById('settings-status').textContent = 'Saved!';
      setTimeout(function() { document.getElementById('settings-status').textContent = ''; }, 3000);
    } else {
      showMessage(data.error || 'Save failed', true);
    }
  });
}

function uploadLogo() {
  var fileInput = document.getElementById('logo-file');
  if (!fileInput.files.length) { alert('Select an image file first'); return; }
  var formData = new FormData();
  formData.append('logo', fileInput.files[0]);
  fetch('/api/admin/competition/' + COMP_ID + '/logo', {
    method: 'POST', body: formData
  }).then(function(r) { return r.json(); }).then(function(data) {
    if (data.ok) {
      showMessage(data.message);
      document.getElementById('logo-preview').innerHTML = '<img src="' + data.logo + '" style="max-height:80px;max-width:200px;background:#fff;padding:8px;border-radius:4px;">';
    } else {
      showMessage(data.error || 'Upload failed', true);
    }
  });
}

function deleteLogo() {
  if (!confirm('Remove the competition logo?')) return;
  fetch('/api/admin/competition/' + COMP_ID + '/logo/delete', { method: 'POST' })
    .then(function(r) { return r.json(); }).then(function(data) {
      if (data.ok) {
        showMessage(data.message);
        document.getElementById('logo-preview').innerHTML = '<span style="color:var(--text2);">No logo uploaded</span>';
      } else { showMessage(data.error || 'Failed', true); }
    });
}

function uploadGuide() {
  var fileInput = document.getElementById('guide-file');
  if (!fileInput.files.length) { alert('Select an HTML file first'); return; }
  var reader = new FileReader();
  reader.onload = function(e) {
    fetch('/api/admin/competition/' + COMP_ID + '/guide', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({guide_html: e.target.result})
    }).then(function(r) { return r.json(); }).then(function(data) {
      if (data.ok) {
        showMessage('Guide uploaded successfully');
        document.getElementById('guide-status').textContent = 'Guide uploaded (custom)';
      } else { showMessage(data.error || 'Upload failed', true); }
    });
  };
  reader.readAsText(fileInput.files[0]);
}

function clearGuide() {
  if (!confirm('Remove the competition guide? It will fall back to the default guide.')) return;
  fetch('/api/admin/competition/' + COMP_ID + '/guide', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({guide_html: ''})
  }).then(function(r) { return r.json(); }).then(function(data) {
    if (data.ok) {
      showMessage('Guide cleared');
      document.getElementById('guide-status').textContent = 'Using default guide';
    } else { showMessage(data.error || 'Failed', true); }
  });
}

function exportCSV() {
  window.location.href = '/api/admin/competition/' + COMP_ID + '/export-csv';
}
</script>
</body>
</html>
"""
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

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
  <a href="/admin/manage" class="refresh-btn" style="background:var(--green); margin-left:10px; text-decoration:none;">⚙️ Manage</a>
  <a href="/admin/wiki" class="refresh-btn" style="background:var(--blue, #4a9eff); margin-left:10px; text-decoration:none;">📖 Wiki</a>
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
        <tr><th>Name</th><th>Route</th><th>Scores</th><th>Actions</th></tr>
        {% for comp in competitions %}
        <tr><td>{{ comp.name }}</td><td>/{{ comp.route }}</td><td>{{ comp.score_count }}</td><td><a href="/admin/competition/{{ comp.id }}" style="color:var(--blue);">Edit</a> · <a href="/{{ comp.route }}" style="color:var(--green);">View</a></td></tr>
        {% endfor %}
      </table>
    </div>
  </div>
  
  <div class="card">
    <h2>Ranges</h2>
    <table>
      <tr><th>Name</th><th>Route</th><th>Days</th><th>Latest</th></tr>
      {% for r in ranges %}
      <tr><td>{{ r.name }}</td><td>/range/{{ r.id }}</td><td>{{ r.day_count }}</td><td>{{ r.latest or "-" }}</td></tr>
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
        competitions.append({'id': comp.id, 'name': comp.name, 'route': comp.route, 'score_count': score_count})
    
    ranges = []
    for r in Range.query.all():
        days = db.session.query(db.func.date(Shotlog.shoot_date)).filter_by(range_id=r.id).distinct().count()
        latest = db.session.query(db.func.max(db.func.date(Shotlog.shoot_date))).filter_by(range_id=r.id).scalar()
        ranges.append({'name': r.name, 'route': r.id, 'day_count': days, 'latest': str(latest) if latest else None})
    
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

# ══════════════════════════════════════════════
#  ADMIN WIKI
# ══════════════════════════════════════════════

ADMIN_WIKI_HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Admin Wiki - SM Scores</title>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;600&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root { --bg:#0a0a0a; --bg2:#141414; --bg3:#1e1e1e; --text:#e0e0e0; --gold:#c8a200; --green:#28a745; --red:#dc3545; --blue:#4a9eff; --border:#333; }
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--bg); color:var(--text); font-family:"Inter",sans-serif; line-height:1.6; }
.container { max-width:1000px; margin:0 auto; padding:20px; }
.nav { display:flex; gap:20px; margin-bottom:20px; }
.nav a { color:var(--gold); text-decoration:none; font-size:14px; }
.nav a:hover { text-decoration:underline; }
h1 { font-family:"Oswald",sans-serif; color:var(--gold); font-size:28px; margin-bottom:8px; }
.subtitle { color:#888; font-size:14px; margin-bottom:30px; }
h2 { font-family:"Oswald",sans-serif; color:var(--gold); font-size:20px; margin:30px 0 15px; padding-bottom:8px; border-bottom:1px solid var(--border); }
h3 { color:var(--text); font-size:16px; margin:20px 0 10px; }
.card { background:var(--bg2); border:1px solid var(--border); border-radius:8px; padding:20px; margin-bottom:20px; }
table { width:100%; border-collapse:collapse; margin:10px 0 20px; }
th, td { padding:8px 12px; text-align:left; border-bottom:1px solid var(--border); font-size:14px; }
th { color:var(--gold); font-family:"Oswald",sans-serif; font-size:13px; text-transform:uppercase; }
td { vertical-align:top; }
code { background:var(--bg3); color:var(--blue); padding:2px 6px; border-radius:3px; font-size:13px; font-family:monospace; }
pre { background:var(--bg3); border:1px solid var(--border); border-radius:6px; padding:12px; margin:10px 0; overflow-x:auto; font-size:13px; color:var(--text); font-family:monospace; line-height:1.5; }
.url { color:var(--blue); word-break:break-all; }
.badge { display:inline-block; padding:2px 8px; border-radius:3px; font-size:11px; font-weight:600; text-transform:uppercase; }
.badge-public { background:#28a74533; color:#28a745; }
.badge-admin { background:#dc354533; color:#dc3545; }
.badge-api { background:#4a9eff33; color:#4a9eff; }
.note { background:#c8a20015; border-left:3px solid var(--gold); padding:10px 15px; margin:10px 0; border-radius:0 6px 6px 0; font-size:14px; }
.warning { background:#dc354515; border-left:3px solid var(--red); padding:10px 15px; margin:10px 0; border-radius:0 6px 6px 0; font-size:14px; }
ol, ul { padding-left:24px; margin:10px 0; }
li { margin:6px 0; font-size:14px; }
.toc { background:var(--bg2); border:1px solid var(--border); border-radius:8px; padding:15px 20px; margin-bottom:30px; }
.toc a { color:var(--blue); text-decoration:none; font-size:14px; }
.toc a:hover { text-decoration:underline; }
.toc ul { list-style:none; padding-left:0; }
.toc li { margin:4px 0; }
.toc li::before { content:"→ "; color:var(--gold); }
@media print { body { background:#fff; color:#000; } .nav { display:none; } code { background:#eee; color:#333; } pre { background:#f5f5f5; border-color:#ddd; } }
</style>
</head>
<body>
<div class="container">
  <div class="nav">
    <a href="/admin/dashboard">← Dashboard</a>
    <a href="/admin/manage">Manage</a>
    <a href="/">Home</a>
  </div>

  <h1>Admin Wiki</h1>
  <p class="subtitle">Internal reference for SM Scores administration. Admin access only.</p>

  <div class="toc">
    <strong>Contents</strong>
    <ul>
      <li><a href="#quick-links">Quick Links</a></li>
      <li><a href="#pages">All Pages & Routes</a></li>
      <li><a href="#competition-setup">Setting Up a Competition</a></li>
      <li><a href="#squadding">Uploading Squadding</a></li>
      <li><a href="#scoring">Managing Scores</a></li>
      <li><a href="#photos">Photo Gallery</a></li>
      <li><a href="#scraper">Pi Scraper Setup & Operation</a></li>
      <li><a href="#server">Server & Database</a></li>
      <li><a href="#troubleshooting">Troubleshooting</a></li>
    </ul>
  </div>

  <!-- QUICK LINKS -->
  <h2 id="quick-links">Quick Links</h2>
  <div class="card">
    <table>
      <tr><th>Page</th><th>URL</th><th>Access</th></tr>
      <tr><td>Home Page</td><td class="url">/</td><td><span class="badge badge-public">Public</span></td></tr>
      <tr><td>Admin Login</td><td class="url">/admin</td><td>Password: <code>Gregory</code></td></tr>
      <tr><td>Dashboard</td><td class="url">/admin/dashboard</td><td><span class="badge badge-admin">Admin</span></td></tr>
      <tr><td>Manage Ranges/Comps</td><td class="url">/admin/manage</td><td><span class="badge badge-admin">Admin</span></td></tr>
      <tr><td>This Wiki</td><td class="url">/admin/wiki</td><td><span class="badge badge-admin">Admin</span></td></tr>
      <tr><td>Scoreboard</td><td class="url">/CoastalCup</td><td><span class="badge badge-public">Public</span></td></tr>
      <tr><td>Squadding</td><td class="url">/CoastalCup/squadding</td><td><span class="badge badge-public">Public</span></td></tr>
      <tr><td>Competitors Guide</td><td class="url">/CoastalCup/guide</td><td><span class="badge badge-public">Public</span></td></tr>
      <tr><td>Photo Gallery</td><td class="url">/CoastalCup/photos</td><td><span class="badge badge-public">Public</span></td></tr>
      <tr><td>Upload Squadding</td><td class="url">/CoastalCup/upload-squadding</td><td><span class="badge badge-public">Public</span></td></tr>
      <tr><td>Edit Competition</td><td class="url">/admin/competition/{id}</td><td><span class="badge badge-admin">Admin</span></td></tr>
    </table>
    <div class="note">Replace <code>/CoastalCup</code> with the competition route for other competitions (e.g. <code>/ClubDay</code>).</div>
  </div>

  <!-- ALL PAGES & ROUTES -->
  <h2 id="pages">All Pages & Routes</h2>

  <div class="card">
    <h3>Public Pages</h3>
    <table>
      <tr><th>URL Pattern</th><th>Description</th></tr>
      <tr><td class="url">/</td><td>Home page — lists all active & archived competitions and ranges</td></tr>
      <tr><td class="url">/{route}</td><td>Competition scoreboard — live scores, auto-scroll, shot badges</td></tr>
      <tr><td class="url">/{route}/squadding</td><td>Squadding / competitor list — relay, target, match assignments</td></tr>
      <tr><td class="url">/{route}/guide</td><td>Competitors guide (if HTML file exists on server)</td></tr>
      <tr><td class="url">/{route}/photos</td><td>Photo gallery &mdash; public upload, lightbox viewer</td></tr>
      <tr><td class="url">/{route}/upload-squadding</td><td>Upload squadding via CSV or pasted JSON</td></tr>
      <tr><td class="url">/{route}/scores/latest.json</td><td>Latest scores as JSON (used by scoreboard JS)</td></tr>
      <tr><td class="url">/{route}/competitors.json</td><td>Competitors as JSON (used by scoreboard/squadding JS)</td></tr>
      <tr><td class="url">/range/{range_id}</td><td>Range history — calendar view of shotlogs</td></tr>
      <tr><td class="url">/range/{range_id}/{date}</td><td>Specific day shotlog viewer</td></tr>
      <tr><td class="url">/range/{range_id}/upload</td><td>Upload shotlog CSV for a range</td></tr>
      <tr><td class="url">/about</td><td>About page</td></tr>
      <tr><td class="url">/contact</td><td>Contact form</td></tr>
    </table>
  </div>

  <div class="card">
    <h3>Admin Pages (require login)</h3>
    <table>
      <tr><th>URL</th><th>Description</th></tr>
      <tr><td class="url">/admin</td><td>Login page — password: <code>Gregory</code></td></tr>
      <tr><td class="url">/admin/dashboard</td><td>System status, stats, activity log, competition links</td></tr>
      <tr><td class="url">/admin/manage</td><td>Create/delete ranges and competitions, archive comps, view API keys</td></tr>
      <tr><td class="url">/admin/wiki</td><td>This wiki page</td></tr>
      <tr><td class="url">/admin/competition/{id}</td><td>Edit competition — manage shooters, scores, matches, sponsors</td></tr>
      <tr><td class="url">/admin/logout</td><td>Log out</td></tr>
    </table>
  </div>

  <div class="card">
    <h3>API Endpoints (Pi Scraper)</h3>
    <table>
      <tr><th>URL</th><th>Method</th><th>Auth</th><th>Description</th></tr>
      <tr><td class="url">/api/push/scores</td><td>POST</td><td><span class="badge badge-api">API Key</span></td><td>Push scores from Pi scraper</td></tr>
      <tr><td class="url">/api/push/competitors</td><td>POST</td><td><span class="badge badge-api">API Key</span></td><td>Push squadding data from Pi scraper</td></tr>
      <tr><td class="url">/api/push/shotlog</td><td>POST</td><td><span class="badge badge-api">API Key</span></td><td>Push shotlog CSV for club days</td></tr>
      <tr><td class="url">/api/destinations</td><td>GET</td><td><span class="badge badge-public">None</span></td><td>List ranges & competitions (for Pi config dropdown)</td></tr>
    </table>
    <div class="note">API key is sent in the <code>X-API-Key</code> header. Each range has its own key — visible on the Manage page.</div>
  </div>

  <!-- COMPETITION SETUP -->
  <h2 id="competition-setup">Setting Up a Competition</h2>
  <div class="card">
    <ol>
      <li>Go to <a href="/admin/manage">/admin/manage</a></li>
      <li>If needed, create a <strong>Range</strong> first (e.g. "BDRC" with ID "bdrc"). This generates an API key for the Pi scraper.</li>
      <li>Create a <strong>Competition</strong>:
        <ul>
          <li><strong>Name:</strong> Display name (e.g. "2026 Coastal Cup")</li>
          <li><strong>Route:</strong> URL slug — no spaces (e.g. "CoastalCup"). This becomes the URL: <code>/CoastalCup</code></li>
          <li><strong>Range:</strong> Select the range it belongs to</li>
        </ul>
      </li>
      <li>Upload squadding (see below)</li>
      <li>Configure the Pi scraper to point at this competition (see Scraper section)</li>
      <li>When the competition is over, use the <strong>Archive</strong> button on the Manage page to move it to the archived section</li>
    </ol>
  </div>

  <!-- SQUADDING -->
  <h2 id="squadding">Uploading Squadding</h2>
  <div class="card">
    <h3>URL</h3>
    <p>Go to <code>/{route}/upload-squadding</code> — e.g. <a href="/CoastalCup/upload-squadding">/CoastalCup/upload-squadding</a></p>

    <h3>CSV Format</h3>
    <p>Upload a CSV file with these columns (header row required):</p>
    <pre>name,class,relay,target,match,position
John Smith,F-Open,1,1,Match One 10+2,1
Jane Doe,FTR,1,2,Match One 10+2,2
Bob Jones,F-Open,2,1,Match Two,3</pre>
    <div class="note">
      <strong>Columns:</strong><br>
      <strong>name</strong> — Shooter name (must match ShotMarker exactly)<br>
      <strong>class</strong> — Category (F-Open, FTR, Sporter, etc.)<br>
      <strong>relay</strong> — Relay number<br>
      <strong>target</strong> — Target/lane number<br>
      <strong>match</strong> — Match name (e.g. "Match One 10+2", "Match Two", "Match Three Finals")<br>
      <strong>position</strong> — Firing position number
    </div>

    <h3>JSON Format (paste)</h3>
    <p>Alternatively, paste JSON in this format:</p>
    <pre>{
  "competitors": [
    {"name": "John Smith", "class": "F-Open", "relay": "1", "target": "1", "match": "Match One 10+2"},
    {"name": "Jane Doe", "class": "FTR", "relay": "1", "target": "2", "match": "Match One 10+2"}
  ]
}</pre>
    <div class="warning">Uploading new squadding <strong>replaces all existing competitors</strong> for that competition. Make sure your file is complete.</div>
  </div>

  <!-- SCORING -->
  <h2 id="scoring">Managing Scores</h2>
  <div class="card">
    <h3>Automatic (via Pi Scraper)</h3>
    <p>Scores are pushed automatically by the Pi scraper when connected to ShotMarker WiFi and uplink. See Scraper section below.</p>

    <h3>Manual Score Management</h3>
    <p>Go to <a href="/admin/dashboard">/admin/dashboard</a> → click a competition → <strong>Scores</strong> tab.</p>
    <ul>
      <li><strong>Add Score:</strong> Manually enter a shooter\'s shots for a match (comma-separated: X,6,5,5,4,...)</li>
      <li><strong>Edit Score:</strong> Click a score row to modify shots</li>
      <li><strong>Delete Score:</strong> Remove a single shooter\'s match score</li>
      <li><strong>Clear All Scores:</strong> Wipe all scores for the competition (use with caution!)</li>
    </ul>

    <h3>Match Management</h3>
    <p>Under the <strong>Matches</strong> tab, you can rename matches (e.g. fix "Match One 10+2" → "Match One").</p>

    <h3>Shooter Management</h3>
    <p>Under the <strong>Shooters</strong> tab:</p>
    <ul>
      <li><strong>Add/Edit/Delete</strong> individual shooters</li>
      <li><strong>Merge:</strong> Combine duplicate names (e.g. if ShotMarker has "J Smith" and squadding has "John Smith")</li>
    </ul>

    <h3>Scoring Format</h3>
    <p>Shots are comma-separated. Values: <code>X</code> (6pts + X-count), <code>V</code> or <code>5</code> (5pts + V-count), <code>4</code>, <code>3</code>, <code>2</code>, <code>1</code>, <code>0</code> (miss).</p>
  </div>

  <!-- PHOTOS -->
  <h2 id="photos">Photo Gallery</h2>
  <div class="card">
    <h3>Public Gallery</h3>
    <p>Available at <code>/{route}/photos</code> &mdash; e.g. <a href="/CoastalCup/photos">/CoastalCup/photos</a></p>
    <ul>
      <li><strong>Anyone</strong> can upload photos &mdash; no login required</li>
      <li>Photos are automatically resized to 800px and compressed (JPEG 70% quality, ~30-80KB each)</li>
      <li>Works from iPhone/Android &mdash; tap "Upload Photos" to pick from camera roll or take a photo</li>
      <li>Lightbox viewer with keyboard arrows and swipe on mobile</li>
      <li>Photos link appears in the scoreboard nav bar</li>
    </ul>

    <h3>Admin Management</h3>
    <p>Go to <a href="/admin/dashboard">/admin/dashboard</a> &rarr; click a competition &rarr; <strong>Photos</strong> tab.</p>
    <ul>
      <li><strong>Delete individual photo:</strong> Click the red &times; button on any photo</li>
      <li><strong>Clear All Photos:</strong> Deletes every photo for that competition (double confirmation required)</li>
    </ul>

    <h3>Storage</h3>
    <ul>
      <li>Photos stored on server at <code>/opt/smscores/photos/</code></li>
      <li>Filenames: <code>{comp_id}_{timestamp}_{random}.jpg</code></li>
      <li>Directory must exist with write permissions: <code>chmod 777 /opt/smscores/photos</code></li>
    </ul>
  </div>

  <!-- PI SCRAPER -->
  <h2 id="scraper">Pi Scraper Setup & Operation</h2>
  <div class="card">
    <h3>Hardware</h3>
    <ul>
      <li><strong>Device:</strong> Raspberry Pi 5, hostname: <code>ScoreScraper</code></li>
      <li><strong>AP adapter (wlan2):</strong> USB MediaTek mt76x2u — runs the "scraper" hotspot (open network, channel 6)</li>
      <li><strong>Scrape adapter (wlan1):</strong> USB MediaTek mt76x2u — cycles through ShotMarker networks then connects to uplink WiFi to upload</li>
      <li><strong>Ethernet (eth0):</strong> Home LAN (IP: 192.168.1.107)</li>
      <li><strong>Internal WiFi (wlan0):</strong> Disabled (broken in AP mode on Trixie)</li>
    </ul>

    <h3>Connecting to the Pi</h3>
    <ol>
      <li>Connect your device to the <strong>"scraper"</strong> WiFi network (open, no password)</li>
      <li>Open a browser and go to <code>http://192.168.100.1:8080</code></li>
      <li>This is the scraper web config interface</li>
    </ol>

    <h3>Pi Web Config Interface</h3>
    <p>The config page at <code>http://192.168.100.1:8080</code> lets you:</p>
    <ul>
      <li><strong>Select Destination:</strong> Choose which range and competition scores are pushed to</li>
      <li><strong>Configure Uplink WiFi:</strong> Set the SSID and password for the internet-connected network (e.g. phone hotspot, venue WiFi)</li>
      <li><strong>Manage SM Channels:</strong> Enable/disable ShotMarker networks to scrape (SM1=ShotMarker, SM2=ShotMarker2, etc.)</li>
      <li><strong>Set Scrape Interval:</strong>
        <ul>
          <li><strong>None:</strong> Manual only — use the "Load Now" button</li>
          <li><strong>15 sec:</strong> Competition mode — fastest refresh</li>
          <li><strong>90 sec:</strong> Moderate refresh</li>
          <li><strong>300 sec:</strong> Slow refresh (5 minutes)</li>
        </ul>
      </li>
      <li><strong>Load Now:</strong> Manually trigger an immediate scrape+upload cycle</li>
    </ul>

    <h3>How the Scraper Works</h3>
    <ol>
      <li>wlan1 connects to each enabled ShotMarker WiFi network in turn</li>
      <li>Fetches scores from <code>http://192.168.100.1/api/v1/match/scores</code></li>
      <li>Fetches shotlog CSV (rate-limited to every 5 minutes)</li>
      <li>Disconnects from ShotMarker, connects to uplink WiFi</li>
      <li>Pushes scores to cloud: <code>POST /api/push/scores</code> with API key</li>
      <li>Pushes shotlog to cloud: <code>POST /api/push/shotlog</code></li>
      <li>Disconnects, waits for next interval, repeats</li>
    </ol>

    <h3>SSH Access</h3>
    <pre>ssh tghaines@192.168.1.107    # via home LAN / ethernet</pre>

    <h3>Key Files on Pi</h3>
    <table>
      <tr><th>File</th><th>Purpose</th></tr>
      <tr><td><code>/opt/scraper/scraper_web.py</code></td><td>Web config UI (port 8080)</td></tr>
      <tr><td><code>/opt/scraper/multi_scraper.py</code></td><td>ShotMarker data scraper</td></tr>
      <tr><td><code>/opt/scraper/scraper_config.json</code></td><td>Current config (destination, uplink, channels, interval)</td></tr>
      <tr><td><code>/tmp/multi_scraper.log</code></td><td>Scraper log file</td></tr>
      <tr><td><code>/tmp/scraper_trigger</code></td><td>Trigger file for manual "Load Now"</td></tr>
    </table>

    <h3>Services</h3>
    <pre>sudo systemctl status scraper_web.service      # Web config UI
sudo systemctl status multi_scraper.service     # Data scraper
sudo systemctl restart scraper_web.service      # Restart web UI
sudo systemctl restart multi_scraper.service    # Restart scraper
sudo journalctl -u multi_scraper -f             # Live scraper logs</pre>

    <h3>Deploying Updates</h3>
    <pre># From your PC (in the project folder):
scp "./scraper_web_v3.py" tghaines@192.168.1.107:/opt/scraper/scraper_web_v3.py
scp "./multi_scraper_v2.py" tghaines@192.168.1.107:/opt/scraper/multi_scraper_v2.py

# Then SSH into the Pi and run:
sudo cp /opt/scraper/scraper_web_v3.py /opt/scraper/scraper_web.py
sudo cp /opt/scraper/multi_scraper_v2.py /opt/scraper/multi_scraper.py
sudo systemctl restart scraper_web.service
sudo systemctl restart multi_scraper.service</pre>
  </div>

  <!-- SERVER -->
  <h2 id="server">Server & Database</h2>
  <div class="card">
    <h3>Cloud Server</h3>
    <table>
      <tr><td>IP</td><td><code>134.199.153.50</code></td></tr>
      <tr><td>SSH</td><td><code>ssh root@134.199.153.50</code></td></tr>
      <tr><td>App Location</td><td><code>/opt/smscores/app.py</code></td></tr>
      <tr><td>App Backup</td><td><code>/opt/smscores/app.py.bak</code></td></tr>
      <tr><td>Service</td><td><code>smscores</code></td></tr>
      <tr><td>Restart</td><td><code>sudo systemctl restart smscores</code></td></tr>
    </table>

    <h3>Database</h3>
    <table>
      <tr><td>Type</td><td>PostgreSQL</td></tr>
      <tr><td>Database</td><td><code>smscores</code></td></tr>
      <tr><td>User</td><td><code>smscores</code></td></tr>
      <tr><td>Password</td><td><code>smscores123</code></td></tr>
    </table>
    <pre># Connect to database:
sudo -u postgres psql smscores

# Useful queries:
SELECT id, name, route, active FROM competition;
SELECT id, name, api_key FROM range;
SELECT COUNT(*) FROM score WHERE competition_id = 1;</pre>

    <h3>Deploying App Updates</h3>
    <pre># From your PC:
scp "./app.py" root@134.199.153.50:/opt/smscores/app.py
ssh root@134.199.153.50 "sudo systemctl restart smscores"</pre>
  </div>

  <!-- TROUBLESHOOTING -->
  <h2 id="troubleshooting">Troubleshooting</h2>
  <div class="card">
    <h3>Scores not appearing on scoreboard</h3>
    <ol>
      <li>Check Pi scraper is running: <code>sudo systemctl status multi_scraper.service</code></li>
      <li>Check scraper logs: <code>cat /tmp/multi_scraper.log</code></li>
      <li>Verify destination is configured on Pi web UI (<code>http://192.168.100.1:8080</code>)</li>
      <li>Verify uplink WiFi is set and reachable</li>
      <li>Check scrape interval is not set to "None" (or use "Load Now" button)</li>
      <li>Check shooter names match between ShotMarker and squadding — use Merge on admin page if needed</li>
    </ol>

    <h3>Squadding upload not working</h3>
    <ul>
      <li>Ensure CSV has a header row with: <code>name,class,relay,target,match</code></li>
      <li>Check there are no extra commas or encoding issues (save as UTF-8)</li>
      <li>The <code>name</code> column must not be empty</li>
    </ul>

    <h3>Pi scraper can\'t connect to ShotMarker</h3>
    <ul>
      <li>Ensure ShotMarker device is powered on and broadcasting WiFi</li>
      <li>Check the correct SSID is configured (ShotMarker, ShotMarker2, etc.)</li>
      <li>Try moving the Pi closer to the ShotMarker unit</li>
      <li>Restart the scraper: <code>sudo systemctl restart multi_scraper.service</code></li>
    </ul>

    <h3>500 Internal Server Error</h3>
    <ul>
      <li>SSH into server: <code>ssh root@134.199.153.50</code></li>
      <li>Check logs: <code>sudo journalctl -u smscores -n 50</code></li>
      <li>Common cause: missing Python import or syntax error in app.py</li>
    </ul>

    <h3>Pi undervoltage warnings</h3>
    <ul>
      <li>Use the official Raspberry Pi 5 27W USB-C power supply</li>
      <li>Two USB WiFi adapters draw significant power — a powered USB hub may help</li>
    </ul>
  </div>

  <div style="text-align:center; color:#555; font-size:12px; margin-top:40px; padding-top:20px; border-top:1px solid var(--border);">
    SM Scores Admin Wiki — Last updated March 2026
  </div>
</div>
</body>
</html>'''

@app.route('/admin/wiki')
def admin_wiki():
    if not session.get('admin'):
        return redirect('/admin')
    return ADMIN_WIKI_HTML

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
    <a href="/admin/wiki">Wiki</a>
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
        <td class="api-key" id="key-{{ r.id }}">{{ r.api_key }}</td>
        <td style="white-space:nowrap;">
          <button class="btn btn-primary btn-small" onclick="copyKey('{{ r.id }}')" title="Copy API key">Copy</button>
          <button class="btn btn-small" style="background:var(--gold);color:var(--bg);" onclick="confirmRegen('{{ r.id }}', '{{ r.name }}')" title="Generate new API key">Regenerate</button>
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
      <tr><th>Route</th><th>Name</th><th>Range</th><th>Status</th><th>Actions</th></tr>
      {% for c in competitions %}
      <tr>
        <td>/{{ c.route }}</td>
        <td>{{ c.name }}</td>
        <td>{{ c.range_id }}</td>
        <td style="color:{% if c.active %}var(--green){% else %}var(--text2){% endif %};">{% if c.active %}Live{% else %}Archived{% endif %}</td>
        <td>
          <a href="/{{ c.route }}" class="btn btn-primary btn-small" target="_blank">View</a>
          <form method="POST" action="/admin/manage/comp/archive/{{ c.id }}" style="display:inline;">
            <button type="submit" class="btn btn-small" style="background:var(--blue);color:var(--bg);">{% if c.active %}Archive{% else %}Unarchive{% endif %}</button>
          </form>
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

<!-- Confirmation Modal -->
<div class="confirm-delete" id="confirmModal">
  <div class="confirm-box">
    <p id="confirmText"></p>
    <p id="confirmWarning" style="font-size:0.9rem;"></p>
    <form method="POST" id="confirmForm">
      <button type="submit" class="btn btn-danger" id="confirmBtn">Confirm</button>
      <button type="button" class="btn btn-primary" onclick="closeModal()">Cancel</button>
    </form>
  </div>
</div>

<script>
function confirmDelete(type, id, name) {
  document.getElementById('confirmText').innerHTML = 'Are you sure you want to delete <strong>' + name + '</strong>?';
  document.getElementById('confirmWarning').textContent = 'This cannot be undone!';
  document.getElementById('confirmWarning').style.color = 'var(--red)';
  document.getElementById('confirmBtn').textContent = 'Yes, Delete';
  document.getElementById('confirmBtn').className = 'btn btn-danger';
  document.getElementById('confirmForm').action = '/admin/manage/' + type + '/delete/' + id;
  document.getElementById('confirmModal').style.display = 'flex';
}
function confirmRegen(id, name) {
  document.getElementById('confirmText').innerHTML = 'Regenerate API key for <strong>' + name + '</strong>?';
  document.getElementById('confirmWarning').textContent = 'The old key will stop working immediately. Update all scrapers with the new key.';
  document.getElementById('confirmWarning').style.color = 'var(--gold)';
  document.getElementById('confirmBtn').textContent = 'Yes, Regenerate';
  document.getElementById('confirmBtn').className = 'btn btn-primary';
  document.getElementById('confirmForm').action = '/admin/manage/range/regenerate/' + id;
  document.getElementById('confirmModal').style.display = 'flex';
}
function copyKey(rangeId) {
  var keyText = document.getElementById('key-' + rangeId).textContent;
  navigator.clipboard.writeText(keyText).then(function() {
    alert('API key copied to clipboard');
  });
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

@app.route('/admin/manage/range/regenerate/<range_id>', methods=['POST'])
def admin_regenerate_key(range_id):
    if not session.get('admin'):
        return redirect('/admin')
    range_obj = Range.query.get(range_id)
    if not range_obj:
        return redirect('/admin/manage?msg=Range not found&type=error')
    range_obj.api_key = secrets.token_hex(32)
    db.session.commit()
    log_activity(f'API key regenerated for {range_obj.name} ({range_id})', 'warn')
    return redirect(f'/admin/manage?msg=API key regenerated for {range_obj.name}. Update all scrapers with the new key.&type=success')

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

@app.route('/admin/manage/comp/archive/<int:comp_id>', methods=['POST'])
def admin_archive_comp(comp_id):
    if not session.get('admin'):
        return redirect('/admin')
    comp = Competition.query.get(comp_id)
    if not comp:
        return redirect('/admin/manage?msg=Competition not found&type=error')
    comp.active = not comp.active
    db.session.commit()
    action = 'unarchived' if comp.active else 'archived'
    log_activity(f'Competition {action}: {comp.name}', 'info')
    return redirect(f'/admin/manage?msg={comp.name} {action}&type=success')

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

# ══════════════════════════════════════════════
#  API - List Available Destinations
# ══════════════════════════════════════════════

@app.route('/api/destinations')
def api_destinations():
    """Return available ranges and competitions for Pi config"""
    ranges = []
    for r in Range.query.all():
        ranges.append({
            'id': r.id,
            'name': r.name
        })
    
    competitions = []
    for c in Competition.query.all():
        competitions.append({
            'id': c.id,
            'route': c.route,
            'name': c.name,
            'range_id': c.range_id
        })
    
    return jsonify({
        'ranges': ranges,
        'competitions': competitions
    })

# ══════════════════════════════════════════════
#  API - Validate API Key
# ══════════════════════════════════════════════

@app.route('/api/validate-key')
def api_validate_key():
    """Validate an API key and return the range info + competitions"""
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return jsonify({'error': 'Missing API key'}), 401
    range_obj = Range.query.filter_by(api_key=api_key).first()
    if not range_obj:
        return jsonify({'error': 'Invalid API key'}), 401

    competitions = []
    for c in Competition.query.filter_by(range_id=range_obj.id).all():
        if c.active:
            competitions.append({
                'id': c.id,
                'route': c.route,
                'name': c.name
            })

    return jsonify({
        'range_id': range_obj.id,
        'range_name': range_obj.name,
        'competitions': competitions
    })
