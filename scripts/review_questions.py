
import json

with open('storage/knowledge_base/exam_questions.jsonl', encoding='utf-8') as f:
    questions = [json.loads(l) for l in f if l.strip()]

target_years = [2011, 2021, 2022, 2024, 2025]
target = [(i, q) for i, q in enumerate(questions) if q['year'] in target_years]
print(f'Target questions: {len(target)}')

for i, q in target:
    exp = q.get('explanation', '')
    topic = q.get('topic', '')
    print(f"{q['year']}-Q{q['number']:02d} [{q['subject'][:8]}] A={q['answer']} exp={len(exp):3d} | {topic[:30]}")
