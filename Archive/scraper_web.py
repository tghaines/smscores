#!/usr/bin/env python3
"""
ScoreScraper Configuration Web App
Run on Pi to configure which range/competition to push data to
"""
from flask import Flask, render_template_string, request, jsonify
import json
import os
import requests

app = Flask(__name__)

# Config file path
CONFIG_FILE = '/opt/scraper/scraper_config.json'
CLOUD_URL = 'http://134.199.153.50'

# Default config
DEFAULT_CONFIG = {
    'active_range': None,
    'active_competition': None,
    'cloud_url': CLOUD_URL,
    'api_key': 'ab6d1435dccd0fb7a09133284ed0f256d901a0c0538c1e56d5d3c7e4726b791f',
    'sm_channels': [
        {'name': 'SM1', 'ssid': 'ShotMarker', 'enabled': True},
        {'name': 'SM2', 'ssid': 'ShotMarker2', 'enabled': True},
        {'name': 'SM3', 'ssid': 'ShotMarker3', 'enabled': True},
        {'name': 'SM4', 'ssid': 'ShotMarker4', 'enabled': True},
    ]
}

def load_config():
    """Load config from file or return defaults"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return DEFAULT_CONFIG.copy()

def save_config(config):
    """Save config to file"""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

def fetch_destinations():
    """Fetch available ranges and competitions from cloud"""
    try:
        resp = requests.get(f'{CLOUD_URL}/api/destinations', timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f'Error fetching destinations: {e}')
    return {'ranges': [], 'competitions': []}

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ScoreScraper Config</title>
<style>
:root { --bg:#0c1e2b; --bg2:#122a3a; --gold:#f4c566; --blue:#54b8db; --green:#5cc9a7; --red:#e74c3c; --text:#f0ece4; --text2:#8ab4c8; --border:#1e3d50; }
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--bg); color:var(--text); font-family:system-ui,-apple-system,sans-serif; min-height:100vh; padding:20px; }
.container { max-width:500px; margin:0 auto; }
h1 { color:var(--gold); margin-bottom:10px; font-size:1.8rem; }
h2 { color:var(--gold); font-size:1.2rem; margin:20px 0 10px; }
.subtitle { color:var(--text2); margin-bottom:20px; font-size:0.9rem; }
.card { background:var(--bg2); border:1px solid var(--border); border-radius:8px; padding:20px; margin-bottom:20px; }
.form-group { margin-bottom:15px; }
.form-group label { display:block; color:var(--text2); margin-bottom:5px; font-size:0.9rem; }
.form-group select, .form-group input { width:100%; padding:12px; background:var(--bg); border:1px solid var(--border); border-radius:4px; color:var(--text); font-size:1rem; }
.form-group select:focus, .form-group input:focus { outline:none; border-color:var(--gold); }
.btn { width:100%; padding:14px; border:none; border-radius:4px; cursor:pointer; font-size:1.1rem; font-weight:600; }
.btn-primary { background:var(--gold); color:var(--bg); }
.btn-secondary { background:var(--blue); color:var(--bg); margin-top:10px; }
.btn:hover { opacity:0.9; }
.status { padding:15px; border-radius:4px; margin-bottom:20px; }
.status-ok { background:rgba(92,201,167,0.2); border:1px solid var(--green); }
.status-warn { background:rgba(244,197,102,0.2); border:1px solid var(--gold); }
.status-none { background:rgba(231,76,60,0.2); border:1px solid var(--red); }
.status-label { color:var(--text2); font-size:0.85rem; }
.status-value { font-size:1.1rem; font-weight:600; margin-top:3px; }
.channel-grid { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
.channel { padding:10px; background:var(--bg); border-radius:4px; display:flex; align-items:center; justify-content:space-between; }
.channel-name { font-weight:600; }
.channel-status { font-size:0.85rem; }
.channel-on { color:var(--green); }
.channel-off { color:var(--red); }
.toggle { position:relative; width:50px; height:26px; }
.toggle input { opacity:0; width:0; height:0; }
.toggle .slider { position:absolute; cursor:pointer; top:0; left:0; right:0; bottom:0; background:var(--border); border-radius:26px; transition:0.3s; }
.toggle .slider:before { position:absolute; content:""; height:20px; width:20px; left:3px; bottom:3px; background:var(--text); border-radius:50%; transition:0.3s; }
.toggle input:checked + .slider { background:var(--green); }
.toggle input:checked + .slider:before { transform:translateX(24px); }
.flash { padding:15px; border-radius:4px; margin-bottom:20px; text-align:center; }
.flash-success { background:rgba(92,201,167,0.2); border:1px solid var(--green); color:var(--green); }
.flash-error { background:rgba(231,76,60,0.2); border:1px solid var(--red); color:var(--red); }
.refresh-note { text-align:center; color:var(--text2); font-size:0.85rem; margin-top:10px; }
</style>
</head>
<body>
<div class="container">
  <h1>📡 ScoreScraper</h1>
  <p class="subtitle">Configure data destination</p>
  
  {% if message %}
  <div class="flash flash-{{ message_type }}">{{ message }}</div>
  {% endif %}
  
  <!-- Current Status -->
  <div class="card">
    <div class="status {% if config.active_range %}status-ok{% else %}status-none{% endif %}">
      <div class="status-label">Currently pushing to:</div>
      <div class="status-value">
        {% if config.active_range %}
          {{ config.active_range }}{% if config.active_competition %} → {{ config.active_competition }}{% endif %}
        {% else %}
          Not configured
        {% endif %}
      </div>
    </div>
  </div>
  
  <!-- Destination Config -->
  <div class="card">
    <h2>📍 Destination</h2>
    <form method="POST" action="/save">
      <div class="form-group">
        <label>Range</label>
        <select name="active_range" id="rangeSelect" onchange="filterCompetitions()">
          <option value="">-- Select Range --</option>
          {% for r in destinations.ranges %}
          <option value="{{ r.id }}" {% if config.active_range == r.id %}selected{% endif %}>{{ r.name }}</option>
          {% endfor %}
        </select>
      </div>
      
      <div class="form-group">
        <label>Competition (optional - leave blank for club day)</label>
        <select name="active_competition" id="compSelect">
          <option value="">-- No Competition (Club Day) --</option>
          {% for c in destinations.competitions %}
          <option value="{{ c.route }}" data-range="{{ c.range_id }}" {% if config.active_competition == c.route %}selected{% endif %}>{{ c.name }}</option>
          {% endfor %}
        </select>
      </div>
      
      <button type="submit" class="btn btn-primary">💾 Save Destination</button>
    </form>
  </div>
  
  <!-- SM Channels -->
  <div class="card">
    <h2>📶 ShotMarker Channels</h2>
    <form method="POST" action="/save-channels">
      <div class="channel-grid">
        {% for ch in config.sm_channels %}
        <div class="channel">
          <div>
            <div class="channel-name">{{ ch.name }}</div>
            <div class="channel-status">{{ ch.ssid }}</div>
          </div>
          <label class="toggle">
            <input type="checkbox" name="ch_{{ loop.index0 }}" {% if ch.enabled %}checked{% endif %}>
            <span class="slider"></span>
          </label>
        </div>
        {% endfor %}
      </div>
      <button type="submit" class="btn btn-secondary">Save Channels</button>
    </form>
  </div>
  
  <button class="btn btn-secondary" onclick="location.reload()">🔄 Refresh</button>
  <p class="refresh-note">Scraper will use new settings on next cycle (within 30 seconds)</p>
</div>

<script>
function filterCompetitions() {
  var range = document.getElementById('rangeSelect').value;
  var compSelect = document.getElementById('compSelect');
  var options = compSelect.options;
  
  for (var i = 0; i < options.length; i++) {
    var opt = options[i];
    var optRange = opt.getAttribute('data-range');
    if (!optRange || optRange === range) {
      opt.style.display = '';
    } else {
      opt.style.display = 'none';
      if (opt.selected) {
        compSelect.value = '';
      }
    }
  }
}
// Run on page load
filterCompetitions();
</script>
</body>
</html>
'''

@app.route('/')
def index():
    config = load_config()
    destinations = fetch_destinations()
    message = request.args.get('msg')
    message_type = request.args.get('type', 'success')
    
    return render_template_string(HTML_TEMPLATE,
        config=config,
        destinations=destinations,
        message=message,
        message_type=message_type
    )

@app.route('/save', methods=['POST'])
def save_destination():
    config = load_config()
    
    config['active_range'] = request.form.get('active_range') or None
    config['active_competition'] = request.form.get('active_competition') or None
    
    save_config(config)
    
    dest = config['active_range'] or 'None'
    if config['active_competition']:
        dest += f" → {config['active_competition']}"
    
    return redirect(f'/?msg=Destination saved: {dest}&type=success')

@app.route('/save-channels', methods=['POST'])
def save_channels():
    config = load_config()
    
    for i, ch in enumerate(config['sm_channels']):
        ch['enabled'] = request.form.get(f'ch_{i}') == 'on'
    
    save_config(config)
    
    enabled = [ch['name'] for ch in config['sm_channels'] if ch['enabled']]
    return redirect(f'/?msg=Channels saved: {", ".join(enabled) or "None"}&type=success')

@app.route('/config')
def get_config():
    """API endpoint for scraper to read config"""
    return jsonify(load_config())

from flask import redirect

if __name__ == '__main__':
    # Ensure config file exists
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
    
    app.run(host='0.0.0.0', port=8080, debug=False)
