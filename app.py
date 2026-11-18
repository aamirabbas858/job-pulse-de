import os
import sys
import json
import html as _html
import streamlit as st
import streamlit.components.v1 as components
import plotly.graph_objects as go

sys.path.insert(0, "src")
from fetcher  import fetch_all
from analyser import analyse_market, SKILL_CATEGORIES
from store    import save, load, age_hours

st.set_page_config(page_title="JobPulse DE", layout="wide", page_icon="🇩🇪")

# ─── CONSTANTS ────────────────────────────────────────────────────────────────
CAT_COLORS = {
    "Languages":             "#4F6BF5",
    "AI / LLM":              "#FF7A3C",
    "ML / Data":             "#C77EFF",
    "Web / Frontend":        "#00D46A",
    "Backend / API":         "#0AC8A8",
    "Cloud / DevOps":        "#FFD100",
    "Databases":             "#FF5C8A",
    "Tools / Practices":     "#9AA8B8",
    "Embedded / Industrial": "#E8003A",
}
SRC_COLORS = {
    "Adzuna":        "#4F6BF5",
    "Bundesagentur": "#E8003A",
    "Arbeitnow":     "#FFD100",
}


def esc(v) -> str:
    """Escape third-party text before it goes anywhere near unsafe_allow_html.

    Job postings are attacker-controlled input: anyone can publish one on a free
    board with a title like <img onerror=...>. Everything fetched from the APIs
    is escaped at render time, not trusted at fetch time.
    """
    return _html.escape(str(v or ""), quote=True)


def safe_url(u) -> str:
    """Allow only http(s) - a posting URL of javascript:... must not become a link."""
    u = str(u or "").strip()
    return u if u.startswith(("http://", "https://")) else ""


def block(s: str) -> str:
    """Flatten an HTML string to one line before handing it to st.markdown.

    Streamlit runs the text through Markdown first. Two things break there:
    a line indented 4+ spaces becomes a <pre><code> block, and a
    whitespace-only line closes the surrounding HTML block early so
    everything after it renders as literal source. Both occur the moment an
    f-string placeholder interpolates to "", which is why this must be
    applied to any template with optional sections.
    """
    return " ".join(ln.strip() for ln in s.splitlines() if ln.strip())

# ─── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@300;400;500&display=swap');

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html, body, .stApp { background: #0B0B0B !important; font-family: 'Inter', sans-serif !important; color: #F0F0F0 !important; }
#MainMenu, footer, header, [data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }
.block-container { padding: 0 !important; max-width: 100% !important; }
[data-testid="stVerticalBlock"] { gap: 0 !important; }

/* ── Refresh FAB — bottom-right corner ── */
.stButton > button {
    position: fixed !important;
    bottom: 30px; right: 30px;
    z-index: 9999;
    font-family: 'Inter', sans-serif !important;
    font-size: 1.15rem !important; font-weight: 400 !important;
    letter-spacing: 0 !important; text-transform: none !important;
    background: #E8003A !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 50% !important;
    width: 52px !important; height: 52px !important;
    padding: 0 !important; line-height: 1 !important;
    box-shadow: 0 4px 20px rgba(232,0,58,0.45) !important;
    transition: transform 0.2s ease, box-shadow 0.2s ease !important;
}
.stButton > button:hover {
    transform: scale(1.1) !important;
    box-shadow: 0 6px 28px rgba(232,0,58,0.6) !important;
}

/* ── Progress / spinner ── */
.stProgress > div > div > div > div { background: linear-gradient(90deg, #E8003A, #FFD100) !important; }
[data-testid="stStatusWidget"] { font-family: 'Inter', sans-serif !important; font-size: 0.78rem !important; color: rgba(240,240,240,0.4) !important; }

/* ── Filter controls (in dark section) ── */
[data-testid="stCheckbox"] label { font-family: 'Inter', sans-serif !important; font-size: 0.78rem !important; color: rgba(240,240,240,0.5) !important; }
[data-testid="stCheckbox"] label:hover { color: rgba(240,240,240,0.85) !important; }
[data-testid="stCheckbox"] span[aria-checked="true"] { background: #E8003A !important; border-color: #E8003A !important; }
.stMultiSelect > label { font-family: 'Inter', sans-serif !important; font-size: 0.72rem !important; color: rgba(240,240,240,0.35) !important; letter-spacing: 0.06em !important; }
.stMultiSelect > div > div { background: rgba(255,255,255,0.05) !important; border-color: rgba(255,255,255,0.1) !important; font-family: 'Inter', sans-serif !important; color: rgba(240,240,240,0.7) !important; }

/* ─ Side-navigation dots ── */
.jp-sidenav {
    position: fixed; right: 20px; top: 50%; transform: translateY(-50%);
    z-index: 1000; display: flex; flex-direction: column; gap: 10px;
}
.jp-sidenav a {
    display: block; width: 7px; height: 7px;
    border-radius: 50%; background: rgba(255,255,255,0.18);
    text-decoration: none; transition: all 0.22s ease;
    position: relative;
}
.jp-sidenav a:hover { background: #E8003A; transform: scale(1.6); }
.jp-sidenav a::after {
    content: attr(data-label);
    position: absolute; right: 18px; top: 50%; transform: translateY(-50%);
    background: rgba(15,15,15,0.9); color: rgba(240,240,240,0.8);
    font-family: 'Inter', sans-serif; font-size: 0.65rem; font-weight: 500;
    letter-spacing: 0.08em; white-space: nowrap;
    padding: 4px 10px; border-radius: 4px;
    opacity: 0; pointer-events: none;
    transition: opacity 0.18s ease;
}
.jp-sidenav a:hover::after { opacity: 1; }

/* ── HEADER ── */
.jp-header { background: #0B0B0B; padding: 22px 56px; display: flex; align-items: center; gap: 16px; border-bottom: 1px solid rgba(255,255,255,0.04); }
.jp-flag { width: 30px; height: 20px; display: flex; flex-direction: column; border-radius: 2px; overflow: hidden; flex-shrink: 0; }
.jp-f-b { flex:1; background:#181818; } .jp-f-r { flex:1; background:#DD0000; } .jp-f-g { flex:1; background:#FFCE00; }
.jp-wordmark { font-family:'Space Grotesk',sans-serif; font-size:1.1rem; font-weight:700; color:#F0F0F0; letter-spacing:-0.02em; line-height:1; }
.jp-wordmark em { font-style:normal; color:#E8003A; }
.jp-hdivider { width:1px; height:16px; background:rgba(255,255,255,0.08); flex-shrink:0; }
.jp-tagline { font-size:0.65rem; color:rgba(240,240,240,0.48); letter-spacing:0.14em; text-transform:uppercase; }
.jp-live { display:flex; align-items:center; gap:7px; margin-left:auto; }
.jp-live-dot { width:6px; height:6px; border-radius:50%; background:#00D46A; animation:livepulse 2.2s infinite; }
@keyframes livepulse { 0%,100%{opacity:1;box-shadow:0 0 0 0 rgba(0,212,106,.4)} 50%{opacity:.7;box-shadow:0 0 0 7px rgba(0,212,106,0)} }
.jp-live-text { font-size:0.62rem; letter-spacing:0.12em; text-transform:uppercase; color:rgba(240,240,240,0.5); }

/* ── BIG METRICS ── */
.jp-metrics { background:#0B0B0B; padding:8px 0 64px; display:grid; grid-template-columns:repeat(3,1fr); border-top:1px solid rgba(255,255,255,0.04); }
.jp-metric { padding:44px 0 44px 56px; border-right:1px solid rgba(255,255,255,0.04); position:relative; transition:background 0.25s; cursor:default; }
.jp-metric:hover { background:rgba(255,255,255,0.015); }
.jp-metric:last-child { border-right:none; }
.jp-metric-lbl { display:block; font-size:0.56rem; font-weight:600; letter-spacing:0.22em; text-transform:uppercase; color:rgba(240,240,240,0.55); margin-bottom:10px; }
.jp-metric-num { display:block; font-family:'Bebas Neue',sans-serif; font-size:6rem; line-height:0.88; margin-bottom:12px; transition:transform 0.25s; }
.jp-metric:hover .jp-metric-num { transform:translateX(4px); }
.jp-metric-num.cw { color:#F0F0F0; } .jp-metric-num.cg { color:#00D46A; } .jp-metric-num.cr { color:#E8003A; } .jp-metric-num.cy { color:#FFD100; }
.jp-metric-sub { font-size:0.7rem; color:rgba(240,240,240,0.52); line-height:1.55; max-width:200px; }
.jp-metric-bar { position:absolute; bottom:0; left:0; height:2px; background:currentColor; opacity:0.3; width:0%; transition:width 0.8s cubic-bezier(.4,0,.2,1) 0.3s; }

/* ── INSIGHTS (white section) ── */
.jp-insights { background:#F7F6F2; padding:80px 56px; color:#0B0B0B; }
.jp-eyebrow { font-size:0.56rem; font-weight:700; letter-spacing:0.24em; text-transform:uppercase; display:flex; align-items:center; gap:12px; margin-bottom:52px; }
.jp-eyebrow span { color:#E8003A; }
.jp-eyebrow::after { content:''; flex:1; height:1px; background:rgba(0,0,0,0.1); }
.jp-ins-grid { display:grid; grid-template-columns:repeat(2,1fr); gap:0; }
.jp-ins-col { padding:0 56px 0 0; border-right:1px solid rgba(0,0,0,0.07); }
.jp-ins-col:last-child { border-right:none; padding-right:0; padding-left:56px; }
.jp-ins-figure { font-family:'Bebas Neue',sans-serif; font-size:5.5rem; line-height:0.88; margin-bottom:12px; letter-spacing:0.02em; }
.jp-ins-col:nth-child(1) .jp-ins-figure { color:#0B0B0B; }
.jp-ins-col:nth-child(2) .jp-ins-figure { color:#B08000; }
.jp-ins-head { font-family:'Space Grotesk',sans-serif; font-size:1rem; font-weight:700; color:#0B0B0B; margin-bottom:10px; line-height:1.25; }
.jp-ins-body { font-size:0.79rem; color:rgba(11,11,11,0.48); line-height:1.75; }
.jp-ins-body strong { color:#0B0B0B; font-weight:600; }

/* ── METHODOLOGY (dark, between insights and skills) ── */
.jp-method { background:#111111; padding:64px 56px; border-top:1px solid rgba(255,255,255,0.05); }
.jp-eyebrow-d { font-size:0.56rem; font-weight:700; letter-spacing:0.24em; text-transform:uppercase; display:flex; align-items:center; gap:12px; margin-bottom:38px; }
.jp-eyebrow-d span { color:#E8003A; }
.jp-eyebrow-d::after { content:''; flex:1; height:1px; background:rgba(255,255,255,0.09); }
.jp-method-grid { display:grid; grid-template-columns:minmax(300px,0.85fr) 1.15fr; gap:56px; align-items:start; }
.jp-mtable { width:100%; border-collapse:collapse; }
.jp-mtable th { text-align:left; font-size:0.56rem; font-weight:700; letter-spacing:0.18em; text-transform:uppercase; color:rgba(240,240,240,0.3); padding:0 0 10px; border-bottom:1px solid rgba(255,255,255,0.1); }
.jp-mtable td { padding:11px 0; border-bottom:1px solid rgba(255,255,255,0.05); }
.jp-mtable .mk { font-size:0.8rem; color:rgba(240,240,240,0.78); }
.jp-mtable .mb { display:block; font-size:0.56rem; letter-spacing:0.13em; text-transform:uppercase; color:rgba(240,240,240,0.3); margin-top:3px; }
.jp-mcap b { color:rgba(240,240,240,0.6); font-weight:600; }
.jp-mtable .mv { font-family:'Bebas Neue',sans-serif; font-size:1.5rem; text-align:right; padding-right:14px; font-variant-numeric:tabular-nums; }
.jp-mtable .mx { font-size:0.66rem; color:rgba(240,240,240,0.3); text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums; }
.jp-mcap { font-size:0.65rem; color:rgba(240,240,240,0.32); margin-top:14px; line-height:1.6; }
.jp-method-text p { font-size:0.8rem; color:rgba(240,240,240,0.6); line-height:1.8; margin-bottom:14px; max-width:62ch; }
.jp-method-text strong { color:rgba(240,240,240,0.92); font-weight:600; }
.jp-mlim { border-left:2px solid rgba(232,0,58,0.5); padding-left:16px; color:rgba(240,240,240,0.5) !important; }
.jp-method code, .jp-mcap code { font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:0.9em; background:rgba(255,255,255,0.06); padding:2px 6px; border-radius:3px; color:rgba(240,240,240,0.75); }
@media (max-width:1100px) { .jp-method-grid { grid-template-columns:1fr; gap:36px; } }

/* ── SKILLS (dark) ── */
.jp-skills { background:#0B0B0B; padding:72px 56px; }
.jp-sec-ey { display:block; font-size:0.56rem; font-weight:700; letter-spacing:0.22em; text-transform:uppercase; color:#E8003A; margin-bottom:6px; }
.jp-sec-title { font-family:'Space Grotesk',sans-serif; font-size:2.4rem; font-weight:700; color:#F0F0F0; letter-spacing:-0.03em; line-height:1.08; margin-bottom:48px; }
.jp-bubble-legend { display:flex; flex-wrap:wrap; gap:20px; margin-bottom:32px; }
.jp-bl-item { display:flex; align-items:center; gap:7px; font-size:0.65rem; letter-spacing:0.08em; text-transform:uppercase; color:rgba(240,240,240,0.35); }
.jp-bl-dot { width:8px; height:8px; border-radius:50%; flex-shrink:0; }

/* ── COMPANIES (white) ── */
.jp-companies { background:#F7F6F2; padding:72px 56px; color:#0B0B0B; }
.jp-companies .jp-sec-title { color:#0B0B0B; }

/* ── JOBS (dark) ── */
.jp-jobs { background:#111111; padding:72px 0 56px; }
.jp-jobs-head { padding:0 56px 36px; }
.jp-jobs-head .jp-sec-title { color:#F0F0F0; margin-bottom:0; }
.jp-filter-wrap { padding:0 56px; margin-bottom:28px; display:flex; align-items:center; gap:32px; }
.jp-src-legend { display:flex; gap:16px; flex-wrap:wrap; }
.jp-src-item { display:flex; align-items:center; gap:6px; font-size:0.62rem; letter-spacing:0.06em; text-transform:uppercase; color:rgba(240,240,240,0.52); }
.jp-src-swatch { width:12px; height:4px; border-radius:2px; flex-shrink:0; }

/* ── Horizontal job scroll ── */
.jp-scroll { display:flex; overflow-x:auto; gap:14px; padding:4px 56px 28px; scrollbar-width:thin; scrollbar-color:rgba(255,255,255,0.07) transparent; -webkit-overflow-scrolling:touch; }
.jp-scroll::-webkit-scrollbar { height:3px; } .jp-scroll::-webkit-scrollbar-track { background:transparent; } .jp-scroll::-webkit-scrollbar-thumb { background:rgba(255,255,255,0.07); border-radius:2px; }
.jp-ticket { flex:0 0 240px; background:#1C1C1C; border-radius:8px; overflow:hidden; transition:transform 0.22s ease,box-shadow 0.22s ease; cursor:default; }
.jp-ticket:hover { transform:translateY(-5px); box-shadow:0 16px 40px rgba(0,0,0,0.5); }
.jp-ticket-stripe { height:3px; width:100%; }
.jp-ticket-body { padding:18px 18px 14px; }
.jp-ticket-co { font-size:0.6rem; font-weight:700; letter-spacing:0.1em; text-transform:uppercase; margin-bottom:7px; }
.jp-ticket-title { font-family:'Space Grotesk',sans-serif; font-size:0.85rem; font-weight:600; color:#F0F0F0; line-height:1.3; margin-bottom:9px; }
.jp-ticket-loc { font-size:0.64rem; color:rgba(240,240,240,0.25); margin-bottom:14px; }
.jp-ticket-tags { display:flex; flex-wrap:wrap; gap:4px; margin-bottom:14px; min-height:22px; }
.jp-ttag { background:rgba(255,255,255,0.05); border-radius:3px; padding:2px 6px; font-size:0.6rem; font-weight:500; color:rgba(240,240,240,0.4); }
.jp-ticket-foot { display:flex; justify-content:space-between; align-items:center; padding-top:10px; border-top:1px solid rgba(255,255,255,0.05); }
.jp-gem-chip { font-size:0.55rem; font-weight:700; letter-spacing:0.1em; text-transform:uppercase; color:#00D46A; }
.jp-ticket-link { font-size:0.65rem; font-weight:600; color:rgba(240,240,240,0.3); text-decoration:none; transition:color 0.15s; }
.jp-ticket-link:hover { color:#E8003A; }

/* ── FOOTER ── */
.jp-footer { background:#0B0B0B; padding:36px 56px; border-top:1px solid rgba(255,255,255,0.04); display:flex; justify-content:space-between; align-items:center; }
.jp-footer-l { font-family:'Space Grotesk',sans-serif; font-size:0.82rem; font-weight:600; color:rgba(240,240,240,0.6); }
.jp-footer-l em { font-style:normal; color:#E8003A; }
.jp-footer-r { font-size:0.62rem; color:rgba(240,240,240,0.4); letter-spacing:0.1em; }

/* ── Anchor sections ── */
#sec-insights, #sec-skills, #sec-companies, #sec-jobs { scroll-margin-top: 0; }

/* ── Responsive ── */
@media (max-width: 1000px) {
    .jp-metrics { grid-template-columns: repeat(2, 1fr); }
    .jp-metric { padding: 32px 0 32px 32px; }
    .jp-metric-num { font-size: 4.2rem; }
    .jp-ins-grid { grid-template-columns: 1fr; }
    .jp-ins-col, .jp-ins-col:nth-child(2), .jp-ins-col:last-child {
        padding: 0 0 32px 0; border-right: none;
        border-bottom: 1px solid rgba(0,0,0,0.07); margin-bottom: 32px;
    }
    .jp-ins-col:last-child { border-bottom: none; margin-bottom: 0; padding-bottom: 0; }
    .jp-header, .jp-insights, .jp-method, .jp-skills, .jp-companies,
    .jp-jobs-head, .jp-footer { padding-left: 24px; padding-right: 24px; }
    .jp-scroll { padding-left: 24px; padding-right: 24px; }
    .jp-sidenav { display: none; }
    .jp-sec-title { font-size: 1.7rem; }
}
@media (max-width: 560px) {
    .jp-metrics { grid-template-columns: 1fr; }
    .jp-header-meta, .jp-tagline { display: none; }
}
</style>
""", unsafe_allow_html=True)

# ─── DATA ─────────────────────────────────────────────────────────────────────
cached = load()

# ─── REFRESH ──────────────────────────────────────────────────────────────────
# The public deployment ships a dated snapshot and hides the refresh control.
# A visitor's click would otherwise spend my Gemini quota, and Streamlit Cloud's
# filesystem is ephemeral so any cooldown resets on container restart.
READONLY = os.getenv("JOBPULSE_READONLY", "").lower() in ("1", "true", "yes")

refresh = False
if not READONLY:
    refresh = st.button("↻")

    # Local guard: one full run per hour. A refresh is ~70 Gemini calls.
    REFRESH_COOLDOWN_H = 1.0
    if refresh and cached is not None and age_hours(cached) < REFRESH_COOLDOWN_H:
        st.markdown(
            f'<p style="position:fixed;bottom:94px;right:30px;z-index:9999;'
            f'background:#1C1C1C;border:1px solid rgba(255,255,255,0.1);border-radius:6px;'
            f'padding:8px 14px;font-size:0.7rem;color:rgba(240,240,240,0.6);">'
            f'Data is {age_hours(cached):.1f}h old — refresh unlocks at '
            f'{REFRESH_COOLDOWN_H:.0f}h to protect API quota.</p>',
            unsafe_allow_html=True,
        )
        refresh = False

if READONLY and cached is None:
    st.error("No data snapshot found. This deployment is read-only — "
             "commit data/cache.json or unset JOBPULSE_READONLY.")
    st.stop()

if refresh or (cached is None):
    prog   = st.progress(0)
    status = st.empty()

    def _cb(pct, msg):
        prog.progress(pct)
        status.markdown(
            f'<p style="font-family:Inter,sans-serif;font-size:0.7rem;'
            f'color:rgba(240,240,240,0.3);padding:6px 56px;">{msg}</p>',
            unsafe_allow_html=True,
        )

    with st.spinner(""):
        jobs = fetch_all(_cb)
    with st.spinner(""):
        data = analyse_market(jobs, _cb)

    save(data)
    cached = data
    prog.progress(1.0)
    prog.empty()
    status.empty()
    st.rerun()

# ─── SIDE NAV ─────────────────────────────────────────────────────────────────
st.markdown("""
<nav class="jp-sidenav">
    <a href="#sec-insights"  data-label="Findings"></a>
    <a href="#sec-method"    data-label="Methodology"></a>
    <a href="#sec-skills"    data-label="Skills"></a>
    <a href="#sec-companies" data-label="Companies"></a>
    <a href="#sec-jobs"      data-label="Jobs"></a>
</nav>
""", unsafe_allow_html=True)

# ─── HEADER ───────────────────────────────────────────────────────────────────
if not cached:
    age_str = "No data"
elif READONLY:
    # A fixed snapshot should be dated, not counted in hours since collection.
    try:
        from datetime import datetime
        _d = datetime.fromisoformat(cached.get("fetched_at", ""))
        age_str = f"snapshot {_d:%d %b %Y} · {cached['total_jobs']} postings"
    except Exception:
        age_str = f"{cached['total_jobs']} postings"
else:
    age_str = f"{age_hours(cached):.1f}h ago · {cached['total_jobs']} jobs"
st.markdown(f"""
<div class="jp-header">
    <div class="jp-flag"><div class="jp-f-b"></div><div class="jp-f-r"></div><div class="jp-f-g"></div></div>
    <div class="jp-wordmark">JobPulse <em>DE</em></div>
    <div class="jp-hdivider"></div>
    <div class="jp-tagline">German Tech Job Intelligence</div>
    <div class="jp-live">
        <div class="jp-live-dot"></div>
        <span class="jp-live-text">{age_str}</span>
    </div>
</div>
""", unsafe_allow_html=True)

# ─── NO DATA STATE ────────────────────────────────────────────────────────────
if not cached:
    st.markdown("""
<div style="min-height:80vh;display:flex;flex-direction:column;align-items:center;justify-content:center;background:#0B0B0B;gap:20px;text-align:center;padding:40px">
    <div style="font-family:'Bebas Neue',sans-serif;font-size:9rem;line-height:0.85;color:rgba(240,240,240,0.06);">DATA</div>
    <div style="font-family:'Space Grotesk',sans-serif;font-size:1.4rem;font-weight:700;color:rgba(240,240,240,0.7);margin-top:-40px;">No market data yet.</div>
    <div style="font-size:0.82rem;color:rgba(240,240,240,0.28);max-width:320px;line-height:1.65;">Click the <strong style="color:rgba(240,240,240,0.5)">↻ Refresh</strong> button above to pull live listings from across the German tech market.</div>
</div>""", unsafe_allow_html=True)
    st.stop()

# ─── METRICS BAND ─────────────────────────────────────────────────────────────
n1 = cached.get("analysed_jobs", cached["total_jobs"])
n2 = cached["realistic_pct"]
n4 = cached["salary_pct"]

_total    = cached["total_jobs"]
_skipped  = cached.get("skipped_no_text", 0)
_failed   = cached.get("failed_analysis", 0)
_sal_src  = cached.get("salary_basis", "model-inferred")
_sal_n    = cached.get("salary_n", n1)

# Two different exclusions, previously reported as one number.
_sub1 = (f"of {_total} fetched — {_skipped} had too little text, "
         f"{_failed} failed to parse")
_sub4 = (f"taken from the job board's own pay field on {_sal_n} postings, "
         f"not from the model" if _sal_src == "source-reported"
         else f"inferred by the model across {_sal_n} postings")

_an_jobs = [j for j in cached.get("jobs", []) if j.get("analysis")]

st.markdown(f"""
<div class="jp-metrics" id="jp-metrics">
    <div class="jp-metric">
        <span class="jp-metric-lbl">Postings Analysed</span>
        <span class="jp-metric-num cw" id="m1" data-t="{n1}" data-s="">{n1}</span>
        <span class="jp-metric-sub">{_sub1}</span>
        <div class="jp-metric-bar" style="color:#F0F0F0"></div>
    </div>
    <div class="jp-metric">
        <span class="jp-metric-lbl">Student-Realistic</span>
        <span class="jp-metric-num cg" id="m2" data-t="{n2}" data-s="%">{n2}%</span>
        <span class="jp-metric-sub">Postings a CS student could actually apply to</span>
        <div class="jp-metric-bar" style="color:#00D46A;width:{n2}%"></div>
    </div>
    <div class="jp-metric">
        <span class="jp-metric-lbl">Salary Transparency</span>
        <span class="jp-metric-num cy" id="m4" data-t="{n4}" data-s="%">{n4}%</span>
        <span class="jp-metric-sub">{_sub4}</span>
        <div class="jp-metric-bar" style="color:#FFD100;width:{n4}%"></div>
    </div>
</div>
<script>
(function(){{
    ['m1','m2','m4'].forEach(function(id){{
        // data-t is absent on a withheld metric; skip it rather than
        // animating toward NaN.
        var el=document.getElementById(id);
        if(!el||!el.dataset.t)return;
        var t=parseFloat(el.dataset.t),s=el.dataset.s||'';
        if(!isFinite(t))return;
        var d=1100,st=performance.now();
        function tick(now){{
            var p=Math.min((now-st)/d,1),e=1-Math.pow(1-p,3);
            el.textContent=Math.round(t*e)+s;
            if(p<1)requestAnimationFrame(tick);
        }}
        requestAnimationFrame(tick);
    }});
}})();
</script>
""", unsafe_allow_html=True)

# ─── INSIGHTS SECTION ─────────────────────────────────────────────────────────
real = cached["realistic_pct"]
sal  = cached["salary_pct"]
avg  = cached.get("avg_exp_required", 0)

_n_an   = cached.get("analysed_jobs", cached["total_jobs"])
_salsrc = cached.get("salary_basis", "model-inferred")
_saln   = cached.get("salary_n", _n_an)
_salnote = ("reported by the job board itself, not inferred"
            if _salsrc == "source-reported" else
            "inferred by the model — see accuracy below")

st.markdown(block(f"""
<div class="jp-insights" id="sec-insights">
    <div class="jp-eyebrow"><span>What the data shows</span></div>
    <div class="jp-ins-grid">
        <div class="jp-ins-col">
            <div class="jp-ins-figure">{real}%</div>
            <div class="jp-ins-head">Open to a student on paper</div>
            <div class="jp-ins-body">
                <strong>{real}%</strong> ask for nothing a CS student with 0–2 years could not
                offer, at a mean stated requirement of <strong>{avg:.1f} years</strong>.
                This rate is high partly by construction: the queries target Werkstudent
                and junior roles, so the sample is not the German tech market as a whole.
            </div>
        </div>
        <div class="jp-ins-col">
            <div class="jp-ins-figure">{sal}%</div>
            <div class="jp-ins-head">Postings that state pay</div>
            <div class="jp-ins-body">
                <strong>{sal}%</strong> of {_saln} postings give a figure, range or band.
                This one is {_salnote} — Bundesagentur and Adzuna both expose an explicit
                compensation field, so this number is read from the source rather than
                inferred, which makes it the most reliable figure on this page.
            </div>
        </div>
    </div>
</div>
"""), unsafe_allow_html=True)

# ─── METHODOLOGY ──────────────────────────────────────────────────────────────
def _read(path):
    try:
        return json.load(open(path)) if os.path.exists(path) else None
    except Exception:
        return None

_acc  = _read("data/accuracy.json")   # human-labelled fields
_auto = _read("data/autoeval.json")   # scored against the boards' own fields


def _mrow(label, f1, extra, basis):
    col = "#00D46A" if f1 >= .8 else "#FFD100" if f1 >= .6 else "#E8003A"
    return (f'<tr><td class="mk">{label}<span class="mb">{basis}</span></td>'
            f'<td class="mv" style="color:{col}">{f1:.2f}</td>'
            f'<td class="mx">{extra}</td></tr>')


rows = ""
if _auto:
    rows += _mrow("Salary mentioned", _auto["f1"],
                  f"P {_auto['precision']:.2f} / R {_auto['recall']:.2f} · n={_auto['n']}",
                  "independent")
if _acc:
    if "skills" in _acc:
        s = _acc["skills"]
        rows += _mrow("Skill extraction", s.get("f1", 0),
                      f"P {s.get('precision',0):.2f} / R {s.get('recall',0):.2f} · n={_acc.get('n_predicted','?')}",
                      "human-labelled")
    for k, lbl in [("is_realistic_for_student", "Student-realistic"),
                   ("salary_mentioned", "Salary mentioned")]:
        if k in _acc:
            rows += _mrow(lbl, _acc[k]["f1"], f"acc {_acc[k].get('accuracy',0):.2f} · n={_acc.get('n_predicted','?')}",
                          "human-labelled")

if _auto:
    imbalance = (f"On <strong>salary mentioned</strong> the model scores "
                 f"{_auto.get('accuracy', 0):.0%} accuracy but only "
                 f"<strong>F1 {_auto['f1']:.2f}</strong> — it catches "
                 f"{_auto['confusion']['tp']} of {_auto['positives_in_truth']} postings that "
                 f"really do quote pay. Accuracy looks high only because "
                 f"{100 - round(_auto['positives_in_truth']/_auto['n']*100)}% "
                 f"of postings quote nothing, so answering \"no\" every time is almost always right. "
                 f"That is exactly why the salary figure above is read from the job board's own "
                 f"structured field and not from the model.")
else:
    imbalance = ""

withheld = ""
if _acc and _acc.get("skills_withheld_reason"):
    withheld = (f"<p class='jp-mlim'><strong>Withheld:</strong> "
                f"{esc(_acc['skills_withheld_reason'])}</p>")

pending = ("" if _acc else
           "<p class='jp-mlim'>Skills, experience and title honesty need human labels and are "
           "not yet measured. Run <code>streamlit run label_app.py</code>, then "
           "<code>python src/groundtruth.py score</code> — results appear here automatically.</p>")

degen = ("<p class='jp-mlim'><strong>A metric was dropped.</strong> This page used to "
         "report title inflation — how often a job title oversells the work. The model "
         "flagged 0 of 365 postings and every hand-labelled posting came back honest, so "
         "there was never a negative case to score against. A judgement with only one "
         "possible answer measures nothing, so the field was removed from the pipeline "
         "rather than shown as 0%.</p>")

body = block(f"""
<div class="jp-method-text">
<p>Every figure on this page comes from a language model reading posting text,
so the figures are only as trustworthy as that model. Rather than assume, I measured it.</p>
<p>{imbalance}</p>
<p>Of {_total} postings fetched, {_skipped} carried too little description to judge and
{_failed} could not be parsed by the model. Both are excluded and counted here rather than
being treated as passes — a posting the model fails on is never scored as a positive result.</p>
{withheld}
{degen}
{pending}
<p class="jp-mlim"><strong>Known limits:</strong> the sample comes from Werkstudent
and junior queries, so it describes that slice and not the German tech market as a
whole; three APIs is not every job board; and duplicates are matched on title and
company only, so one role advertised under two titles is counted twice.</p>
</div>""")

if rows:
    st.markdown(block(f"""
<div class="jp-method" id="sec-method">
<div class="jp-eyebrow-d"><span>Methodology &amp; measured accuracy</span></div>
<div class="jp-method-grid">
<div>
<table class="jp-mtable">
<tr><th>Field</th><th>F1</th><th>detail</th></tr>
{rows}
</table>
<div class="jp-mcap"><b>independent</b> = scored against the job board's own
structured field, no human labelling involved.
<b>human-labelled</b> = scored against postings I read and labelled myself.</div>
</div>
{body}
</div>
</div>"""), unsafe_allow_html=True)
else:
    st.markdown(block(f"""
<div class="jp-method" id="sec-method">
<div class="jp-eyebrow-d"><span>Methodology</span></div>
<div style="max-width:820px">{body}</div>
</div>"""), unsafe_allow_html=True)

# ─── SKILLS BUBBLE CHART (D3) ─────────────────────────────────────────────────
skill_map = dict(cached.get("top_skills", []))
skill_data = []
for cat, skills_in_cat in SKILL_CATEGORIES.items():
    for sk in skills_in_cat:
        if sk in skill_map:
            skill_data.append({"name": sk, "count": skill_map[sk], "category": cat})

legend_html = "".join(
    f'<div class="jp-bl-item"><div class="jp-bl-dot" style="background:{CAT_COLORS[c]}"></div>{c}</div>'
    for c in CAT_COLORS
)

st.markdown(f"""
<div class="jp-skills" id="sec-skills">
    <span class="jp-sec-ey">Skill Landscape</span>
    <div class="jp-sec-title">What the market<br>is asking for</div>
    <div class="jp-bubble-legend">{legend_html}</div>
</div>
""", unsafe_allow_html=True)

if skill_data:
    bubble_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#0B0B0B;overflow:hidden}}
#chart{{width:100%;height:100%}}
.tip{{position:fixed;background:#F0F0F0;color:#0B0B0B;padding:6px 12px;border-radius:5px;font-family:Inter,sans-serif;font-size:12px;font-weight:600;pointer-events:none;opacity:0;transition:opacity .15s;z-index:10;letter-spacing:0.02em}}
</style>
</head>
<body>
<div class="tip" id="tip"></div>
<div id="chart"></div>
<script>
var skills={json.dumps(skill_data)};
var colors={json.dumps(CAT_COLORS)};
var W=window.innerWidth,H=window.innerHeight;
var svg=d3.select('#chart').append('svg').attr('width',W).attr('height',H);
var rScale=d3.scaleSqrt().domain([0,d3.max(skills,function(d){{return d.count;}})]).range([18,72]);
skills.forEach(function(d){{d.r=rScale(d.count);}});
var sim=d3.forceSimulation(skills)
    .force('charge',d3.forceManyBody().strength(3))
    .force('center',d3.forceCenter(W/2,H/2))
    .force('collision',d3.forceCollide(function(d){{return d.r+3;}}).iterations(4))
    .on('tick',ticked);
var node=svg.selectAll('.node').data(skills).join('g').attr('class','node').style('cursor','default');
node.append('circle')
    .attr('r',function(d){{return d.r;}})
    .attr('fill',function(d){{return colors[d.category]||'#888';}})
    .attr('opacity',0.8)
    .attr('stroke','rgba(255,255,255,0.08)')
    .attr('stroke-width',1);
node.append('text')
    .attr('text-anchor','middle').attr('dominant-baseline','middle')
    .attr('fill','white').attr('font-family','Inter,sans-serif').attr('font-weight','600')
    .attr('pointer-events','none')
    .attr('font-size',function(d){{return Math.max(Math.min(d.r*0.36,14),7);}})
    .text(function(d){{return d.r>24?d.name:'';}});
var tip=document.getElementById('tip');
node.on('mouseover',function(event,d){{
    tip.style.opacity='1';
    tip.textContent=d.name+' — '+d.count+' listings';
    d3.select(this).select('circle').attr('opacity',1).attr('stroke-width',2).attr('stroke','rgba(255,255,255,0.3)');
}}).on('mousemove',function(event){{
    tip.style.left=(event.clientX+14)+'px';
    tip.style.top=(event.clientY-28)+'px';
}}).on('mouseout',function(){{
    tip.style.opacity='0';
    d3.select(this).select('circle').attr('opacity',0.8).attr('stroke-width',1).attr('stroke','rgba(255,255,255,0.08)');
}});
function ticked(){{node.attr('transform',function(d){{return 'translate('+d.x+','+d.y+')';}});}}
</script>
</body>
</html>"""
    components.html(bubble_html, height=480)

# ─── COMPANIES TREEMAP ────────────────────────────────────────────────────────
st.markdown('<div id="sec-companies"></div>', unsafe_allow_html=True)

if cached["top_companies"]:
    companies = cached["top_companies"]
    n_co = len(companies)
    co_colors = [
        f"hsl({int(i * 360 / n_co)},45%,42%)" for i in range(n_co)
    ]

    st.markdown(f"""
<div class="jp-companies">
    <span class="jp-sec-ey">Hiring Companies</span>
    <div class="jp-sec-title" style="color:#0B0B0B;margin-bottom:36px">Who's posting<br>right now</div>
</div>
""", unsafe_allow_html=True)

    fig = go.Figure(go.Treemap(
        labels=[c[0] for c in companies],
        parents=[""] * len(companies),
        values=[c[1] for c in companies],
        texttemplate="<b>%{label}</b><br><span style='font-size:11px;opacity:0.7'>%{value} listings</span>",
        hovertemplate="<b>%{label}</b><br>%{value} listings<extra></extra>",
        marker=dict(
            colors=co_colors,
            line=dict(width=3, color="#F7F6F2"),
            pad=dict(t=6, b=6, l=6, r=6),
        ),
        textfont=dict(family="Space Grotesk, sans-serif", size=14, color="white"),
    ))
    fig.update_layout(
        paper_bgcolor="#F7F6F2",
        margin=dict(t=0, b=0, l=56, r=56),
        height=380,
        hoverlabel=dict(bgcolor="#0B0B0B", font=dict(family="Inter", size=12, color="white"), bordercolor="#0B0B0B"),
    )
    st.plotly_chart(fig, width="stretch")

    # Padding bottom of white section
    st.markdown('<div style="background:#F7F6F2;height:56px"></div>', unsafe_allow_html=True)

# ─── JOBS HORIZONTAL SCROLL ───────────────────────────────────────────────────
st.markdown('<div id="sec-jobs"></div>', unsafe_allow_html=True)

jobs_all = cached.get("jobs", [])

if jobs_all:
    # Source legend
    src_legend = "".join(
        f'<div class="jp-src-item"><div class="jp-src-swatch" style="background:{SRC_COLORS.get(s, "#888")}"></div>{s}</div>'
        for s in SRC_COLORS if any(j["source"] == s for j in jobs_all)
    )

    st.markdown(f"""
<div class="jp-jobs">
    <div class="jp-jobs-head">
        <span class="jp-sec-ey">Open Positions</span>
        <div class="jp-sec-title" style="margin-bottom:24px">Browse the market</div>
        <div class="jp-src-legend">{src_legend}</div>
    </div>
</div>
""", unsafe_allow_html=True)

    # Filter controls
    filter_col1, filter_col2, _ = st.columns([2, 2, 6])
    with filter_col1:
        student_only = st.checkbox("Student-realistic only")
    with filter_col2:
        with_skills = st.checkbox("Names a technology")

    st.markdown('<div style="background:#111111;height:16px"></div>', unsafe_allow_html=True)

    filtered = [
        j for j in jobs_all
        if not j.get("off_topic")   # metrics exclude these; the list must match
        and (not student_only or (j.get("analysis") or {}).get("is_realistic_for_student"))
        and (not with_skills or (j.get("analysis") or {}).get("skills"))
    ][:80]

    tickets = ""
    for job in filtered:
        a       = job.get("analysis") or {}
        skills  = a.get("skills", [])[:4]
        is_gem  = a.get("is_realistic_for_student")
        color   = SRC_COLORS.get(job["source"], "#555555")
        tags    = "".join(f'<span class="jp-ttag">{esc(s)}</span>' for s in skills)
        url     = safe_url(job.get("url"))
        link    = (f'<a class="jp-ticket-link" href="{esc(url)}" target="_blank" '
                   f'rel="noopener noreferrer">Apply →</a>' if url
                   else '<span class="jp-ticket-link" style="opacity:0.3">No link</span>')
        gem     = '<span class="jp-gem-chip">✓ Student</span>' if is_gem else '<span style="font-size:0.55rem;color:rgba(240,240,240,0.15)">—</span>'
        co      = esc((job.get("company") or "Undisclosed")[:28])
        loc     = esc(job.get("location") or "Germany")
        title   = esc(job["title"][:50])
        tickets += f"""<div class="jp-ticket">
<div class="jp-ticket-stripe" style="background:{color}"></div>
<div class="jp-ticket-body">
<div class="jp-ticket-co" style="color:{color}">{co}</div>
<div class="jp-ticket-title">{title}</div>
<div class="jp-ticket-loc">{loc}</div>
<div class="jp-ticket-tags">{tags}</div>
<div class="jp-ticket-foot">{gem}{link}</div>
</div></div>"""

    st.markdown(f'<div class="jp-scroll" style="background:#111111">{tickets}</div>', unsafe_allow_html=True)

    count_txt = f"{len(filtered)} of {len(jobs_all)} listings"
    st.markdown(f'<div style="background:#111111;padding:0 56px 40px;font-size:0.65rem;color:rgba(240,240,240,0.38);letter-spacing:0.08em">{count_txt}</div>', unsafe_allow_html=True)

# ─── FOOTER ───────────────────────────────────────────────────────────────────
st.markdown("""
<div class="jp-footer">
    <div class="jp-footer-l">JobPulse <em>DE</em></div>
    <div class="jp-footer-r">Adzuna · Bundesagentur für Arbeit · Arbeitnow</div>
</div>
""", unsafe_allow_html=True)
