import csv
import sys
sys.stdout.reconfigure(encoding='utf-8')

deletion_keywords = [
    'delet', 'eras', 'close', 'remov', 'supprim', 'elimin', 'apag',
    'exclusão', 'exclusao', '삭제', '削除'
]

with open('dataset/deletion_requests.csv', 'r', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        txt = row['request_text'].lower()
        if not any(k in txt for k in deletion_keywords):
            print(f"{row['case_id']}: {row['email']}: {row['request_text']}")
