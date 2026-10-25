import sys
sys.path.insert(0, '.')
import csv
from code.agent import DeletionAuditAgent
from code.usage import UsageLogger

agent = DeletionAuditAgent('dataset', UsageLogger())

with open('dataset/sample_deletion_requests.csv', 'r', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        if row['case_id'] in ('case_03', 'case_26'):
            txt = row['request_text'].lower()
            try:
                prompt = agent.llm.chat([
                    {"role": "system", "content": "hi"},
                    {"role": "user", "content": row['request_text']}
                ])
                print('LLM worked:', prompt)
            except Exception as e:
                print('LLM exception:', type(e), e)
                del_keywords = [
                    'delete', 'delet', 'eras', 'close', 'remov', 'supprim', 'elimin', 'apag',
                    'exclusão', 'exclusao', '삭제', '削除'
                ]
                print('Matched del_keywords:', [k for k in del_keywords if k in txt])
