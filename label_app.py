"""Labelling UI for the ground-truth set.

    venv/bin/streamlit run label_app.py --server.port 8505

Skills come pre-filled from the model because retyping them is pure tedium and
an omission is obvious once the posting is on screen next to the list. The two
judgement fields are deliberately NOT pre-filled — a pre-ticked box gets
rubber-stamped, and that would quietly inflate the very numbers this exists to
verify. Every save records whether you changed the model's skill list.

Every widget keys off the row id. Without that Streamlit reuses one widget for
all postings and the previous row's answers survive the rerun.
"""
import os
import sys
import json
import html
import streamlit as st

sys.path.insert(0, "src")
from analyser import extract_batch, ALL_SKILLS

LABELS = "data/labels.json"

st.set_page_config(page_title="Labelling · JobPulse DE", layout="wide", page_icon="🏷️")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Space+Grotesk:wght@500;600;700&family=Inter:wght@300;400;500;600&display=swap');
html, body, .stApp { background:#12100E !important; font-family:'Inter',sans-serif !important; color:#EDE8E2 !important; }
#MainMenu, footer, header, [data-testid="stToolbar"], [data-testid="stDecoration"] { display:none !important; }
.block-container { padding:1.6rem 2.4rem 3rem !important; max-width:1500px !important; }

.lb-top { display:flex; align-items:baseline; gap:14px; margin-bottom:6px; }
.lb-title { font-family:'Space Grotesk',sans-serif; font-size:1.05rem; font-weight:700; color:#EDE8E2; }
.lb-title em { font-style:normal; color:#E86A33; }
.lb-count { font-family:'Bebas Neue',sans-serif; font-size:1.5rem; color:#E86A33; letter-spacing:0.04em; }
.lb-sub { font-size:0.7rem; color:rgba(237,232,226,0.35); letter-spacing:0.05em; }

.lb-card { background:#1A1815; border:1px solid rgba(237,232,226,0.09); border-radius:10px; padding:22px 26px; }
.lb-src { display:inline-block; font-size:0.58rem; font-weight:700; letter-spacing:0.14em; text-transform:uppercase; padding:3px 9px; border-radius:3px; margin-bottom:12px; }
.s-adzuna{background:rgba(79,107,245,.16);color:#93A7FF}
.s-bundesagentur{background:rgba(232,0,58,.16);color:#FF8098}
.s-arbeitnow{background:rgba(255,209,0,.16);color:#FFDE5C}
.lb-jt { font-family:'Space Grotesk',sans-serif; font-size:1.25rem; font-weight:600; color:#EDE8E2; line-height:1.28; margin-bottom:5px; }
.lb-co { font-size:0.78rem; color:rgba(237,232,226,0.42); margin-bottom:16px; }
.lb-desc { font-size:0.83rem; line-height:1.78; color:rgba(237,232,226,0.76); max-height:460px; overflow-y:auto; white-space:pre-wrap; padding-right:16px; border-top:1px solid rgba(237,232,226,0.07); padding-top:16px; }
.lb-desc::-webkit-scrollbar{width:5px} .lb-desc::-webkit-scrollbar-thumb{background:rgba(237,232,226,.14);border-radius:3px}

.lb-q { font-size:0.86rem; font-weight:600; color:#EDE8E2; margin:20px 0 2px; }
.lb-hint { font-size:0.7rem; color:rgba(237,232,226,0.38); line-height:1.55; margin-bottom:9px; }
.lb-hint code { background:rgba(237,232,226,0.08); padding:1px 5px; border-radius:3px; font-size:0.94em; }
.lb-truth { background:rgba(0,212,106,0.07); border:1px solid rgba(0,212,106,0.25); border-radius:6px; padding:9px 13px; font-size:0.73rem; color:#8FE9B8; margin:10px 0 2px; line-height:1.5; }

.stButton>button { font-family:'Inter',sans-serif !important; font-size:0.8rem !important; font-weight:600 !important;
  background:rgba(237,232,226,0.05) !important; color:rgba(237,232,226,0.75) !important;
  border:1px solid rgba(237,232,226,0.14) !important; border-radius:6px !important; width:100% !important;
  padding:0.5rem 0.6rem !important; transition:all .16s ease !important; }
.stButton>button:hover { border-color:#E86A33 !important; color:#E86A33 !important; background:rgba(232,106,51,.1) !important; }
.stButton>button[kind="primary"] { background:#E86A33 !important; border-color:#E86A33 !important; color:#12100E !important; }
.stButton>button[kind="primary"]:hover { background:#FF7D42 !important; color:#12100E !important; }

.stProgress>div>div>div>div { background:linear-gradient(90deg,#E86A33,#FFD100) !important; }
[data-testid="stRadio"] label { font-size:0.82rem !important; color:rgba(237,232,226,0.8) !important; }
.stMultiSelect>div>div, .stNumberInput input { background:rgba(237,232,226,0.05) !important; border-color:rgba(237,232,226,0.14) !important; color:#EDE8E2 !important; }
[data-baseweb="tag"] { background:#E86A33 !important; color:#12100E !important; font-weight:600 !important; }
label[data-testid="stWidgetLabel"] p { font-size:0.72rem !important; color:rgba(237,232,226,0.4) !important; }
</style>
""", unsafe_allow_html=True)

if not os.path.exists(LABELS):
    st.error("data/labels.json not found. Run:  python src/groundtruth.py sample --n 51")
    st.stop()


def load():
    with open(LABELS, encoding="utf-8") as f:
        return json.load(f)


def save(rows):
    tmp = LABELS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
    os.replace(tmp, LABELS)          # atomic: a crash cannot truncate your work


rows = load()
BOOLS = ["LABEL_is_realistic_for_student", "LABEL_salary_mentioned"]


def handled(r) -> bool:
    return bool(r.get("LABEL_out_of_scope")) or all(r.get(b) is not None for b in BOOLS)


done_ids  = [r["id"] for r in rows if handled(r)]
n_scoped  = sum(1 for r in rows if r.get("LABEL_out_of_scope"))

if "idx" not in st.session_state:
    st.session_state.idx = next((i for i, r in enumerate(rows) if not handled(r)), 0)
if "sugg" not in st.session_state:
    st.session_state.sugg = {}

idx = max(0, min(st.session_state.idx, len(rows) - 1))
row = rows[idx]

st.markdown(f"""
<div class="lb-top">
  <span class="lb-title">Ground-truth <em>labelling</em></span>
  <span class="lb-count">{len(done_ids)}/{len(rows)}</span>
  <span class="lb-sub">posting {idx + 1} · id {row['id']} · {len(rows) - len(done_ids)} remaining{
      f" · {n_scoped} excluded as non-IT" if n_scoped else ""}</span>
</div>
""", unsafe_allow_html=True)
st.progress(len(done_ids) / len(rows))
if row.get("LABEL_out_of_scope"):
    st.warning("Marked as not an IT role. It will be excluded from scoring.")

if len(done_ids) == len(rows):
    st.success("All postings labelled. Run:  python src/groundtruth.py score")

left, right = st.columns([1.32, 1])

# ── posting text ──────────────────────────────────────────────────────────────
with left:
    # Escape everything: posting text is third-party and routinely contains
    # &, <, quotes and $ that would otherwise corrupt the markup or be eaten
    # by Streamlit's markdown/LaTeX pass.
    e = lambda v: html.escape(str(v or ""), quote=True)
    src_cls = f"s-{row['source'].lower()}"
    desc = e(row.get("description")) or (
        "<em style='color:rgba(237,232,226,.4)'>This posting has no description text. "
        "Skip it — it should not have been sampled.</em>")

    st.markdown(f"""
<div class="lb-card">
  <span class="lb-src {src_cls}">{e(row.get('source'))}</span>
  <div class="lb-jt">{e(row.get('title')) or 'Untitled posting'}</div>
  <div class="lb-co">{e(row.get('company')) or 'Company not stated'}</div>
  <div class="lb-desc">{desc}</div>
</div>""", unsafe_allow_html=True)

    url = (row.get("url") or "").strip()
    if url.startswith(("http://", "https://")):
        st.markdown(
            f'<a href="{e(url)}" target="_blank" rel="noopener noreferrer" '
            f'style="font-size:0.74rem;color:#E86A33;text-decoration:none">'
            f'Open original posting &rarr;</a>'
            f'<span style="font-size:0.68rem;color:rgba(237,232,226,0.3);margin-left:10px">'
            f'full text is already shown above — the link is optional</span>',
            unsafe_allow_html=True)
    else:
        st.caption("No external link for this posting — label from the text above.")

# ── labelling form ────────────────────────────────────────────────────────────
with right:
    # Skills: pre-filled from the model, because retyping 40 options is tedium.
    if row["id"] not in st.session_state.sugg:
        with st.spinner("Reading posting…"):
            try:
                pred = extract_batch([{
                    "title": row["title"], "company": row["company"],
                    "description": row["description"],
                }])[0]
            except Exception:
                pred = None
        st.session_state.sugg[row["id"]] = (pred or {}).get("skills", [])
    suggested = st.session_state.sugg[row["id"]]

    already = row.get("LABEL_skills")
    default = already if already else suggested

    st.markdown('<div class="lb-q">Required skills</div>'
                '<div class="lb-hint">Pre-filled by the model — <b>correct it</b>. '
                'Count anything asked for, including <code>von Vorteil</code>. '
                'Ignore stack the company merely brags about.</div>',
                unsafe_allow_html=True)
    # The key MUST include the row id. Without it Streamlit reuses one widget
    # for every posting and the previous row's selection survives the rerun,
    # silently carrying skills forward into postings that never mentioned them.
    skills = st.multiselect("skills", ALL_SKILLS,
                            default=[s for s in default if s in ALL_SKILLS],
                            key=f"skills_{row['id']}",
                            label_visibility="collapsed")
    if suggested:
        st.caption(f"model suggested: {', '.join(suggested)}")
    else:
        st.caption("model suggested: none")

    # A real posting names a handful of technologies. Anything near the whole
    # taxonomy is a mis-click, and one such row would dominate the skills F1.
    if len(skills) > 25:
        st.error(f"{len(skills)} skills selected — that is almost certainly a "
                 f"mis-click. Clear it and pick only what the posting asks for.")

    st.markdown('<div class="lb-q">Minimum years of experience</div>'
                '<div class="lb-hint">Lower bound of any range. <code>0</code> for genuine '
                'Werkstudent roles. Enrolment is not experience.</div>',
                unsafe_allow_html=True)
    yrs = st.number_input("years", 0, 40,
                          value=int(row.get("LABEL_experience_years") or 0),
                          step=1, key=f"yrs_{row['id']}",
                          label_visibility="collapsed")

    def tri(key, question, hint, truth_note=None):
        st.markdown(f'<div class="lb-q">{question}</div><div class="lb-hint">{hint}</div>',
                    unsafe_allow_html=True)
        if truth_note:
            st.markdown(f'<div class="lb-truth">{truth_note}</div>', unsafe_allow_html=True)
        cur = row.get(key)
        opts = ["— not set —", "Yes", "No"]
        i = 1 if cur is True else 2 if cur is False else 0
        c = st.radio(key, opts, index=i, horizontal=True,
                     key=f"{key}_{row['id']}",   # per-row, or state carries over
                     label_visibility="collapsed")
        return True if c == "Yes" else False if c == "No" else None

    realistic = tri("LABEL_is_realistic_for_student",
                    "Could a CS student realistically be hired?",
                    "No for completed-degree, 3+ years, or senior scope.")

    gt = row.get("salary_stated_by_source")
    note = None
    if gt is not None:
        note = ("The job board's own salary field says <b>pay IS quoted</b>. "
                if gt else
                "The job board's own salary field says <b>no pay quoted</b>. ")
        note += "Trust the posting text if it disagrees — then tell me, it's a real finding."
    salary = tri("LABEL_salary_mentioned",
                 "Does it state actual pay?",
                 "A figure, range or tariff band. <code>Attraktive Vergütung</code> is No.",
                 note)

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    b1, b2, b3 = st.columns([1, 1, 1.25])
    back = b1.button("← Back", disabled=idx == 0)
    skip = b2.button("Skip")
    ready = None not in (realistic, salary) and len(skills) <= 25
    save_next = b3.button("Save & next →", type="primary", disabled=not ready)

    if not ready:
        st.caption("Answer both questions to save.")

    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
    off_topic = st.button("Not an IT role — exclude from the sample")
    st.caption(
        "Use this only for genuinely non-IT postings (sales, marketing, production). "
        "A full-time software role a student could not get is **not** out of scope — "
        "label it *No* on the first question. Those negatives are what make the "
        "accuracy score meaningful."
    )

if back:
    st.session_state.idx = max(0, idx - 1)
    st.rerun()

if skip:
    st.session_state.idx = min(len(rows) - 1, idx + 1)
    st.rerun()

if off_topic:
    rows[idx]["LABEL_out_of_scope"] = True
    rows[idx]["_labelled_by"] = "human-reviewed"
    save(rows)
    st.session_state.idx = min(len(rows) - 1, idx + 1)
    st.rerun()

if save_next:
    rows[idx].update({
        "LABEL_skills": skills,
        "LABEL_experience_years": int(yrs),
        "LABEL_is_realistic_for_student": realistic,
        "LABEL_salary_mentioned": salary,
        # provenance: skills were model-seeded, the judgements were not
        "_skills_model_suggested": suggested,
        "_skills_edited_by_human": sorted(skills) != sorted(suggested),
        "_labelled_by": "human-reviewed",
    })
    save(rows)
    st.session_state.idx = min(len(rows) - 1, idx + 1)
    st.rerun()
