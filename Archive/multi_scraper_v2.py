#!/usr/bin/env python3
"""
Multi-channel ShotMarker scraper
- wlan0: stays connected to internet (home WiFi / 4G hotspot)
- wlan1: rotates through ShotMarker networks to scrape
- Reads destination config from scraper_config.json
"""
import subprocess
import requests
import time
import json
import hashlib
import logging
import os
from datetime import datetime

# ══════════════════════════════════════════════
#  CONFIGURATION
# ══════════════════════════════════════════════
CONFIG_FILE = '/opt/scraper/scraper_config.json'
CLOUD_URL = 'http://134.199.153.50'
API_KEY = 'ab6d1435dccd0fb7a09133284ed0f256d901a0c0538c1e56d5d3c7e4726b791f'
SHOTMARKER_IP = '192.168.100.1'
SCRAPE_INTERFACE = 'wlan1'
SCORE_INTERVAL = 15
SHOTLOG_INTERVAL = 300
CSV_DAYS = 7
REQUEST_TIMEOUT = 10

# Default SM channels (used if no config file)
DEFAULT_CHANNELS = [
    {'name': 'SM1', 'ssid': 'ShotMarker', 'enabled': True},
    {'name': 'SM2', 'ssid': 'ShotMarker2', 'enabled': True},
    {'name': 'SM3', 'ssid': 'ShotMarker3', 'enabled': True},
    {'name': 'SM4', 'ssid': 'ShotMarker4', 'enabled': True},
]

# ══════════════════════════════════════════════
#  LOGGING
# ══════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger('multi_scraper')

# ══════════════════════════════════════════════
#  CONFIG MANAGEMENT
# ══════════════════════════════════════════════
def load_config():
    """Load config from file"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            log.warning(f'Error loading config: {e}')
    return None

def get_destination():
    """Get current active range and competition from config"""
    config = load_config()
    if config:
        return config.get('active_range'), config.get('active_competition')
    return None, None

def get_channels():
    """Get enabled SM channels from config"""
    config = load_config()
    if config and 'sm_channels' in config:
        return [ch for ch in config['sm_channels'] if ch.get('enabled', True)]
    return DEFAULT_CHANNELS

# ══════════════════════════════════════════════
#  WIFI MANAGEMENT
# ══════════════════════════════════════════════
def wifi_connect(ssid, interface='wlan1'):
    """Connect to a WiFi network using nmcli"""
    log.info(f'Connecting {interface} to {ssid}...')
    
    # First disconnect
    subprocess.run(['sudo', 'nmcli', 'device', 'disconnect', interface], 
                   capture_output=True, timeout=10)
    time.sleep(1)
    
    # Connect to network (open network, no password)
    cmd = ['sudo', 'nmcli', 'device', 'wifi', 'connect', ssid, 'ifname', interface]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    
    if result.returncode == 0:
        log.info(f'Connected to {ssid}')
        time.sleep(3)
        return True
    else:
        log.warning(f'Failed to connect to {ssid}: {result.stderr.strip()}')
        return False

def wifi_disconnect(interface='wlan1'):
    """Disconnect WiFi interface"""
    subprocess.run(['sudo', 'nmcli', 'device', 'disconnect', interface],
                   capture_output=True, timeout=10)

def check_shotmarker_reachable():
    """Check if ShotMarker is reachable"""
    try:
        resp = requests.get(f'http://{SHOTMARKER_IP}/', timeout=5)
        return resp.status_code == 200
    except:
        return False

# ══════════════════════════════════════════════
#  SCRAPING FUNCTIONS
# ══════════════════════════════════════════════
last_scores_hash = {}
last_shotlog_time = {}

def fetch_scores():
    """Fetch current scores from ShotMarker"""
    try:
        resp = requests.get(f'http://{SHOTMARKER_IP}/scores', timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        log.debug(f'Score fetch error: {e}')
    return None

def fetch_shotlog_csv():
    """Fetch CSV shotlog from ShotMarker"""
    try:
        url = f'http://{SHOTMARKER_IP}/export_csv?days={CSV_DAYS}'
        resp = requests.get(url, timeout=30)
        if resp.status_code == 200:
            return resp.text
    except Exception as e:
        log.debug(f'CSV fetch error: {e}')
    return None

def push_scores(scores, channel_name, competition):
    """Push scores to cloud server"""
    if not competition:
        log.debug(f'{channel_name}: No competition configured, skipping score push')
        return False
    
    try:
        resp = requests.post(
            f'{CLOUD_URL}/{competition}/api/scores',
            json=scores,
            headers={
                'X-API-Key': API_KEY,
                'X-Source-Channel': channel_name
            },
            timeout=REQUEST_TIMEOUT
        )
        if resp.status_code == 200:
            return True
        else:
            log.warning(f'{channel_name}: Score push failed: {resp.status_code}')
    except Exception as e:
        log.error(f'{channel_name}: Push scores error: {e}')
    return False

def push_shotlog(csv_content, channel_name, range_id):
    """Push shotlog CSV to cloud server"""
    if not range_id:
        log.debug(f'{channel_name}: No range configured, skipping shotlog push')
        return False
    
    try:
        resp = requests.post(
            f'{CLOUD_URL}/range/{range_id}/upload',
            files={'file': ('shotlog.csv', csv_content, 'text/csv')},
            data={'api_key': API_KEY, 'source_channel': channel_name},
            timeout=30
        )
        if resp.status_code in [200, 302]:
            return True
        else:
            log.warning(f'{channel_name}: Shotlog push failed: {resp.status_code}')
    except Exception as e:
        log.error(f'{channel_name}: Push shotlog error: {e}')
    return False

def hash_data(data):
    """Create hash of data to detect changes"""
    return hashlib.md5(json.dumps(data, sort_keys=True).encode()).hexdigest()

# ══════════════════════════════════════════════
#  MAIN SCRAPE LOOP
# ══════════════════════════════════════════════
def scrape_channel(channel, range_id, competition):
    """Scrape a single ShotMarker channel"""
    name = channel['name']
    ssid = channel['ssid']
    
    # Connect to this SM network
    if not wifi_connect(ssid, SCRAPE_INTERFACE):
        return False
    
    # Wait for ShotMarker to be reachable
    for _ in range(5):
        if check_shotmarker_reachable():
            break
        time.sleep(2)
    else:
        log.warning(f'{name}: ShotMarker not reachable')
        return False
    
    # Fetch and push scores (only if competition is set)
    if competition:
        scores = fetch_scores()
        if scores:
            scores_hash = hash_data(scores)
            if scores_hash != last_scores_hash.get(name):
                if push_scores(scores, name, competition):
                    log.info(f'{name}: Pushed scores to {competition}')
                    last_scores_hash[name] = scores_hash
    
    # Fetch and push shotlog (only if range is set)
    if range_id:
        now = time.time()
        if now - last_shotlog_time.get(name, 0) > SHOTLOG_INTERVAL:
            csv = fetch_shotlog_csv()
            if csv:
                if push_shotlog(csv, name, range_id):
                    log.info(f'{name}: Pushed shotlog to {range_id}')
                    last_shotlog_time[name] = now
    
    return True

def main():
    log.info('Multi-channel ShotMarker scraper starting')
    log.info(f'Config file: {CONFIG_FILE}')
    
    while True:
        # Reload config each cycle (allows live updates from web UI)
        range_id, competition = get_destination()
        channels = get_channels()
        
        if not range_id:
            log.warning('No destination configured - waiting...')
            time.sleep(SCORE_INTERVAL)
            continue
        
        enabled_names = [ch['name'] for ch in channels]
        log.info(f'Destination: {range_id}' + (f' → {competition}' if competition else ' (club day)'))
        log.info(f'Enabled channels: {enabled_names}')
        
        for channel in channels:
            try:
                scrape_channel(channel, range_id, competition)
            except Exception as e:
                log.error(f"{channel['name']} error: {e}")
            
            time.sleep(2)
        
        # Disconnect wlan1 between rounds
        wifi_disconnect(SCRAPE_INTERFACE)
        
        # Wait before next round
        log.info(f'Cycle complete, waiting {SCORE_INTERVAL}s...')
        time.sleep(SCORE_INTERVAL)

if __name__ == '__main__':
    main()
