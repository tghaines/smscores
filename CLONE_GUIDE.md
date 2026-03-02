# Clone Pi Scraper — SD Card Cloning Guide

## What You Need
- The working Pi's micro SD card
- A blank micro SD card (same size or larger)
- A micro SD card reader for your Windows PC
- **Win32DiskImager** (free download)

---

## Step 1: Shut down the Pi cleanly

On the Pi (SSH in or use terminal):

```
sudo shutdown now
```

Wait for the green LED to stop blinking, then unplug power.

## Step 2: Remove the SD card

Pull the micro SD card out of the Pi.

## Step 3: Read the SD card image on your PC

1. Insert the SD card into your PC's card reader
2. Download & install **Win32DiskImager** from https://sourceforge.net/projects/win32diskimager/
3. Open Win32DiskImager **as Administrator** (right-click → Run as administrator)
4. In the **Image File** box, click the folder icon and set save path to:
   `C:\Users\tghai\OneDrive\Desktop\2026 Coastal Cup\ScoreScraper_backup.img`
5. In the **Device** dropdown, select the SD card drive letter (e.g. `E:\`)
6. Click **Read** — this copies the entire SD card to an image file
7. Wait for it to finish (10-30 minutes depending on card size)
8. Click OK when done

**IMPORTANT:** Make sure you select the correct drive letter! Don't select your C: drive.

## Step 4: Write the image to the new SD card

1. Remove the original SD card from the reader — put it somewhere safe
2. Insert the **blank** SD card into the reader
3. In Win32DiskImager, keep the same image file path:
   `C:\Users\tghai\OneDrive\Desktop\2026 Coastal Cup\ScoreScraper_backup.img`
4. Select the **new** SD card's drive letter in **Device**
5. Click **Write** — this clones the image onto the new card
6. Wait for it to finish
7. Click OK when done
8. Eject the new SD card safely

## Step 5: Put the original SD card back

Insert the original SD card back into the primary Pi. Boot it up and confirm it still works:

```
ssh tghaines@192.168.1.107
sudo systemctl status scraper_web.service
sudo systemctl status multi_scraper.service
```

## Step 6: Boot the clone

1. Insert the cloned SD card into the **spare** Pi 5
2. Plug in both USB WiFi adapters (same MediaTek mt76x2u as primary)
3. Plug in power — it will boot as an exact copy
4. Connect via ethernet to your router

**Finding the clone on your network:** Both Pis will initially have the same hostname. Check your router's admin page for connected devices, or try:

```
ping ScoreScraper.local
```

If both are on the network, use your router to find the second IP address.

## Step 7: Change hostname on the clone

SSH into the clone:

```
ssh tghaines@<clone-ip-address>
```

Then run:

```
sudo hostnamectl set-hostname ScoreScraper2
sudo nano /etc/hosts
```

In the nano editor:
- Find the line that says `ScoreScraper`
- Change it to `ScoreScraper2`
- Press `Ctrl+O` then `Enter` to save
- Press `Ctrl+X` to exit

## Step 8: Change the AP SSID on the clone

So both Pis don't broadcast the same hotspot name:

```
sudo nmcli connection modify ScraperAP wifi.ssid scraper2
sudo nmcli connection up ScraperAP
```

## Step 9: Reboot the clone

```
sudo reboot
```

## Step 10: Verify the clone works

1. Look for the `scraper2` WiFi hotspot on your phone
2. Connect to it
3. Open the web UI in your phone's browser: `http://10.42.0.1:8080`
4. Verify the config page loads
5. SSH back in and check services:
   ```
   ssh tghaines@ScoreScraper2.local
   sudo systemctl status scraper_web.service
   sudo systemctl status multi_scraper.service
   ```

---

## What's the same on both units

| Item | Value |
|------|-------|
| All software & services | Identical |
| Python venv & packages | Identical |
| Cloud API key | Same key |
| Cloud server URL | http://134.199.153.50 |
| ShotMarker channels | SM1-SM4 |
| Uplink WiFi config | Same (from scraper_config.json) |
| SSH user/password | tghaines (same) |

## What's different on the clone

| Setting | Primary | Spare |
|---------|---------|-------|
| Hostname | ScoreScraper | ScoreScraper2 |
| AP SSID | scraper | scraper2 |

---

## At the Competition

- **Only power on ONE unit at a time** (unless they're covering different ranges)
- The spare has identical config — just swap the whole Pi if the primary fails
- Connect the same USB WiFi adapters and power supply
- The uplink WiFi and destination config are already saved on both units
- To reconfigure, connect to the spare's `scraper2` hotspot and open the web UI

## If You Need to Update the Clone Later

If you make changes to the primary Pi's software, you have two options:

**Option A — SCP the changed files:**
```
scp tghaines@ScoreScraper.local:/opt/scraper/scraper_web.py tghaines@ScoreScraper2.local:/opt/scraper/scraper_web.py
scp tghaines@ScoreScraper.local:/opt/scraper/multi_scraper.py tghaines@ScoreScraper2.local:/opt/scraper/multi_scraper.py
ssh tghaines@ScoreScraper2.local "sudo systemctl restart scraper_web.service && sudo systemctl restart multi_scraper.service"
```

**Option B — Clone the SD card again:**
Repeat Steps 1-9 above.
