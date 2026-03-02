#!/usr/bin/env python3
"""
ScoreScraper Configuration Web App
Run on Pi to configure which range/competition to push data to
Includes WiFi uplink configuration and diagnostics
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
    'scrape_interval': 0,
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                if 'uplink_ssid' not in config:
                    config['uplink_ssid'] = ''
                if 'uplink_password' not in config:
                    config['uplink_password'] = ''
                if 'scrape_interval' not in config:
                    config['scrape_interval'] = 0
                return config
        except:
            pass
    return DEFAULT_CONFIG.copy()

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

def fetch_destinations():
    try:
        resp = requests.get(f'{CLOUD_URL}/api/destinations', timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f'Error fetching destinations: {e}')
    return {'ranges': [], 'competitions': []}

def scan_wifi():
    networks = []
    try:
        result = subprocess.run(
            ['sudo', 'nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY', 'device', 'wifi', 'list', 'ifname', 'wlan0', '--rescan', 'yes'],
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
        networks.sort(key=lambda x: x['signal'], reverse=True)
    except Exception as e:
        print(f'WiFi scan error: {e}')
    return networks

def test_uplink_connection(ssid, password):
    try:
        conn_name = 'Uplink-Network'
        subprocess.run(['sudo', 'nmcli', 'connection', 'delete', conn_name], 
                      capture_output=True, timeout=10)
        
        if password:
            result = subprocess.run([
                'sudo', 'nmcli', 'connection', 'add',
                'type', 'wifi', 'ifname', 'wlan0', 'con-name', conn_name,
                'ssid', ssid, 'wifi-sec.key-mgmt', 'wpa-psk', 'wifi-sec.psk', password
            ], capture_output=True, text=True, timeout=15)
        else:
            result = subprocess.run([
                'sudo', 'nmcli', 'connection', 'add',
                'type', 'wifi', 'ifname', 'wlan0', 'con-name', conn_name, 'ssid', ssid
            ], capture_output=True, text=True, timeout=15)
        
        if result.returncode != 0:
            return False, f"Failed to create connection: {result.stderr}"
        
        result = subprocess.run(['sudo', 'nmcli', 'connection', 'up', conn_name],
                               capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            subprocess.run(['sudo', 'nmcli', 'connection', 'down', conn_name], 
                          capture_output=True, timeout=10)
            return True, "Connection successful!"
        else:
            return False, f"Failed to connect: {result.stderr}"
    except Exception as e:
        return False, str(e)

def get_diagnostics():
    diag = {
        'interfaces': [],
        'connections': [],
        'scraper_status': 'Unknown',
        'uptime': '',
        'disk_free': ''
    }
    
    try:
        result = subprocess.run(['ip', '-br', 'addr'], capture_output=True, text=True, timeout=5)
        for line in result.stdout.strip().split('\n'):
            parts = line.split()
            if len(parts) >= 2 and parts[0] in ['wlan0', 'wlan1', 'wlan2', 'eth0']:
                diag['interfaces'].append({
                    'name': parts[0],
                    'status': parts[1],
                    'ip': parts[2] if len(parts) > 2 else '-'
                })
    except Exception as e:
        diag['interfaces'].append({'name': 'Error', 'status': str(e), 'ip': ''})
    
    try:
        result = subprocess.run(['nmcli', '-t', '-f', 'NAME,TYPE,DEVICE', 'connection', 'show', '--active'],
                               capture_output=True, text=True, timeout=5)
        for line in result.stdout.strip().split('\n'):
            if line and ':' in line:
                parts = line.split(':')
                if len(parts) >= 3:
                    diag['connections'].append({
                        'name': parts[0],
                        'type': parts[1],
                        'device': parts[2]
                    })
    except:
        pass
    
    try:
        result = subprocess.run(['pgrep', '-f', 'multi_scraper.py'], capture_output=True, text=True, timeout=5)
        if result.stdout.strip():
            diag['scraper_status'] = 'Running (PID: ' + result.stdout.strip().split()[0] + ')'
        else:
            diag['scraper_status'] = 'Not Running'
    except:
        pass
    
    try:
        result = subprocess.run(['uptime', '-p'], capture_output=True, text=True, timeout=5)
        diag['uptime'] = result.stdout.strip()
    except:
        pass
    
    try:
        result = subprocess.run(['df', '-h', '/'], capture_output=True, text=True, timeout=5)
        lines = result.stdout.strip().split('\n')
        if len(lines) > 1:
            parts = lines[1].split()
            if len(parts) >= 4:
                diag['disk_free'] = parts[3] + ' free of ' + parts[1]
    except:
        pass
    
    return diag

def scan_wifi_channels():
    """Scan nearby networks and return channel usage info."""
    channels = {}
    try:
        result = subprocess.run(
            ['sudo', 'nmcli', '-t', '-f', 'SSID,CHAN,SIGNAL,SECURITY', 'device', 'wifi', 'list', '--rescan', 'yes'],
            capture_output=True, text=True, timeout=30
        )
        for line in result.stdout.strip().split('\n'):
            if line and ':' in line:
                parts = line.split(':')
                ssid = parts[0] or '(hidden)'
                chan = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
                signal = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
                if chan > 0:
                    if chan not in channels:
                        channels[chan] = []
                    channels[chan].append({'ssid': ssid, 'signal': signal})
    except Exception as e:
        print(f'Channel scan error: {e}')
    return channels

def get_hotspot_info():
    """Get the current AP hotspot connection name and channel."""
    info = {'connection': None, 'channel': None, 'ssid': None}
    try:
        # Find the AP connection (wlan1 USB adapter)
        result = subprocess.run(
            ['nmcli', '-t', '-f', 'NAME,TYPE,DEVICE', 'connection', 'show', '--active'],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.strip().split('\n'):
            if line and ':' in line:
                parts = line.split(':')
                if len(parts) >= 3 and parts[2] == 'wlan1':
                    info['connection'] = parts[0]
                    info['device'] = parts[2]
                    break

        if info['connection']:
            # Get the channel and SSID from the connection profile
            result = subprocess.run(
                ['nmcli', '-t', '-f', '802-11-wireless.channel,802-11-wireless.ssid',
                 'connection', 'show', info['connection']],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.strip().split('\n'):
                if 'channel' in line and ':' in line:
                    val = line.split(':')[-1].strip()
                    if val.isdigit():
                        info['channel'] = int(val)
                elif 'ssid' in line and ':' in line:
                    info['ssid'] = line.split(':')[-1].strip()

        # If channel is 0 or unset, get it from iw (actual operating channel)
        if not info['channel']:
            ap_dev = info.get('device', 'wlan1')
            result = subprocess.run(
                ['sudo', 'iw', 'dev', ap_dev, 'info'],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.strip().split('\n'):
                if 'channel' in line.lower():
                    parts = line.strip().split()
                    if len(parts) >= 2 and parts[1].isdigit():
                        info['channel'] = int(parts[1])
                    break
    except Exception as e:
        print(f'Hotspot info error: {e}')
    return info

def set_hotspot_channel(channel):
    """Change the AP hotspot to a new WiFi channel."""
    hotspot = get_hotspot_info()
    if not hotspot['connection']:
        return False, 'No hotspot connection found'

    try:
        conn = hotspot['connection']
        result = subprocess.run(
            ['sudo', 'nmcli', 'connection', 'modify', conn, 'wifi.band', 'bg', 'wifi.channel', str(channel)],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return False, f'Failed to set channel: {result.stderr}'

        # Restart the connection to apply
        subprocess.run(['sudo', 'nmcli', 'connection', 'down', conn],
                      capture_output=True, text=True, timeout=10)
        result = subprocess.run(['sudo', 'nmcli', 'connection', 'up', conn],
                               capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            return False, f'Channel set but failed to restart AP: {result.stderr}'

        return True, f'Hotspot moved to channel {channel}'
    except Exception as e:
        return False, str(e)

def recommend_channel(channel_usage):
    """Recommend the best non-overlapping channel (1, 6, or 11)."""
    best_channels = [1, 6, 11]
    scores = {}
    for ch in best_channels:
        # Count networks on this channel and overlapping channels
        count = 0
        total_signal = 0
        for scan_ch, networks in channel_usage.items():
            # Channels overlap if within 4 of each other (2.4GHz)
            if abs(scan_ch - ch) <= 4:
                count += len(networks)
                total_signal += sum(n['signal'] for n in networks)
        scores[ch] = (count, total_signal)
    # Pick the channel with fewest networks, then lowest total signal
    return min(best_channels, key=lambda c: scores[c])

def auto_select_channel():
    """Scan nearby networks and auto-select the least congested channel."""
    print('[AutoChannel] Scanning nearby networks...')
    channel_usage = scan_wifi_channels()
    hotspot = get_hotspot_info()

    if not hotspot['connection']:
        print('[AutoChannel] No hotspot found, skipping.')
        return

    recommended = recommend_channel(channel_usage)
    current = hotspot.get('channel')

    # Show what we found
    for ch in [1, 6, 11]:
        networks = channel_usage.get(ch, [])
        marker = ' <-- current' if ch == current else ''
        marker += ' <-- best' if ch == recommended else ''
        print(f'[AutoChannel] Channel {ch}: {len(networks)} networks{marker}')

    if recommended == current:
        print(f'[AutoChannel] Already on best channel {current}, no change needed.')
        return

    print(f'[AutoChannel] Switching from channel {current} to {recommended}...')
    success, message = set_hotspot_channel(recommended)
    if success:
        print(f'[AutoChannel] {message}')
    else:
        print(f'[AutoChannel] Failed: {message}')

def get_logs(log_type='scraper', lines=50):
    log_files = {
        'scraper': '/tmp/multi_scraper.log',
        'web': '/tmp/scraper_web.log',
        'system': '/var/log/syslog'
    }
    log_file = log_files.get(log_type, log_files['scraper'])
    
    try:
        result = subprocess.run(['sudo', 'tail', '-n', str(lines), log_file],
                               capture_output=True, text=True, timeout=10)
        return result.stdout.strip().split('\n')
    except Exception as e:
        return [f'Error reading log: {e}']

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
h3 { color:var(--gold); font-size:1rem; margin:15px 0 10px; }
.subtitle { color:var(--text2); margin-bottom:20px; font-size:0.9rem; }
.card { background:var(--bg2); border:1px solid var(--border); border-radius:8px; padding:20px; margin-bottom:20px; }
.form-group { margin-bottom:15px; }
.form-group label { display:block; color:var(--text2); margin-bottom:5px; font-size:0.9rem; }
.form-group select, .form-group input { width:100%; padding:12px; background:var(--bg); border:1px solid var(--border); border-radius:4px; color:var(--text); font-size:1rem; }
.form-group select:focus, .form-group input:focus { outline:none; border-color:var(--gold); }
.btn { width:100%; padding:14px; border:none; border-radius:4px; cursor:pointer; font-size:1.1rem; font-weight:600; }
.btn-primary { background:var(--gold); color:var(--bg); }
.btn-secondary { background:var(--blue); color:var(--bg); margin-top:10px; }
.btn-danger { background:var(--red); color:white; }
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
.tabs { display:flex; gap:4px; margin-bottom:20px; flex-wrap:wrap; }
.tab { flex:1; padding:10px 8px; background:var(--bg2); border:1px solid var(--border); border-radius:4px; text-align:center; cursor:pointer; color:var(--text2); font-size:0.85rem; min-width:70px; }
.tab.active { background:var(--gold); color:var(--bg); border-color:var(--gold); }
.tab-content { display:none; }
.tab-content.active { display:block; }
.uplink-current { padding:10px; background:var(--bg); border-radius:4px; margin-bottom:15px; }
.uplink-current .label { font-size:0.85rem; color:var(--text2); }
.uplink-current .value { color:var(--green); font-weight:600; }
.scanning { text-align:center; padding:20px; color:var(--text2); }
.log-output { background:var(--bg); border:1px solid var(--border); border-radius:4px; padding:10px; font-family:monospace; font-size:0.7rem; max-height:250px; overflow-y:auto; white-space:pre-wrap; word-break:break-all; color:var(--text2); }
.diag-grid { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
.diag-item { background:var(--bg); padding:10px; border-radius:4px; }
.diag-label { font-size:0.8rem; color:var(--text2); }
.diag-value { font-weight:600; margin-top:2px; }
.diag-ok { color:var(--green); }
.diag-warn { color:var(--gold); }
.diag-err { color:var(--red); }
.interface-item { display:flex; justify-content:space-between; padding:8px 10px; background:var(--bg); border-radius:4px; margin-bottom:5px; }
.interface-name { font-weight:600; }
.interface-status { font-size:0.85rem; }
.ch-bar-container { display:flex; align-items:flex-end; gap:4px; height:80px; padding:10px 0; }
.ch-bar-wrapper { display:flex; flex-direction:column; align-items:center; flex:1; }
.ch-bar { width:100%; min-height:4px; border-radius:3px 3px 0 0; transition:height 0.3s; }
.ch-bar-label { font-size:0.7rem; color:var(--text2); margin-top:4px; }
.ch-bar.clear { background:var(--green); }
.ch-bar.moderate { background:var(--gold); }
.ch-bar.busy { background:var(--red); }
.ch-bar.current { outline:2px solid var(--blue); outline-offset:2px; }
.ch-quick-btns { display:flex; gap:8px; margin-top:15px; }
.ch-quick-btns button { flex:1; padding:12px 8px; border:2px solid var(--border); border-radius:6px; background:var(--bg); color:var(--text); cursor:pointer; font-size:0.95rem; font-weight:600; transition:0.2s; }
.ch-quick-btns button:hover { border-color:var(--gold); }
.ch-quick-btns button.ch-current { border-color:var(--blue); background:rgba(84,184,219,0.15); }
.ch-quick-btns button.ch-recommended { border-color:var(--green); }
.ch-quick-btns button:disabled { opacity:0.5; cursor:not-allowed; }
.ch-legend { display:flex; gap:12px; margin-top:10px; flex-wrap:wrap; }
.ch-legend-item { display:flex; align-items:center; gap:4px; font-size:0.75rem; color:var(--text2); }
.ch-legend-dot { width:10px; height:10px; border-radius:2px; }
.ch-hotspot-info { display:flex; justify-content:space-between; align-items:center; padding:10px; background:var(--bg); border-radius:4px; margin-bottom:12px; }
.ch-hotspot-ssid { font-weight:600; }
.ch-hotspot-chan { font-size:1.1rem; font-weight:700; color:var(--blue); }
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
    <div class="tab active" onclick="showTab('destination')">📍 Dest</div>
    <div class="tab" onclick="showTab('wifi')">📶 WiFi</div>
    <div class="tab" onclick="showTab('channels')">🎯 SM</div>
    <div class="tab" onclick="showTab('diag')">🔧 Diag</div>
  </div>

  <!-- Destination Tab -->
  <div id="destination-tab" class="tab-content active">
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
          <label>Competition (optional)</label>
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

    <div class="card">
      <h2>⏰ Auto-Load Interval</h2>
      <form method="POST" action="/save-schedule">
        <div class="form-group">
          <label>Scrape & upload frequency</label>
          <select name="scrape_interval" style="font-size:1.1rem;">
            <option value="0" {% if config.scrape_interval == 0 %}selected{% endif %}>None (manual only)</option>
            <option value="15" {% if config.scrape_interval == 15 %}selected{% endif %}>15 sec (Competition)</option>
            <option value="90" {% if config.scrape_interval == 90 %}selected{% endif %}>90 sec</option>
            <option value="300" {% if config.scrape_interval == 300 %}selected{% endif %}>300 sec (5 min)</option>
          </select>
        </div>
        <button type="submit" class="btn btn-primary">💾 Save Interval</button>
      </form>
    </div>

    <div class="card">
      <button type="button" class="btn btn-primary" style="background:var(--green);" onclick="triggerLoad();" id="loadNowBtn">📡 Load Now</button>
      <p style="color:var(--text2); font-size:0.85rem; margin-top:8px; text-align:center;">Triggers a full scrape + upload on next cycle (~30s)</p>
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
        <form method="POST" action="/remove-uplink" style="margin-top:8px;">
          <button type="submit" class="btn btn-small btn-danger">🗑️ Remove</button>
        </form>
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

  <!-- Diagnostics Tab -->
  <div id="diag-tab" class="tab-content">
    <div class="card">
      <h2>🔧 System Status</h2>
      <div id="diagStatus">Click tab to load...</div>
    </div>
    
    <div class="card">
      <h2>📡 Hotspot Channel</h2>
      <p style="color:var(--text2); font-size:0.85rem; margin-bottom:12px;">
        Change the Pi's WiFi channel to avoid congestion from nearby networks.
      </p>
      <div id="channelStatus">
        <button type="button" class="btn btn-secondary" onclick="scanChannels()">🔍 Scan Channels</button>
      </div>
    </div>

    <div class="card">
      <h2>📋 Logs</h2>
      <div class="form-group">
        <select id="logType" onchange="loadLogs()" style="width:auto;display:inline-block;">
          <option value="scraper">Scraper Log</option>
          <option value="web">Web Config Log</option>
          <option value="system">System Log</option>
        </select>
        <button type="button" class="btn btn-small btn-secondary" onclick="loadLogs()">🔄</button>
      </div>
      <div id="logOutput" class="log-output">Select a log type...</div>
    </div>
    
    <div class="card">
      <h2>🛠️ Actions</h2>
      <button type="button" class="btn btn-secondary" onclick="restartScraper()">🔄 Restart Scraper</button>
      <button type="button" class="btn btn-secondary" onclick="testCloudConnection()">☁️ Test Cloud</button>
    </div>
  </div>

  <button class="btn btn-secondary" onclick="location.reload()">🔄 Refresh Page</button>
  <p class="refresh-note">Scraper uses new settings on next cycle (~30s)</p>
</div>

<script>
function showTab(tab) {
  document.querySelectorAll('.tab').forEach(function(t) { t.classList.remove('active'); });
  document.querySelectorAll('.tab-content').forEach(function(t) { t.classList.remove('active'); });
  event.target.classList.add('active');
  document.getElementById(tab + '-tab').classList.add('active');
  if (tab === 'diag') {
    loadDiagnostics();
    loadLogs();
    scanChannels();
  }
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
      if (opt.selected) compSelect.value = '';
    }
  }
}

function scanWifi() {
  var list = document.getElementById('wifiList');
  list.innerHTML = '<div class="scanning">Scanning...</div>';
  fetch('/api/scan-wifi')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.networks && data.networks.length > 0) {
        var html = '';
        data.networks.forEach(function(n) {
          var fillWidth = n.signal + '%';
          html += '<div class="wifi-item" onclick="selectWifi(\\'' + n.ssid.replace(/'/g, "\\\\'") + '\\')">' +
            '<span class="wifi-ssid">' + n.ssid + '</span>' +
            '<span class="wifi-signal">' + n.security + 
            '<span class="wifi-signal-bar"><span class="wifi-signal-fill" style="width:' + fillWidth + '"></span></span></span>' +
            '</div>';
        });
        list.innerHTML = html;
      } else {
        list.innerHTML = '<div class="scanning">No networks found</div>';
      }
    })
    .catch(function(err) {
      list.innerHTML = '<div class="scanning">Scan failed</div>';
    });
}

function selectWifi(ssid) {
  document.getElementById('uplinkSsid').value = ssid;
  document.getElementById('uplinkPassword').focus();
}

function testUplink() {
  var ssid = document.getElementById('uplinkSsid').value;
  var password = document.getElementById('uplinkPassword').value;
  if (!ssid) { alert('Please enter a network name'); return; }
  var btn = event.target;
  btn.disabled = true;
  btn.textContent = 'Testing...';
  fetch('/api/test-uplink', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ssid: ssid, password: password})
  })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      alert(data.success ? '✅ ' + data.message : '❌ ' + data.message);
      btn.disabled = false;
      btn.textContent = '🧪 Test Connection';
    })
    .catch(function(err) {
      alert('Error: ' + err);
      btn.disabled = false;
      btn.textContent = '🧪 Test Connection';
    });
}

function loadDiagnostics() {
  document.getElementById('diagStatus').innerHTML = 'Loading...';
  fetch('/api/diagnostics')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var html = '<div class="diag-grid">';
      html += '<div class="diag-item"><div class="diag-label">Scraper</div><div class="diag-value ' + 
              (data.scraper_status.includes('Running') ? 'diag-ok' : 'diag-err') + '">' + 
              data.scraper_status + '</div></div>';
      html += '<div class="diag-item"><div class="diag-label">Uptime</div><div class="diag-value">' + 
              data.uptime + '</div></div>';
      html += '<div class="diag-item"><div class="diag-label">Disk</div><div class="diag-value">' + 
              data.disk_free + '</div></div>';
      html += '</div>';
      
      html += '<h3>Network Interfaces</h3><div>';
      data.interfaces.forEach(function(i) {
        var statusClass = i.status === 'UP' ? 'diag-ok' : 'diag-warn';
        html += '<div class="interface-item"><span class="interface-name">' + i.name + '</span>' +
                '<span class="interface-status"><span class="' + statusClass + '">' + i.status + '</span> ' + i.ip + '</span></div>';
      });
      html += '</div>';
      
      if (data.connections.length > 0) {
        html += '<h3>Active Connections</h3><div>';
        data.connections.forEach(function(c) {
          html += '<div class="interface-item"><span class="interface-name">' + c.name + '</span>' +
                  '<span class="interface-status">' + c.device + '</span></div>';
        });
        html += '</div>';
      }
      document.getElementById('diagStatus').innerHTML = html;
    })
    .catch(function(err) {
      document.getElementById('diagStatus').innerHTML = '<div class="diag-err">Error loading</div>';
    });
}

function loadLogs() {
  var logType = document.getElementById('logType').value;
  var output = document.getElementById('logOutput');
  output.textContent = 'Loading...';
  fetch('/api/logs?type=' + logType)
    .then(function(r) { return r.json(); })
    .then(function(data) {
      output.textContent = data.logs.join('\\n') || 'No logs found';
      output.scrollTop = output.scrollHeight;
    })
    .catch(function(err) {
      output.textContent = 'Error: ' + err;
    });
}

function restartScraper() {
  if (!confirm('Restart the scraper service?')) return;
  fetch('/api/restart-scraper', {method:'POST'})
    .then(function(r) { return r.json(); })
    .then(function(data) {
      alert(data.message);
      setTimeout(loadDiagnostics, 2000);
    });
}

function testCloudConnection() {
  var btn = event.target;
  btn.disabled = true;
  btn.textContent = 'Testing...';
  fetch('/api/test-cloud')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      alert(data.success ? '✅ ' + data.message : '❌ ' + data.message);
      btn.disabled = false;
      btn.textContent = '☁️ Test Cloud';
    });
}

function scanChannels() {
  var container = document.getElementById('channelStatus');
  container.innerHTML = '<div class="scanning">Scanning nearby networks...</div>';
  fetch('/api/scan-channels')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var html = '';

      // Current hotspot info
      if (data.hotspot && data.hotspot.connection) {
        html += '<div class="ch-hotspot-info">' +
                '<div><span class="ch-hotspot-ssid">' + (data.hotspot.ssid || data.hotspot.connection) + '</span>' +
                '<span style="color:var(--text2); font-size:0.85rem;"> on ' + (data.hotspot.device || 'wlan1') + '</span></div>' +
                '<div>Channel <span class="ch-hotspot-chan">' + (data.hotspot.channel || '?') + '</span></div></div>';
      } else {
        html += '<div class="ch-hotspot-info"><span style="color:var(--red);">No hotspot found</span></div>';
      }

      // Channel usage bars
      var maxNetworks = 1;
      data.channels.forEach(function(ch) { if (ch.networks > maxNetworks) maxNetworks = ch.networks; });

      html += '<div class="ch-bar-container">';
      data.channels.forEach(function(ch) {
        var height = ch.networks > 0 ? Math.max(15, (ch.networks / maxNetworks) * 70) : 4;
        var cls = 'clear';
        if (ch.networks >= 3) cls = 'busy';
        else if (ch.networks >= 1) cls = 'moderate';
        if (ch.is_current) cls += ' current';
        var title = 'Ch ' + ch.channel + ': ' + ch.networks + ' network' + (ch.networks !== 1 ? 's' : '');
        if (ch.ssids.length > 0) title += '\\n' + ch.ssids.join(', ');
        html += '<div class="ch-bar-wrapper">' +
                '<div class="ch-bar ' + cls + '" style="height:' + height + 'px;" title="' + title + '"></div>' +
                '<div class="ch-bar-label">' + ch.channel + '</div></div>';
      });
      html += '</div>';

      // Legend
      html += '<div class="ch-legend">' +
              '<div class="ch-legend-item"><div class="ch-legend-dot" style="background:var(--green);"></div> Clear</div>' +
              '<div class="ch-legend-item"><div class="ch-legend-dot" style="background:var(--gold);"></div> 1-2 networks</div>' +
              '<div class="ch-legend-item"><div class="ch-legend-dot" style="background:var(--red);"></div> 3+ networks</div>' +
              '<div class="ch-legend-item"><div class="ch-legend-dot" style="outline:2px solid var(--blue);outline-offset:1px;"></div> Current</div>' +
              '</div>';

      // Quick-set buttons for non-overlapping channels
      html += '<h3>Set Channel</h3>';
      html += '<div class="ch-quick-btns">';
      [1, 6, 11].forEach(function(ch) {
        var chData = data.channels[ch - 1];
        var label = 'Ch ' + ch;
        var extra = '';
        if (chData.is_current) extra = ' ch-current';
        if (ch === data.recommended) {
          label += ' ★';
          extra += ' ch-recommended';
        }
        label += ' (' + chData.networks + ')';
        var disabled = chData.is_current ? ' disabled' : '';
        html += '<button class="' + extra.trim() + '"' + disabled + ' onclick="setChannel(' + ch + ')">' + label + '</button>';
      });
      html += '</div>';

      // Rescan button
      html += '<button type="button" class="btn btn-secondary" style="margin-top:12px;" onclick="scanChannels()">🔍 Rescan</button>';

      container.innerHTML = html;
    })
    .catch(function(err) {
      container.innerHTML = '<div class="scanning" style="color:var(--red);">Scan failed: ' + err + '</div>' +
                            '<button type="button" class="btn btn-secondary" onclick="scanChannels()">🔍 Retry</button>';
    });
}

function setChannel(channel) {
  if (!confirm('Move hotspot to channel ' + channel + '?\\n\\nThis will briefly disconnect WiFi clients.')) return;
  var container = document.getElementById('channelStatus');
  var btns = container.querySelectorAll('.ch-quick-btns button');
  btns.forEach(function(b) { b.disabled = true; });

  fetch('/api/set-channel', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({channel: channel})
  })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.success) {
        alert('✅ ' + data.message);
        scanChannels();
      } else {
        alert('❌ ' + data.message);
        btns.forEach(function(b) { b.disabled = false; });
      }
    })
    .catch(function(err) {
      alert('Error: ' + err);
      btns.forEach(function(b) { b.disabled = false; });
    });
}

filterCompetitions();

function triggerLoad() {
  var btn = document.getElementById('loadNowBtn');
  btn.disabled = true;
  btn.textContent = 'Triggering...';
  fetch('/api/trigger-load', {method: 'POST'})
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.success) {
        btn.textContent = '✅ Triggered!';
        btn.style.background = 'var(--green)';
        setTimeout(function() {
          btn.disabled = false;
          btn.textContent = '📡 Load Now';
        }, 5000);
      } else {
        alert('Error: ' + data.message);
        btn.disabled = false;
        btn.textContent = '📡 Load Now';
      }
    })
    .catch(function(err) {
      alert('Error: ' + err);
      btn.disabled = false;
      btn.textContent = '📡 Load Now';
    });
}
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
        config=config, destinations=destinations,
        message=message, message_type=message_type)

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

@app.route('/save-schedule', methods=['POST'])
def save_schedule():
    config = load_config()
    config['scrape_interval'] = int(request.form.get('scrape_interval', 0))
    save_config(config)
    if config['scrape_interval'] == 0:
        msg = 'Auto-load disabled (manual only)'
    else:
        msg = f"Auto-load interval: {config['scrape_interval']}s"
    return redirect(f'/?msg={msg}&type=success')

@app.route('/api/trigger-load', methods=['POST'])
def api_trigger_load():
    try:
        with open('/tmp/scraper_trigger', 'w') as f:
            f.write('trigger')
        return jsonify({'success': True, 'message': 'Load triggered! Will run on next cycle (~30s)'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/remove-uplink', methods=['POST'])
def remove_uplink():
    config = load_config()
    config['uplink_ssid'] = ''
    config['uplink_password'] = ''
    save_config(config)
    try:
        subprocess.run(['sudo', 'nmcli', 'connection', 'delete', 'Uplink-Network'], 
                      capture_output=True, timeout=10)
    except:
        pass
    return redirect('/?msg=Uplink removed&type=success')

@app.route('/api/scan-wifi')
def api_scan_wifi():
    return jsonify({'networks': scan_wifi()})

@app.route('/api/test-uplink', methods=['POST'])
def api_test_uplink():
    data = request.get_json()
    ssid = data.get('ssid', '')
    password = data.get('password', '')
    if not ssid:
        return jsonify({'success': False, 'message': 'SSID required'})
    success, message = test_uplink_connection(ssid, password)
    return jsonify({'success': success, 'message': message})

@app.route('/api/diagnostics')
def api_diagnostics():
    return jsonify(get_diagnostics())

@app.route('/api/logs')
def api_logs():
    log_type = request.args.get('type', 'scraper')
    lines = int(request.args.get('lines', 50))
    return jsonify({'logs': get_logs(log_type, lines)})

@app.route('/api/restart-scraper', methods=['POST'])
def api_restart_scraper():
    try:
        subprocess.run(['sudo', 'pkill', '-f', 'multi_scraper.py'], timeout=5)
        subprocess.Popen(['sudo', '/opt/scraper/venv/bin/python', '/opt/scraper/multi_scraper.py'],
                        stdout=open('/tmp/multi_scraper.log', 'a'),
                        stderr=subprocess.STDOUT)
        return jsonify({'success': True, 'message': 'Scraper restarted'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/test-cloud')
def api_test_cloud():
    try:
        config = load_config()
        resp = requests.get(config['cloud_url'] + '/api/destinations', timeout=10)
        if resp.status_code == 200:
            return jsonify({'success': True, 'message': 'Cloud connected! Found ' + str(len(resp.json().get('ranges', []))) + ' ranges'})
        else:
            return jsonify({'success': False, 'message': 'Cloud returned status ' + str(resp.status_code)})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/scan-channels')
def api_scan_channels():
    channel_usage = scan_wifi_channels()
    hotspot = get_hotspot_info()
    recommended = recommend_channel(channel_usage)
    # Build a summary for channels 1-11
    summary = []
    for ch in range(1, 12):
        networks = channel_usage.get(ch, [])
        summary.append({
            'channel': ch,
            'networks': len(networks),
            'ssids': [n['ssid'] for n in networks],
            'is_current': ch == hotspot.get('channel'),
            'is_recommended': ch == recommended,
            'non_overlapping': ch in [1, 6, 11]
        })
    return jsonify({
        'channels': summary,
        'hotspot': hotspot,
        'recommended': recommended
    })

@app.route('/api/set-channel', methods=['POST'])
def api_set_channel():
    data = request.get_json()
    channel = data.get('channel')
    if not channel or not isinstance(channel, int) or channel not in range(1, 12):
        return jsonify({'success': False, 'message': 'Invalid channel (must be 1-11)'})
    success, message = set_hotspot_channel(channel)
    return jsonify({'success': success, 'message': message})

@app.route('/config')
def get_config_api():
    return jsonify(load_config())

if __name__ == '__main__':
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
    try:
        auto_select_channel()
    except Exception as e:
        print(f'[AutoChannel] Error during auto-select: {e}')
    app.run(host='0.0.0.0', port=8080, debug=False)
