# Contributing to SMScores

Thanks for helping out. This project powers live scoring for competitive shooting events, so reliability matters. Here's what you need to know.

## The Golden Rule

**Don't break live scoring.** People are watching scoreboards during competitions. Test your changes thoroughly before they go anywhere near production.

## Project Structure

This is a single-file Flask app (`app.py`). Yes, it's big (~5000 lines). It contains:
- SQLAlchemy models
- API endpoints
- HTML templates (as Python strings)
- JavaScript (embedded in templates)
- CSS (embedded in templates)

It's not pretty, but it works and it's easy to deploy (one file to copy). Don't refactor the structure without discussing it first.

## How to Contribute

1. **Fork or branch** — never commit directly to `main`
2. **One feature per PR** — keep changes focused
3. **Test locally** — run `python app.py` and verify your changes work
4. **Describe what you changed** — clear PR descriptions help everyone

## Development Setup

```bash
# Clone and set up
git clone <repo-url>
cd smscores
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt

# You need PostgreSQL running locally
createdb smscores
python app.py
# Visit http://localhost:5000
```

## Areas That Need Work

### Parked (need design discussion first)
- **Competition archive page** — public list of past competitions with final results
- **Shooter statistics** — track individuals across competitions. Blocked by inconsistent name entry (free text). Needs a solution for name matching/normalisation.

### Always Welcome
- Bug fixes
- UI/UX improvements
- Mobile responsiveness
- Performance improvements
- Better error handling
- Documentation

## Code Style

- This is Python/Flask — keep it simple and readable
- HTML/CSS/JS is embedded in Python template strings — watch your quote escaping
- Use `'''` for template strings, escape single quotes in JS as `\\'`
- No build tools, no npm, no webpack — everything is vanilla HTML/CSS/JS
- Stick to the existing dark theme (CSS variables defined in templates)

## Things to Be Careful With

- **API keys** — don't commit secrets. The API key and database password in the code are for reference only.
- **Database migrations** — there's no Alembic. New columns need manual `ALTER TABLE` on the server. Document any schema changes in your PR.
- **The Pi scraper** — changes to `multi_scraper_v2.py` or `scraper_web_v3.py` need to be deployed to the Raspberry Pi separately. These run on a Pi 5 with USB WiFi adapters.
- **ShotMarker integration** — the scraper talks to ShotMarker targets over WiFi. You can't easily test this without the hardware. If you're changing scraper code, be very careful.

## Deployment

Only the maintainer deploys to production. When your PR is merged:

1. `app.py` gets copied to the cloud server and the service restarted
2. Pi scripts get copied to the Raspberry Pi if changed
3. Any database migrations get run manually

## Questions?

Open an issue or contact the maintainer.
