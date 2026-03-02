#!/usr/bin/env python3
"""Patch app.py to fix sponsor logos on competition pages."""
import re

APP_FILE = '/opt/smscores/app.py'

with open(APP_FILE, 'r') as f:
    code = f.read()

# ── 1. Add sponsor CSS to SCOREBOARD_HTML style block ──
# Insert before the closing </style> in SCOREBOARD_HTML
old_css_end = "footer a { color:var(--text2); text-decoration:none; margin:0 12px; }\n</style>"
new_css_end = """footer a { color:var(--text2); text-decoration:none; margin:0 12px; }
.sponsor-bar { display:flex; flex-wrap:wrap; gap:12px; align-items:center; justify-content:center; padding:12px 16px; background:rgba(255,255,255,0.05); border-radius:6px; margin-top:12px; }
.sponsor-bar a { display:inline-block; transition:transform 0.2s; }
.sponsor-bar a:hover { transform:scale(1.08); }
.sponsor-bar img { max-height:50px; max-width:120px; object-fit:contain; background:#fff; padding:6px; border-radius:4px; }
@media(max-width:600px) { .sponsor-bar img { max-height:36px; max-width:90px; } }
</style>"""

code = code.replace(old_css_end, new_css_end, 1)
print("[1/4] Added sponsor CSS")

# ── 2. Update sponsor display on competition page ──
old_sponsor_html = """      {% if competition.sponsors %}
      <div class="sponsor-bar" style="display:flex;flex-wrap:wrap;gap:16px;align-items:center;margin-top:12px;">
        {% for url in competition.sponsors %}
        <img src="{{ url }}" style="max-height:50px;max-width:120px;object-fit:contain;background:#fff;padding:6px;border-radius:4px;" onerror="this.style.display=\'none\'">
        {% endfor %}
      </div>
      {% endif %}"""

new_sponsor_html = """      {% if competition.sponsors %}
      <div class="sponsor-bar">
        {% for s in competition.sponsors %}
          {% if s is mapping %}
        <a href="{{ s.link }}" target="_blank" rel="noopener"><img src="{{ s.logo }}" alt="Sponsor" onerror="this.parentElement.style.display=\'none\'"></a>
          {% else %}
        <img src="{{ s }}" alt="Sponsor" onerror="this.style.display=\'none\'">
          {% endif %}
        {% endfor %}
      </div>
      {% endif %}"""

code = code.replace(old_sponsor_html, new_sponsor_html, 1)
print("[2/4] Updated sponsor display template")

# ── 3. Update admin sponsor management UI ──
old_admin_sponsor = """      <h3 style="color:var(--gold);font-family:Oswald,sans-serif;margin-bottom:16px;">🏆 Sponsor Logos</h3>
      <p style="color:var(--text2);margin-bottom:16px;">Add sponsor logo URLs (max 8). Logos display on the scoreboard.</p>
      <div id="sponsor-list" style="margin-bottom:16px;"></div>
      <div style="display:flex;gap:8px;">
        <input type="text" id="new-sponsor-url" class="search-input" placeholder="Paste logo URL..." style="flex:1;width:auto;">
        <button class="action-btn primary" onclick="addSponsor()">+ Add Logo</button>
      </div>
      <div id="sponsor-preview" style="display:flex;flex-wrap:wrap;gap:16px;margin-top:16px;"></div>"""

new_admin_sponsor = """      <h3 style="color:var(--gold);font-family:Oswald,sans-serif;margin-bottom:16px;">🏆 Sponsor Logos</h3>
      <p style="color:var(--text2);margin-bottom:16px;">Add sponsor logos (max 8). Logos display on the scoreboard and link to sponsor websites.</p>
      <div id="sponsor-list" style="margin-bottom:16px;"></div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        <input type="text" id="new-sponsor-logo" class="search-input" placeholder="Logo image URL..." style="flex:2;min-width:200px;width:auto;">
        <input type="text" id="new-sponsor-link" class="search-input" placeholder="Sponsor website URL..." style="flex:2;min-width:200px;width:auto;">
        <button class="action-btn primary" onclick="addSponsor()">+ Add</button>
      </div>
      <div id="sponsor-preview" style="display:flex;flex-wrap:wrap;gap:16px;margin-top:16px;"></div>"""

code = code.replace(old_admin_sponsor, new_admin_sponsor, 1)
print("[3/4] Updated admin sponsor UI")

# ── 4. Update admin sponsor JavaScript ──
old_admin_js = """var sponsors = [];

function loadSponsors() {
  fetch("/api/admin/competition/" + COMP_ID + "/sponsors")
    .then(function(r) { return r.json(); })
    .then(function(data) { sponsors = data.sponsors || []; renderSponsors(); });
}

function renderSponsors() {
  var list = document.getElementById("sponsor-list");
  var preview = document.getElementById("sponsor-preview");
  if (!sponsors.length) {
    list.innerHTML = "<p style=\\"color:var(--text2);\\">No sponsors added yet.</p>";
    preview.innerHTML = "";
    return;
  }
  var html = "";
  sponsors.forEach(function(url, i) {
    html += "<div style=\\"display:flex;align-items:center;gap:8px;margin-bottom:8px;padding:8px;background:var(--bg);border-radius:4px;\\">";
    html += "<span style=\\"flex:1;color:var(--text);font-size:0.85rem;word-break:break-all;\\">" + url + "</span>";
    html += "<button class=\\"delete-btn\\" onclick=\\"removeSponsor(" + i + ")\\">Remove</button>";
    html += "</div>";
  });
  list.innerHTML = html;
  var phtml = "";
  sponsors.forEach(function(url) {
    phtml += "<img src=\\"" + url + "\\" style=\\"max-height:50px;max-width:120px;object-fit:contain;background:#fff;padding:6px;border-radius:4px;\\" onerror=\\"this.style.display=\'none\'\\">";
  });
  preview.innerHTML = phtml;
}

function addSponsor() {
  var url = document.getElementById("new-sponsor-url").value.trim();
  if (!url) return;
  if (sponsors.length >= 8) { alert("Maximum 8 sponsors"); return; }
  sponsors.push(url);
  saveSponsors();
  document.getElementById("new-sponsor-url").value = "";
}

function removeSponsor(index) {
  sponsors.splice(index, 1);
  saveSponsors();
}

function saveSponsors() {
  fetch("/api/admin/competition/" + COMP_ID + "/sponsors", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({sponsors: sponsors})
  }).then(function(r) { return r.json(); })
    .then(function(data) {
    if (data.ok) { renderSponsors(); showMessage("Sponsors saved"); }
  });
}

loadSponsors();"""

new_admin_js = """var sponsors = [];

function loadSponsors() {
  fetch("/api/admin/competition/" + COMP_ID + "/sponsors")
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var raw = data.sponsors || [];
      // Migrate old format (plain URL strings) to new format (objects)
      sponsors = raw.map(function(s) {
        if (typeof s === "string") return {logo: s, link: ""};
        return s;
      });
      renderSponsors();
    });
}

function renderSponsors() {
  var list = document.getElementById("sponsor-list");
  var preview = document.getElementById("sponsor-preview");
  if (!sponsors.length) {
    list.innerHTML = "<p style=\\"color:var(--text2);\\">No sponsors added yet.</p>";
    preview.innerHTML = "";
    return;
  }
  var html = "";
  sponsors.forEach(function(s, i) {
    html += "<div style=\\"display:flex;align-items:center;gap:8px;margin-bottom:8px;padding:8px;background:var(--bg);border-radius:4px;flex-wrap:wrap;\\">";
    html += "<img src=\\"" + s.logo + "\\" style=\\"max-height:32px;max-width:80px;object-fit:contain;background:#fff;padding:4px;border-radius:3px;\\" onerror=\\"this.style.display=\'none\'\\">";
    html += "<span style=\\"flex:1;color:var(--text);font-size:0.85rem;word-break:break-all;min-width:150px;\\">" + s.logo + "</span>";
    if (s.link) html += "<a href=\\"" + s.link + "\\" target=\\"_blank\\" style=\\"color:var(--blue);font-size:0.8rem;\\">Link ↗</a>";
    html += "<button class=\\"delete-btn\\" onclick=\\"removeSponsor(" + i + ")\\">Remove</button>";
    html += "</div>";
  });
  list.innerHTML = html;
  var phtml = "";
  sponsors.forEach(function(s) {
    if (s.link) {
      phtml += "<a href=\\"" + s.link + "\\" target=\\"_blank\\" style=\\"display:inline-block;\\"><img src=\\"" + s.logo + "\\" style=\\"max-height:50px;max-width:120px;object-fit:contain;background:#fff;padding:6px;border-radius:4px;\\" onerror=\\"this.parentElement.style.display=\'none\'\\"></a>";
    } else {
      phtml += "<img src=\\"" + s.logo + "\\" style=\\"max-height:50px;max-width:120px;object-fit:contain;background:#fff;padding:6px;border-radius:4px;\\" onerror=\\"this.style.display=\'none\'\\">";
    }
  });
  preview.innerHTML = phtml;
}

function addSponsor() {
  var logo = document.getElementById("new-sponsor-logo").value.trim();
  var link = document.getElementById("new-sponsor-link").value.trim();
  if (!logo) return;
  if (sponsors.length >= 8) { alert("Maximum 8 sponsors"); return; }
  sponsors.push({logo: logo, link: link});
  saveSponsors();
  document.getElementById("new-sponsor-logo").value = "";
  document.getElementById("new-sponsor-link").value = "";
}

function removeSponsor(index) {
  sponsors.splice(index, 1);
  saveSponsors();
}

function saveSponsors() {
  fetch("/api/admin/competition/" + COMP_ID + "/sponsors", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({sponsors: sponsors})
  }).then(function(r) { return r.json(); })
    .then(function(data) {
    if (data.ok) { renderSponsors(); showMessage("Sponsors saved"); }
  });
}

loadSponsors();"""

code = code.replace(old_admin_js, new_admin_js, 1)
print("[4/4] Updated admin sponsor JavaScript")

# ── Write the patched file ──
with open(APP_FILE, 'w') as f:
    f.write(code)

print("\nDone! Restart the app: sudo systemctl restart smscores")
