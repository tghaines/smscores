#!/usr/bin/env python3
with open('/opt/smscores/app.py', 'r') as f:
    content = f.read()

# 1. Add Edit button next to Delete in the scores table
old_score_btn = '''html += '<td><button class="delete-btn" data-name="' + shooter.name + '" data-match="' + m.match + '">Delete</button></td>';'''
new_score_btn = '''html += '<td><button class="edit-btn" data-name="' + shooter.name + '" data-match="' + m.match + '" data-shots="' + (m.shots || '') + '">Edit</button> <button class="delete-btn" data-name="' + shooter.name + '" data-match="' + m.match + '">Delete</button></td>';'''

content = content.replace(old_score_btn, new_score_btn)

# 2. Add event listener for edit buttons in renderScores function
old_render_scores_end = '''  tbody.querySelectorAll('.delete-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      if (confirm('Delete score?')) deleteScore(btn.dataset.name, btn.dataset.match);
    });
  });
}

function renderMatches()'''

new_render_scores_end = '''  tbody.querySelectorAll('.delete-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      if (confirm('Delete score?')) deleteScore(btn.dataset.name, btn.dataset.match);
    });
  });
  tbody.querySelectorAll('.edit-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      showEditScore(btn.dataset.name, btn.dataset.match, btn.dataset.shots);
    });
  });
}

function showEditScore(name, match, shots) {
  document.getElementById('edit-score-name').value = name;
  document.getElementById('edit-score-match').value = match;
  document.getElementById('edit-score-shots').value = shots || '';
  renderEditShots(shots || '');
  document.getElementById('modal-edit-score').classList.add('active');
}

function renderEditShots(shotsStr) {
  var container = document.getElementById('edit-shots-container');
  var shots = shotsStr ? shotsStr.split(',') : [];
  var html = '';
  shots.forEach(function(s, i) {
    html += '<div class="shot-edit-row">';
    html += '<span class="shot-num">' + (i + 1) + '</span>';
    html += '<input type="text" class="shot-input" value="' + s.trim() + '" maxlength="1">';
    html += '<button type="button" class="shot-remove" data-idx="' + i + '">x</button>';
    html += '</div>';
  });
  html += '<button type="button" class="action-btn" id="btn-add-shot" style="margin-top:8px;">+ Add Shot</button>';
  container.innerHTML = html;
  
  container.querySelectorAll('.shot-remove').forEach(function(btn) {
    btn.addEventListener('click', function() {
      var currentShots = getEditShots();
      currentShots.splice(parseInt(btn.dataset.idx), 1);
      document.getElementById('edit-score-shots').value = currentShots.join(',');
      renderEditShots(currentShots.join(','));
    });
  });
  
  document.getElementById('btn-add-shot').addEventListener('click', function() {
    var currentShots = getEditShots();
    currentShots.push('6');
    document.getElementById('edit-score-shots').value = currentShots.join(',');
    renderEditShots(currentShots.join(','));
  });
  
  container.querySelectorAll('.shot-input').forEach(function(inp) {
    inp.addEventListener('change', function() {
      document.getElementById('edit-score-shots').value = getEditShots().join(',');
    });
  });
}

function getEditShots() {
  var inputs = document.querySelectorAll('#edit-shots-container .shot-input');
  var shots = [];
  inputs.forEach(function(inp) { shots.push(inp.value.trim().toUpperCase()); });
  return shots;
}

function updateScore() {
  var name = document.getElementById('edit-score-name').value;
  var match = document.getElementById('edit-score-match').value;
  var shots = getEditShots().join(',');
  fetch('/api/admin/competition/' + COMP_ID + '/score/update', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ name: name, match: match, shots: shots })
  }).then(function(r) { return r.json(); }).then(function(result) {
    if (result.success) { showMessage(result.message); document.getElementById('modal-edit-score').classList.remove('active'); loadScores(); }
    else showMessage(result.error, true);
  });
}

function renderMatches()'''

content = content.replace(old_render_scores_end, new_render_scores_end)

# 3. Add the edit score modal HTML (after the add score modal)
old_modal_end = '''<script>
var COMP_ID'''

new_modal_end = '''<div class="modal" id="modal-edit-score">
  <div class="modal-content" style="min-width:450px;">
    <div class="modal-header"><h2>Edit Score</h2><button class="modal-close" data-close="modal-edit-score">x</button></div>
    <input type="hidden" id="edit-score-name">
    <input type="hidden" id="edit-score-match">
    <input type="hidden" id="edit-score-shots">
    <div class="form-row">
      <div class="form-group"><label>Shooter</label><div id="edit-score-name-display" style="padding:8px 0;font-family:Oswald,sans-serif;"></div></div>
      <div class="form-group"><label>Match</label><div id="edit-score-match-display" style="padding:8px 0;"></div></div>
    </div>
    <div class="form-group" style="margin-top:12px;">
      <label>Shots (click to edit, x to remove)</label>
      <div id="edit-shots-container" style="display:flex;flex-wrap:wrap;gap:8px;margin-top:8px;"></div>
    </div>
    <div class="form-row" style="margin-top:20px;"><button class="action-btn primary" id="btn-update-score">Save Changes</button></div>
  </div>
</div>
<style>
.shot-edit-row { display:flex; align-items:center; gap:4px; background:var(--bg); padding:4px 8px; border-radius:4px; border:1px solid var(--border); }
.shot-num { font-family:JetBrains Mono,monospace; font-size:0.75rem; color:var(--text2); width:20px; }
.shot-input { width:30px; text-align:center; padding:4px; background:var(--bg2); border:1px solid var(--border); color:var(--gold); font-family:JetBrains Mono,monospace; font-weight:bold; border-radius:3px; text-transform:uppercase; }
.shot-input:focus { outline:none; border-color:var(--gold); }
.shot-remove { background:var(--red); color:white; border:none; width:18px; height:18px; border-radius:50%; cursor:pointer; font-size:0.7rem; }
.shot-remove:hover { opacity:0.8; }
</style>
<script>
var COMP_ID'''

content = content.replace(old_modal_end, new_modal_end)

# 4. Add event listener for modal close and update button
old_modal_close = '''document.querySelectorAll('.modal-close').forEach(function(btn) {
  btn.addEventListener('click', function() {
    document.getElementById(btn.dataset.close).classList.remove('active');
  });
});'''

new_modal_close = '''document.querySelectorAll('.modal-close').forEach(function(btn) {
  btn.addEventListener('click', function() {
    document.getElementById(btn.dataset.close).classList.remove('active');
  });
});

document.getElementById('btn-update-score').addEventListener('click', updateScore);'''

content = content.replace(old_modal_close, new_modal_close)

# 5. Fix showEditScore to also display name/match
old_show_edit = '''function showEditScore(name, match, shots) {
  document.getElementById('edit-score-name').value = name;
  document.getElementById('edit-score-match').value = match;
  document.getElementById('edit-score-shots').value = shots || '';
  renderEditShots(shots || '');
  document.getElementById('modal-edit-score').classList.add('active');
}'''

new_show_edit = '''function showEditScore(name, match, shots) {
  document.getElementById('edit-score-name').value = name;
  document.getElementById('edit-score-match').value = match;
  document.getElementById('edit-score-shots').value = shots || '';
  document.getElementById('edit-score-name-display').textContent = name;
  document.getElementById('edit-score-match-display').textContent = match;
  renderEditShots(shots || '');
  document.getElementById('modal-edit-score').classList.add('active');
}'''

content = content.replace(old_show_edit, new_show_edit)

with open('/opt/smscores/app.py', 'w') as f:
    f.write(content)

print("Edit score UI added!")
