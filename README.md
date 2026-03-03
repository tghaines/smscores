# ScoreScraper

Grabs scores from ShotMarker targets and puts them on the website automatically.

---

## Getting Started

Someone gave you a file called **ScoreScraper.exe** (on a USB stick, email, whatever). Here's what to do.

### Step 1: Copy it to your laptop

Copy `ScoreScraper.exe` to your Desktop (or anywhere you like). There's nothing to install.

### Step 2: Run it

Double-click `ScoreScraper.exe`.

**You will see a blue warning screen** that says "Windows protected your PC". This is normal -- Windows shows this for any app it hasn't seen before. It's safe.

To get past it:
1. Click **"More info"** (small text under the warning message)
2. Click **"Run anyway"**

The ScoreScraper window will open.

### Step 3: Enter your API key

Your range admin will give you an API key -- it's a long string of letters and numbers that tells the system which range you are.

1. At the bottom of the window, click **Advanced Settings**
2. Find the **API Key** box
3. Paste in the key your admin gave you
4. Click **Validate** -- you should see your range name appear
5. Click **Advanced Settings** again to close that section

### Step 4: Set up your WiFi

You need two WiFi connections:
- One to talk to the **ShotMarker** targets on the range
- One for the **internet** to upload scores to the website

#### ShotMarker (top section)

1. **Adapter** -- click the dropdown and pick your WiFi adapter. If you have a USB WiFi dongle plugged in, you'll see two adapters listed with their real names (e.g. "Wi-Fi -- Intel..." and "Wi-Fi 2 -- Realtek..."). Pick whichever one you want to use for ShotMarker.
2. **Channels** -- tick **ShotMarker** (this is the WiFi network name the ShotMarker creates). Leave the others unticked unless you know you need them.

#### Upload WiFi (second section)

1. **Adapter** -- pick the WiFi adapter for your internet connection. If you only have one adapter, pick the same one as above (the app will switch between networks automatically, just a bit slower).
2. Click **Scan** to find nearby WiFi networks
3. **SSID** -- pick your internet WiFi network from the dropdown
4. **Password** -- type the WiFi password. If your laptop already connects to this network automatically, leave the password blank.

#### One adapter or two?

- **One adapter** (most laptops): Set both adapters to the same one. The app will connect to ShotMarker, grab the scores, disconnect, connect to internet, upload, then switch back. Works fine, just takes about 10 seconds to switch each time.
- **Two adapters** (laptop + USB WiFi dongle): Set each adapter to a different one. Both stay connected all the time. Much faster, no switching delays.

### Step 5: Pick your range and competition

1. Click **Fetch** to load the list of ranges
2. Pick your **Range** from the dropdown
3. Choose what you're doing:
   - **Competition** -- pick the competition from the dropdown. Scores and squadding go to the competition's live scoreboard page.
   - **Club day only** -- for regular club practice. No competition needed. Shotlog data goes to the club's range page.

### Step 6: Go!

- Click **Scrape Once** to grab scores and upload them one time
- Click **Start Auto** to keep scraping automatically (every 30 seconds by default)

Watch the log at the bottom of the window -- it tells you everything that's happening.

---

## Pushing Squadding

If your competition has squadding (who's shooting where) set up on the ShotMarker:

1. Make sure the ShotMarker is powered on and the competition is loaded on it
2. Click **Push Squadding**
3. Done -- the app connects to the ShotMarker, grabs the squadding, and uploads it

---

## Updating

When a new version comes out, your range admin will send you a new `ScoreScraper.exe`. Just delete the old one and use the new one. Your settings are saved separately so you won't lose them.

---

## Troubleshooting

**The blue "Windows protected your PC" screen won't go away**
Make sure you click "More info" first. The "Run anyway" button only appears after you click that.

**WiFi won't connect to ShotMarker**
- Is the ShotMarker powered on?
- Are you close enough? ShotMarker WiFi range is limited.
- Did you pick the right adapter in the dropdown?
- Click the little refresh button next to the adapter dropdown and try again.

**"No profile assigned to the specified interface"**
This happens the first time you use a new WiFi adapter. The app creates the WiFi profile automatically -- just try again and it should work.

**Scores say "unchanged"**
That's normal. It means nobody has fired any new shots since the last scrape. The app only uploads when something has changed.

**"Could not connect to upload WiFi"**
- Check your upload WiFi SSID is correct (click Scan to refresh the list)
- Check the password is right
- Try the **Test Upload** button to test the connection

**Nothing seems to happen when I click Scrape**
Check the log at the bottom of the window. It shows exactly what's happening and any errors.

---

## For Developers

Source code: `win_scraper_gui.py`. To run from source:

```
pip install requests
python win_scraper_gui.py
```

To build the exe: run `build.bat` (requires Python).
