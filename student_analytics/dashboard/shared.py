"""Shared Streamlit helpers: cached loading, sidebar filters, KPI cards, CSS."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from .. import config as C
from ..core import analytics, loader

CSS = """
<style>
  .block-container {padding-top: 1.6rem; padding-bottom: 2rem; max-width: 1500px;}
  h1, h2, h3 {letter-spacing: -0.01em;}
  .sa-hero {
      background: linear-gradient(120deg, #4C6FFF 0%, #845EF7 55%, #00C2A8 100%);
      color: #fff; padding: 1.15rem 1.4rem; border-radius: 14px; margin-bottom: 1.1rem;
  }
  .sa-hero h1 {color:#fff; margin:0; font-size:1.6rem; font-weight:700;}
  .sa-hero p {margin:.3rem 0 0; opacity:.92; font-size:.92rem;}
  .sa-kpi {
      background:#fff; border:1px solid #E9ECEF; border-radius:12px; padding:.85rem 1rem;
      box-shadow:0 1px 3px rgba(16,24,40,.04); height:100%;
  }
  .sa-kpi .lbl {font-size:.72rem; text-transform:uppercase; letter-spacing:.06em; color:#868E96;
                font-weight:600;}
  .sa-kpi .val {font-size:1.6rem; font-weight:700; color:#212529; line-height:1.15;}
  .sa-kpi .sub {font-size:.76rem; color:#868E96;}
  .sa-pill {display:inline-block; padding:.16rem .55rem; border-radius:999px;
            font-size:.72rem; font-weight:600; color:#fff;}
  div[data-testid="stMetricValue"] {font-size:1.5rem;}
  section[data-testid="stSidebar"] {background:#F8F9FB;}
</style>
"""


def page_setup(title: str, icon: str = "chart_with_upwards_trend") -> None:
    st.set_page_config(page_title=f"{title} · Student Analytics", page_icon="📊",
                       layout="wide", initial_sidebar_state="expanded")
    st.markdown(CSS, unsafe_allow_html=True)


def hero(title: str, subtitle: str) -> None:
    st.markdown(f'<div class="sa-hero"><h1>{title}</h1><p>{subtitle}</p></div>',
                unsafe_allow_html=True)


@st.cache_resource(show_spinner="Loading dataset …")
def get_dataset():
    return loader.load_dataset()


@st.cache_resource(show_spinner=False)
def _bootstrap_dataset() -> bool:
    """Generate the dataset on first run if it is missing.

    Normally the committed .parquet files mean this never fires. It exists so a
    fresh clone (or a cloud deploy without the data files) still comes up on its
    own instead of showing an error page.
    """
    from ..generate_dataset import main as generate
    generate(excel=False, parquet=True)
    loader.clear_cache()
    return True


def require_dataset():
    if not loader.dataset_exists():
        with st.spinner("First run: generating the student dataset (about a minute) …"):
            _bootstrap_dataset()
    if not loader.dataset_exists():
        st.error("Dataset generation failed.")
        st.code("python -m student_analytics.generate_dataset", language="powershell")
        st.stop()
    return get_dataset()


def sidebar_filters(ds, key_prefix: str = "f") -> dict:
    """Grade / campus / section / band selectors. Returns the filter dict + scoped frame."""
    st.sidebar.markdown("### Cohort")
    grades = ds.grades
    default_idx = 0
    grade = st.sidebar.selectbox("Class / Standard", grades, index=default_idx,
                                format_func=lambda g: f"Grade {g}", key=f"{key_prefix}_grade")

    campuses = ["All"] + ds.campuses
    campus = st.sidebar.multiselect("Campus", campuses, default=["All"], key=f"{key_prefix}_campus")
    sections = ["All"] + ds.sections_for(grade)
    section = st.sidebar.multiselect("Section", sections, default=["All"], key=f"{key_prefix}_section")

    df = analytics.scope(ds.summary, grade, campus, section)

    with st.sidebar.expander("More filters", expanded=False):
        bands = sorted(df["performance_band"].dropna().unique().tolist()) if not df.empty else []
        pick_bands = st.multiselect("Performance band", bands, default=bands,
                                    key=f"{key_prefix}_band")
        if pick_bands and len(pick_bands) != len(bands):
            df = df[df["performance_band"].isin(pick_bands)]
        risk = st.multiselect("Risk level", ["Low", "Moderate", "High", "Critical"],
                              default=["Low", "Moderate", "High", "Critical"],
                              key=f"{key_prefix}_risk")
        if risk:
            df = df[df["risk_level"].isin(risk)]
        gender = st.multiselect("Gender", ["M", "F"], default=["M", "F"], key=f"{key_prefix}_gender")
        if gender:
            df = df[df["gender"].isin(gender)]
        lo, hi = st.slider("Overall score range (%)", 0, 100, (0, 100), key=f"{key_prefix}_score")
        df = df[df["overall_pct"].between(lo, hi)]
        min_att = st.slider("Minimum attendance (%)", 0, 100, 0, key=f"{key_prefix}_att")
        df = df[df["attendance_pct"] >= min_att]

    label = f"Grade {grade}"
    if campus and "All" not in campus:
        label += " · " + ", ".join(c.replace(" Campus", "") for c in campus)
    if section and "All" not in section:
        label += " · Sec " + ", ".join(section)

    st.sidebar.markdown("---")
    st.sidebar.caption(f"**{len(df):,}** students in view  \n"
                       f"{ds.meta['n_master_rows']:,} student×subject rows  \n"
                       f"{ds.meta['n_mark_rows']:,} individual exam marks")
    st.sidebar.markdown(f"<span class='sa-pill' style='background:#4C6FFF'>{C.ACADEMIC_YEAR}"
                        f"</span>", unsafe_allow_html=True)

    return {"grade": grade, "campus": campus, "section": section, "df": df, "label": label}


def kpi(col, label: str, value, sub: str = "", color: str = "#212529") -> None:
    col.markdown(
        f'<div class="sa-kpi"><div class="lbl">{label}</div>'
        f'<div class="val" style="color:{color}">{value}</div>'
        f'<div class="sub">{sub}</div></div>', unsafe_allow_html=True)


def kpi_row(df: pd.DataFrame) -> dict:
    k = analytics.cohort_kpis(df)
    c = st.columns(7)
    kpi(c[0], "Students", f"{k['students']:,}", f"pass rate {k['pass_rate']:.0f}%")
    kpi(c[1], "Average score", f"{k['avg_pct']:.1f}%", f"median {k['median_pct']:.1f}% · σ{k['std_pct']:.1f}")
    kpi(c[2], "Average GPA", f"{k['avg_gpa']:.2f}", "out of 10")
    kpi(c[3], "Attendance", f"{k['attendance_pct']:.1f}%",
        f"threshold {C.ATTENDANCE_RISK_THRESHOLD:.0f}%",
        "#00A86B" if k["attendance_pct"] >= 85 else "#E8590C")
    kpi(c[4], "Toppers", f"{k['toppers']}", f"top {100 - C.TOPPER_PERCENTILE}% of the grade", "#00A86B")
    kpi(c[5], "Need improvement", f"{k['needs_improvement']}",
        f"bottom {C.IMPROVEMENT_PERCENTILE}% of the grade", "#E8590C")
    kpi(c[6], "At risk", f"{k['at_risk']}", "High / Critical risk", "#E03131")
    return k


def insight_cards(items: list[tuple[str, str]], columns: int = 2) -> None:
    cols = st.columns(columns)
    render = {"success": lambda c, m: c.success(m), "warning": lambda c, m: c.warning(m),
              "error": lambda c, m: c.error(m), "info": lambda c, m: c.info(m)}
    for i, (sev, msg) in enumerate(items):
        render.get(sev, render["info"])(cols[i % columns], msg)


def df_download(df: pd.DataFrame, filename: str, label: str | None = None, key=None) -> None:
    st.download_button(label or f"Download {filename}", df.to_csv(index=False).encode("utf-8"),
                       file_name=filename, mime="text/csv", key=key)


def styled_table(df: pd.DataFrame, height: int = 420, gradient_cols=("overall_pct",),
                 bar_cols=()) -> None:
    """A dataframe with colour scales on the numeric columns that matter."""
    if df.empty:
        st.info("Nothing to show for the current selection.")
        return
    cfg = {}
    for col in df.columns:
        if col in ("overall_pct", "final_subject_score", "avg_score", "attendance_pct",
                   "submission_rate", "percentile_in_grade", "pass_rate"):
            cfg[col] = st.column_config.ProgressColumn(
                col.replace("_", " ").title(), format="%.1f%%", min_value=0, max_value=100)
        elif col in ("risk_score",):
            cfg[col] = st.column_config.ProgressColumn("Risk", format="%.0f",
                                                       min_value=0, max_value=100)
        elif col in ("gpa", "gpa_points"):
            cfg[col] = st.column_config.NumberColumn("GPA", format="%.2f")
        elif col in ("trend_delta", "avg_trend", "vs_grade_avg", "vs_section_avg",
                     "vs_view_avg", "attendance_trend"):
            cfg[col] = st.column_config.NumberColumn(col.replace("_", " ").title(), format="%+.1f")
        else:
            cfg[col] = st.column_config.Column(col.replace("_", " ").title())
    st.dataframe(df, width="stretch", hide_index=True, height=height,
                 column_config=cfg)
