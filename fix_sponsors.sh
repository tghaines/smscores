#!/bin/bash
# Fix admin JS escaping and update sponsor management
set -e

APP="/opt/smscores/app.py"
cp "$APP" "${APP}.pre_fix"
echo "Backed up to app.py.pre_fix"

# Step 1: Fix the \" -> \\" escaping bug in ALL admin JS
# The admin <script> starts after "var COMP_ID" and ends at the next </script>
python3 << 'PYEOF'
with open("/opt/smscores/app.py") as f:
    content = f.read()

# Find admin script boundaries
import re
# Find the admin script block containing COMP_ID
pattern = r'(<script>\nvar COMP_ID = \{\{ competition\.id \}\};)'
match = re.search(r'<script>\s*\nvar COMP_ID', content)
if not match:
    print("ERROR: Could not find admin script")
    exit(1)

start = match.start()
end = content.find('</script>', start)
if end == -1:
    print("ERROR: Could not find admin </script>")
    exit(1)
end += len('</script>')

admin_js = content[start:end]
# Fix: replace \" with \\" (but not already-correct \\")
# Use a two-pass approach
admin_js_fixed = admin_js.replace('\\\\"', '\x00SAFE\x00')  # protect existing
admin_js_fixed = admin_js_fixed.replace('\\"', '\\\\"')       # fix broken ones
admin_js_fixed = admin_js_fixed.replace('\x00SAFE\x00', '\\\\"')  # restore

content = content[:start] + admin_js_fixed + content[end:]

with open("/opt/smscores/app.py", "w") as f:
    f.write(content)
print("Fixed admin JS escaping")
PYEOF

# Step 2: Write the new sponsor JS to a temp file (heredoc = exact content)
cat > /tmp/new_sponsor_js.txt << 'SPONSORJS'
var sponsors = [];

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
    list.innerHTML = "<p style=\\"color:var(--text2);\\">No sponsors added yet.</p>";
    preview.innerHTML = "";
    return;
  }
  var html = "";
  sponsors.forEach(function(s, i) {
    html += "<div style=\\"display:flex;align-items:center;gap:8px;margin-bottom:8px;padding:8px;background:var(--bg);border-radius:4px;flex-wrap:wrap;\\">";
    html += "<img src=\\"" + s.logo + "\\" style=\\"max-height:32px;max-width:80px;object-fit:contain;background:#fff;padding:4px;border-radius:3px;\\" onerror=\\"this.style.display=\\'none\\'\\">";
    html += "<span style=\\"flex:1;color:var(--text);font-size:0.85rem;word-break:break-all;min-width:150px;\\">" + s.logo + "</span>";
    if (s.link) html += "<a href=\\"" + s.link + "\\" target=\\"_blank\\" style=\\"color:var(--blue);font-size:0.8rem;\\">Link &#8599;</a>";
    html += "<button class=\\"delete-btn\\" onclick=\\"removeSponsor(" + i + ")\\">Remove</button>";
    html += "</div>";
  });
  list.innerHTML = html;
  var phtml = "";
  sponsors.forEach(function(s) {
    if (s.link) {
      phtml += "<a href=\\"" + s.link + "\\" target=\\"_blank\\" style=\\"display:inline-block;\\"><img src=\\"" + s.logo + "\\" style=\\"max-height:50px;max-width:120px;object-fit:contain;background:#fff;padding:6px;border-radius:4px;\\" onerror=\\"this.parentElement.style.display=\\'none\\'\\"></a>";
    } else {
      phtml += "<img src=\\"" + s.logo + "\\" style=\\"max-height:50px;max-width:120px;object-fit:contain;background:#fff;padding:6px;border-radius:4px;\\" onerror=\\"this.style.display=\\'none\\'\\">";
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
SPONSORJS

# Step 3: Write the new sponsor admin HTML
cat > /tmp/new_sponsor_html.txt << 'SPONSORHTML'
      <h3 style="color:var(--gold);font-family:Oswald,sans-serif;margin-bottom:16px;">🏆 Sponsor Logos</h3>
      <p style="color:var(--text2);margin-bottom:16px;">Add sponsor logos (max 8). Click logo to visit sponsor website.</p>
      <div id="sponsor-list" style="margin-bottom:16px;"></div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        <input type="text" id="new-sponsor-logo" class="search-input" placeholder="Logo image URL..." style="flex:2;min-width:200px;width:auto;">
        <input type="text" id="new-sponsor-link" class="search-input" placeholder="Sponsor website URL..." style="flex:2;min-width:200px;width:auto;">
        <button class="action-btn primary" onclick="addSponsor()">+ Add</button>
      </div>
      <div id="sponsor-preview" style="display:flex;flex-wrap:wrap;gap:16px;margin-top:16px;"></div>
SPONSORHTML

# Step 4: Splice in the new content using Python
python3 << 'PYEOF2'
with open("/opt/smscores/app.py") as f:
    lines = f.readlines()

# Replace sponsor JS section
with open("/tmp/new_sponsor_js.txt") as f:
    new_js = f.read()

sjs_start = sjs_end = None
for i, line in enumerate(lines):
    if 'var sponsors = [];' in line:
        sjs_start = i
    if sjs_start and 'loadSponsors();' in line and i > sjs_start:
        sjs_end = i
        break

if sjs_start and sjs_end:
    lines[sjs_start:sjs_end+1] = [new_js]
    print(f"Replaced sponsor JS (lines {sjs_start+1}-{sjs_end+1})")
else:
    print("WARNING: Could not find sponsor JS section")

# Replace sponsor HTML section
with open("/tmp/new_sponsor_html.txt") as f:
    new_html = f.read()

sh_start = sh_end = None
for i, line in enumerate(lines):
    if 'Sponsor Logos</h3>' in line:
        sh_start = i
    if sh_start and 'sponsor-preview' in line and i > sh_start:
        sh_end = i
        break

if sh_start and sh_end:
    lines[sh_start:sh_end+1] = [new_html]
    print(f"Replaced sponsor HTML (lines {sh_start+1}-{sh_end+1})")
else:
    print("WARNING: Could not find sponsor HTML section")

with open("/opt/smscores/app.py", "w") as f:
    f.writelines(lines)

print("All replacements done")
PYEOF2

echo ""
echo "Done! Restarting service..."
sudo systemctl restart smscores
echo "Service restarted. Test the admin page now."
