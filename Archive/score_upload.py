
@app.route('/<comp_route>/upload-scores', methods=['GET', 'POST'])
def upload_scores(comp_route):
    """Upload JSON scores for a competition"""
    comp = Competition.query.filter_by(route=comp_route).first()
    if not comp:
        return "Competition not found", 404
    
    if request.method == 'GET':
        return render_template_string(SCORE_UPLOAD_HTML, competition=comp)
    
    # POST - process JSON
    try:
        if 'file' in request.files:
            file = request.files['file']
            raw_data = json.loads(file.read().decode('utf-8'))
        else:
            raw_data = request.get_json()
        
        if not raw_data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Convert from upload format to internal format
        # Group by user
        shooter_map = {}
        for entry in raw_data:
            name = entry.get('user') or entry.get('name', 'Unknown')
            match = entry.get('match', '')
            shots = entry.get('shots', '')
            total_str = str(entry.get('total', '0-0X'))
            
            # Parse total like "57-1X" or "60-10X"
            import re
            m = re.match(r'(\d+)-(\d+)X?', total_str)
            if m:
                score = int(m.group(1))
                x_count = int(m.group(2))
            else:
                # Try to calculate from shots
                score = 0
                x_count = 0
                for s in shots.split(','):
                    s = s.strip().upper()
                    if s == 'X':
                        score += 6
                        x_count += 1
                    elif s == 'V':
                        score += 5
                        x_count += 1
                    elif s.isdigit():
                        score += int(s)
            
            if name not in shooter_map:
                shooter_map[name] = {'name': name, 'class': '', 'matches': [], 'total': 0, 'vCount': 0}
            
            shooter_map[name]['matches'].append({
                'match': match,
                'shots': shots,
                'score': score,
                'xCount': x_count
            })
            shooter_map[name]['total'] += score
            shooter_map[name]['vCount'] += x_count
        
        # Convert to list
        score_data = list(shooter_map.values())
        
        # Save to database
        new_score = Score(competition_id=comp.id, data=score_data)
        db.session.add(new_score)
        db.session.commit()
        
        return jsonify({'success': True, 'shooters': len(score_data), 'message': f'Loaded {len(score_data)} shooters'})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 400

SCORE_UPLOAD_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Upload Scores - {{ competition.name }}</title>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&family=Barlow+Condensed:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root { --bg:#0c1e2b; --bg2:#122a3a; --gold:#f4c566; --green:#5cc9a7; --text:#f0ece4; --text2:#8ab4c8; --border:#1e3d50; }
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--bg); color:var(--text); font-family:'Barlow Condensed',sans-serif; min-height:100vh; padding:20px; }
.container { max-width:800px; margin:0 auto; }
.header { display:flex; justify-content:space-between; align-items:center; padding:20px 0; border-bottom:1px solid var(--border); margin-bottom:30px; }
.header h1 { font-family:'Oswald',sans-serif; font-size:1.6rem; color:var(--gold); }
.nav-link { color:var(--gold); text-decoration:none; border:1px solid var(--gold); padding:8px 16px; border-radius:4px; }
.nav-link:hover { background:var(--gold); color:var(--bg); }
.upload-box { background:var(--bg2); border:2px dashed var(--border); border-radius:8px; padding:40px; text-align:center; margin-bottom:20px; }
.upload-box.dragover { border-color:var(--gold); background:rgba(244,197,102,0.1); }
.upload-box input[type="file"] { display:none; }
.upload-btn { background:var(--gold); color:var(--bg); border:none; padding:12px 24px; border-radius:4px; font-size:1rem; cursor:pointer; font-family:'Oswald',sans-serif; }
.upload-btn:hover { opacity:0.9; }
.or-text { color:var(--text2); margin:20px 0; text-align:center; }
textarea { width:100%; height:300px; background:var(--bg); border:1px solid var(--border); border-radius:4px; padding:12px; color:var(--text); font-family:'JetBrains Mono',monospace; font-size:0.85rem; resize:vertical; }
textarea:focus { outline:none; border-color:var(--gold); }
.submit-btn { background:var(--green); color:var(--bg); border:none; padding:12px 24px; border-radius:4px; font-size:1rem; cursor:pointer; font-family:'Oswald',sans-serif; margin-top:16px; }
.submit-btn:hover { opacity:0.9; }
.result { margin-top:20px; padding:16px; border-radius:4px; font-family:'JetBrains Mono',monospace; }
.result.success { background:rgba(92,201,167,0.2); border:1px solid var(--green); color:var(--green); }
.result.error { background:rgba(255,100,100,0.2); border:1px solid #ff6464; color:#ff6464; }
.format-help { background:var(--bg2); padding:16px; border-radius:4px; margin-top:30px; font-size:0.9rem; }
.format-help h3 { color:var(--gold); margin-bottom:12px; font-family:'Oswald',sans-serif; }
.format-help pre { background:var(--bg); padding:12px; border-radius:4px; overflow-x:auto; font-size:0.8rem; color:var(--text2); }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>Upload Scores - {{ competition.name }}</h1>
    <a href="/{{ competition.route }}" class="nav-link">← Back to Scoreboard</a>
  </div>
  
  <div class="upload-box" id="dropZone">
    <p style="margin-bottom:16px; color:var(--text2);">Drag & drop a JSON file here</p>
    <label class="upload-btn">
      Choose File
      <input type="file" id="fileInput" accept=".json">
    </label>
  </div>
  
  <div class="or-text">— OR paste JSON below —</div>
  
  <textarea id="jsonInput" placeholder='[{"match":"10+2 1","user":"John Smith","shots":"6,6,5,X,6,5,5,X,6,6","total":"57-2X"}, ...]'></textarea>
  
  <button class="submit-btn" onclick="submitJson()">Upload Scores</button>
  
  <div id="result"></div>
  
  <div class="format-help">
    <h3>Expected JSON Format</h3>
    <pre>[
  {"match":"10+2 1", "user":"John Smith", "shots":"6,6,5,X,6,5,5,X,6,6", "total":"57-2X"},
  {"match":"10+2 2", "user":"John Smith", "shots":"X,X,6,6,6,5,5,5,5,6", "total":"56-2X"},
  ...
]</pre>
    <p style="margin-top:12px; color:var(--text2);">Each row is one match for one shooter. Scores are grouped by user automatically.</p>
  </div>
</div>

<script>
const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const jsonInput = document.getElementById('jsonInput');
const resultDiv = document.getElementById('result');

dropZone.addEventListener('dragover', (e) => {
  e.preventDefault();
  dropZone.classList.add('dragover');
});

dropZone.addEventListener('dragleave', () => {
  dropZone.classList.remove('dragover');
});

dropZone.addEventListener('drop', (e) => {
  e.preventDefault();
  dropZone.classList.remove('dragover');
  const file = e.dataTransfer.files[0];
  if (file) handleFile(file);
});

fileInput.addEventListener('change', (e) => {
  if (e.target.files[0]) handleFile(e.target.files[0]);
});

function handleFile(file) {
  const reader = new FileReader();
  reader.onload = (e) => {
    jsonInput.value = e.target.result;
  };
  reader.readAsText(file);
}

async function submitJson() {
  const json = jsonInput.value.trim();
  if (!json) {
    showResult('Please provide JSON data', false);
    return;
  }
  
  try {
    const data = JSON.parse(json);
    const resp = await fetch('/{{ competition.route }}/upload-scores', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(data)
    });
    const result = await resp.json();
    if (result.success) {
      showResult(result.message + ' - <a href="/{{ competition.route }}" style="color:inherit;">View Scoreboard</a>', true);
    } else {
      showResult('Error: ' + result.error, false);
    }
  } catch (e) {
    showResult('Invalid JSON: ' + e.message, false);
  }
}

function showResult(msg, success) {
  resultDiv.innerHTML = msg;
  resultDiv.className = 'result ' + (success ? 'success' : 'error');
}
</script>
</body>
</html>
'''
