"""Run baselines on the Kanakkathigaram gold set and score them.

Kaggle / Colab (GPU T4 x2 or better):
    !pip -q install -U transformers accelerate bitsandbytes
    # Llama is gated: accept the licence on Hugging Face, then
    from huggingface_hub import login; login("hf_...")
    !python eval_gold.py kanakkathigaram_gold_v3.jsonl
Outputs: predictions.jsonl (every model output), results.csv (accuracy table), per_item.csv
Scores the 24 scorable gold-v3 items (answer_status gold or book), in English and in Tamil (question only).
Model names in results carry [en] or [ta].
"""
import csv, json, re, sys, collections, gc
from fractions import Fraction as F

MODELS = {
    'Qwen2.5-7B-Instruct': 'Qwen/Qwen2.5-7B-Instruct',
    'Llama-3.1-8B-Instruct': 'meta-llama/Llama-3.1-8B-Instruct',
    'Tamil-LLaMA-7B-Instruct': 'abhinand/tamil-llama-7b-instruct-v0.2',
}
SYSTEM_TA = ('You are solving a classical Tamil arithmetic word problem written in Tamil. Numbers may be in traditional '
             'Tamil numerals (௧=1 … ௯=9, ௰=10, ௱=100, ௲=1000; ௪௰=40) and the letter உ often means 2. '
             'Reason step by step, then end with one line exactly in this form:\n'
             'Final answer: <number or numbers separated by commas, in Arabic digits>\n'
             'Write fractions as a/b. Do not put units on the final line.')
SYSTEM = ('You are solving classical Tamil arithmetic word problems. Units are transliterated Tamil units. '
          'Reason step by step, then end with one line exactly in this form:\n'
          'Final answer: <number or numbers separated by commas>\n'
          'Write fractions as a/b. Do not put units on the final line.')

# ---------- scoring ----------
NUM = re.compile(r'(\d{1,3}(?:,\d{2,3})*,\d{3}(?!\d)|\d+)\s+(\d+)/(\d+)|(\d{1,3}(?:,\d{2,3})*,\d{3}(?!\d)|\d+)/(\d+)|((?:\d{1,3}(?:,\d{2,3})*,\d{3}(?!\d)|\d+)(?:\.\d+)?)')
UNI = {'½': '1/2', '¼': '1/4', '¾': '3/4', '⅛': '1/8', '⅜': '3/8', '⅝': '5/8', '⅞': '7/8'}
def numbers(text):
    for k, v in UNI.items():
        text = re.sub(r'(\d)\s*' + k, r'\1 ' + v, text).replace(k, v)
    out = []
    for m in NUM.finditer(text):
        if m.group(1): out.append(F(int(m.group(1).replace(',', ''))) + F(int(m.group(2)), int(m.group(3))))
        elif m.group(4): out.append(F(int(m.group(4).replace(',', '')), int(m.group(5))))
        else: out.append(F(m.group(6).replace(',', '').rstrip('.') or 0))
    return out
FINAL = re.compile(r'(?i)(?:final answer|இறுதி\s*(?:பதில்|விடை))\s*[:\-]?\s*(.+)')
def final_segment(text):
    """Text after the last 'Final answer' marker (English or Tamil); '' if the output has none."""
    m = FINAL.findall(text or '')
    return m[-1] if m else ''
def correct(g, output):
    nums = numbers(final_segment(output))
    gold = [F(x.strip()) for x in g['answer_value'].split(',')]
    if g['answer_type'] == 'tuple':
        pool = collections.Counter(nums)
        return all(pool[v] >= c for v, c in collections.Counter(gold).items())
    return bool(nums) and nums[-1] == gold[0]


# ---------- gold v3 -> evaluation items ----------
def prepare(r):
    """Keep only scorable records (answer from the book or confirmed gold) and map v3 fields."""
    if r.get('answer_status') not in ('gold', 'book') or not r.get('answer_value'):
        return None
    flags = r.get('flags') or []
    return {**r,
            'question_en': r.get('english_question'),
            'question_ta': r.get('tamil_question_with_symbols'),
            'answer_type': 'tuple' if ',' in str(r['answer_value']) else 'number',
            'subset': 'book_convention' if 'book_convention' in flags else 'core'}

# ---------- generation ----------
def run_model(name, repo, gold, langs=('en', 'ta')):
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
    tok = AutoTokenizer.from_pretrained(repo)
    try:
        import bitsandbytes  # noqa: F401
        model = AutoModelForCausalLM.from_pretrained(
            repo, device_map='auto',
            quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16))
        print(name, 'loaded in 4-bit')
    except ImportError:
        model = AutoModelForCausalLM.from_pretrained(repo, device_map='auto', torch_dtype=torch.float16)
        print(name, 'bitsandbytes missing -> loaded in fp16 across available GPUs')
    outs = []
    jobs = [(g, lang) for lang in langs for g in gold if g.get('question_' + lang)]
    for g, lang in jobs:
        question = g['question_' + lang]; system = SYSTEM if lang == 'en' else SYSTEM_TA
        msgs = [{'role': 'system', 'content': system}, {'role': 'user', 'content': question}]
        if tok.chat_template:
            prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        else:
            prompt = f"{system}\n\n### Instruction:\n{question}\n\n### Response:\n"
        ids = tok(prompt, return_tensors='pt').to(model.device)
        with torch.no_grad():
            gen = model.generate(**ids, max_new_tokens=768, do_sample=False,
                                 pad_token_id=tok.pad_token_id or tok.eos_token_id)
        text = tok.decode(gen[0][ids['input_ids'].shape[1]:], skip_special_tokens=True)
        outs.append({'model': f'{name} [{lang}]', 'uid': g['uid'], 'output': text})
        print(name, lang, g['uid'], 'OK' if correct(g, text) else 'x', '|', final_segment(text)[:60] or '(no final answer)')
    del model; gc.collect(); torch.cuda.empty_cache()
    return outs

def score(gold, preds, path_results='results.csv', path_items='per_item.csv'):
    G = {g['uid']: g for g in gold}
    rows, items = [], []
    for model in dict.fromkeys(p['model'] for p in preds):
        P = {p['uid']: p['output'] for p in preds if p['model'] == model}
        t = collections.defaultdict(lambda: [0, 0])
        for uid, g in G.items():
            if uid not in P: continue
            ok = correct(g, P[uid])
            items.append({'model': model, 'uid': uid, 'subset': g['subset'], 'gold': g['answer_value'],
                          'predicted': final_segment(P[uid])[:80], 'correct': int(ok)})
            for k in ('all', g['subset']):
                t[k][0] += ok; t[k][1] += 1
        rows.append({'model': model, **{f'{k}_acc': f'{c}/{n} ({c / n:.1%})' for k, (c, n) in t.items()}})
    for path, data in ((path_results, rows), (path_items, items)):
        with open(path, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=list(data[0])); w.writeheader(); w.writerows(data)
    for r in rows: print(r)

def find_gold():
    import glob, os
    if len(sys.argv) > 1 and sys.argv[1].endswith('.jsonl'):
        return sys.argv[1]
    hits = glob.glob('/kaggle/input/**/kanakkathigaram_gold_v3.jsonl', recursive=True) + glob.glob('kanakkathigaram_gold_v3.jsonl')
    if not hits:
        raise SystemExit('kanakkathigaram_gold_v3.jsonl not found: add it as a Kaggle Dataset or upload it to /kaggle/working')
    return hits[0]

if __name__ == '__main__':
    path = find_gold(); print('gold file:', path)
    gold = [prepare(json.loads(l)) for l in open(path, encoding='utf-8') if l.strip()]
    gold = [g for g in gold if g]
    print(len(gold), 'scorable items')
    preds = []
    for name, repo in MODELS.items():
        try:
            preds += run_model(name, repo, gold)
        except Exception as e:
            print('SKIPPED', name, '->', e)
        with open('predictions.jsonl', 'w', encoding='utf-8') as f:
            for p in preds: f.write(json.dumps(p, ensure_ascii=False) + '\n')
    if preds:
        score(gold, preds)
    else:
        print('No model ran. Fix the SKIPPED reasons above and run again.')
