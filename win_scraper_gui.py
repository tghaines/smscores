#!/usr/bin/env python3
"""
Windows ShotMarker Scraper — GUI Version
tkinter GUI for scraping ShotMarker WiFi scores and pushing to cloud.
Supports multiple ShotMarker channels, password-protected upload WiFi,
and one-click squadding import via browser bookmarklet.
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import threading
import subprocess
import tempfile
import requests
import time
import json
import hashlib
import re
import os
import sys
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False

# Config file — same directory as the script/exe
if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(APP_DIR, 'scraper_config.json')

VERSION = '1.0.0'

SM_CHANNELS = ['ShotMarker', 'ShotMarker2', 'ShotMarker3', 'ShotMarker4']

def play_success_sound():
    """Happy little jingle — scrape pushed OK"""
    if not HAS_WINSOUND:
        return
    try:
        for freq, ms in [(523, 100), (659, 100), (784, 100), (1047, 200)]:
            winsound.Beep(freq, ms)
    except:
        pass

def play_fail_sound():
    """Sad trombone — womp womp womp wommmmp"""
    if not HAS_WINSOUND:
        return
    try:
        for freq, ms in [(392, 350), (370, 350), (349, 350), (262, 600)]:
            winsound.Beep(freq, ms)
    except:
        pass
LISTEN_PORT = 8765
BACKUP_DIR = os.path.join(APP_DIR, 'backups')
QUEUE_FILE = os.path.join(APP_DIR, 'push_queue.json')

DEFAULT_CONFIG = {
    'cloud_url': 'http://134.199.153.50',
    'api_key': '',
    'sm_enabled': ['ShotMarker'],
    'shotmarker_ip': '192.168.100.1',
    'upload_ssid': '',
    'upload_password': '',
    'wifi_interface': 'Wi-Fi',
    'competition': '',
    'mode': 'club',
    'auto_interval': 120,
    'github_repo': 'tghaines/smscores',
    'github_branch': 'master',
    'github_file': 'win_scraper_gui.py',
}


# ══════════════════════════════════════════════
#  VERSION CHECK (GitHub)
# ══════════════════════════════════════════════

def _parse_version(text):
    """Extract VERSION = '...' from script content"""
    m = re.search(r"^VERSION\s*=\s*['\"]([^'\"]+)['\"]", text, re.MULTILINE)
    return m.group(1) if m else None


def _version_tuple(v):
    """Convert '1.2.3' to (1, 2, 3) for comparison"""
    try:
        return tuple(int(x) for x in v.split('.'))
    except:
        return (0,)


def check_for_update(repo, branch, filepath):
    """Check GitHub for a newer version. Returns (has_update, remote_ver, content) or (False, None, None)."""
    try:
        url = f'https://raw.githubusercontent.com/{repo}/{branch}/{filepath}'
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return False, None, None
        content = resp.text
        remote_ver = _parse_version(content)
        if not remote_ver:
            return False, None, None
        if _version_tuple(remote_ver) > _version_tuple(VERSION):
            return True, remote_ver, content
        return False, remote_ver, None
    except:
        return False, None, None


# ══════════════════════════════════════════════
#  WIFI MANAGEMENT (Windows netsh)
# ══════════════════════════════════════════════

def get_current_ssid(interface=None):
    """Get currently connected WiFi SSID via netsh"""
    try:
        cmd = ['netsh', 'wlan', 'show', 'interfaces']
        if interface:
            cmd.extend([f'interface={interface}'])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith('SSID') and not line.startswith('AP BSSID'):
                return line.split(':', 1)[1].strip()
    except:
        pass
    return None


def get_wifi_interfaces():
    """List available WiFi interface names from netsh"""
    interfaces = []
    try:
        result = subprocess.run(
            ['netsh', 'wlan', 'show', 'interfaces'],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.lower().startswith('name') and ':' in line:
                name = line.split(':', 1)[1].strip()
                if name:
                    interfaces.append(name)
    except:
        pass
    return interfaces or ['Wi-Fi']


def scan_wifi_networks(interface='Wi-Fi'):
    """Scan for available WiFi networks via netsh"""
    networks = []
    try:
        result = subprocess.run(
            ['netsh', 'wlan', 'show', 'networks', f'interface={interface}'],
            capture_output=True, text=True, timeout=15
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            # Lines like "SSID 1 : trinity" or "SSID 2 : ShotMarker"
            if line.startswith('SSID') and ':' in line:
                parts = line.split(':', 1)
                if len(parts) == 2:
                    ssid = parts[1].strip()
                    if ssid and ssid not in networks:
                        networks.append(ssid)
    except:
        pass
    return networks


def ensure_wifi_profile(ssid, password=None, interface='Wi-Fi'):
    """Create a Windows WiFi profile so netsh can connect."""
    if password:
        profile_xml = f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>{ssid}</name>
    <SSIDConfig><SSID><name>{ssid}</name></SSID></SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>manual</connectionMode>
    <MSM><security>
        <authEncryption>
            <authentication>WPA2PSK</authentication>
            <encryption>AES</encryption>
            <useOneX>false</useOneX>
        </authEncryption>
        <sharedKey>
            <keyType>passPhrase</keyType>
            <protected>false</protected>
            <keyMaterial>{password}</keyMaterial>
        </sharedKey>
    </security></MSM>
</WLANProfile>"""
    else:
        profile_xml = f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>{ssid}</name>
    <SSIDConfig><SSID><name>{ssid}</name></SSID></SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>manual</connectionMode>
    <MSM><security>
        <authEncryption>
            <authentication>open</authentication>
            <encryption>none</encryption>
            <useOneX>false</useOneX>
        </authEncryption>
    </security></MSM>
</WLANProfile>"""

    profile_path = os.path.join(tempfile.gettempdir(), f'scraper_wifi_{ssid}.xml')
    try:
        with open(profile_path, 'w') as f:
            f.write(profile_xml)
        result = subprocess.run(
            ['netsh', 'wlan', 'add', 'profile', f'filename={profile_path}',
             f'interface={interface}', 'user=current'],
            capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0
    except:
        return False
    finally:
        try:
            os.remove(profile_path)
        except:
            pass


def wifi_connect(ssid, interface, log_fn, password=None):
    """Connect to a WiFi network. Creates profile if needed."""
    current = get_current_ssid()
    if current == ssid:
        log_fn(f'Already connected to {ssid}')
        return True

    log_fn(f'Connecting to {ssid}...')
    try:
        result = subprocess.run(
            ['netsh', 'wlan', 'connect', f'name={ssid}', f'interface={interface}'],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            output = result.stderr.strip() or result.stdout.strip()
            if '1168' in output or 'not found' in output.lower() or 'Element' in output:
                log_fn(f'Creating WiFi profile for {ssid}...')
                if ensure_wifi_profile(ssid, password, interface):
                    result = subprocess.run(
                        ['netsh', 'wlan', 'connect', f'name={ssid}', f'interface={interface}'],
                        capture_output=True, text=True, timeout=15
                    )
                else:
                    log_fn(f'[ERROR] Could not create WiFi profile for {ssid}')
                    return False

        if result.returncode != 0:
            log_fn(f'[ERROR] netsh: {result.stderr.strip() or result.stdout.strip()}')
            return False

        for i in range(15):
            time.sleep(1)
            if get_current_ssid() == ssid:
                log_fn(f'Connected to {ssid}')
                return True
            if i % 3 == 2:
                log_fn(f'Waiting... ({i + 1}s)')

        log_fn(f'[ERROR] Timed out connecting to {ssid}')
        return False
    except Exception as e:
        log_fn(f'[ERROR] {e}')
        return False


# ══════════════════════════════════════════════
#  LOCAL HTTP SERVER (receives squadding from bookmarklet)
# ══════════════════════════════════════════════

class SquaddingHandler(BaseHTTPRequestHandler):
    app = None

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            data = json.loads(body)
            competitors = data.get('competitors', [])

            if self.app:
                self.app.received_squadding = competitors
                matches = {}
                for c in competitors:
                    m = c.get('match', '(no match)')
                    matches[m] = matches.get(m, 0) + 1
                summary = ', '.join(f'{m}: {n}' for m, n in matches.items())
                self.app.log(f'SQUADDING RECEIVED: {len(competitors)} competitors ({summary})')
                self.app.root.after(0, self.app._update_squadding_btn)

            self.send_response(200)
            self._cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'ok': True, 'count': len(competitors)}).encode())
        except Exception as e:
            self.send_response(400)
            self._cors_headers()
            self.end_headers()
            self.wfile.write(str(e).encode())

    def _cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def log_message(self, format, *args):
        pass  # Suppress default HTTP logging


# ══════════════════════════════════════════════
#  SCRAPER APP
# ══════════════════════════════════════════════

class ScraperApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f'ShotMarker Scraper v{VERSION}')
        self.root.geometry('620x700')
        self.root.minsize(550, 550)

        self.running = False
        self.busy = False
        self.auto_timer = None
        self.last_hash = None
        self.competitions = []
        self.advanced_visible = False
        self.received_squadding = None
        self.push_queue = []
        self.next_scrape_at = None
        self.countdown_timer = None
        self._pending_update = None

        self.config = dict(DEFAULT_CONFIG)
        self.load_config()
        self._load_queue()
        self.build_gui()
        self.apply_config_to_gui()

        self._start_local_server()
        self._update_queue_indicator()
        if self.push_queue:
            self.root.after(600, lambda: self.log(
                f'{len(self.push_queue)} queued push(es) from previous session'))
        self.root.after(500, self._show_current_wifi)
        self.root.after(5000, self._auto_check_update)

    # ── Local server for bookmarklet ──

    def _start_local_server(self):
        SquaddingHandler.app = self
        try:
            self.local_server = HTTPServer(('127.0.0.1', LISTEN_PORT), SquaddingHandler)
            thread = threading.Thread(target=self.local_server.serve_forever, daemon=True)
            thread.start()
            self.log(f'Squadding listener ready on localhost:{LISTEN_PORT}')
        except OSError:
            self.log(f'[WARN] Could not start listener on port {LISTEN_PORT}')

    def _update_squadding_btn(self):
        if self.received_squadding:
            self.squad_btn.configure(
                text=f'Push Squadding ({len(self.received_squadding)})')

    # ── Config persistence ──

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    saved = json.load(f)
                if 'shotmarker_ssid' in saved and 'sm_enabled' not in saved:
                    saved['sm_enabled'] = [saved.pop('shotmarker_ssid')]
                if 'sm_channels' in saved and 'sm_enabled' not in saved:
                    saved['sm_enabled'] = saved.pop('sm_channels')
                if 'home_ssid' in saved and 'upload_ssid' not in saved:
                    saved['upload_ssid'] = saved.pop('home_ssid')
                self.config.update(saved)
            except:
                pass

    def save_config(self):
        self.read_gui_to_config()
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.config, f, indent=2)
            self.log('Config saved')
        except Exception as e:
            self.log(f'[ERROR] Save config: {e}')

    def read_gui_to_config(self):
        self.config['upload_ssid'] = self.upload_ssid_var.get().strip()
        self.config['upload_password'] = self.upload_pass_var.get()
        self.config['sm_enabled'] = [ch for ch in SM_CHANNELS if self.sm_vars[ch].get()]
        self.config['mode'] = self.mode_var.get()
        self.config['competition'] = self.comp_var.get().strip()
        self.config['cloud_url'] = self.cloud_url_var.get().strip().rstrip('/')
        self.config['api_key'] = self.api_key_var.get().strip()
        self.config['wifi_interface'] = self.iface_var.get().strip()
        self.config['shotmarker_ip'] = self.sm_ip_var.get().strip()
        try:
            self.config['auto_interval'] = int(self.interval_var.get())
        except ValueError:
            self.config['auto_interval'] = 120

    # ── Backup & Queue ──

    def _load_queue(self):
        if os.path.exists(QUEUE_FILE):
            try:
                with open(QUEUE_FILE, 'r') as f:
                    self.push_queue = json.load(f)
            except:
                self.push_queue = []

    def _save_queue(self):
        try:
            with open(QUEUE_FILE, 'w') as f:
                json.dump(self.push_queue, f, indent=2)
        except Exception as e:
            self.log(f'[ERROR] Save queue: {e}')

    def _save_backup(self, scores, shotlog, competition):
        try:
            os.makedirs(BACKUP_DIR, exist_ok=True)
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            path = os.path.join(BACKUP_DIR, f'{ts}.json')
            data = {
                'timestamp': datetime.now().isoformat(),
                'competition': competition,
                'scores': scores,
                'shotlog': shotlog,
            }
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
            self.log(f'Backup saved: {os.path.basename(path)}')
        except Exception as e:
            self.log(f'[ERROR] Backup: {e}')

    def _queue_push(self, push_type, data, competition=''):
        item = {
            'type': push_type,
            'competition': competition,
            'data': data,
            'timestamp': datetime.now().isoformat(),
        }
        self.push_queue.append(item)
        self._save_queue()
        self.log(f'Queued {push_type} for retry (queue: {len(self.push_queue)})')
        self._update_queue_indicator()

    def _drain_queue(self, headers, cloud_url):
        if not self.push_queue:
            return
        self.log(f'Retrying {len(self.push_queue)} queued push(es)...')
        remaining = []
        for item in self.push_queue:
            ok = False
            try:
                if item['type'] == 'scores':
                    resp = requests.post(
                        f'{cloud_url}/api/push/scores', headers=headers,
                        json={'competition': item['competition'], 'scores': item['data']},
                        timeout=30
                    )
                    ok = resp.status_code in (200, 201)
                elif item['type'] == 'shotlog':
                    resp = requests.post(
                        f'{cloud_url}/api/push/shotlog', headers=headers,
                        json={'csv': item['data']},
                        timeout=30
                    )
                    ok = resp.status_code in (200, 201)
            except:
                pass
            if ok:
                self.log(f'Queue: {item["type"]} from {item["timestamp"][:16]} pushed OK')
            else:
                remaining.append(item)
        self.push_queue = remaining
        self._save_queue()
        if remaining:
            self.log(f'{len(remaining)} item(s) still queued')
        else:
            self.log('Queue drained — all caught up')
        self._update_queue_indicator()

    def apply_config_to_gui(self):
        self.upload_ssid_var.set(self.config.get('upload_ssid', ''))
        self.upload_pass_var.set(self.config.get('upload_password', ''))
        enabled = self.config.get('sm_enabled', ['ShotMarker'])
        for ch in SM_CHANNELS:
            self.sm_vars[ch].set(ch in enabled)
        self.mode_var.set(self.config.get('mode', 'club'))
        self.comp_var.set(self.config.get('competition', ''))
        self.interval_var.set(str(self.config.get('auto_interval', 120)))
        self.cloud_url_var.set(self.config.get('cloud_url', ''))
        self.api_key_var.set(self.config.get('api_key', ''))
        self.iface_var.set(self.config.get('wifi_interface', 'Wi-Fi'))
        self.sm_ip_var.set(self.config.get('shotmarker_ip', '192.168.100.1'))

    # ── Build GUI ──

    def build_gui(self):
        # --- ShotMarker Channels (checkboxes) ---
        sm_frame = ttk.LabelFrame(self.root, text='ShotMarker Channels', padding=8)
        sm_frame.pack(fill='x', padx=10, pady=(10, 5))

        self.sm_vars = {}
        cb_row = ttk.Frame(sm_frame)
        cb_row.pack(fill='x')
        for i, ch in enumerate(SM_CHANNELS):
            var = tk.BooleanVar(value=(ch == 'ShotMarker'))
            self.sm_vars[ch] = var
            ttk.Checkbutton(cb_row, text=ch, variable=var).grid(
                row=i // 2, column=i % 2, sticky='w', padx=(0, 20), pady=1)

        # --- Upload WiFi ---
        upload = ttk.LabelFrame(self.root, text='Upload WiFi (internet)', padding=8)
        upload.pack(fill='x', padx=10, pady=5)

        ttk.Label(upload, text='Adapter:').grid(row=0, column=0, sticky='e', padx=(0, 5), pady=2)
        self.iface_var = tk.StringVar()
        iface_row = ttk.Frame(upload)
        iface_row.grid(row=0, column=1, sticky='ew', pady=2)
        self.iface_combo = ttk.Combobox(iface_row, textvariable=self.iface_var, width=30)
        self.iface_combo.pack(side='left', fill='x', expand=True)
        ttk.Button(iface_row, text='\u21bb', width=3,
                    command=self._refresh_interfaces).pack(side='left', padx=(5, 0))

        ttk.Label(upload, text='SSID:').grid(row=1, column=0, sticky='e', padx=(0, 5), pady=2)
        self.upload_ssid_var = tk.StringVar()
        ssid_row = ttk.Frame(upload)
        ssid_row.grid(row=1, column=1, sticky='ew', pady=2)
        self.ssid_combo = ttk.Combobox(ssid_row, textvariable=self.upload_ssid_var, width=30)
        self.ssid_combo.pack(side='left', fill='x', expand=True)
        ttk.Button(ssid_row, text='Scan', width=5,
                    command=self._scan_networks).pack(side='left', padx=(5, 0))

        ttk.Label(upload, text='Password:').grid(row=2, column=0, sticky='e', padx=(0, 5), pady=2)
        self.upload_pass_var = tk.StringVar()
        ttk.Entry(upload, textvariable=self.upload_pass_var, width=35, show='*').grid(
            row=2, column=1, sticky='ew', pady=2)

        ttk.Label(upload, text='Leave password blank if already saved in Windows',
                   font=('', 8)).grid(row=3, column=0, columnspan=2, sticky='w')
        upload.columnconfigure(1, weight=1)

        # --- Competition settings ---
        comp = ttk.LabelFrame(self.root, text='Competition', padding=8)
        comp.pack(fill='x', padx=10, pady=5)

        mode_row = ttk.Frame(comp)
        mode_row.grid(row=0, column=0, columnspan=3, sticky='w', pady=(0, 5))
        self.mode_var = tk.StringVar(value='club')
        ttk.Radiobutton(mode_row, text='Competition', variable=self.mode_var,
                         value='competition').pack(side='left')
        ttk.Radiobutton(mode_row, text='Club day only', variable=self.mode_var,
                         value='club').pack(side='left', padx=(15, 0))

        ttk.Label(comp, text='Competition:').grid(row=1, column=0, sticky='e', padx=(0, 5))
        self.comp_var = tk.StringVar()
        self.comp_combo = ttk.Combobox(comp, textvariable=self.comp_var, width=30)
        self.comp_combo.grid(row=1, column=1, sticky='ew')
        ttk.Button(comp, text='Fetch', command=self.fetch_destinations,
                    width=8).grid(row=1, column=2, padx=(5, 0))
        comp.columnconfigure(1, weight=1)

        auto_row = ttk.Frame(comp)
        auto_row.grid(row=2, column=0, columnspan=3, sticky='w', pady=(5, 0))
        ttk.Label(auto_row, text='Auto interval (sec):').pack(side='left')
        self.interval_var = tk.StringVar(value='120')
        ttk.Entry(auto_row, textvariable=self.interval_var, width=6).pack(side='left', padx=5)

        # --- Action buttons (two rows) ---
        btn_frame1 = ttk.Frame(self.root)
        btn_frame1.pack(fill='x', padx=10, pady=(10, 2))

        self.scrape_btn = ttk.Button(btn_frame1, text='Scrape Now', command=self.scrape_once)
        self.scrape_btn.pack(side='left', padx=(0, 5))

        self.auto_btn = ttk.Button(btn_frame1, text='Start Auto', command=self.toggle_auto)
        self.auto_btn.pack(side='left', padx=5)

        self.squad_btn = ttk.Button(btn_frame1, text='Push Squadding', command=self.push_squadding)
        self.squad_btn.pack(side='left', padx=5)

        ttk.Button(btn_frame1, text='Save', command=self.save_config).pack(side='right')
        ttk.Button(btn_frame1, text='Save Log', command=self._export_log).pack(side='right', padx=(0, 5))

        btn_frame2 = ttk.Frame(self.root)
        btn_frame2.pack(fill='x', padx=10, pady=(2, 5))

        self.test_sm_btn = ttk.Button(btn_frame2, text='Test SM', command=self.test_sm)
        self.test_sm_btn.pack(side='left', padx=(0, 5))

        self.test_upload_btn = ttk.Button(btn_frame2, text='Test Upload', command=self.test_upload)
        self.test_upload_btn.pack(side='left', padx=5)

        self.update_btn = ttk.Button(btn_frame2, text='Update', command=self._check_update_clicked)
        self.update_btn.pack(side='right')

        # --- Advanced settings (hidden by default) ---
        self.adv_toggle = ttk.Button(self.root, text='\u25b8 Advanced Settings',
                                      command=self._toggle_advanced)
        self.adv_toggle.pack(anchor='w', padx=10)

        self.adv_frame = ttk.LabelFrame(self.root, text='Advanced', padding=8)

        self.cloud_url_var = tk.StringVar()
        self.api_key_var = tk.StringVar()
        self.sm_ip_var = tk.StringVar()

        for i, (label, var) in enumerate([
            ('Cloud URL:', self.cloud_url_var),
            ('API Key:', self.api_key_var),
            ('ShotMarker IP:', self.sm_ip_var),
        ]):
            ttk.Label(self.adv_frame, text=label).grid(row=i, column=0, sticky='e', padx=(0, 5), pady=2)
            entry = ttk.Entry(self.adv_frame, textvariable=var, width=45)
            if var is self.api_key_var:
                entry.configure(show='*')
            entry.grid(row=i, column=1, sticky='ew', pady=2)
        self.adv_frame.columnconfigure(1, weight=1)

        # --- Status indicators ---
        ind_frame = ttk.Frame(self.root)
        ind_frame.pack(fill='x', padx=10, pady=(5, 0))

        self.ind_labels = {}
        for name, text in [('sm', 'SM: --'), ('upload', 'Upload: --'), ('cloud', 'Cloud: --')]:
            lbl = tk.Label(ind_frame, text=f'\u25cf {text}', fg='grey', font=('Consolas', 9),
                           padx=6, pady=2)
            lbl.pack(side='left', padx=(0, 10))
            self.ind_labels[name] = lbl

        self.queue_label = tk.Label(ind_frame, text='Queue: 0', fg='grey',
                                     font=('Consolas', 9), padx=6, pady=2)
        self.queue_label.pack(side='left', padx=(0, 10))

        self.countdown_label = tk.Label(ind_frame, text='', fg='#555555',
                                         font=('Consolas', 9), padx=6, pady=2)
        self.countdown_label.pack(side='right')

        # --- Log output ---
        log_frame = ttk.LabelFrame(self.root, text='Log', padding=4)
        log_frame.pack(fill='both', expand=True, padx=10, pady=(5, 5))

        self.log_text = scrolledtext.ScrolledText(
            log_frame, height=12, state='disabled',
            font=('Consolas', 9), wrap='word'
        )
        self.log_text.pack(fill='both', expand=True)

        # --- Status bar ---
        self.status_var = tk.StringVar(value='Ready')
        ttk.Label(self.root, textvariable=self.status_var, relief='sunken',
                   anchor='w', padding=4).pack(fill='x', padx=10, pady=(0, 10))

        self.root.protocol('WM_DELETE_WINDOW', self.on_close)

    def _toggle_advanced(self):
        if self.advanced_visible:
            self.adv_frame.pack_forget()
            self.adv_toggle.configure(text='\u25b8 Advanced Settings')
            self.advanced_visible = False
        else:
            self.adv_frame.pack(fill='x', padx=10, pady=(0, 5), after=self.adv_toggle)
            self.adv_toggle.configure(text='\u25be Advanced Settings')
            self.advanced_visible = True

    def _refresh_interfaces(self):
        def _scan():
            ifaces = get_wifi_interfaces()
            current = self.iface_var.get()
            self.root.after(0, lambda: self.iface_combo.configure(values=ifaces))
            if current not in ifaces and ifaces:
                self.root.after(0, lambda: self.iface_var.set(ifaces[0]))
            self.log(f'WiFi adapters: {", ".join(ifaces)}')
        threading.Thread(target=_scan, daemon=True).start()

    def _scan_networks(self):
        def _scan():
            iface = self.iface_var.get() or 'Wi-Fi'
            self.log(f'Scanning networks on {iface}...')
            networks = scan_wifi_networks(iface)
            if networks:
                self.root.after(0, lambda: self.ssid_combo.configure(values=networks))
                self.log(f'Found {len(networks)} network(s): {", ".join(networks)}')
            else:
                self.log('No networks found (adapter may be busy)')
        threading.Thread(target=_scan, daemon=True).start()

    # ── Status indicators ──

    def _update_indicator(self, name, status):
        """Update a status indicator. status: 'ok', 'fail', or 'unknown'"""
        colours = {'ok': '#22aa22', 'fail': '#cc2222', 'unknown': 'grey'}
        labels = {'ok': 'OK', 'fail': 'FAIL', 'unknown': '--'}
        fg = colours.get(status, 'grey')
        text = f'\u25cf {name.upper()}: {labels.get(status, "--")}'
        def _set():
            if name in self.ind_labels:
                self.ind_labels[name].configure(text=text, fg=fg)
        self.root.after(0, _set)

    def _update_queue_indicator(self):
        n = len(self.push_queue)
        fg = '#cc2222' if n > 0 else 'grey'
        def _set():
            self.queue_label.configure(text=f'Queue: {n}', fg=fg)
        self.root.after(0, _set)

    def _countdown_tick(self):
        if not self.running:
            self.root.after(0, lambda: self.countdown_label.configure(text=''))
            return
        if self.next_scrape_at and not self.busy:
            remaining = max(0, int(self.next_scrape_at - time.time()))
            self.root.after(0, lambda r=remaining: self.countdown_label.configure(
                text=f'Next scrape in {r}s'))
        elif self.busy:
            self.root.after(0, lambda: self.countdown_label.configure(text='Scraping...'))
        self.countdown_timer = self.root.after(1000, self._countdown_tick)

    # ── Logging (thread-safe) ──

    def log(self, msg):
        ts = datetime.now().strftime('%H:%M:%S')
        line = f'[{ts}] {msg}\n'
        self.root.after(0, self._append_log, line)

    def _append_log(self, line):
        self.log_text.configure(state='normal')
        self.log_text.insert('end', line)
        self.log_text.see('end')
        self.log_text.configure(state='disabled')

    def _export_log(self):
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        path = filedialog.asksaveasfilename(
            defaultextension='.txt',
            initialfile=f'scraper_log_{ts}.txt',
            filetypes=[('Text files', '*.txt'), ('All files', '*.*')],
        )
        if not path:
            return
        try:
            content = self.log_text.get('1.0', 'end-1c')
            with open(path, 'w') as f:
                f.write(content)
            self.log(f'Log saved to {path}')
        except Exception as e:
            self.log(f'[ERROR] Save log: {e}')

    def set_status(self, msg):
        self.root.after(0, lambda: self.status_var.set(msg))

    def set_buttons(self, enabled):
        state = 'normal' if enabled else 'disabled'
        for btn in (self.scrape_btn, self.test_sm_btn, self.test_upload_btn, self.squad_btn):
            self.root.after(0, lambda b=btn, s=state: b.configure(state=s))

    def _show_current_wifi(self):
        def _get():
            ifaces = get_wifi_interfaces()
            self.root.after(0, lambda: self.iface_combo.configure(values=ifaces))
            current_iface = self.iface_var.get()
            if current_iface not in ifaces and ifaces:
                self.root.after(0, lambda: self.iface_var.set(ifaces[0]))
            ssid = get_current_ssid()
            self.log(f'Current WiFi: {ssid or "(not connected)"}')
            self.log(f'WiFi adapters: {", ".join(ifaces)}')
            # Auto-scan nearby networks
            iface = current_iface if current_iface in ifaces else (ifaces[0] if ifaces else 'Wi-Fi')
            networks = scan_wifi_networks(iface)
            if networks:
                self.root.after(0, lambda: self.ssid_combo.configure(values=networks))
                self.log(f'Nearby networks: {", ".join(networks)}')
        threading.Thread(target=_get, daemon=True).start()

    # ── Fetch competitions from server ──

    def fetch_destinations(self):
        self.read_gui_to_config()

        def _fetch():
            url = self.config['cloud_url']
            self.log(f'Fetching competitions from {url}...')
            try:
                resp = requests.get(f'{url}/api/destinations', timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    comps = data.get('competitions', [])
                    self.competitions = comps
                    values = [f"{c['route']} \u2014 {c['name']}" for c in comps]
                    self.root.after(0, lambda: self.comp_combo.configure(values=values))
                    self.log(f'Found {len(comps)} competition(s)')
                else:
                    self.log(f'[ERROR] HTTP {resp.status_code}')
            except Exception as e:
                self.log(f'[ERROR] {e}')

        threading.Thread(target=_fetch, daemon=True).start()

    # ── Push Squadding ──

    def push_squadding(self):
        if self.busy:
            return

        competitors = self.received_squadding
        if not competitors:
            self.log('[ERROR] No squadding data — use the bookmarklet on the ShotMarker page first')
            return

        self.read_gui_to_config()
        self.busy = True
        self.set_buttons(False)

        def _push():
            try:
                cfg = self.config
                iface = cfg['wifi_interface']
                upload_ssid = cfg['upload_ssid']
                upload_pass = cfg['upload_password'] or None
                cloud_url = cfg['cloud_url']
                api_key = cfg['api_key']

                comp_raw = cfg['competition']
                competition = comp_raw.split(' \u2014 ')[0].strip() if ' \u2014 ' in comp_raw else comp_raw.strip()

                if not competition:
                    self.log('[ERROR] No competition selected')
                    return
                if not api_key:
                    self.log('[ERROR] API key not set')
                    return

                self.log(f'Pushing {len(competitors)} competitors for {competition}...')

                # Switch to upload WiFi if needed
                current = get_current_ssid()
                if current != upload_ssid:
                    self.set_status(f'Switching to {upload_ssid}...')
                    if not wifi_connect(upload_ssid, iface, self.log, password=upload_pass):
                        self.log('[ERROR] Could not connect to upload WiFi')
                        return
                    time.sleep(2)

                self.set_status('Pushing squadding...')
                try:
                    resp = requests.post(
                        f'{cloud_url}/api/push/competitors',
                        headers={'X-API-Key': api_key},
                        json={'competition': competition, 'competitors': competitors},
                        timeout=30
                    )
                    if resp.status_code in (200, 201):
                        msg = resp.json().get('message', 'OK')
                        self.log(f'Squadding pushed: {msg}')
                        self.received_squadding = None
                        self.root.after(0, lambda: self.squad_btn.configure(text='Push Squadding'))
                    else:
                        self.log(f'[ERROR] HTTP {resp.status_code}: {resp.text[:200]}')
                except Exception as e:
                    self.log(f'[ERROR] Push squadding: {e}')

            finally:
                self.set_status('Ready')
                self.busy = False
                self.set_buttons(True)

        threading.Thread(target=_push, daemon=True).start()

    # ── Test Upload WiFi ──

    def test_upload(self):
        if self.busy:
            return
        self.read_gui_to_config()
        self.busy = True
        self.set_buttons(False)

        def _test():
            try:
                iface = self.config['wifi_interface']
                upload_ssid = self.config['upload_ssid']
                upload_pass = self.config['upload_password'] or None

                if not upload_ssid:
                    self.log('[ERROR] Upload WiFi SSID is not set')
                    return

                self.log('\u2500\u2500 Upload WiFi Test \u2500\u2500')
                self.set_status(f'Testing {upload_ssid}...')
                ok = wifi_connect(upload_ssid, iface, self.log, password=upload_pass)
                if ok:
                    self._update_indicator('upload', 'ok')
                    self.log(f'OK \u2014 connected to {upload_ssid}')
                    try:
                        requests.get(self.config['cloud_url'], timeout=5)
                        self._update_indicator('cloud', 'ok')
                        self.log('OK \u2014 internet reachable')
                    except:
                        self._update_indicator('cloud', 'fail')
                        self.log('WARNING \u2014 connected but no internet')
                else:
                    self._update_indicator('upload', 'fail')
                    self.log(f'FAILED \u2014 could not connect to {upload_ssid}')
                self.log('\u2500\u2500 Test complete \u2500\u2500')
            finally:
                self.set_status('Ready')
                self.busy = False
                self.set_buttons(True)

        threading.Thread(target=_test, daemon=True).start()

    # ── Test ShotMarker channels ──

    def test_sm(self):
        if self.busy:
            return
        self.read_gui_to_config()
        self.busy = True
        self.set_buttons(False)

        def _test():
            try:
                iface = self.config['wifi_interface']
                channels = self.config['sm_enabled']
                upload_ssid = self.config['upload_ssid']
                upload_pass = self.config['upload_password'] or None

                if not channels:
                    self.log('[ERROR] No ShotMarker channels enabled')
                    return

                self.log(f'\u2500\u2500 ShotMarker Test ({len(channels)} channel{"s" if len(channels) != 1 else ""}) \u2500\u2500')

                sm_any_ok = False
                for ch in channels:
                    self.set_status(f'Testing {ch}...')
                    ok = wifi_connect(ch, iface, self.log)
                    if ok:
                        sm_any_ok = True
                        self.log(f'OK \u2014 {ch} reachable')
                        sm_ip = self.config['shotmarker_ip']
                        try:
                            resp = requests.get(f'http://{sm_ip}/ts_export', timeout=5)
                            self.log(f'OK \u2014 {ch} ShotMarker responding (HTTP {resp.status_code})')
                        except:
                            self.log(f'WARNING \u2014 {ch} WiFi OK but ShotMarker not responding at {sm_ip}')
                    else:
                        self.log(f'FAILED \u2014 {ch} not available')
                    time.sleep(1)
                self._update_indicator('sm', 'ok' if sm_any_ok else 'fail')

                if upload_ssid:
                    self.set_status(f'Reconnecting to {upload_ssid}...')
                    wifi_connect(upload_ssid, iface, self.log, password=upload_pass)

                self.log('\u2500\u2500 Test complete \u2500\u2500')
            finally:
                self.set_status('Ready')
                self.busy = False
                self.set_buttons(True)

        threading.Thread(target=_test, daemon=True).start()

    # ── Single scrape cycle ──

    def scrape_once(self):
        if self.busy:
            return
        self.read_gui_to_config()
        self.busy = True
        self.set_buttons(False)
        threading.Thread(target=self._do_scrape, daemon=True).start()

    def _do_scrape(self):
        cfg = self.config
        iface = cfg['wifi_interface']
        channels = cfg['sm_enabled']
        sm_ip = cfg['shotmarker_ip']
        upload_ssid = cfg['upload_ssid']
        upload_pass = cfg['upload_password'] or None
        mode = cfg['mode']
        cloud_url = cfg['cloud_url']
        api_key = cfg['api_key']

        comp_raw = cfg['competition']
        competition = comp_raw.split(' \u2014 ')[0].strip() if ' \u2014 ' in comp_raw else comp_raw.strip()

        try:
            if not upload_ssid:
                self.log('[ERROR] Upload WiFi SSID not set')
                return
            if not channels:
                self.log('[ERROR] No ShotMarker channels enabled')
                return
            if mode == 'competition' and not competition:
                self.log('[ERROR] No competition selected')
                return
            if not api_key:
                self.log('[ERROR] API key not set \u2014 check Advanced Settings')
                return

            self.log('\u2550\u2550\u2550 Scrape cycle started \u2550\u2550\u2550')

            all_scores = []
            all_shotlog = ''

            for ch_idx, sm_ssid in enumerate(channels):
                ch_label = f'[{ch_idx + 1}/{len(channels)}] {sm_ssid}'
                self.set_status(f'Connecting to {sm_ssid}...')
                self.log(f'{ch_label}: connecting...')

                if not wifi_connect(sm_ssid, iface, self.log):
                    self.log(f'{ch_label}: SKIPPED \u2014 could not connect')
                    self._update_indicator('sm', 'fail')
                    continue

                self._update_indicator('sm', 'ok')
                time.sleep(2)

                if mode == 'competition':
                    self.set_status(f'{sm_ssid}: fetching scores...')
                    try:
                        resp = requests.get(f'http://{sm_ip}/ts_export', timeout=10)
                        if resp.status_code == 200:
                            scores = resp.json()
                            self.log(f'{ch_label}: got {len(scores)} score entries')
                            all_scores.extend(scores)
                        else:
                            self.log(f'{ch_label}: scores HTTP {resp.status_code}')
                    except Exception as e:
                        self.log(f'{ch_label}: [ERROR] scores: {e}')

                self.set_status(f'{sm_ssid}: fetching shotlog...')
                try:
                    resp = requests.get(f'http://{sm_ip}/export_csv?days=1', timeout=15)
                    if resp.status_code == 200 and resp.text.strip():
                        csv_text = resp.text
                        lines = csv_text.strip().split('\n')
                        self.log(f'{ch_label}: got {len(lines)} CSV lines')
                        if all_shotlog and lines:
                            all_shotlog += '\n' + '\n'.join(lines[1:])
                        else:
                            all_shotlog = csv_text
                    else:
                        self.log(f'{ch_label}: no shotlog data')
                except Exception as e:
                    self.log(f'{ch_label}: [ERROR] shotlog: {e}')

            has_scores = bool(all_scores) and mode == 'competition'
            has_shotlog = bool(all_shotlog.strip())

            if has_scores:
                h = hashlib.md5(json.dumps(all_scores, sort_keys=True).encode()).hexdigest()
                if h == self.last_hash:
                    self.log('Combined scores unchanged since last scrape')
                    has_scores = False
                else:
                    self.last_hash = h

            if not has_scores and not has_shotlog:
                self.log('Nothing new to push')
                return

            # Save local backup before switching WiFi
            self._save_backup(
                all_scores if has_scores else None,
                all_shotlog if has_shotlog else None,
                competition
            )

            self.set_status(f'Switching to {upload_ssid}...')
            if not wifi_connect(upload_ssid, iface, self.log, password=upload_pass):
                self.log(f'[ERROR] Could not connect to {upload_ssid}.')
                self._update_indicator('upload', 'fail')
                # Queue everything for retry
                if has_scores and competition:
                    self._queue_push('scores', all_scores, competition)
                if has_shotlog:
                    self._queue_push('shotlog', all_shotlog, competition)
                threading.Thread(target=play_fail_sound, daemon=True).start()
                return

            self._update_indicator('upload', 'ok')
            time.sleep(2)

            self.set_status('Checking internet...')
            try:
                requests.get(cloud_url, timeout=5)
            except Exception:
                self.log('[ERROR] No internet.')
                self._update_indicator('cloud', 'fail')
                if has_scores and competition:
                    self._queue_push('scores', all_scores, competition)
                if has_shotlog:
                    self._queue_push('shotlog', all_shotlog, competition)
                threading.Thread(target=play_fail_sound, daemon=True).start()
                return

            headers = {'X-API-Key': api_key}

            # Drain any previously queued items first
            self._drain_queue(headers, cloud_url)

            cloud_ok = True

            if has_scores and competition:
                self.set_status('Pushing scores...')
                self.log(f'Pushing {len(all_scores)} scores for {competition}...')
                try:
                    resp = requests.post(
                        f'{cloud_url}/api/push/scores', headers=headers,
                        json={'competition': competition, 'scores': all_scores},
                        timeout=30
                    )
                    if resp.status_code in (200, 201):
                        self.log(f'Scores: {resp.json().get("message", "OK")}')
                    else:
                        self.log(f'[ERROR] Scores HTTP {resp.status_code}: {resp.text[:200]}')
                        self._queue_push('scores', all_scores, competition)
                        cloud_ok = False
                except Exception as e:
                    self.log(f'[ERROR] Push scores: {e}')
                    self._queue_push('scores', all_scores, competition)
                    cloud_ok = False

            if has_shotlog:
                self.set_status('Pushing shotlog...')
                self.log('Pushing shotlog...')
                try:
                    resp = requests.post(
                        f'{cloud_url}/api/push/shotlog', headers=headers,
                        json={'csv': all_shotlog},
                        timeout=30
                    )
                    if resp.status_code in (200, 201):
                        self.log(f'Shotlog: {resp.json().get("message", "OK")}')
                    else:
                        self.log(f'[ERROR] Shotlog HTTP {resp.status_code}: {resp.text[:200]}')
                        self._queue_push('shotlog', all_shotlog, competition)
                        cloud_ok = False
                except Exception as e:
                    self.log(f'[ERROR] Push shotlog: {e}')
                    self._queue_push('shotlog', all_shotlog, competition)
                    cloud_ok = False

            self._update_indicator('cloud', 'ok' if cloud_ok else 'fail')

            self.log('\u2550\u2550\u2550 Scrape complete \u2550\u2550\u2550')
            threading.Thread(target=play_success_sound if cloud_ok else play_fail_sound,
                             daemon=True).start()

        except Exception as e:
            self.log(f'[ERROR] Unexpected: {e}')
            threading.Thread(target=play_fail_sound, daemon=True).start()

        finally:
            if upload_ssid and get_current_ssid() != upload_ssid:
                self.log(f'Reconnecting to {upload_ssid}...')
                wifi_connect(upload_ssid, iface, self.log, password=upload_pass)
            self.set_status('Ready')
            self.busy = False
            self.set_buttons(True)

    # ── Auto scrape ──

    def toggle_auto(self):
        if self.running:
            self.stop_auto()
        else:
            self.start_auto()

    def start_auto(self):
        self.read_gui_to_config()
        interval = self.config['auto_interval']
        self.running = True
        self.root.after(0, lambda: self.auto_btn.configure(text='Stop Auto'))
        self.log(f'Auto-scrape ON \u2014 every {interval}s')
        self.set_status(f'Auto-scrape \u2014 every {interval}s')
        self._auto_tick()
        self._countdown_tick()

    def stop_auto(self):
        self.running = False
        self.next_scrape_at = None
        if self.auto_timer:
            self.root.after_cancel(self.auto_timer)
            self.auto_timer = None
        if self.countdown_timer:
            self.root.after_cancel(self.countdown_timer)
            self.countdown_timer = None
        self.root.after(0, lambda: self.auto_btn.configure(text='Start Auto'))
        self.root.after(0, lambda: self.countdown_label.configure(text=''))
        self.log('Auto-scrape OFF')
        self.set_status('Ready')

    def _auto_tick(self):
        if not self.running:
            return
        if not self.busy:
            self.scrape_once()
        interval = self.config.get('auto_interval', 120)
        self.next_scrape_at = time.time() + interval
        self.auto_timer = self.root.after(interval * 1000, self._auto_tick)

    # ── Update ──

    def _ensure_internet_and_check(self, silent=False):
        """Connect to upload WiFi if needed, then check for updates."""
        self.read_gui_to_config()
        cfg = self.config
        iface = cfg['wifi_interface']
        upload_ssid = cfg['upload_ssid']
        upload_pass = cfg['upload_password'] or None
        repo = cfg.get('github_repo', 'tghaines/smscores')
        branch = cfg.get('github_branch', 'master')
        filepath = cfg.get('github_file', 'win_scraper_gui.py')

        # Connect to upload WiFi if not already on it
        current = get_current_ssid()
        if upload_ssid and current != upload_ssid:
            if not silent:
                self.log(f'Connecting to {upload_ssid} for update check...')
            if not wifi_connect(upload_ssid, iface, self.log, password=upload_pass):
                if not silent:
                    self.log('[ERROR] Could not connect to upload WiFi for update check')
                return
            time.sleep(2)

        has_update, remote_ver, content = check_for_update(repo, branch, filepath)
        if has_update:
            self._pending_update = (remote_ver, content)
            if silent:
                self.log(f'UPDATE AVAILABLE: v{VERSION} -> v{remote_ver} — click Update to install')
                threading.Thread(target=play_success_sound, daemon=True).start()
            else:
                self.log(f'Update available: v{VERSION} -> v{remote_ver}')
                self.root.after(0, lambda: self._prompt_update(remote_ver, content))
        elif remote_ver:
            if not silent:
                self.log(f'Up to date (v{VERSION})')
        else:
            if not silent:
                self.log('[ERROR] Could not check for updates')

    def _check_update_clicked(self):
        """Manual update check — shows dialogs."""
        if self.busy:
            return
        # Use cached result from startup check if available
        if self._pending_update:
            remote_ver, content = self._pending_update
            self._prompt_update(remote_ver, content)
            return

        self.log(f'Checking for updates (current: v{VERSION})...')
        threading.Thread(target=lambda: self._ensure_internet_and_check(silent=False),
                         daemon=True).start()

    def _auto_check_update(self):
        """Silent update check on startup — log only, no popup."""
        threading.Thread(target=lambda: self._ensure_internet_and_check(silent=True),
                         daemon=True).start()

    def _prompt_update(self, remote_ver, content):
        """Show update dialog and apply if user says yes."""
        answer = messagebox.askyesno(
            'Update Available',
            f'A new version is available.\n\n'
            f'Current:  v{VERSION}\n'
            f'Latest:    v{remote_ver}\n\n'
            f'Update now?'
        )
        if not answer:
            self.log('Update skipped')
            return
        self._apply_update(remote_ver, content)

    def _apply_update(self, remote_ver, content):
        """Overwrite the script file with the new version."""
        if getattr(sys, 'frozen', False):
            self.log('[ERROR] Auto-update not supported in .exe mode — download manually from GitHub')
            messagebox.showinfo('Update', 'Auto-update is not supported in .exe mode.\n'
                                'Download the latest version from GitHub.')
            return
        try:
            script_path = os.path.abspath(__file__)
            # Backup current version
            backup_path = script_path + f'.v{VERSION}.bak'
            with open(script_path, 'r', encoding='utf-8') as f:
                old_content = f.read()
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(old_content)
            # Write new version
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(content)
            self.log(f'Updated to v{remote_ver} (backup: {os.path.basename(backup_path)})')
            messagebox.showinfo('Updated',
                f'Updated to v{remote_ver}!\n\n'
                f'Restart the app to use the new version.\n'
                f'Old version backed up as {os.path.basename(backup_path)}')
        except Exception as e:
            self.log(f'[ERROR] Update failed: {e}')
            messagebox.showerror('Update Failed', f'Could not write update:\n{e}')

    # ── Cleanup ──

    def on_close(self):
        self.save_config()
        if self.running:
            self.running = False
            if self.auto_timer:
                self.root.after_cancel(self.auto_timer)
            if self.countdown_timer:
                self.root.after_cancel(self.countdown_timer)
        if hasattr(self, 'local_server'):
            self.local_server.shutdown()
        self.root.destroy()


# ══════════════════════════════════════════════

def main():
    root = tk.Tk()
    ScraperApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
