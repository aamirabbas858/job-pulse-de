# JobPulse DE

**A dashboard for the German Werkstudent and junior tech market that publishes its own error rates.**

Live: _(add Streamlit Cloud URL)_

Most job-market dashboards ask a language model to read postings and then present
whatever it returns as fact. This one measures how often the model is wrong, per
field, and shows those numbers next to the findings — including the ones that make
the pipeline look bad.

---

## Findings

538 postings collected from three APIs and deduplicated; 498 analysed after
excluding 7 off-topic, 1 with too little text, and 32 the model failed to parse
(6%). Snapshot: 26 July 2026.

| | |
|---|---|
| **60%** | of postings are realistic for a CS student with 0–2 years. Skewed high by construction — the queries target Werkstudent and junior roles. |
| **10%** | state actual pay, across the 321 postings whose source publishes a compensation field. Read from that field, not inferred by the model. |
| **6%** | of postings fail to parse and are excluded rather than counted as passes. |

Most-demanded skills: Python, SQL, Agile, Machine Learning, REST API, Git, CI/CD, Java.

## Measured accuracy

Every claim above depends on the extraction being correct, so it was tested against
ground truth rather than assumed.

| Field | F1 | Basis |
|---|---|---|
| `salary_mentioned` | **0.30** | 176 postings, scored against the boards' own structured field — no human labelling |
| `salary_mentioned` | **0.29** | 22 hand-labelled postings |
| `is_realistic_for_student` | **0.96** | 22 hand-labelled postings |
| `experience_years` | MAE 0.64 yrs | 22 hand-labelled postings |
| `skills` | withheld | labelling-tool defect, see below |

### The salary number is the interesting one

`salary_mentioned` scores **92% accuracy and F1 0.30** on the same data.

Only about 7% of German postings quote pay, so a model that answers "no" every
single time is right 93% of the time while being useless. Accuracy is the wrong
metric under that imbalance; F1 exposes it. The model finds 3 of the 12 postings
that genuinely quote a figure, with 5 false positives.

**This is why the dashboard's salary figure is read from the job boards' own
compensation field instead of from the model.** Bundesagentur returns
`verguetungsangabe`, and Adzuna exposes `salary_min/max` with a
`salary_is_predicted` flag. Both are publisher-stated, so checking the model
against them costs no human labelling and gives a genuinely independent measure.

Two methods — 176 auto-scored postings and 22 hand-labelled ones — independently
agree the field is weak (0.30 and 0.29). Different data, different scoring
procedure, near-identical answer.

## What was found by measuring, and fixed

**Descriptions were truncated mid-requirements — and it corrupted a headline
number, not just the skills.** German postings put requirements last (*"Dein
Profil"*, *"Was du mitbringst"*), and the pipeline cut them at 1600 characters.
**42%** of skill mentions fell past the cutoff.

Raising the limit to 6000 changed the output substantially:

| | before | after |
|---|---|---|
| skills found per posting | 0.63 | **3.21** |
| student-realistic rate | 84% | **60%** |
| `salary_mentioned` F1 (independent) | 0.18 | **0.30** |

The student-realistic figure is the one that matters. It was not a market finding
at 84% — the model simply could not see the experience requirements it was being
asked to judge, so it defaulted to permissive. A 24-point error in the headline
statistic, caused by a constant.

Measured two ways: skills F1 rose 0.287 → 0.430 against hand labels, and
independently of any labelling, 34% of vocabulary terms across 60 live postings
had been sitting past the cutoff.

Notably, the prompt rewrite that accompanied the fix made things *worse* —
precision fell 0.812 → 0.768 for no recall gain. The boring constant was the
entire win. See `src/tune.py`, which compares prompt variants and prints the table.

**The labelling tool was corrupting its own ground truth.** Streamlit reuses a
widget across reruns unless given an explicit `key`, so skill selections carried
from one posting to the next. The tell: **120 of 128 apparent model misses were
skills absent from the posting text entirely** — a model doesn't fail that way, so
the labels had to be wrong. 15 of 22 skill lists were affected. Widget keys are
now row-scoped, and the skills metric is withheld rather than published from
contaminated data.

**A metric was deleted.** The dashboard used to report "title inflation". The model
flagged 0 of 365 postings and every hand label came back honest, so there was never
a negative case to score against. A judgement with only one possible answer measures
nothing, so the field was removed from the pipeline rather than displayed as 0%.

**Arbeitnow ignores its own documented filters.** `tags[]=python`,
`tags[]=machine-learning`, and no tag at all return byte-identical responses
(verified 25 July 2026). Eight "different" queries were fetching the same 100 jobs.
Now the raw feed is paginated and filtered client-side: 165 tech roles from 600
scanned, instead of ~40 mostly irrelevant ones.

**Bundesagentur's search endpoint returns titles only.** Descriptions averaged 53
characters, so the model received a job title with no content and returned defaults
for everything — which is what produced an earlier "100% student-realistic" reading.
Full text lives at an undocumented `v4/jobdetails/{base64(refnr)}` endpoint, fetched
in parallel. Descriptions went from 53 to ~2800 characters.

## Data sources

| Source | Access | Notes |
|---|---|---|
| [Adzuna](https://developer.adzuna.com/) | API key | 8 search terms; salary flagged as stated vs modelled |
| [Bundesagentur für Arbeit](https://www.arbeitsagentur.de/) | `X-API-Key` header, no OAuth | Germany's federal employment agency; largest source; publishes an explicit pay field |
| [Arbeitnow](https://www.arbeitnow.com/api) | Open, no auth | Feed paginated and filtered client-side |

LinkedIn, Indeed, XING and StepStone have no public job API. An earlier version used
web-search scraping for them; it returned page snippets rather than structured
postings and was removed rather than left in to pad the source count.

## Known limits

- The sample comes from Werkstudent and junior queries. It describes that slice, not the German tech market as a whole.
- Human labelling is **n=22**. Small, and the hand-labelled scores in the table were measured before the truncation fix; the independent salary score was re-run after it.
- Deduplication matches on title + company, so one role advertised under two titles counts twice.
- Off-topic postings (sales, marketing, production planning) leak in through fuzzy search — about 4% after filtering, excluded from all rates and counted.
- Three APIs is not every job board.

## Running it

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then fill in your keys
streamlit run app.py
```

### Measuring accuracy yourself

```bash
python src/autoeval.py                      # no labelling needed — scores salary
                                            # against the boards' own fields
python src/groundtruth.py sample --n 51     # build a labelling set
streamlit run label_app.py                  # label it
python src/groundtruth.py score             # writes data/accuracy.json
python src/tune.py                          # compare prompt variants
```

The dashboard reads `data/accuracy.json` automatically. `score` refuses to report
an F1 for any field where the labels are single-class.

## Layout

```
app.py              dashboard
label_app.py        labelling UI (row-scoped widget keys)
src/fetcher.py      three APIs, dedup, off-topic flagging
src/analyser.py     extraction + aggregation; failures never count as passes
src/groundtruth.py  stratified sampling and scoring
src/autoeval.py     scoring against publisher-stated fields
src/tune.py         prompt variant comparison
data/labels.json    the hand-labelled set
data/accuracy.json  measured error rates, read by the dashboard
```

## Stack

Python · Streamlit · Gemini · Plotly · D3 · Adzuna / Bundesagentur für Arbeit / Arbeitnow

---

Built by [Abbas Aamir](https://www.linkedin.com/in/abbas-aamir-474969353/) — CS undergraduate in Berlin.
