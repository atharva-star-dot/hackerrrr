import csv

with open('dataset/deletion_requests.csv', 'r', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        txt = row['request_text'].lower()
        if any(w in txt for w in ['access', 'export', 'download', 'copy', 'portability', 'opt out', 'newsletter', 'correct']):
            if not any(w in txt for w in ['delet', 'eras', 'close', 'remov', 'supprim', 'eliminar', 'apagar']):
                print(f"{row['case_id']}: {row['email']}: {row['request_text']}")
