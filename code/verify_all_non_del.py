import csv

non_del_keywords = [
    'download', 'portable format', 'copy of', 'resetting the login',
    'misspelled', 'correct it without', 'marketing lists only', 'promotional emails',
    'information request', 'still use it', 'leave the account active',
    'leave my profile', 'continue using the service', 'do not close the account'
]

with open('dataset/deletion_requests.csv', 'r', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        txt = row['request_text'].lower()
        matched = [k for k in non_del_keywords if k in txt]
        if matched:
            print(f"{row['case_id']}: matched {matched}")
