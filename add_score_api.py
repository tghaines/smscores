#!/usr/bin/env python3
with open('/opt/smscores/app.py', 'r') as f:
    content = f.read()

# Add the update score API endpoint after the add score endpoint
old_api = '''@app.route('/api/admin/competition/<int:comp_id>/score/delete', methods=['POST'])
def api_delete_score(comp_id):'''

new_api = '''@app.route('/api/admin/competition/<int:comp_id>/score/update', methods=['POST'])
def api_update_score(comp_id):
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json()
    shooter_name = data.get('name', '').strip()
    match_name = data.get('match', '').strip()
    shots = data.get('shots', '').strip()
    if not shooter_name or not match_name:
        return jsonify({'error': 'Name and match required'}), 400
    # Calculate score from shots
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
    latest = Score.query.filter_by(competition_id=comp_id).order_by(Score.created_at.desc()).first()
    if not latest or not latest.data:
        return jsonify({'error': 'No scores found'}), 404
    for shooter in latest.data:
        if shooter.get('name') == shooter_name:
            for m in shooter.get('matches', []):
                if m.get('match') == match_name:
                    # Update totals
                    old_score = m.get('score', 0)
                    old_x = m.get('xCount', 0)
                    shooter['total'] = shooter.get('total', 0) - old_score + score
                    shooter['vCount'] = shooter.get('vCount', 0) - old_x + x_count
                    # Update the match
                    m['shots'] = shots
                    m['score'] = score
                    m['xCount'] = x_count
                    break
            break
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(latest, 'data')
    db.session.commit()
    return jsonify({'success': True, 'message': 'Score updated'})

@app.route('/api/admin/competition/<int:comp_id>/score/delete', methods=['POST'])
def api_delete_score(comp_id):'''

content = content.replace(old_api, new_api)

with open('/opt/smscores/app.py', 'w') as f:
    f.write(content)

print("Score update API endpoint added!")
