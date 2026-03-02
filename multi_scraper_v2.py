#!/usr/bin/env python3
"""
Multi-channel ShotMarker scraper v2
- wlan0: Access Point (SMscraper hotspot)
- wlan1: Cycles through ShotMarker networks to scrape, then uplink to upload
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
SCRAPE_INTERFACE = 'wlan0'

CYCLE_INTERVAL = 30  # seconds between full cycles
CONNECT_TIMEOUT = 15  # seconds to wait for WiFi connection
SM_CONNECT_RETRIES = 2  # retries for each SM connection
UPLINK_CONNECT_RETRIES = 3  # retries for uplink connection

SHOTLOG_INTERVAL = 300  # only push shotlog every 5 minutes
TRIGGER_FILE = '/tmp/scraper_trigger'  # manual trigger from web UI

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
    datefmt='%H:%M:%S',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/tmp/multi_scraper.log')
    ]
)
log = logging.getLogger('multi_scraper')

# ══════════════════════════════════════════════
#  STATE TRACKING
# ══════════════════════════════════════════════

# Store scraped data until we can upload
pending_scores = {}  # {channel_name: scores_data}
pending_shotlogs = {}  # {channel_name: csv_content}

# Track what we've already uploaded (to avoid duplicates)
last_scores_hash = {}
last_shotlog_time = {}

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
            log.error(f'Error loading config: {e}')
    return {}

def get_destination():
    """Get current destination from config"""
    config = load_config()
    return config.get('active_range'), config.get('active_competition')

def get_channels():
    """Get enabled SM channels from config"""
    config = load_config()
    channels = config.get('sm_channels', DEFAULT_CHANNELS)
    return [ch for ch in channels if ch.get('enabled', True)]

def get_uplink():
    """Get uplink WiFi config"""
    config = load_config()
    ssid = config.get('uplink_ssid', '')
    password = config.get('uplink_password', '')
    return ssid, password

def get_scrape_interval():
    """Get configured scrape interval (0 = manual only)"""
    config = load_config()
    return config.get('scrape_interval', 0)

def check_manual_trigger():
    """Check if manual trigger was requested, clear it"""
    if os.path.exists(TRIGGER_FILE):
        try:
            os.remove(TRIGGER_FILE)
        except:
            pass
        return True
    return False

# ══════════════════════════════════════════════
#  WIFI MANAGEMENT
# ══════════════════════════════════════════════

def wifi_connect(ssid, interface='wlan1', password=None, retries=2):
    """Connect to a WiFi network on specified interface"""
    for attempt in range(retries):
        try:
            # Check if already connected
            result = subprocess.run(
                ['nmcli', '-t', '-f', 'GENERAL.CONNECTION', 'device', 'show', interface],
                capture_output=True, text=True, timeout=10
            )
            current = result.stdout.strip().split(':')[-1] if ':' in result.stdout else ''
            if current == ssid:
                log.debug(f'{interface}: Already connected to {ssid}')
                return True
            
            # Disconnect any current connection
            subprocess.run(['nmcli', 'device', 'disconnect', interface],
                          capture_output=True, timeout=10)
            time.sleep(1)
            
            # Try to connect
            if password:
                # For password-protected networks, create/update connection
                conn_name = f'{ssid}-{interface}'
                # Delete old connection if exists
                subprocess.run(['nmcli', 'connection', 'delete', conn_name],
                              capture_output=True, timeout=10)
                # Create new connection
                result = subprocess.run([
                    'nmcli', 'connection', 'add',
                    'type', 'wifi',
                    'ifname', interface,
                    'con-name', conn_name,
                    'ssid', ssid,
                    'wifi-sec.key-mgmt', 'wpa-psk',
                    'wifi-sec.psk', password
                ], capture_output=True, text=True, timeout=15)
                
                if result.returncode != 0:
                    log.warning(f'{interface}: Failed to create connection for {ssid}')
                    continue
                
                # Connect
                result = subprocess.run(['nmcli', 'connection', 'up', conn_name],
                                       capture_output=True, text=True, timeout=CONNECT_TIMEOUT)
            else:
                # For open networks (ShotMarker)
                result = subprocess.run(
                    ['nmcli', 'device', 'wifi', 'connect', ssid, 'ifname', interface],
                    capture_output=True, text=True, timeout=CONNECT_TIMEOUT
                )
            
            if result.returncode == 0:
                log.info(f'{interface}: Connected to {ssid}')
                time.sleep(2)  # Give it a moment to get IP
                return True
            else:
                log.warning(f'{interface}: Connect attempt {attempt+1} failed for {ssid}: {result.stderr.strip()}')
                
        except subprocess.TimeoutExpired:
            log.warning(f'{interface}: Connection timeout for {ssid}')
        except Exception as e:
            log.error(f'{interface}: Connection error for {ssid}: {e}')
        
        time.sleep(2)
    
    return False

def wifi_disconnect(interface='wlan1'):
    """Disconnect interface"""
    try:
        subprocess.run(['nmcli', 'device', 'disconnect', interface],
                      capture_output=True, timeout=10)
        log.debug(f'{interface}: Disconnected')
    except Exception as e:
        log.error(f'{interface}: Disconnect error: {e}')

def check_shotmarker_reachable():
    """Check if ShotMarker device is reachable"""
    try:
        result = subprocess.run(
            ['ping', '-c', '1', '-W', '2', SHOTMARKER_IP],
            capture_output=True, timeout=5
        )
        return result.returncode == 0
    except:
        return False

def check_internet():
    """Check if we have internet connectivity"""
    try:
        result = subprocess.run(
            ['ping', '-c', '1', '-W', '3', '8.8.8.8'],
            capture_output=True, timeout=5
        )
        return result.returncode == 0
    except:
        return False

# ══════════════════════════════════════════════
#  SHOTMARKER DATA FETCHING
# ══════════════════════════════════════════════

def fetch_scores():
    """Fetch competition scores from ShotMarker"""
    try:
        url = f'http://{SHOTMARKER_IP}/ts_export'
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        log.debug(f'Fetch scores error: {e}')
    return None

def fetch_shotlog_csv():
    """Fetch shotlog CSV from ShotMarker"""
    try:
        url = f'http://{SHOTMARKER_IP}/export_csv?days=1'
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200 and resp.text.strip():
            return resp.text
    except Exception as e:
        log.debug(f'Fetch shotlog error: {e}')
    return None

# ══════════════════════════════════════════════
#  CLOUD UPLOAD
# ══════════════════════════════════════════════

def push_scores(scores, channel_name, competition):
    """Push scores to cloud"""
    try:
        resp = requests.post(
            f'{CLOUD_URL}/api/push/scores',
            headers={'X-API-Key': API_KEY},
            json={'competition': competition, 'scores': scores},
            timeout=30
        )
        if resp.status_code not in [200, 201]:
            log.warning(f'Push scores HTTP {resp.status_code}: {resp.text[:200]}')
        return resp.status_code in [200, 201]
    except Exception as e:
        log.error(f'Push scores error: {e}')
    return False

def push_shotlog(csv_content, channel_name, range_id):
    """Push raw shotlog CSV to cloud for server-side parsing"""
    try:
        resp = requests.post(
            f'{CLOUD_URL}/api/push/shotlog',
            headers={'X-API-Key': API_KEY},
            json={'csv': csv_content},
            timeout=30
        )
        if resp.status_code not in [200, 201]:
            log.warning(f'Push shotlog HTTP {resp.status_code}: {resp.text[:200]}')
        return resp.status_code in [200, 201]
    except Exception as e:
        log.error(f'Push shotlog error: {e}')
    return False

def hash_data(data):
    """Create hash of data to detect changes"""
    return hashlib.md5(json.dumps(data, sort_keys=True).encode()).hexdigest()

# ══════════════════════════════════════════════
#  MAIN SCRAPE CYCLE
# ══════════════════════════════════════════════

def scrape_channel(channel, manual_trigger=False):
    """Scrape a single ShotMarker channel, store data locally"""
    name = channel['name']
    ssid = channel['ssid']
    
    log.info(f'{name}: Connecting to {ssid}...')
    
    # Connect to this SM network (no password for ShotMarker)
    if not wifi_connect(ssid, SCRAPE_INTERFACE, retries=SM_CONNECT_RETRIES):
        log.warning(f'{name}: Failed to connect to {ssid}')
        return False
    
    # Wait for ShotMarker to be reachable
    for i in range(5):
        if check_shotmarker_reachable():
            break
        time.sleep(1)
    else:
        log.warning(f'{name}: ShotMarker not reachable at {SHOTMARKER_IP}')
        return False
    
    log.info(f'{name}: ShotMarker reachable, fetching data...')
    
    # Fetch scores
    scores = fetch_scores()
    if scores:
        scores_hash = hash_data(scores)
        if scores_hash != last_scores_hash.get(name):
            pending_scores[name] = scores
            last_scores_hash[name] = scores_hash
            log.info(f'{name}: New scores fetched')
        else:
            log.debug(f'{name}: Scores unchanged')
    
    # Fetch shotlog (rate limited, unless manual trigger)
    now = time.time()
    if manual_trigger or now - last_shotlog_time.get(name, 0) > SHOTLOG_INTERVAL:
        csv = fetch_shotlog_csv()
        if csv:
            pending_shotlogs[name] = csv
            log.info(f'{name}: Shotlog fetched')
    
    return True

def upload_to_cloud(range_id, competition):
    """Connect to uplink and upload all pending data"""
    global pending_scores, pending_shotlogs, last_shotlog_time
    
    uplink_ssid, uplink_password = get_uplink()
    
    if not uplink_ssid:
        log.warning('No uplink WiFi configured - cannot upload')
        return False
    
    # Check if we have anything to upload
    if not pending_scores and not pending_shotlogs:
        log.debug('Nothing to upload')
        return True
    
    log.info(f'Connecting to uplink: {uplink_ssid}...')
    
    # Connect to uplink
    if not wifi_connect(uplink_ssid, SCRAPE_INTERFACE, uplink_password, retries=UPLINK_CONNECT_RETRIES):
        log.error(f'Failed to connect to uplink: {uplink_ssid}')
        return False
    
    # Wait for internet
    for i in range(5):
        if check_internet():
            break
        time.sleep(1)
    else:
        log.warning('No internet on uplink')
        return False
    
    log.info('Uplink connected, uploading data...')
    
    # Upload scores
    if competition and pending_scores:
        for channel_name, scores in list(pending_scores.items()):
            if push_scores(scores, channel_name, competition):
                log.info(f'{channel_name}: Scores uploaded to {competition}')
                del pending_scores[channel_name]
            else:
                log.warning(f'{channel_name}: Score upload failed')
    
    # Upload shotlogs
    if range_id and pending_shotlogs:
        for channel_name, csv in list(pending_shotlogs.items()):
            if push_shotlog(csv, channel_name, range_id):
                log.info(f'{channel_name}: Shotlog uploaded to {range_id}')
                del pending_shotlogs[channel_name]
                last_shotlog_time[channel_name] = time.time()
            else:
                log.warning(f'{channel_name}: Shotlog upload failed')
    
    return True

def main():
    log.info('=' * 50)
    log.info('Multi-channel ShotMarker scraper v2 starting')
    log.info(f'Config file: {CONFIG_FILE}')
    log.info(f'Cloud URL: {CLOUD_URL}')
    log.info('=' * 50)
    
    while True:
        try:
            # Reload config each cycle (allows live updates from web UI)
            range_id, competition = get_destination()
            channels = get_channels()
            uplink_ssid, _ = get_uplink()
            
            if not range_id:
                log.warning('No destination configured - waiting...')
                time.sleep(CYCLE_INTERVAL)
                continue
            
            if not uplink_ssid:
                log.warning('No uplink WiFi configured - waiting...')
                time.sleep(CYCLE_INTERVAL)
                continue

            # Check interval and manual trigger
            interval = get_scrape_interval()
            manual = check_manual_trigger()

            if interval == 0 and not manual:
                log.debug('Auto-load disabled - waiting for manual trigger')
                time.sleep(CYCLE_INTERVAL)
                continue

            if manual:
                log.info('*** Manual trigger detected - running full cycle ***')

            enabled_names = [ch['name'] for ch in channels]
            log.info(f'--- New cycle ---')
            log.info(f'Destination: {range_id}' + (f' -> {competition}' if competition else ' (club day)'))
            log.info(f'Channels: {enabled_names}')
            log.info(f'Uplink: {uplink_ssid}')
            
            # Phase 1: Scrape all SM channels
            for channel in channels:
                try:
                    scrape_channel(channel, manual_trigger=manual)
                except Exception as e:
                    log.error(f"{channel['name']} scrape error: {e}")
                
                # Disconnect between channels
                wifi_disconnect(SCRAPE_INTERFACE)
                time.sleep(1)
            
            # Phase 2: Upload to cloud via uplink
            try:
                upload_to_cloud(range_id, competition)
            except Exception as e:
                log.error(f'Upload error: {e}')
            
            # Disconnect wlan1
            wifi_disconnect(SCRAPE_INTERFACE)
            
            # Wait before next cycle
            wait = interval if interval > 0 else CYCLE_INTERVAL
            log.info(f'Cycle complete. Pending: {len(pending_scores)} scores, {len(pending_shotlogs)} shotlogs')
            log.info(f'Waiting {wait}s...')
            time.sleep(wait)
            
        except Exception as e:
            log.error(f'Main loop error: {e}')
            time.sleep(10)

if __name__ == '__main__':
    main()
