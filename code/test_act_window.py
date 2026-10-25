import csv
import re

# Test finding account_id from activity
activities = []
with open('dataset/system_activity.csv', 'r', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        if row['target_system'] == 'account_service' and row['event_type'] == 'DELETE_RECORD':
            activities.append(row)

samples = []
with open('dataset/sample_deletion_requests.csv', 'r', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        samples.append(row)

for s in samples[:10]:
    cid = s['case_id']
    req_t = s['requested_at']
    rep_t = s['reported_at']
    # find activities in window
    window_acts = [a['resource_id'] for a in activities if req_t <= a['event_time'] <= rep_t]
    print(f"{cid}: req={req_t} rep={rep_t} acts={window_acts}")
