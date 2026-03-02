#!/usr/bin/env python3
"""
ScoreScraper Configuration Web App
Run on Pi to configure which range/competition to push data to
Now includes WiFi uplink configuration
"""
from flask import Flask, render_template_string, request, jsonify, redirect
import json
import os
import requests
import subprocess

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
    ],
    'uplink_ssid': '',
    'uplink_password': '',
}

def load_config():
    """Load config from file or return defaults"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                # Ensure new fields exist
                if 'uplink_ssid' not in config:
                    config['uplink_ssid'] = ''
                if 'uplink_password' not in config:
                    config['uplink_password'] = ''
                return config
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

def scan_wifi():
    """Scan for available WiFi networks using wlan1"""
    networks = []
    try:
        # Use nmcli to scan
        result = subprocess.run(
            ['sudo', 'nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY', 'device', 'wifi', 'list', 'ifname', 'wlan1', '--rescan', 'yes'],
            capture_output=True, text=True, timeout=30
        )
        seen = set()
        for line in result.stdout.strip().split('\n'):
            if line and ':' in line:
                parts = line.split(':')
                ssid = parts[0]
                if ssid and ssid not in seen and not ssid.startswith('ShotMarker'):
                    seen.add(ssid)
                    signal = parts[1] if len(parts) > 1 else '0'
                    security = parts[2] if len(parts) > 2 else ''
                    networks.append({
                        'ssid': ssid,
                        'signal': int(signal) if signal.isdigit() else 0,
                        'security': 'Open' if not security else 'Secured'
                    })
        # Sort by signal strength
        networks.sort(key=lambda x: x['signal'], reverse=True)
    except Exception as e:
        print(f'WiFi scan error: {e}')
    return networks

def test_uplink_connection(ssid, password):
    """Test connection to uplink network"""
    try:
        # Create or update the connection
        conn_name = 'Uplink-Network'
        
        # Delete existing if present
        subprocess.run(['sudo', 'nmcli', 'connection', 'delete', conn_name], 
                      capture_output=True, timeout=10)
        
        # Create new connection
        if password:
            result = subprocess.run([
                'sudo', 'nmcli', 'connection', 'add',
                'type', 'wifi',
                'ifname', 'wlan1',
                'con-name', conn_name,
                'ssid', ssid,
                'wifi-sec.key-mgmt', 'wpa-psk',
                'wifi-sec.psk', password
            ], capture_output=True, text=True, timeout=15)
        else:
            result = subprocess.run([
                'sudo', 'nmcli', 'connection', 'add',
                'type', 'wifi',
                'ifname', 'wlan1',
                'con-name', conn_name,
                'ssid', ssid
            ], capture_output=True, text=True, timeout=15)
        
        if result.returncode != 0:
            return False, f"Failed to create connection: {result.stderr}"
        
        # Try to connect
        result = subprocess.run([
            'sudo', 'nmcli', 'connection', 'up', conn_name
        ], capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            # Disconnect after test
            subprocess.run(['sudo', 'nmcli', 'connection', 'down', conn_name], 
                          capture_output=True, timeout=10)
            return True, "Connection successful!"
        else:
            return False, f"Failed to connect: {result.stderr}"
            
    except Exception as e:
        return False, str(e)

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
.btn-small { width:auto; padding:8px 16px; font-size:0.9rem; }
.btn:hover { opacity:0.9; }
.btn:disabled { opacity:0.5; cursor:not-allowed; }
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
.wifi-list { max-height:200px; overflow-y:auto; background:var(--bg); border-radius:4px; margin-bottom:15px; }
.wifi-item { display:flex; justify-content:space-between; align-items:center; padding:10px 12px; border-bottom:1px solid var(--border); cursor:pointer; }
.wifi-item:hover { background:var(--bg2); }
.wifi-item:last-child { border-bottom:none; }
.wifi-ssid { font-weight:500; }
.wifi-signal { font-size:0.85rem; color:var(--text2); }
.wifi-signal-bar { display:inline-block; width:30px; height:12px; background:var(--border); border-radius:2px; overflow:hidden; margin-left:8px; }
.wifi-signal-fill { height:100%; background:var(--green); }
.tabs { display:flex; gap:4px; margin-bottom:20px; }
.tab { flex:1; padding:12px; background:var(--bg2); border:1px solid var(--border); border-radius:4px; text-align:center; cursor:pointer; color:var(--text2); }
.tab.active { background:var(--gold); color:var(--bg); border-color:var(--gold); }
.tab-content { display:none; }
.tab-content.active { display:block; }
.uplink-current { padding:10px; background:var(--bg); border-radius:4px; margin-bottom:15px; }
.uplink-current .label { font-size:0.85rem; color:var(--text2); }
.uplink-current .value { color:var(--green); font-weight:600; }
.scanning { text-align:center; padding:20px; color:var(--text2); }
</style>
</head>
<body>
<div class="container">
  <h1>📡 ScoreScraper</h1>
  <p class="subtitle">Configure data destination & WiFi uplink</p>

  {% if message %}
  <div class="flash flash-{{ message_type }}">{{ message }}</div>
  {% endif %}

  <div class="tabs">
    <div class="tab active" onclick="showTab('destination')">📍 Destination</div>
    <div class="tab" onclick="showTab('wifi')">📶 WiFi Uplink</div>
    <div class="tab" onclick="showTab('channels')">🎯 SM Channels</div>
  </div>

  <!-- Destination Tab -->
  <div id="destination-tab" class="tab-content active">
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
  </div>

  <!-- WiFi Uplink Tab -->
  <div id="wifi-tab" class="tab-content">
    <div class="card">
      <h2>📶 WiFi Uplink Network</h2>
      <p style="color:var(--text2); font-size:0.9rem; margin-bottom:15px;">
        Configure which WiFi network to use for uploading data to the cloud.
      </p>
      
      {% if config.uplink_ssid %}
      <div class="uplink-current">
        <div class="label">Current uplink:</div>
        <div class="value">{{ config.uplink_ssid }}</div>
      </div>
      {% endif %}

      <form method="POST" action="/save-uplink">
        <div class="form-group">
          <label>Available Networks <button type="button" class="btn btn-small btn-secondary" onclick="scanWifi()">🔍 Scan</button></label>
          <div class="wifi-list" id="wifiList">
            <div class="scanning">Click Scan to find networks...</div>
          </div>
        </div>

        <div class="form-group">
          <label>Network Name (SSID)</label>
          <input type="text" name="uplink_ssid" id="uplinkSsid" value="{{ config.uplink_ssid }}" placeholder="Enter or select from scan">
        </div>

        <div class="form-group">
          <label>Password</label>
          <input type="password" name="uplink_password" id="uplinkPassword" value="{{ config.uplink_password }}" placeholder="WiFi password">
        </div>

        <button type="button" class="btn btn-secondary" onclick="testUplink()">🧪 Test Connection</button>
        <button type="submit" class="btn btn-primary" style="margin-top:10px;">💾 Save Uplink</button>
      </form>
    </div>
  </div>

  <!-- SM Channels Tab -->
  <div id="channels-tab" class="tab-content">
    <div class="card">
      <h2>🎯 ShotMarker Channels</h2>
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
  </div>

  <button class="btn btn-secondary" onclick="location.reload()">🔄 Refresh</button>
  <p class="refresh-note">Scraper will use new settings on next cycle (within 30 seconds)</p>
</div>

<script>
function showTab(tab) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  event.target.classList.add('active');
  document.getElementById(tab + '-tab').classList.add('active');
}

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

function scanWifi() {
  var list = document.getElementById('wifiList');
  list.innerHTML = '<div class="scanning">Scanning...</div>';
  
  fetch('/api/scan-wifi')
    .then(r => r.json())
    .then(data => {
      if (data.networks && data.networks.length > 0) {
        var html = '';
        data.networks.forEach(n => {
          var fillWidth = n.signal + '%';
          html += '<div class="wifi-item" onclick="selectWifi(\\''+n.ssid.replace(/'/g, "\\\\'")+'\\')">' +
            '<span class="wifi-ssid">' + n.ssid + '</span>' +
            '<span class="wifi-signal">' + n.security + 
            '<span class="wifi-signal-bar"><span class="wifi-signal-fill" style="width:'+fillWidth+'"></span></span></span>' +
            '</div>';
        });
        list.innerHTML = html;
      } else {
        list.innerHTML = '<div class="scanning">No networks found</div>';
      }
    })
    .catch(err => {
      list.innerHTML = '<div class="scanning">Scan failed: ' + err + '</div>';
    });
}

function selectWifi(ssid) {
  document.getElementById('uplinkSsid').value = ssid;
  document.getElementById('uplinkPassword').focus();
}

function testUplink() {
  var ssid = document.getElementById('uplinkSsid').value;
  var password = document.getElementById('uplinkPassword').value;
  
  if (!ssid) {
    alert('Please enter a network name');
    return;
  }
  
  var btn = event.target;
  btn.disabled = true;
  btn.textContent = 'Testing...';
  
  fetch('/api/test-uplink', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ssid: ssid, password: password})
  })
    .then(r => r.json())
    .then(data => {
      if (data.success) {
        alert('✅ ' + data.message);
      } else {
        alert('❌ ' + data.message);
      }
      btn.disabled = false;
      btn.textContent = '🧪 Test Connection';
    })
    .catch(err => {
      alert('Error: ' + err);
      btn.disabled = false;
      btn.textContent = '🧪 Test Connection';
    });
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
        dest += f" -> {config['active_competition']}"

    return redirect(f'/?msg=Destination saved: {dest}&type=success')

@app.route('/save-channels', methods=['POST'])
def save_channels():
    config = load_config()

    for i, ch in enumerate(config['sm_channels']):
        ch['enabled'] = request.form.get(f'ch_{i}') == 'on'

    save_config(config)

    enabled = [ch['name'] for ch in config['sm_channels'] if ch['enabled']]
    return redirect(f'/?msg=Channels saved: {", ".join(enabled) or "None"}&type=success')

@app.route('/save-uplink', methods=['POST'])
def save_uplink():
    config = load_config()
    
    config['uplink_ssid'] = request.form.get('uplink_ssid', '').strip()
    config['uplink_password'] = request.form.get('uplink_password', '')
    
    save_config(config)
    
    return redirect(f'/?msg=Uplink saved: {config["uplink_ssid"]}&type=success')

@app.route('/api/scan-wifi')
def api_scan_wifi():
    """API endpoint to scan for WiFi networks"""
    networks = scan_wifi()
    return jsonify({'networks': networks})

@app.route('/api/test-uplink', methods=['POST'])
def api_test_uplink():
    """API endpoint to test uplink connection"""
    data = request.get_json()
    ssid = data.get('ssid', '')
    password = data.get('password', '')
    
    if not ssid:
        return jsonify({'success': False, 'message': 'SSID required'})
    
    success, message = test_uplink_connection(ssid, password)
    return jsonify({'success': success, 'message': message})

@app.route('/config')
def get_config():
    """API endpoint for scraper to read config"""
    return jsonify(load_config())

if __name__ == '__main__':
    # Ensure config file exists
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)

    app.run(host='0.0.0.0', port=8080, debug=False)
