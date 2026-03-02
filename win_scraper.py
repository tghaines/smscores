#!/usr/bin/env python3
"""
Windows ShotMarker Scraper — Proof of Concept
Connects to ShotMarker WiFi, scrapes scores + shotlog,
switches to home WiFi, pushes to cloud server.
"""
import subprocess
import requests
import time
import json
import hashlib
import sys

# ══════════════════════════════════════════════
#  CONFIGURATION
# ══════════════════════════════════════════════

CLOUD_URL = 'http://134.199.153.50'
API_KEY = ''  # Set your API key here or use the GUI version

SHOTMARKER_IP = '192.168.100.1'
SHOTMARKER_SSID = 'ShotMarker'
HOME_SSID = 'trinity'

WIFI_INTERFACE = 'Wi-Fi'  # From netsh wlan show interfaces

# ══════════════════════════════════════════════
#  WINDOWS WIFI MANAGEMENT
# ══════════════════════════════════════════════

def get_current_ssid():
    """Get currently connected WiFi SSID"""
    try:
        result = subprocess.run(
            ['netsh', 'wlan', 'show', 'interfaces'],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith('SSID') and not line.startswith('AP BSSID'):
                return line.split(':', 1)[1].strip()
    except Exception as e:
        print(f'  [ERROR] Get SSID failed: {e}')
    return None

def wifi_connect(ssid):
    """Connect to a WiFi network on Windows"""
    current = get_current_ssid()
    if current == ssid:
        print(f'  Already connected to {ssid}')
        return True

    print(f'  Connecting to {ssid}...')
    try:
        result = subprocess.run(
            ['netsh', 'wlan', 'connect', f'name={ssid}', f'interface={WIFI_INTERFACE}'],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            print(f'  [ERROR] Connect failed: {result.stderr.strip() or result.stdout.strip()}')
            return False

        # Wait for connection to establish
        for i in range(10):
            time.sleep(1)
            if get_current_ssid() == ssid:
                print(f'  Connected to {ssid}')
                return True
            print(f'  Waiting... ({i+1}s)')

        print(f'  [ERROR] Timed out connecting to {ssid}')
        return False
    except Exception as e:
        print(f'  [ERROR] Connect error: {e}')
        return False

def wifi_disconnect():
    """Disconnect from current WiFi"""
    try:
        subprocess.run(
            ['netsh', 'wlan', 'disconnect', f'interface={WIFI_INTERFACE}'],
            capture_output=True, timeout=10
        )
    except:
        pass

# ══════════════════════════════════════════════
#  SHOTMARKER SCRAPING
# ══════════════════════════════════════════════

def fetch_scores():
    """Fetch competition scores from ShotMarker"""
    try:
        resp = requests.get(f'http://{SHOTMARKER_IP}/ts_export', timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f'  [ERROR] Fetch scores: {e}')
    return None

def fetch_shotlog():
    """Fetch shotlog CSV from ShotMarker"""
    try:
        resp = requests.get(f'http://{SHOTMARKER_IP}/export_csv?days=1', timeout=15)
        if resp.status_code == 200 and resp.text.strip():
            return resp.text
    except Exception as e:
        print(f'  [ERROR] Fetch shotlog: {e}')
    return None

# ══════════════════════════════════════════════
#  CLOUD PUSH
# ══════════════════════════════════════════════

def push_scores(scores, competition):
    """Push competition scores to cloud"""
    try:
        resp = requests.post(
            f'{CLOUD_URL}/api/push/scores',
            headers={'X-API-Key': API_KEY},
            json={'competition': competition, 'scores': scores},
            timeout=30
        )
        if resp.status_code in [200, 201]:
            print(f'  Scores pushed OK')
            return True
        else:
            print(f'  [ERROR] Push scores HTTP {resp.status_code}: {resp.text[:200]}')
    except Exception as e:
        print(f'  [ERROR] Push scores: {e}')
    return False

def push_shotlog(csv_content):
    """Push shotlog CSV to cloud"""
    try:
        resp = requests.post(
            f'{CLOUD_URL}/api/push/shotlog',
            headers={'X-API-Key': API_KEY},
            json={'csv': csv_content},
            timeout=30
        )
        if resp.status_code in [200, 201]:
            print(f'  Shotlog pushed OK')
            return True
        else:
            print(f'  [ERROR] Push shotlog HTTP {resp.status_code}: {resp.text[:200]}')
    except Exception as e:
        print(f'  [ERROR] Push shotlog: {e}')
    return False

def check_internet():
    """Quick check for internet connectivity"""
    try:
        requests.get('http://134.199.153.50', timeout=5)
        return True
    except:
        return False

# ══════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════

def main():
    print('=' * 50)
    print('  Windows ShotMarker Scraper — POC')
    print('=' * 50)

    # Check config
    if not HOME_SSID:
        print('\n[!] HOME_SSID is not set.')
        print('    Edit win_scraper.py and set HOME_SSID to your home WiFi name.')
        print('    To find it, run: netsh wlan show interfaces')
        sys.exit(1)

    competition = input('\nCompetition route (e.g. CoastalCup, or blank for club only): ').strip()
    mode = 'competition' if competition else 'club'
    print(f'\nMode: {mode}')
    if competition:
        print(f'Competition: {competition}')
    print(f'ShotMarker SSID: {SHOTMARKER_SSID}')
    print(f'Home WiFi: {HOME_SSID}')
    print(f'Cloud: {CLOUD_URL}')
    print()

    last_hash = None

    while True:
        try:
            input('Press Enter to scrape (Ctrl+C to quit)...\n')

            # ── Phase 1: Connect to ShotMarker and scrape ──
            print('[1] Connecting to ShotMarker...')
            if not wifi_connect(SHOTMARKER_SSID):
                print('    Failed to connect to ShotMarker. Skipping.\n')
                continue

            time.sleep(2)  # Let connection settle

            scores = None
            shotlog = None

            if mode == 'competition':
                print('[2] Fetching competition scores...')
                scores = fetch_scores()
                if scores:
                    h = hashlib.md5(json.dumps(scores, sort_keys=True).encode()).hexdigest()
                    if h == last_hash:
                        print('    Scores unchanged since last scrape')
                        scores = None
                    else:
                        last_hash = h
                        print(f'    Got {len(scores)} score entries')
                else:
                    print('    No scores returned')

            print('[3] Fetching shotlog CSV...')
            shotlog = fetch_shotlog()
            if shotlog:
                lines = shotlog.strip().split('\n')
                print(f'    Got {len(lines)} lines')
            else:
                print('    No shotlog returned')

            if not scores and not shotlog:
                print('    Nothing to push.\n')
                continue

            # ── Phase 2: Connect to home WiFi and push ──
            print('[4] Switching to home WiFi...')
            if not wifi_connect(HOME_SSID):
                print('    Failed to connect to home WiFi. Data NOT pushed.\n')
                continue

            time.sleep(2)

            if not check_internet():
                print('    No internet. Data NOT pushed.\n')
                continue

            print('[5] Pushing to cloud...')
            if scores and competition:
                push_scores(scores, competition)
            if shotlog:
                push_shotlog(shotlog)

            print('\nDone!\n')

        except KeyboardInterrupt:
            print('\n\nExiting. Reconnecting to home WiFi...')
            wifi_connect(HOME_SSID)
            print('Bye!')
            sys.exit(0)

if __name__ == '__main__':
    main()
