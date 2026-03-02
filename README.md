# SMScores

Live scoring system for competitive shooting events. Scrapes data from ShotMarker electronic targets via a Raspberry Pi, pushes it to a cloud server, and displays live scoreboards to the public.

Built for the Coastal Cup but designed to support multiple competitions and ranges.

## How It Works

```
ShotMarker Targets ──WiFi──> Raspberry Pi ──HTTP API──> Cloud Server ──> Public Scoreboards
```

1. **ShotMarker targets** record shots electronically on the range
2. **Raspberry Pi** (ScoreScraper) connects to ShotMarker WiFi networks, scrapes score data, then switches to an uplink network to push data to the cloud
3. **Cloud server** (Flask + PostgreSQL) stores scores and serves the web app
4. **Public scoreboards** auto-refresh every 15 seconds with live results, rankings, and shot-by-shot detail

## Architecture

### Cloud Server (`app.py`)
- Flask web app (~5000 lines, single file)
- PostgreSQL database via SQLAlchemy
- Serves: public scoreboards, photo galleries, event guides, admin panel
- Receives score data via API from the Pi scraper
- Runs on DigitalOcean with Gunicorn + systemd

### Raspberry Pi Scraper
- **`multi_scraper_v2.py`** — Cycles through ShotMarker WiFi networks, scrapes scores and shotlog CSVs, pushes to cloud
- **`scraper_web_v3.py`** — Local web UI (port 8080) for configuring the scraper (WiFi channels, destination range/competition, manual triggers)
- Dual USB WiFi adapters: one for AP (config access), one for scraping + uplink
- Runs as systemd services

## Key Files

| File | What it does |
|------|-------------|
| `app.py` | Cloud server — the main application |
| `multi_scraper_v2.py` | Pi data scraper |
| `scraper_web_v3.py` | Pi configuration web UI |
| `backup.sh` | Database + app backup script (runs on server) |
| `TODO.md` | Feature tracking |
| `CLONE_GUIDE.md` | Pi SD card cloning instructions |

## Database Models

- **Range** — A shooting range/club (e.g. "ANZAC")
- **Competition** — A live event with its own scoreboard and URL slug
- **Score** — JSON snapshot of all competitor scores (pushed from ShotMarker)
- **Competitor** — Squadding entry (name, class, relay, target, match)
- **Shotlog** — Daily club shooting record
- **ShotlogString** — Individual string within a shotlog (shots, scores, X count)
- **Photo** — Competition photo gallery images

## Local Development

### Prerequisites
- Python 3.10+
- PostgreSQL

### Setup
```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/smscores.git
cd smscores

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Create database
createdb smscores
# Or via psql: CREATE DATABASE smscores;

# Run
python app.py
# App runs at http://localhost:5000
```

### Database Connection
The app expects PostgreSQL at `localhost` with database `smscores`. Update the connection string in `app.py` if your setup differs.

## Admin Access

Navigate to `/admin` and log in. The admin panel provides:
- Competition management (create, rename, archive, delete)
- Shooter/squadding management
- Score editing
- Photo gallery management
- Sponsor logos
- Competition settings (logo, guide, contact info)
- CSV export of results

## Public URLs

Each competition gets its own set of URLs:
- `/<route>` — Live scoreboard
- `/<route>/squadding` — Competitor list
- `/<route>/guide` — Event guide
- `/<route>/contact` — Contact information
- `/<route>/photos` — Photo gallery

Range/club days:
- `/range/<range_id>` — Club shooting history
- `/range/<range_id>/<date>` — Specific day's scores

## API Endpoints

Data push (from Pi scraper, requires API key):
- `POST /api/push/scores` — Push competition scores
- `POST /api/push/competitors` — Push squadding data
- `POST /api/push/shotlog` — Push club shooting CSV

## Deployment

### Cloud Server
- Located at `/opt/smscores/` on the server
- Service: `smscores` (systemd)
- Behind Gunicorn with 2 workers on port 5000
- Daily backup via cron (`backup.sh`)

### Raspberry Pi
- Located at `/opt/scraper/` on the Pi
- Services: `scraper_web.service`, `multi_scraper.service`
- AP network: "scraper" (open, 10.42.0.1:8080)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

Private repository. Contact the maintainer for access.
