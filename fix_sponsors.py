#!/usr/bin/env python3
"""Fix admin JS escaping bug and update sponsor management."""
import shutil, sys

APP = '/opt/smscores/app.py'

# Backup first
shutil.copy2(APP, APP + '.pre_fix')
print('Backed up to app.py.pre_fix')

with open(APP) as f:
    lines = f.readlines()

# ── Step 1: Find admin <script> section ──
admin_start = admin_end = None
for i, line in enumerate(lines):
    if 'var COMP_ID = {{ competition.id }};' in line:
        admin_start = i - 1  # <script> tag is one line before
    if admin_start and i > admin_start and '</script>' in line:
        admin_end = i
        break

if not admin_start or not admin_end:
    print('ERROR: Could not find admin script section')
    sys.exit(1)

print(f'Found admin script: lines {admin_start+1}-{admin_end+1}')

# ── Step 2: Fix ALL \" to \\" in admin JS ──
# In the file, \" (2 chars) needs to be \\" (3 chars)
# so Python renders it as \" which is valid JS escaping
fix_count = 0
for i in range(admin_start, admin_end + 1):
    old = lines[i]
    # Replace \" with \\" but avoid double-fixing existing \\"
    # First protect any existing \\" by using a placeholder
    lines[i] = lines[i].replace('\\\\"', '\x00PLACEHOLDER\x00')
    lines[i] = lines[i].replace('\\"', '\\\\"')
    lines[i] = lines[i].replace('\x00PLACEHOLDER\x00', '\\\\"')
    if lines[i] != old:
        fix_count += 1

print(f'Fixed escaping on {fix_count} lines')

# ── Step 3: Replace sponsor JS functions ──
# Find the section from "var sponsors = [];" to "loadSponsors();"
sjs_start = sjs_end = None
for i in range(admin_start, admin_end + 1):
    if 'var sponsors = [];' in lines[i]:
        sjs_start = i
    if sjs_start and 'loadSponsors();' in lines[i] and i > sjs_start:
        sjs_end = i
        break

if sjs_start and sjs_end:
    new_js = '''var sponsors = [];

function loadSponsors() {
  fetch("/api/admin/competition/" + COMP_ID + "/sponsors")
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var raw = data.sponsors || [];
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
    list.innerHTML = '<p style=\\\\"color:var(--text2);\\\\">No sponsors added yet.</p>';
    preview.innerHTML = "";
    return;
  }
  var html = "";
  sponsors.forEach(function(s, i) {
    html += '<div style=\\\\"display:flex;align-items:center;gap:8px;margin-bottom:8px;padding:8px;background:var(--bg);border-radius:4px;flex-wrap:wrap;\\\\">';
    html += '<img src=\\\\"' + s.logo + '\\\\" style=\\\\"max-height:32px;max-width:80px;object-fit:contain;background:#fff;padding:4px;border-radius:3px;\\\\" onerror=\\\\"this.style.display=\\'none\\'\\\\">';
    html += '<span style=\\\\"flex:1;color:var(--text);font-size:0.85rem;word-break:break-all;min-width:150px;\\\\">' + s.logo + '</span>';
    if (s.link) html += '<a href=\\\\"' + s.link + '\\\\" target=\\\\"_blank\\\\" style=\\\\"color:var(--blue);font-size:0.8rem;\\\\">Link \\u2197</a>';
    html += '<button class=\\\\"delete-btn\\\\" onclick=\\\\"removeSponsor(' + i + ')\\\\">Remove</button>';
    html += '</div>';
  });
  list.innerHTML = html;
  var phtml = "";
  sponsors.forEach(function(s) {
    if (s.link) {
      phtml += '<a href=\\\\"' + s.link + '\\\\" target=\\\\"_blank\\\\" style=\\\\"display:inline-block;\\\\"><img src=\\\\"' + s.logo + '\\\\" style=\\\\"max-height:50px;max-width:120px;object-fit:contain;background:#fff;padding:6px;border-radius:4px;\\\\" onerror=\\\\"this.parentElement.style.display=\\'none\\'\\\\"></a>';
    } else {
      phtml += '<img src=\\\\"' + s.logo + '\\\\" style=\\\\"max-height:50px;max-width:120px;object-fit:contain;background:#fff;padding:6px;border-radius:4px;\\\\" onerror=\\\\"this.style.display=\\'none\\'\\\\">';
    }
  });
  preview.innerHTML = phtml;
}

function addSponsor() {
  var logo = document.getElementById("new-sponsor-logo").value.trim();
  var link = document.getElementById("new-sponsor-link").value.trim();
  if (!logo) { alert("Enter a logo URL"); return; }
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
  })
  .then(function(r) { return r.json(); })
  .then(function(data) {
    if (data.ok) { renderSponsors(); showMessage("Sponsors saved"); }
    else { showMessage(data.error || "Save failed", true); }
  });
}

loadSponsors();
'''
    # Replace the section
    lines[sjs_start:sjs_end+1] = [new_js]
    print(f'Replaced sponsor JS (was lines {sjs_start+1}-{sjs_end+1})')
else:
    print('WARNING: Could not find sponsor JS section')

# ── Step 4: Replace sponsor admin HTML ──
# Find the sponsor settings section
sh_start = sh_end = None
for i, line in enumerate(lines):
    if 'Sponsor Logos</h3>' in line:
        sh_start = i
    if sh_start and 'sponsor-preview' in line and i > sh_start:
        sh_end = i
        break

if sh_start and sh_end:
    new_html = '''      <h3 style="color:var(--gold);font-family:Oswald,sans-serif;margin-bottom:16px;">🏆 Sponsor Logos</h3>
      <p style="color:var(--text2);margin-bottom:16px;">Add sponsor logos (max 8). Click logo to visit sponsor website.</p>
      <div id="sponsor-list" style="margin-bottom:16px;"></div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        <input type="text" id="new-sponsor-logo" class="search-input" placeholder="Logo image URL..." style="flex:2;min-width:200px;width:auto;">
        <input type="text" id="new-sponsor-link" class="search-input" placeholder="Sponsor website URL..." style="flex:2;min-width:200px;width:auto;">
        <button class="action-btn primary" onclick="addSponsor()">+ Add</button>
      </div>
      <div id="sponsor-preview" style="display:flex;flex-wrap:wrap;gap:16px;margin-top:16px;"></div>
'''
    lines[sh_start:sh_end+1] = [new_html]
    print(f'Replaced sponsor admin HTML (was lines {sh_start+1}-{sh_end+1})')
else:
    print('WARNING: Could not find sponsor HTML section')

# ── Write back ──
with open(APP, 'w') as f:
    f.writelines(lines)

print('\\nDone! Restart: sudo systemctl restart smscores')
