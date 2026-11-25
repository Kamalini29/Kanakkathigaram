"""Audit the Kanakkathigaram release v3 and recompute the counts reported in the paper.

Usage:  python audit_release.py [release_dir]
Checks: row counts, unique and paired uids, SHA-256 checksums (SHA256SUMS.txt).
Prints: release totals and the script-conformity table (Table 5 of the paper).
Writes: script_profile.csv (one row per problem).
"""
import csv, hashlib, json, os, re, sys

D = sys.argv[1] if len(sys.argv) > 1 else '.'
FILES = {
    'tamil': 'kanakkathigaram_tamil_problems_v3.jsonl',
    'english': 'kanakkathigaram_english_problems_v3.jsonl',
    'glossary': 'kanakkathigaram_alavai_glossary_v3.jsonl',
    'fractions': 'kanakkathigaram_pinna_ilakkam_fractions_v3.jsonl',
    'chains': 'kanakkathigaram_reasoning_chains_v3.jsonl',
    'persona': 'kanakkathigaram_persona_note_LLM_WRITTEN_not_benchmark_v3.jsonl',
}
EXPECTED = {'tamil': 207, 'english': 207, 'glossary': 155, 'fractions': 35, 'chains': 53, 'persona': 89}
load = lambda f: [json.loads(l) for l in open(os.path.join(D, f), encoding='utf-8') if l.strip()]
data = {k: load(f) for k, f in FILES.items()}
ok = True

def check(cond, msg):
    global ok
    print(('PASS ' if cond else 'FAIL ') + msg)
    ok &= cond

for k, rows in data.items():
    check(len(rows) == EXPECTED[k], f'{FILES[k]}: {len(rows)} rows (expected {EXPECTED[k]})')
    uids = [r['uid'] for r in rows]
    check(len(uids) == len(set(uids)), f'{FILES[k]}: uids unique')
check({r['uid'] for r in data['tamil']} == {r['uid'] for r in data['english']}, 'Tamil and English views pair on uid')

sums = os.path.join(D, 'SHA256SUMS.txt')
if os.path.exists(sums):
    for line in open(sums, encoding='utf-8'):
        if not line.strip():
            continue
        h, name = line.split(maxsplit=1); name = name.strip().lstrip('*')
        path = os.path.join(D, name)
        if os.path.exists(path):
            check(hashlib.sha256(open(path, 'rb').read()).hexdigest() == h, f'sha256 {name}')
        else:
            print('SKIP sha256', name, '(file not present)')

rows_total = sum(len(v) for v in data.values())
print(f'\nTotals: {rows_total} rows, {rows_total - 207} distinct records, {len(data["tamil"])} paired problems')

# ---- script conformity (conventions of Appendix B) ----
ta = lambda s: bool(re.search('[஀-௿]', s))
lat = lambda s: len(re.findall('[A-Za-z]', s))
ar = lambda s: len(re.findall('[0-9]', s))
tnum = lambda s: bool(re.search('[௦-௲]', s))
mult = lambda s: len(re.findall('[௰௱௲]', s))
ne = lambda s: isinstance(s, str) and s.strip() != ''

def tamil_row(name, vals):
    v = [x for x in vals if ne(x)]
    print(f'{name:32s} Tamil only  {len(v):4d} {sum(ta(x) and not lat(x) and not ar(x) for x in v):5d} '
          f'{sum(bool(lat(x)) for x in v):5d} {sum(bool(ar(x)) for x in v):5d} {sum(tnum(x) for x in v):5d}')

def english_row(name, vals):
    v = [x for x in vals if ne(x)]
    print(f'{name:32s} No Tamil    {len(v):4d} {sum(not ta(x) for x in v):5d}   contain Tamil: {sum(ta(x) for x in v)}')

print('\nField                            Rule      Non-empty Keeps Latin Arabic TamilNum')
T, E, A, F, R, P = (data[k] for k in ('tamil', 'english', 'glossary', 'fractions', 'chains', 'persona'))
tamil_row('Tamil problem text', [r['tamil_text'] for r in T])
tamil_row('Glossary Tamil term', [r.get('tamil_term') for r in A])
tamil_row('Glossary Tamil value statement', [r.get('tamil_value_statement') for r in A])
tamil_row('Fraction Tamil name', [r.get('tamil_name') for r in F])
tamil_row('Chain goal (Tamil)', [r.get('goal_tamil') for r in R])
tamil_row('Chain steps (Tamil)', [r.get('steps_tamil') for r in R])
tamil_row('Persona question', [r.get('question_tamil') for r in P])
tamil_row('Persona answer', [r.get('answer_tamil') for r in P])
english_row('English question', [r.get('english_question') for r in E])
english_row('English solution', [r.get('english_solution') for r in E])
for k in ('english_term_roman', 'english_value', 'english_usage_note'):
    english_row('Glossary ' + k, [r.get(k) for r in A])
english_row('Chain goal (English)', [r.get('goal_english') for r in R])
english_row('Chain steps (English)', [r.get('steps_english') for r in R])

flagged = {
    'tamil': sum(bool(r.get('needs_review')) for r in T), 'english': sum(bool(r.get('flags')) for r in E),
    'glossary': sum(bool(r.get('needs_review')) for r in A), 'fractions': sum(bool(r.get('needs_review')) for r in F),
    'chains': sum(bool(r.get('needs_review')) for r in R), 'persona': sum(bool(r.get('needs_review')) for r in P)}
print('\nRows with at least one flag:', flagged, 'total', sum(flagged.values()))
print('Problem texts with multiplier signs:', sum(mult(r['tamil_text']) > 0 for r in T))

with open('script_profile.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['uid', 'source_book', 'source_page_printed', 'flags', 'tamil_chars', 'latin_letters',
                'arabic_digits', 'tamil_digits', 'multiplier_signs', 'traditional_numeral'])
    for r in T:
        t = r['tamil_text']
        w.writerow([r['uid'], r.get('source_book'), r.get('source_page_printed'), ';'.join(r.get('needs_review') or []),
                    len(t), lat(t), ar(t), len(re.findall('[௦-௯]', t)), mult(t), int(mult(t) > 0)])
print('\nwrote script_profile.csv')
print('\nAUDIT', 'PASSED' if ok else 'FAILED')
