# Kanakkathigaram: scripts for the BHASHA 2026 paper

Code accompanying *Kanakkathigaram: A Bilingual Dataset of Classical Tamil Arithmetic Problems, Unit Tables and Fraction Signs* (BHASHA 2026).

The dataset itself is on Zenodo, not in this repository:

- Release v3: https://doi.org/10.5281/zenodo.24478955
- All versions: https://doi.org/10.5281/zenodo.23200763

## Setup

Download the release files from Zenodo into one folder. These are the eight `.jsonl` files and `SHA256SUMS.txt`.

The checks need only Python 3.8 or newer. The baselines also need a GPU and the packages in `requirements.txt`.

## Scripts

| Script | What it does | Paper section |
|---|---|---|
| `audit_release.py` | Checks row counts, unique and paired `uid`s and the SHA-256 checksums. Recomputes the release totals (746 rows, 539 distinct records, 207 paired problems) and the script-conformity table. Writes `script_profile.csv`, one row per problem. | §4, §6.1, Table 5 |
| `check_arithmetic.py` | Re-evaluates in exact arithmetic every bracketed step of the English solutions (373 steps in 116 problems). For the 100 glossary conversions, it checks every step against the grain-capacity ladder and every final answer, and compares the Tamil and English numbers. Writes `arithmetic_report.csv`. | §6.2 |
| `check_alignment.py` | Number-level Tamil–English alignment check over all 207 problems. Writes `alignment_report.csv`. | §6.2 |
| `eval_gold_v3.py` | Zero-shot baselines on the 24 scorable gold items, in English and in Tamil. Saves every output and scores them. | §7, Table 6 |
| `audit_prompt.txt` | The read-only, record-by-record consistency-audit checklist. | §5 |

## Usage

```bash
python audit_release.py   path/to/release
python check_arithmetic.py path/to/release
python check_alignment.py  path/to/release
python eval_gold_v3.py     path/to/release/kanakkathigaram_gold_v3.jsonl
```

Each script prints its counts and writes a CSV report into the current folder.

`eval_gold_v3.py` runs `Qwen/Qwen2.5-7B-Instruct` and `abhinand/tamil-llama-7b-instruct-v0.2` in 4-bit with greedy decoding and at most 768 new tokens. It writes:

- `predictions.jsonl`, the full output of every model;
- `results.csv`;
- `per_item.csv`.

Only the text after the last "Final answer" (or "இறுதி பதில்") marker is scored.

## What a passing run means

A passing audit confirms that the files are complete and consistent. It does not confirm:

- that the OCR text matches the printed page;
- that the translations are accurate;
- that every answer is correct.

The paper's Limitations section describes what remains unchecked.

## Licence

The data on Zenodo are released under CC BY-NC 4.0 for research use.
