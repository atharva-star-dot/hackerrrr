import csv
import sys
sys.stdout.reconfigure(encoding='utf-8')

non_del_phrases = [
    'leave the account active', 'keep the account', 'continue using',
    'leave my profile', 'keep my account', 'portable format', 'copy of',
    'replace it with the new one', 'change the email address', 'out of date'
]

with open('dataset/deletion_requests.csv', 'r', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        txt = row['request_text'].lower()
        if any(p in txt for p in non_del_phrases):
            print(f"{row['case_id']}: {row['email']}: {row['request_text']}")
