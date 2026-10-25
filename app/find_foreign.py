import csv
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('dataset/deletion_requests.csv', 'r', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        txt = row['request_text']
        # check if contains non-ascii or typical foreign words
        words = txt.split()
        foreign = False
        for w in words:
            if any(ord(c) > 127 for c in w) or w.lower() in ['por', 'favor', 'je', 'vous', 'prie', 'de', 'supprimer', 'desejo', 'apagar', 'cuenta', 'eliminar']:
                foreign = True
                break
        if foreign:
            print(f"{row['case_id']}: {txt[:80]}")
