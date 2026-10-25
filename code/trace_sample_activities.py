import csv
import json

# Check activity for case_01 to case_10
samples = {}
with open('dataset/sample_deletion_requests.csv', 'r', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        samples[row['case_id']] = row

activities = []
with open('dataset/system_activity.csv', 'r', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        activities.append(row)

for cid in ['case_01', 'case_02', 'case_03', 'case_04', 'case_05', 'case_06', 'case_07', 'case_08', 'case_09', 'case_10']:
    s = samples[cid]
    req_time = s['requested_at']
    rep_time = s['reported_at']
    # Look for activities between req_time and rep_time
    matches = [a for a in activities if req_time <= a['event_time'] <= rep_time]
    print(f"=== {cid} ({s['email']}): req={req_time} rep={rep_time} ===")
    for m in matches:
        if any(w in m['resource_id'] for w in ['account', 'search', 'support', 'export', 'backup']):
            print(f"  {m['activity_id']} {m['event_time']} {m['event_type']} {m['target_system']} {m['resource_id']} {m['reported_result']}")
