import streamlit as st
import pandas as pd
import pipeline

st.set_page_config(
    page_title="ABI — Wound Care Billing Pipeline",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── ABI Design System CSS ──
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
    /* ── ABI Theme Overrides ── */
    :root {
        --bg: #0A1414;
        --bg-elev: #101E1E;
        --bg-soft: #132424;
        --surface: #101E1E;
        --border: rgba(255,255,255,0.07);
        --border-strong: rgba(255,255,255,0.14);
        --text: #F2EDE8;
        --text-2: #B8B0A0;
        --text-3: #7A7060;
        --text-muted: #5A5040;
        --accent: #E8491B;
        --accent-hover: #F5621E;
        --accent-soft: rgba(232,73,27,0.14);
        --good: #5fd4a3;
        --good-soft: rgba(95,212,163,0.12);
        --warn: #e0a050;
        --warn-soft: rgba(224,160,80,0.12);
        --bad: #f07070;
        --bad-soft: rgba(240,112,112,0.12);
        --lilac: #3DBFA0;
        --lilac-soft: rgba(61,191,160,0.12);
        --shadow-card: 0 1px 2px rgba(0,0,0,0.4), 0 10px 30px rgba(0,0,0,0.5);
    }

    /* Force dark background everywhere */
    .stApp, .main .block-container, [data-testid="stAppViewContainer"],
    [data-testid="stHeader"], [data-testid="stToolbar"] {
        background-color: var(--bg) !important;
    }
    .block-container { padding-top: 1rem !important; max-width: 1400px !important; }

    /* Grid pattern background */
    .stApp::before {
        content: ''; position: fixed; inset: 0; pointer-events: none; z-index: 0;
        background-image:
            linear-gradient(rgba(255,255,255,0.02) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255,255,255,0.02) 1px, transparent 1px);
        background-size: 72px 72px;
        mask-image: radial-gradient(ellipse 90% 70% at 50% 30%, #000 30%, transparent 80%);
        -webkit-mask-image: radial-gradient(ellipse 90% 70% at 50% 30%, #000 30%, transparent 80%);
    }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background: var(--bg-elev) !important;
        border-right: 1px solid var(--border) !important;
    }
    section[data-testid="stSidebar"] * { color: var(--text-2) !important; }
    section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 { color: var(--text) !important; }

    /* Override all Streamlit text */
    .stApp, .stApp p, .stApp span, .stApp label, .stApp div,
    [data-testid="stMetricValue"], [data-testid="stMetricLabel"] {
        font-family: 'Inter', system-ui, -apple-system, sans-serif !important;
        color: var(--text) !important;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 2px;
        background: var(--bg-elev);
        border: 1px solid var(--border);
        border-radius: 999px;
        padding: 4px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 999px !important;
        padding: 8px 18px !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 11px !important;
        letter-spacing: 0.12em !important;
        text-transform: uppercase !important;
        color: var(--text-3) !important;
        font-weight: 500 !important;
        background: transparent !important;
    }
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        background: var(--bg-soft) !important;
        color: var(--text) !important;
        font-weight: 600 !important;
    }
    .stTabs [data-baseweb="tab-highlight"],
    .stTabs [data-baseweb="tab-border"] { display: none !important; }

    /* Buttons */
    .stButton > button {
        background: var(--bg-elev) !important;
        color: var(--text-2) !important;
        border: 1px solid var(--border) !important;
        border-radius: 10px !important;
        font-family: 'Inter', system-ui, sans-serif !important;
        font-weight: 600 !important;
        font-size: 13.5px !important;
        transition: all 0.15s !important;
    }
    .stButton > button:hover {
        border-color: var(--border-strong) !important;
        background: var(--bg-soft) !important;
        color: var(--text) !important;
    }
    .stButton > button:disabled {
        opacity: 0.3 !important;
    }

    /* Selectbox */
    [data-baseweb="select"] > div {
        background: var(--bg-soft) !important;
        border: 1px solid var(--border) !important;
        border-radius: 10px !important;
        color: var(--text) !important;
    }

    /* Hide streamlit branding */
    #MainMenu, footer, header { visibility: hidden; }

    /* ── Custom Components ── */

    /* Section kicker */
    .kicker {
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        color: var(--text-3);
        display: inline-flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 8px;
    }
    .kicker::before {
        content: '';
        width: 22px;
        height: 1px;
        background: var(--border-strong);
    }

    /* Hero header */
    .hero-title {
        font-family: 'Inter', system-ui, sans-serif;
        font-weight: 800;
        font-size: 42px;
        line-height: 1.05;
        letter-spacing: -0.03em;
        color: var(--text);
        margin-bottom: 4px;
    }
    .hero-title em { font-style: italic; color: var(--text-2); }
    .hero-sub {
        font-size: 15px;
        color: var(--text-2);
        line-height: 1.5;
    }
    .facility-pill {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: var(--text-3);
        padding: 6px 14px;
        border-radius: 999px;
        background: var(--bg-elev);
        border: 1px solid var(--border);
        margin-left: 12px;
    }
    .facility-pill .pulse {
        width: 6px; height: 6px;
        border-radius: 50%;
        background: var(--accent);
        animation: pulse 2.2s ease-in-out infinite;
    }
    @keyframes pulse {
        0%,100% { box-shadow: 0 0 0 0 rgba(232,73,27,0.6); }
        50% { box-shadow: 0 0 0 8px rgba(232,73,27,0); }
    }

    /* Stat cards — ABI node style */
    .stat-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin: 20px 0 28px; }
    .stat-node {
        background: var(--bg-elev);
        border: 1px solid var(--border);
        border-radius: 18px;
        padding: 20px 22px;
        display: flex;
        flex-direction: column;
        gap: 6px;
        box-shadow: var(--shadow-card);
        transition: transform 0.2s, box-shadow 0.2s, border-color 0.2s;
    }
    .stat-node:hover { transform: translateY(-2px); border-color: var(--border-strong); }
    .stat-node-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    .stat-tag {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 3px 10px;
        border-radius: 999px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 10px;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        font-weight: 600;
    }
    .stat-tag .dot { width: 6px; height: 6px; border-radius: 50%; }
    .tag-total  { background: rgba(61,191,160,0.10); color: var(--text-2); }
    .tag-total .dot  { background: var(--lilac); }
    .tag-accept { background: var(--good-soft); color: var(--text-2); }
    .tag-accept .dot { background: var(--good); }
    .tag-flag   { background: var(--warn-soft); color: var(--text-2); }
    .tag-flag .dot   { background: var(--warn); }
    .tag-reject { background: var(--bad-soft); color: var(--text-2); }
    .tag-reject .dot { background: var(--bad); }
    .stat-value {
        font-family: 'Inter', system-ui, sans-serif;
        font-size: 36px;
        font-weight: 800;
        line-height: 1.05;
        letter-spacing: -0.025em;
        color: var(--text);
    }
    .stat-label {
        font-size: 13px;
        color: var(--text-3);
        line-height: 1.4;
    }

    /* Patient table — ABI el-rows style */
    .patient-table-wrap {
        background: var(--bg-elev);
        border: 1px solid var(--border);
        border-radius: 18px;
        overflow: hidden;
        box-shadow: var(--shadow-card);
    }
    .pt-header {
        display: grid;
        grid-template-columns: 90px 140px 90px 150px 60px 120px 90px 130px 1fr;
        gap: 0;
        padding: 0 20px;
        background: var(--bg-soft);
        border-bottom: 1px solid var(--border);
    }
    .pt-header-cell {
        padding: 12px 8px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 10px;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: var(--text-3);
        font-weight: 600;
    }
    .pt-rows { max-height: 580px; overflow-y: auto; }
    .pt-rows::-webkit-scrollbar { width: 6px; }
    .pt-rows::-webkit-scrollbar-track { background: var(--bg-elev); }
    .pt-rows::-webkit-scrollbar-thumb { background: var(--border-strong); border-radius: 3px; }

    .pt-row {
        display: grid;
        grid-template-columns: 90px 140px 90px 150px 60px 120px 90px 130px 1fr;
        gap: 0;
        padding: 0 20px;
        border-bottom: 1px solid var(--border);
        transition: background 0.15s;
        align-items: center;
    }
    .pt-row:last-child { border-bottom: none; }
    .pt-row:hover { background: var(--bg-soft); }
    .pt-row-accept { border-left: 3px solid var(--good); }
    .pt-row-flag   { border-left: 3px solid var(--warn); }
    .pt-row-reject { border-left: 3px solid var(--bad); }

    .pt-cell {
        padding: 14px 8px;
        font-size: 13px;
        color: var(--text-2);
        line-height: 1.35;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    .pt-cell-id {
        font-family: 'JetBrains Mono', monospace;
        font-size: 12px;
        font-weight: 600;
        color: var(--text);
        letter-spacing: 0.02em;
    }
    .pt-cell-name { font-weight: 500; color: var(--text); }
    .pt-cell-reason {
        font-size: 11.5px;
        color: var(--text-3);
        white-space: normal;
        line-height: 1.4;
    }
    .pt-cell-dims {
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px;
        letter-spacing: 0.02em;
        color: var(--text-2);
    }

    /* Pills / badges — ABI style */
    .pill {
        font-family: 'JetBrains Mono', monospace;
        font-size: 9px;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        padding: 3px 8px;
        border-radius: 4px;
        font-weight: 700;
        white-space: nowrap;
        display: inline-block;
    }
    .pill-accept { background: var(--good); color: #0a0a0a; }
    .pill-flag   { background: var(--warn); color: #0a0a0a; }
    .pill-reject { background: var(--bad); color: #0a0a0a; }

    .pill-mcb-yes {
        background: var(--good-soft);
        color: var(--good);
        font-family: 'JetBrains Mono', monospace;
        font-size: 9.5px;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        padding: 3px 8px;
        border-radius: 999px;
        font-weight: 600;
    }
    .pill-mcb-no {
        background: var(--bg-soft);
        color: var(--text-3);
        font-family: 'JetBrains Mono', monospace;
        font-size: 9.5px;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        padding: 3px 8px;
        border-radius: 999px;
        font-weight: 600;
        border: 1px solid var(--border);
    }

    /* Pagination */
    .page-dots {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 6px;
        padding: 12px 0;
    }
    .page-dot {
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px;
        width: 28px; height: 28px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        border-radius: 8px;
        color: var(--text-3);
        font-weight: 500;
    }
    .page-dot-active {
        background: var(--accent);
        color: #fff;
        font-weight: 700;
    }

    /* Sidebar logo area */
    .sidebar-logo {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 16px;
    }
    .sidebar-logo-mark {
        width: 40px; height: 40px;
        border-radius: 50%;
        background: var(--bg-soft);
        border: 1px solid var(--border);
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 800;
        font-size: 16px;
        color: var(--accent) !important;
        font-family: 'Inter', sans-serif;
    }
    .sidebar-logo-text {
        font-family: 'Inter', sans-serif;
        font-weight: 800;
        font-size: 20px;
        letter-spacing: -0.02em;
        color: var(--text) !important;
    }
    .sidebar-divider {
        height: 1px;
        background: var(--border);
        margin: 14px 0;
    }
    .sidebar-section-label {
        font-family: 'JetBrains Mono', monospace;
        font-size: 10px;
        letter-spacing: 0.16em;
        text-transform: uppercase;
        color: var(--text-3) !important;
        margin-bottom: 8px;
    }
    .sidebar-stat-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 6px 0;
        font-size: 13px;
    }
    .sidebar-stat-row .label { color: var(--text-3) !important; }
    .sidebar-stat-row .val { color: var(--text) !important; font-weight: 600; font-family: 'JetBrains Mono', monospace; font-size: 12px; }

    /* Progress bar override */
    .stProgress > div > div > div {
        background-color: var(--accent) !important;
    }
</style>
""", unsafe_allow_html=True)


def decision_pill(decision):
    labels = {"auto_accept": "Accept", "flag_for_review": "Review", "reject": "Reject"}
    classes = {"auto_accept": "pill-accept", "flag_for_review": "pill-flag", "reject": "pill-reject"}
    return f'<span class="pill {classes.get(decision, "")}">{labels.get(decision, decision)}</span>'


def mcb_pill(has_mcb):
    if has_mcb:
        return '<span class="pill-mcb-yes">Active</span>'
    return '<span class="pill-mcb-no">None</span>'


def format_dims(w):
    if w is None:
        return "—"
    parts = []
    if w.length_cm is not None:
        parts.append(f"{w.length_cm}")
    if w.width_cm is not None:
        parts.append(f"{w.width_cm}")
    if w.depth_cm is not None:
        parts.append(f"{w.depth_cm}")
    elif len(parts) >= 2:
        parts.append("n/a")
    return " × ".join(parts) if parts else "—"


def build_stat_cards(stats):
    return f"""
    <div class="stat-grid">
        <div class="stat-node">
            <div class="stat-node-head">
                <span class="stat-tag tag-total"><span class="dot"></span> Total</span>
            </div>
            <div class="stat-value">{stats['total']}</div>
            <div class="stat-label">{stats['processed']} processed</div>
        </div>
        <div class="stat-node">
            <div class="stat-node-head">
                <span class="stat-tag tag-accept"><span class="dot"></span> Accept</span>
            </div>
            <div class="stat-value">{stats['auto_accept']}</div>
            <div class="stat-label">Ready for billing</div>
        </div>
        <div class="stat-node">
            <div class="stat-node-head">
                <span class="stat-tag tag-flag"><span class="dot"></span> Review</span>
            </div>
            <div class="stat-value">{stats['flag_for_review']}</div>
            <div class="stat-label">Needs clinician review</div>
        </div>
        <div class="stat-node">
            <div class="stat-node-head">
                <span class="stat-tag tag-reject"><span class="dot"></span> Reject</span>
            </div>
            <div class="stat-value">{stats['reject']}</div>
            <div class="stat-label">Not eligible</div>
        </div>
    </div>
    """


def build_table_html(results):
    html = '<div class="patient-table-wrap">'
    # Header
    html += '<div class="pt-header">'
    for h in ["ID", "Name", "MCB", "Wound Type", "Stage", "Dimensions", "Drainage", "Decision", "Reason"]:
        html += f'<div class="pt-header-cell">{h}</div>'
    html += '</div>'
    # Rows
    html += '<div class="pt-rows">'
    for r in results:
        w = r.wound_data
        row_cls = {"auto_accept": "pt-row-accept", "flag_for_review": "pt-row-flag", "reject": "pt-row-reject"}.get(r.decision, "")
        wtype = (w.wound_type or "—").replace("_", " ").title() if w else "—"
        stage = w.stage if w and w.stage else "—"
        drainage = (w.drainage_amount or "—").title() if w else "—"

        html += f'<div class="pt-row {row_cls}">'
        html += f'<div class="pt-cell pt-cell-id">{r.patient_id}</div>'
        html += f'<div class="pt-cell pt-cell-name">{r.patient_name}</div>'
        html += f'<div class="pt-cell">{mcb_pill(r.has_medicare_b)}</div>'
        html += f'<div class="pt-cell">{wtype}</div>'
        html += f'<div class="pt-cell">{stage}</div>'
        html += f'<div class="pt-cell pt-cell-dims">{format_dims(w)}</div>'
        html += f'<div class="pt-cell">{drainage}</div>'
        html += f'<div class="pt-cell">{decision_pill(r.decision)}</div>'
        html += f'<div class="pt-cell pt-cell-reason">{r.reason}</div>'
        html += '</div>'
    html += '</div></div>'
    return html


# ── Sidebar ──
st.sidebar.markdown("""
<div class="sidebar-logo">
    <div class="sidebar-logo-mark">A</div>
    <div class="sidebar-logo-text">ABI</div>
</div>
""", unsafe_allow_html=True)

st.sidebar.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)
st.sidebar.markdown('<div class="sidebar-section-label">Facility</div>', unsafe_allow_html=True)

facility_id = st.sidebar.selectbox(
    "facility_select",
    [101, 102, 103],
    format_func=lambda x: {101: "Facility A", 102: "Facility B", 103: "Facility C"}[x],
    label_visibility="collapsed",
)

st.sidebar.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)
st.sidebar.markdown('<div class="sidebar-section-label">Actions</div>', unsafe_allow_html=True)

process_all = st.sidebar.button("Process All Patients", use_container_width=True)
refresh = st.sidebar.button("Refresh Data", use_container_width=True)

if refresh:
    pipeline.load_facility(facility_id, force_refresh=True)
    st.session_state.page = 0

# ── Session state ──
if "page" not in st.session_state:
    st.session_state.page = 0
if "last_facility" not in st.session_state:
    st.session_state.last_facility = None

if st.session_state.last_facility != facility_id:
    st.session_state.page = 0
    st.session_state.last_facility = facility_id

# ── Load patients ──
with st.spinner("Loading patient list..."):
    patients = pipeline.load_facility(facility_id)

# ── Hero header ──
facility_names = {101: "Facility A", 102: "Facility B", 103: "Facility C"}
st.markdown(f"""
<div class="kicker">Wound Care Pipeline</div>
<div class="hero-title">Billing <em>Eligibility</em></div>
<div class="hero-sub">
    Medicare Part B wound care routing
    <span class="facility-pill">
        <span class="pulse"></span>
        {facility_names[facility_id]} — {len(patients)} patients
    </span>
</div>
""", unsafe_allow_html=True)

# ── Process all ──
if process_all:
    total_p = pipeline.total_pages()
    progress = st.progress(0, text="Processing all patients...")
    for pg in range(total_p):
        pipeline.process_page(pg)
        progress.progress((pg + 1) / total_p, text=f"Processed page {pg + 1}/{total_p}")
    progress.empty()
    st.toast("All patients processed!", icon="✅")

# ── Process current page ──
page = st.session_state.page
total = pipeline.total_pages()

with st.spinner(f"Processing page {page + 1} of {total}..."):
    results = pipeline.process_page(page)

if page + 1 < total:
    pipeline.start_prefetch(page + 1)

# ── Stat cards ──
stats = pipeline.get_summary_stats()
st.markdown(build_stat_cards(stats), unsafe_allow_html=True)

# ── Sidebar stats ──
st.sidebar.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)
st.sidebar.markdown('<div class="sidebar-section-label">Pipeline Status</div>', unsafe_allow_html=True)
pct = stats["processed"] / max(stats["total"], 1)
st.sidebar.progress(pct)
st.sidebar.markdown(f"""
<div class="sidebar-stat-row"><span class="label">Processed</span><span class="val">{stats['processed']} / {stats['total']}</span></div>
<div class="sidebar-stat-row"><span class="label">Accept</span><span class="val" style="color: var(--good) !important;">{stats['auto_accept']}</span></div>
<div class="sidebar-stat-row"><span class="label">Review</span><span class="val" style="color: var(--warn) !important;">{stats['flag_for_review']}</span></div>
<div class="sidebar-stat-row"><span class="label">Reject</span><span class="val" style="color: var(--bad) !important;">{stats['reject']}</span></div>
""", unsafe_allow_html=True)

# ── Filter tabs + table ──
tab_all, tab_accept, tab_flag, tab_reject = st.tabs(["All Patients", "Auto Accept", "Flag for Review", "Reject"])

with tab_all:
    st.markdown(build_table_html(results), unsafe_allow_html=True)
with tab_accept:
    filtered = [r for r in results if r.decision == "auto_accept"]
    if filtered:
        st.markdown(build_table_html(filtered), unsafe_allow_html=True)
    else:
        st.info("No auto-accepted patients on this page.")
with tab_flag:
    filtered = [r for r in results if r.decision == "flag_for_review"]
    if filtered:
        st.markdown(build_table_html(filtered), unsafe_allow_html=True)
    else:
        st.info("No flagged patients on this page.")
with tab_reject:
    filtered = [r for r in results if r.decision == "reject"]
    if filtered:
        st.markdown(build_table_html(filtered), unsafe_allow_html=True)
    else:
        st.info("No rejected patients on this page.")

# ── Pagination ──
st.markdown("<br>", unsafe_allow_html=True)
col_prev, col_dots, col_next = st.columns([1, 4, 1])
with col_prev:
    if st.button("← Previous", disabled=page == 0, use_container_width=True):
        st.session_state.page = page - 1
        st.rerun()
with col_dots:
    dots_html = '<div class="page-dots">'
    for i in range(total):
        cls = "page-dot page-dot-active" if i == page else "page-dot"
        dots_html += f'<span class="{cls}">{i + 1}</span>'
    dots_html += '</div>'
    st.markdown(dots_html, unsafe_allow_html=True)
with col_next:
    if st.button("Next →", disabled=page >= total - 1, use_container_width=True):
        st.session_state.page = page + 1
        st.rerun()
