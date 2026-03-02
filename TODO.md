# ScoreScraper / SMScores — TODO List

## Priority — Before Competition
- [x] 1. Event guide per-competition — upload HTML guide per competition, falls back to default
- [x] 2. Allow renaming a competition — editable from Settings tab
- [x] 3. Allow changing a competition's route — editable from Settings tab with validation
- [x] 4. Upload competition logos — upload from Settings tab, shown on scoreboard header
- [x] 5. Contact us page per competition — email/phone/info per competition, /<route>/contact page

## Infrastructure
- [x] 6. Git version control — private GitHub repo, local + remote
- [x] 11. Backup script — automated daily backup of database and app.py on server

## Features
- [x] 7. Auto-refresh scoreboard — already implemented (15s polling + auto-scroll)
- [ ] 8. Competition archive page — public list of past competitions with final results (parked)
- [ ] 9. Shooter statistics — track individuals across competitions (parked — needs consistent name entry)
- [x] 10. Export results — CSV download from admin Settings tab
- [x] 12. Admin delete club scores — ability to clear shotlog/club day records from admin page

## Future — Windows Desktop Scraper
- [ ] 13. Windows scraper app — replace Pi with a laptop-based .exe that scrapes ShotMarker and pushes to cloud
  - Rewrite WiFi management from nmcli (Linux) to netsh/pywifi (Windows)
  - Simple GUI (tkinter) — config panel, ShotMarker channel setup, log window, manual trigger
  - Package as standalone .exe via PyInstaller (no Python install needed)
  - Single WiFi adapter: connect to SM → scrape → disconnect → connect to internet → push → repeat
  - Optional: support 2 adapters (one dedicated to SM, one for internet) for faster cycling
  - Key risk: Windows WiFi switching reliability — needs testing with auto-reconnect behaviour
  - Removes need for Pi, AP, SSH, systemd — just download, run, and go
