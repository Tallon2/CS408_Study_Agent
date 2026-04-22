import json

with open('storage/knowledge_base/exam_questions.jsonl', encoding='utf-8') as f:
    questions = [json.loads(l) for l in f if l.strip()]

target_years = [2011, 2021, 2022, 2024, 2025]
year_filter = int(__import__('sys').argv[1]) if len(__import__('sys').argv) > 1 else 0

for q in questions:
    if q['year'] not in target_years:
        continue
    if year_filter and q['year'] != year_filter:
        continue
    print(f"\n=== {q['year']}-Q{q['number']:02d} [{q.get('subject','')}] A={q['answer']} ===")
    print(f"Topic: {q.get('topic','')}")
    print(f"Q: {q['question'][:200]}")
    opts = q.get('options', {})
    for k in ['A','B','C','D']:
        if k in opts:
            print(f"  {k}: {opts[k][:100]}")
    print(f"EXP: {q.get('explanation','')[:150]}")
