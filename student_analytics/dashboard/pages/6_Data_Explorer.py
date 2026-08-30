"""Raw data explorer: browse, filter, pivot and export every table."""
import pathlib
import sys

_ROOT = next(p for p in pathlib.Path(__file__).resolve().parents
             if (p / "student_analytics").is_dir())
sys.path.insert(0, str(_ROOT))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from student_analytics import config as C          # noqa: E402
from student_analytics.dashboard import shared     # noqa: E402

shared.page_setup("Data Explorer")
ds = shared.require_dataset()

shared.hero("Data Explorer",
            "Every generated table, browsable and exportable — plus a free-form pivot builder "
            "for ad-hoc questions.")

TABLES = {
    "student_summary (1 row per student)": (ds.summary, C.SUMMARY_CSV),
    "master_student_subject (1 row per student × subject)": (ds.master, C.MASTER_CSV),
    "marks (1 row per student × subject × exam)": (ds.marks, C.MARKS_CSV),
    "attendance_monthly": (ds.attendance, C.ATTENDANCE_CSV),
    "assignments": (ds.assignments, C.ASSIGNMENTS_CSV),
    "survey_responses": (ds.survey, C.SURVEY_CSV),
    "students": (ds.students, C.STUDENTS_CSV),
    "classes": (ds.classes, C.CLASSES_CSV),
    "subjects": (ds.subjects, C.SUBJECTS_CSV),
    "teachers": (ds.teachers, C.TEACHERS_CSV),
}

m = st.columns(5)
shared.kpi(m[0], "Tables", len(TABLES))
shared.kpi(m[1], "Total rows", f"{ds.meta['total_rows']:,}")
shared.kpi(m[2], "Students", f"{ds.meta['n_students']:,}")
shared.kpi(m[3], "Exam marks", f"{ds.meta['n_mark_rows']:,}")
shared.kpi(m[4], "Classes", f"{ds.meta['n_classes']:,}", "grades 6-10 × 4 campuses")
st.markdown("")

t_browse, t_pivot, t_files = st.tabs(["🔎 Browse a table", "🧮 Pivot builder", "💾 Files & exports"])

with t_browse:
    name = st.selectbox("Table", list(TABLES), key="de_table")
    df, path = TABLES[name]
    st.caption(f"`{path.name}` — {len(df):,} rows × {len(df.columns)} columns")

    c1, c2, c3 = st.columns([2, 2, 1])
    text = c1.text_input("Search (matches any text column)", key="de_q")
    cols = c2.multiselect("Columns", df.columns.tolist(),
                          default=df.columns.tolist()[:14], key="de_cols")
    limit = c3.number_input("Max rows", 100, 50000, 2000, step=500, key="de_limit")

    view = df
    if text:
        obj_cols = view.select_dtypes("object").columns
        mask = pd.Series(False, index=view.index)
        for col in obj_cols:
            mask |= view[col].astype(str).str.contains(text, case=False, na=False)
        view = view[mask]

    with st.expander("Column filters"):
        num_cols = view.select_dtypes("number").columns.tolist()
        pick_num = st.selectbox("Numeric column", ["(none)"] + num_cols, key="de_num")
        if pick_num != "(none)" and not view.empty:
            lo = float(view[pick_num].min())
            hi = float(view[pick_num].max())
            if lo < hi:
                a, b = st.slider(pick_num, lo, hi, (lo, hi), key="de_range")
                view = view[view[pick_num].between(a, b)]
        cat_cols = [c for c in view.select_dtypes("object").columns
                    if view[c].nunique() <= 40]
        pick_cat = st.selectbox("Category column", ["(none)"] + cat_cols, key="de_cat")
        if pick_cat != "(none)":
            vals = st.multiselect(pick_cat, sorted(view[pick_cat].dropna().unique().tolist()),
                                  key="de_catvals")
            if vals:
                view = view[view[pick_cat].isin(vals)]

    sort_col = st.selectbox("Sort by", ["(none)"] + (cols or df.columns.tolist()), key="de_sort")
    if sort_col != "(none)":
        desc = st.checkbox("Descending", value=True, key="de_desc")
        view = view.sort_values(sort_col, ascending=not desc)

    st.caption(f"{len(view):,} rows match — showing the first {min(len(view), int(limit)):,}")
    st.dataframe(view[cols or df.columns].head(int(limit)), width="stretch",
                 hide_index=True, height=520)
    shared.df_download(view[cols or df.columns], f"{path.stem}_filtered.csv",
                       f"⬇ Download {len(view):,} filtered rows", key="de_dl")

    with st.expander("Describe (numeric summary)"):
        st.dataframe(view.describe().T.round(2), width="stretch")

with t_pivot:
    st.caption("Build any cross-tab: pick rows, columns, a value and an aggregation.")
    name = st.selectbox("Table", list(TABLES), key="de_ptable")
    df, _ = TABLES[name]
    cat_cols = [c for c in df.columns if df[c].dtype == object or df[c].nunique() <= 60]
    num_cols = df.select_dtypes("number").columns.tolist()

    c1, c2, c3, c4 = st.columns(4)
    rows = c1.selectbox("Rows", cat_cols, key="de_prows")
    colsel = c2.selectbox("Columns", ["(none)"] + cat_cols, key="de_pcols")
    value = c3.selectbox("Value", num_cols, key="de_pval")
    aggfn = c4.selectbox("Aggregation", ["mean", "median", "sum", "count", "min", "max", "std"],
                         key="de_pagg")

    piv = pd.pivot_table(df, index=rows, columns=None if colsel == "(none)" else colsel,
                         values=value, aggfunc=aggfn).round(2)
    st.dataframe(piv.style.background_gradient(cmap="RdYlGn", axis=None).format("{:.2f}"),
                 width="stretch", height=460)
    shared.df_download(piv.reset_index(), "pivot.csv", "⬇ Download pivot", key="de_pdl")

    if colsel == "(none)":
        d = piv.reset_index()
        d.columns = [rows, value]
        fig = px.bar(d.sort_values(value, ascending=False).head(40), x=rows, y=value,
                     color=value, color_continuous_scale="Tealgrn", template=C.PLOTLY_TEMPLATE)
        fig.update_layout(height=420, coloraxis_showscale=False,
                          margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig, width="stretch")
    else:
        fig = px.imshow(piv, text_auto=".1f", aspect="auto", color_continuous_scale="RdYlGn",
                        template=C.PLOTLY_TEMPLATE)
        fig.update_layout(height=max(360, 26 * len(piv) + 160),
                          margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig, width="stretch")

with t_files:
    st.caption(f"Data folder: `{C.DATA_DIR}`")
    rows = []
    for label, (df, path) in TABLES.items():
        rows.append({"table": path.name, "rows": len(df), "columns": len(df.columns),
                     "size_mb": round(path.stat().st_size / 1_048_576, 2) if path.exists() else 0})
    files = pd.DataFrame(rows)
    st.dataframe(files, width="stretch", hide_index=True)
    st.metric("Total on disk", f"{files['size_mb'].sum():.1f} MB",
              f"{files['rows'].sum():,} rows")

    if C.MASTER_XLSX.exists():
        st.download_button(f"⬇ {C.MASTER_XLSX.name} (multi-sheet Excel workbook)",
                           C.MASTER_XLSX.read_bytes(), file_name=C.MASTER_XLSX.name,
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.markdown("---")
    st.markdown("##### Regenerate the dataset")
    st.caption("Change the size or the random seed and rebuild every table from scratch.")
    st.code("python -m student_analytics.generate_dataset --students 5000 --seed 42",
            language="powershell")
    st.caption("The dashboard caches the data — use the ⋮ menu → *Clear cache* → *Rerun* after "
               "regenerating.")
