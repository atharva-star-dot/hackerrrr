import re

def test_parse_log(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    trace_map = {}
    parsed_lines = []
    for line in lines:
        line = line.strip()
        if not line: continue
        kv = {}
        for m in re.finditer(r'(\w+)=("(?:[^"\\]|\\.)*"|[^\s]+)', line):
            k, v = m.group(1), m.group(2).strip('"')
            if v != 'null': kv[k] = v
        trace_id = kv.get('trace_id')
        if trace_id:
            if trace_id not in trace_map: trace_map[trace_id] = {}
            for k in ['lookup_key', 'match_key', 'subject_key', 'correlation_key', 'matched_value', 'subject_ref']:
                if k in kv and kv[k]:
                    trace_map[trace_id][k] = kv[k]
        parsed_lines.append(kv)

    # Correlate
    results = []
    for kv in parsed_lines:
        rid = kv.get('resource_id')
        if not rid: continue
        trace_id = kv.get('trace_id')
        if trace_id and trace_id in trace_map:
            for k, v in trace_map[trace_id].items():
                if k not in kv: kv[k] = v
        email = kv.get('email') or kv.get('customer_email') or kv.get('correlation_key') or kv.get('matched_value') or kv.get('subject_key') or kv.get('match_key')
        ref = kv.get('customer_reference') or kv.get('subject_reference') or kv.get('subject_ref')
        if email or ref:
            results.append((rid, kv.get('event'), email, ref))
    return results

res = test_parse_log('dataset/evidence/logs/service_events_ap_south_20260915.log')
print(f"Extracted {len(res)} linked resource records from evidence_01")
for r in res[:10]:
    print(" ", r)
