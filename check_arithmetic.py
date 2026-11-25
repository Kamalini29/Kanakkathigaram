"""Re-check the arithmetic of Kanakkathigaram release v3 in exact (rational) arithmetic.

Usage:  python check_arithmetic.py [release_dir]

1. English solutions: every bracketed step "[expr = value]" is re-evaluated.
   Each '='-separated part must equal the first one. Steps the evaluator cannot
   parse (square roots, series, powers written in words) are listed as MANUAL.
2. Glossary conversions (source_file == measurement_conversion): every step
   "a Unit x/÷ f = b Unit2" is re-evaluated, its factor checked against the grain-capacity
   ladder, each step checked to start where the previous one ended, and the Answer line
   checked against the last step. The Tamil and English forms are compared number by number.

Writes arithmetic_report.csv (one row per checked step).
"""
import csv, json, os, re, sys
from fractions import Fraction as F

D = sys.argv[1] if len(sys.argv) > 1 else '.'
load = lambda f: [json.loads(l) for l in open(os.path.join(D, f), encoding='utf-8') if l.strip()]

MIXED = re.compile(r'(\d+)\s+(\d+)/(\d+)')            # 1 1/2 -> (1+1/2)
NUM = re.compile(r'(?<![\w.])(\d+(?:\.\d+)?)')         # wrap numbers as Fractions

def to_expr(text):
    t = text.replace(',', '').replace('×', '*').replace('x', '*').replace('÷', '/').replace('−', '-')
    t = t.replace('^', '**')
    t = MIXED.sub(lambda m: f'({m.group(1)}+{m.group(2)}/{m.group(3)})', t)
    t = re.sub(r'[A-Za-z][A-Za-z\- ]*', ' ', t)            # drop unit words and labels
    if not re.fullmatch(r'[\d\s+\-*/().]*', t) or not re.search(r'\d', t):
        raise ValueError('unparsable')
    t = NUM.sub(lambda m: f'F("{m.group(1)}")', t)
    return eval(t, {'F': F, '__builtins__': {}})

def check_step(text):
    parts = [p for p in text.split('=') if p.strip()]
    if len(parts) < 2:
        return 'MANUAL'
    try:
        vals = [to_expr(p) for p in parts]
    except Exception:
        return 'MANUAL'
    return 'OK' if all(v == vals[0] for v in vals[1:]) else 'MISMATCH'

rows = []
BR = re.compile(r'\[([^\[\]]*?=[^\[\]]*?)\]')
for e in load('kanakkathigaram_english_problems_v3.jsonl'):
    for m in BR.finditer(e.get('english_solution') or ''):
        rows.append(('solution', e['uid'], m.group(1).strip(), check_step(m.group(1))))

LADDER = {('Kalam', 'Thooni'): 3, ('Thooni', 'Padakku'): 2, ('Padakku', 'Kuruni'): 2,
          ('Kuruni', 'Naazhi'): 8, ('Naazhi', 'Uri'): 2, ('Uri', 'Uzhakku'): 2,
          ('Uzhakku', 'Aazhakku'): 2, ('Aazhakku', 'Sevidu'): 5, ('Sevidu', 'Nel'): 360}
STEP = re.compile(r'([\d.]+)\s+([A-Za-z]+)\s*([×÷])\s*([\d.]+)\s*=\s*([\d.]+)\s+([A-Za-z]+)')
ANS = re.compile(r'Answer:\s*[\d.]+\s+[A-Za-z]+\s*=\s*([\d.]+)')
TDIG = str.maketrans('௦௧௨௩௪௫௬௭௮௯', '0123456789')
tamil_numbers = lambda t: sorted(F(x) for x in re.findall(r'\d+(?:\.\d+)?', t.translate(TDIG)))
same_numbers = 0
for a in load('kanakkathigaram_alavai_glossary_v3.jsonl'):
    if a.get('source_file') != 'measurement_conversion':
        continue
    en = a.get('english_usage_note') or ''
    steps = STEP.findall(en)
    prev = None
    for x, u1, op, f, y, u2 in steps:
        x, f, y = F(x), F(f), F(y)
        exact = x * f if op == '×' else x / f
        rounded = exact != y and abs(exact - y) < F(1, 10**4)   # value written as a rounded decimal
        ok = exact == y or rounded
        key, inv = (u1, u2), (u2, u1)
        ok = ok and (LADDER.get(key) == f if op == '×' else LADDER.get(inv) == f)
        ok = ok and (prev is None or prev == x)
        prev = y
        rows.append(('glossary', a['uid'], f'{x} {u1} {op} {f} = {y} {u2}',
                     ('ROUNDED' if rounded else 'OK') if ok else 'MISMATCH'))
    m = ANS.search(en)
    rows.append(('glossary_answer', a['uid'], m.group(0) if m else '(no answer line)',
                 'OK' if m and steps and F(m.group(1)) == prev else 'MISMATCH'))
    en_nums = sorted(F(x) for x in re.findall(r'\d+(?:\.\d+)?', en))
    if tamil_numbers(a.get('tamil_value_statement') or '') == en_nums:
        same_numbers += 1
    else:
        rows.append(('glossary_ta_en', a['uid'], 'Tamil and English numbers differ', 'NOTE'))

with open('arithmetic_report.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f); w.writerow(['part', 'uid', 'step', 'result']); w.writerows(rows)

for part in ('solution', 'glossary', 'glossary_answer'):
    r = [x for x in rows if x[0] == part]
    c = lambda k: sum(1 for x in r if x[3] == k)
    print(f'{part:15s} steps {len(r):4d} in {len({x[1] for x in r}):3d} records | '
          f'OK {c("OK")} | ROUNDED {c("ROUNDED")} | MISMATCH {c("MISMATCH")} | MANUAL {c("MANUAL")}')
print('glossary conversions with identical Tamil and English numbers:', same_numbers)
for x in rows:
    if x[3] not in ('OK',):
        print(x[3], x[0], x[1], x[2][:90])
