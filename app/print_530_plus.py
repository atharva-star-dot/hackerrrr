import csv
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('dataset/deletion_requests.csv', 'r', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        cid_num = int(row['case_id'].split('_')[1])
        if cid_num >= 530:
            print(f"{row['case_id']}: {row['email']}: {row['request_text']}")
