"""Plotly figure factory.

Every function returns a ready-to-render `plotly.graph_objects.Figure`, so the
dashboard pages stay thin and the same visuals can be reused anywhere.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .. import config as C
from . import grading

try:  # `trendline="ols"` needs statsmodels; degrade gracefully without it
    import statsmodels.api  # noqa: F401
    _HAS_STATSMODELS = True
except ImportError:
    _HAS_STATSMODELS = False

PX_KW = dict(template=C.PLOTLY_TEMPLATE, color_discrete_sequence=C.COLOR_SEQUENCE)


def _style(fig: go.Figure, height: int = 380, title: str | None = None,
           legend_bottom: bool = False) -> go.Figure:
    fig.update_layout(
        template=C.PLOTLY_TEMPLATE,
        height=height,
        title=title,
        margin=dict(l=10, r=10, t=50 if title else 20, b=10),
        font=dict(family="Segoe UI, Inter, sans-serif", size=12),
        hoverlabel=dict(font_size=12),
    )
    if legend_bottom:
        fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.0,
                                     xanchor="right", x=1, title=None))
    return fig


def empty(msg: str = "No data for the current selection") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=msg, showarrow=False, font=dict(size=14, color="#888"),
                       xref="paper", yref="paper", x=0.5, y=0.5)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return _style(fig, 260)


# ------------------------------------------------------------------ overview
def score_distribution(df: pd.DataFrame, title="Score distribution across the cohort") -> go.Figure:
    if df.empty:
        return empty()
    fig = px.histogram(df, x="overall_pct", nbins=45, marginal="box",
                       color="performance_band",
                       color_discrete_map=C.BAND_COLORS,
                       labels={"overall_pct": "Overall score (%)"}, **{"template": C.PLOTLY_TEMPLATE})
    mean = df["overall_pct"].mean()
    fig.add_vline(x=mean, line_dash="dash", line_color="#333",
                  annotation_text=f"mean {mean:.1f}%", annotation_position="top right")
    fig.update_layout(bargap=0.04, yaxis_title="Students")
    return _style(fig, 420, title, legend_bottom=True)


def grade_donut(df: pd.DataFrame, title="Letter-grade mix") -> go.Figure:
    if df.empty:
        return empty()
    dist = grading.grade_distribution(df["overall_pct"])
    dist = dist[dist["students"] > 0]
    fig = go.Figure(go.Pie(
        labels=dist["letter_grade"], values=dist["students"], hole=0.55,
        marker=dict(colors=C.COLOR_SEQUENCE), sort=False,
        customdata=dist["descriptor"],
        hovertemplate="<b>%{label}</b> — %{customdata}<br>%{value} students (%{percent})<extra></extra>",
    ))
    fig.add_annotation(text=f"<b>{int(dist['students'].sum())}</b><br>students",
                       showarrow=False, font=dict(size=15))
    return _style(fig, 380, title)


def band_sunburst(df: pd.DataFrame, title="Cohort composition: campus → section → band") -> go.Figure:
    if df.empty:
        return empty()
    d = df.groupby(["campus", "section", "performance_band"]).size().reset_index(name="students")
    fig = px.sunburst(d, path=["campus", "section", "performance_band"], values="students",
                      color="performance_band", color_discrete_map=C.BAND_COLORS,
                      template=C.PLOTLY_TEMPLATE)
    return _style(fig, 480, title)


def performance_band_bar(df: pd.DataFrame, title="Performance bands by section") -> go.Figure:
    if df.empty:
        return empty()
    d = df.groupby(["section", "performance_band"]).size().reset_index(name="students")
    order = ["Topper", "Above Average", "Average", "Needs Improvement", "At Risk"]
    fig = px.bar(d, x="section", y="students", color="performance_band", barmode="stack",
                 category_orders={"performance_band": order},
                 color_discrete_map=C.BAND_COLORS, template=C.PLOTLY_TEMPLATE,
                 labels={"section": "Section", "students": "Students"})
    return _style(fig, 380, title, legend_bottom=True)


# ------------------------------------------------------------------ subjects
def subject_average_bar(subs: pd.DataFrame, cohort_avg: float | None = None,
                        title="Subject averages (strongest → weakest)") -> go.Figure:
    if subs.empty:
        return empty()
    d = subs.sort_values("avg_score")
    fig = go.Figure(go.Bar(
        x=d["avg_score"], y=d["subject_name"], orientation="h",
        marker=dict(color=d["avg_score"], colorscale="RdYlGn", cmin=35, cmax=90,
                    line=dict(width=0)),
        text=d["avg_score"].map(lambda v: f"{v:.1f}%"), textposition="outside",
        customdata=np.stack([d["pass_rate"], d["fail_count"], d["avg_trend"]], axis=-1),
        hovertemplate=("<b>%{y}</b><br>Average %{x:.1f}%<br>Pass rate %{customdata[0]:.0f}%"
                       "<br>Failing %{customdata[1]}<br>Trend %{customdata[2]:+.1f} pts<extra></extra>"),
    ))
    if cohort_avg is not None:
        fig.add_vline(x=cohort_avg, line_dash="dash", line_color="#4C6FFF",
                      annotation_text=f"cohort {cohort_avg:.1f}%")
    fig.update_layout(xaxis_title="Average score (%)", yaxis_title=None,
                      xaxis_range=[0, max(100, d["avg_score"].max() * 1.15)])
    return _style(fig, 420, title)


def subject_box(master: pd.DataFrame, student_ids=None,
                title="Score spread per subject (who is consistent, who is polarised)") -> go.Figure:
    m = master if student_ids is None else master[master["student_id"].isin(student_ids)]
    if m.empty:
        return empty()
    order = (m.groupby("subject_name")["final_subject_score"].median()
             .sort_values(ascending=False).index.tolist())
    fig = px.violin(m, x="subject_name", y="final_subject_score", box=True, points=False,
                    color="subject_name", category_orders={"subject_name": order},
                    labels={"subject_name": "", "final_subject_score": "Subject score (%)"},
                    **PX_KW)
    fig.add_hline(y=C.PASS_MARK_PCT, line_dash="dot", line_color="#E03131",
                  annotation_text=f"pass mark {C.PASS_MARK_PCT:.0f}%")
    fig.update_layout(showlegend=False)
    return _style(fig, 440, title)


def exam_progression_lines(prog: pd.DataFrame,
                           title="Subject averages across the four exams") -> go.Figure:
    if prog.empty:
        return empty()
    fig = px.line(prog, x="exam_type", y="pct", color="subject_name", markers=True,
                  category_orders={"exam_type": C.EXAM_TYPES},
                  labels={"exam_type": "", "pct": "Average score (%)", "subject_name": "Subject"},
                  **PX_KW)
    fig.update_traces(line=dict(width=2.5), marker=dict(size=8))
    return _style(fig, 420, title, legend_bottom=True)


def section_subject_heatmap(master: pd.DataFrame, student_ids=None,
                            title="Section × subject average — where exactly are the gaps?") -> go.Figure:
    m = master if student_ids is None else master[master["student_id"].isin(student_ids)]
    if m.empty:
        return empty()
    m = m.copy()
    m["class_label"] = m["campus"].str.replace(" Campus", "", regex=False) + " / " + m["section"]
    piv = m.pivot_table(index="class_label", columns="subject_name",
                        values="final_subject_score", aggfunc="mean").round(1)
    fig = px.imshow(piv, text_auto=".1f", aspect="auto", color_continuous_scale="RdYlGn",
                    labels=dict(color="Avg %"), template=C.PLOTLY_TEMPLATE)
    fig.update_xaxes(side="top", tickangle=-30)
    fig.update_layout(xaxis_title=None, yaxis_title=None, coloraxis_colorbar=dict(thickness=12))
    return _style(fig, max(360, 34 * len(piv) + 140), title)


def subject_correlation_heatmap(corr: pd.DataFrame,
                                title="Subject-to-subject correlation") -> go.Figure:
    if corr.empty:
        return empty()
    fig = px.imshow(corr, text_auto=".2f", aspect="auto", zmin=-1, zmax=1,
                    color_continuous_scale="RdBu_r", template=C.PLOTLY_TEMPLATE)
    fig.update_xaxes(tickangle=-30)
    fig.update_layout(xaxis_title=None, yaxis_title=None)
    return _style(fig, 480, title)


def subject_difficulty_quadrant(subs: pd.DataFrame,
                                title="Subject quadrant: average vs. spread") -> go.Figure:
    if subs.empty:
        return empty()
    fig = px.scatter(subs, x="avg_score", y="std_score", size="students", color="subject_category",
                     text="subject_name", size_max=45,
                     labels={"avg_score": "Average score (%)", "std_score": "Spread (std dev)",
                             "subject_category": "Category"}, **PX_KW)
    fig.update_traces(textposition="top center", textfont_size=10)
    fig.add_vline(x=subs["avg_score"].mean(), line_dash="dot", line_color="#999")
    fig.add_hline(y=subs["std_score"].mean(), line_dash="dot", line_color="#999")
    fig.add_annotation(x=subs["avg_score"].min(), y=subs["std_score"].max(),
                       text="low score, high spread → uneven teaching/learning",
                       showarrow=False, font=dict(size=10, color="#C92A2A"), xanchor="left")
    return _style(fig, 440, title, legend_bottom=True)


# --------------------------------------------------------------- leaderboards
def leaderboard_bar(d: pd.DataFrame, value="overall_pct", label="name",
                    title="Top performers", ascending=False,
                    colorscale="Greens") -> go.Figure:
    if d.empty:
        return empty()
    d = d.sort_values(value, ascending=not ascending)
    hover_extra = [c for c in ("section", "attendance_pct", "best_subject", "risk_level")
                   if c in d.columns]
    fig = go.Figure(go.Bar(
        x=d[value], y=d[label], orientation="h",
        marker=dict(color=d[value], colorscale=colorscale, line=dict(width=0)),
        text=d[value].map(lambda v: f"{v:.1f}%"), textposition="outside",
        customdata=d[hover_extra].to_numpy() if hover_extra else None,
        hovertemplate="<b>%{y}</b><br>%{x:.1f}%" + "".join(
            f"<br>{c.replace('_', ' ').title()}: %{{customdata[{i}]}}"
            for i, c in enumerate(hover_extra)) + "<extra></extra>",
    ))
    fig.update_layout(xaxis_title="Overall score (%)", yaxis_title=None,
                      xaxis_range=[0, max(100, d[value].max() * 1.12)])
    return _style(fig, max(320, 30 * len(d) + 110), title)


def movers_tornado(up: pd.DataFrame, down: pd.DataFrame,
                   title="Biggest movers — Unit Test 1 → Final Exam") -> go.Figure:
    if up.empty and down.empty:
        return empty()
    d = pd.concat([up, down]).sort_values("trend_delta")
    fig = go.Figure(go.Bar(
        x=d["trend_delta"], y=d["name"], orientation="h",
        marker=dict(color=np.where(d["trend_delta"] >= 0, "#00A86B", "#E03131")),
        text=d["trend_delta"].map(lambda v: f"{v:+.1f}"), textposition="outside",
        customdata=d[["section", "overall_pct"]].to_numpy(),
        hovertemplate=("<b>%{y}</b> (%{customdata[0]})<br>Change %{x:+.1f} pts"
                       "<br>Now at %{customdata[1]:.1f}%<extra></extra>"),
    ))
    fig.add_vline(x=0, line_color="#333")
    fig.update_layout(xaxis_title="Change in score (percentage points)", yaxis_title=None)
    return _style(fig, max(340, 26 * len(d) + 110), title)


# ------------------------------------------------------------- attendance etc.
def attendance_trend(ts: pd.DataFrame, color: str | None = None,
                     title="Monthly attendance trend") -> go.Figure:
    if ts.empty:
        return empty()
    fig = px.line(ts, x="month_label", y="attendance_pct", markers=True,
                  color=color, labels={"month_label": "", "attendance_pct": "Attendance (%)"},
                  **PX_KW)
    fig.add_hline(y=C.ATTENDANCE_RISK_THRESHOLD, line_dash="dot", line_color="#E03131",
                  annotation_text=f"risk threshold {C.ATTENDANCE_RISK_THRESHOLD:.0f}%")
    fig.update_traces(line=dict(width=3), marker=dict(size=9))
    fig.update_layout(yaxis_range=[max(0, ts["attendance_pct"].min() - 6), 100])
    return _style(fig, 380, title, legend_bottom=True)


def attendance_vs_score_scatter(df: pd.DataFrame,
                                title="Attendance vs. score — every dot is a student") -> go.Figure:
    if df.empty:
        return empty()
    fig = px.scatter(df, x="attendance_pct", y="overall_pct", color="performance_band",
                     color_discrete_map=C.BAND_COLORS, opacity=0.65,
                     hover_data=["student_id", "name", "section", "gpa", "submission_rate"],
                     labels={"attendance_pct": "Attendance (%)", "overall_pct": "Overall score (%)",
                             "performance_band": "Band"},
                     template=C.PLOTLY_TEMPLATE,
                     **(dict(trendline="ols", trendline_color_override="#212529")
                        if _HAS_STATSMODELS else {}))
    fig.add_vline(x=C.ATTENDANCE_RISK_THRESHOLD, line_dash="dot", line_color="#E03131")
    return _style(fig, 460, title, legend_bottom=True)


def attendance_band_bar(d: pd.DataFrame,
                        title="Average score by attendance band") -> go.Figure:
    if d.empty:
        return empty()
    fig = go.Figure(go.Bar(
        x=d["attendance_band"].astype(str), y=d["avg_pct"],
        marker=dict(color=d["avg_pct"], colorscale="Blues", cmin=30),
        text=d["avg_pct"].map(lambda v: f"{v:.1f}%"), textposition="outside",
        customdata=d[["students", "at_risk"]].to_numpy(),
        hovertemplate=("Attendance %{x}%<br>Avg score %{y:.1f}%"
                       "<br>%{customdata[0]} students, %{customdata[1]} at risk<extra></extra>"),
    ))
    fig.update_layout(xaxis_title="Attendance band (%)", yaxis_title="Average score (%)")
    return _style(fig, 380, title)


def drivers_bar(drv: pd.DataFrame,
                title="What actually correlates with performance?") -> go.Figure:
    if drv.empty:
        return empty()
    d = drv.sort_values("correlation")
    d = d.assign(label=d["factor"].str.replace("_", " ").str.title())
    fig = go.Figure(go.Bar(
        x=d["correlation"], y=d["label"], orientation="h",
        marker=dict(color=np.where(d["correlation"] >= 0, "#00A86B", "#E03131")),
        text=d["correlation"].map(lambda v: f"{v:+.2f}"), textposition="outside",
        customdata=d["strength"],
        hovertemplate="<b>%{y}</b><br>r = %{x:+.2f} (%{customdata})<extra></extra>",
    ))
    fig.add_vline(x=0, line_color="#333")
    fig.update_layout(xaxis_title="Pearson correlation with overall score", yaxis_title=None,
                      xaxis_range=[-1, 1])
    return _style(fig, 420, title)


def section_comparison_bar(sec: pd.DataFrame,
                           title="Section league table") -> go.Figure:
    if sec.empty:
        return empty()
    d = sec.sort_values("avg_pct")
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=d["class_label"], y=d["avg_pct"], name="Avg score %",
                         marker=dict(color=d["avg_pct"], colorscale="RdYlGn", cmin=45, cmax=80),
                         text=d["avg_pct"].map(lambda v: f"{v:.1f}"), textposition="outside"))
    fig.add_trace(go.Scatter(x=d["class_label"], y=d["avg_attendance"], name="Attendance %",
                             mode="lines+markers", line=dict(color="#4C6FFF", width=2.5)),
                  secondary_y=True)
    fig.update_yaxes(title_text="Average score (%)", secondary_y=False)
    fig.update_yaxes(title_text="Attendance (%)", secondary_y=True, showgrid=False)
    fig.update_xaxes(tickangle=-35)
    return _style(fig, 440, title, legend_bottom=True)


def grade_comparison_bar(df: pd.DataFrame,
                         title="How this grade compares school-wide") -> go.Figure:
    if df.empty:
        return empty()
    d = df.groupby("grade_label").agg(avg=("overall_pct", "mean"),
                                     att=("attendance_pct", "mean"),
                                     n=("student_id", "count")).reset_index().round(2)
    fig = px.bar(d, x="grade_label", y="avg", text=d["avg"].map(lambda v: f"{v:.1f}%"),
                 color="avg", color_continuous_scale="Tealgrn",
                 labels={"grade_label": "", "avg": "Average score (%)"},
                 hover_data={"att": ":.1f", "n": True}, template=C.PLOTLY_TEMPLATE)
    fig.update_traces(textposition="outside")
    fig.update_layout(coloraxis_showscale=False)
    return _style(fig, 360, title)


def treemap_sections(df: pd.DataFrame,
                     title="Where the students are, coloured by average score") -> go.Figure:
    if df.empty:
        return empty()
    d = df.groupby(["campus", "section"]).agg(students=("student_id", "count"),
                                             avg=("overall_pct", "mean")).reset_index().round(2)
    fig = px.treemap(d, path=[px.Constant("Cohort"), "campus", "section"], values="students",
                     color="avg", color_continuous_scale="RdYlGn",
                     color_continuous_midpoint=d["avg"].mean(), template=C.PLOTLY_TEMPLATE)
    fig.update_traces(texttemplate="<b>%{label}</b><br>%{value} students<br>%{color:.1f}%")
    return _style(fig, 460, title)


# ---------------------------------------------------------------- per-student
def student_radar(profile: pd.DataFrame, name: str,
                  title="Subject profile vs. section & grade average") -> go.Figure:
    if profile.empty:
        return empty()
    cats = profile["subject_name"].tolist()
    close = lambda v: v + v[:1]  # noqa: E731  (radar needs a closed loop)
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(r=close(profile["final_subject_score"].tolist()),
                                  theta=close(cats), fill="toself", name=name,
                                  line=dict(color="#4C6FFF", width=2.5)))
    fig.add_trace(go.Scatterpolar(r=close(profile["section_subject_avg"].tolist()),
                                  theta=close(cats), name="Section avg",
                                  line=dict(color="#FFB020", dash="dash")))
    fig.add_trace(go.Scatterpolar(r=close(profile["grade_subject_avg"].tolist()),
                                  theta=close(cats), name="Grade avg",
                                  line=dict(color="#ADB5BD", dash="dot")))
    fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])))
    return _style(fig, 460, title, legend_bottom=True)


def student_vs_class_bar(profile: pd.DataFrame, name: str,
                         title="Student vs. class average, subject by subject") -> go.Figure:
    """The signature chart of the original report-generator project."""
    if profile.empty:
        return empty()
    d = profile.sort_values("final_subject_score", ascending=True)
    fig = go.Figure()
    fig.add_trace(go.Bar(y=d["subject_name"], x=d["final_subject_score"], name=name,
                         orientation="h", marker_color="#4C6FFF",
                         text=d["final_subject_score"].map(lambda v: f"{v:.1f}"),
                         textposition="outside"))
    fig.add_trace(go.Bar(y=d["subject_name"], x=d["section_subject_avg"], name="Section average",
                         orientation="h", marker_color="#FFB020", opacity=0.85,
                         text=d["section_subject_avg"].map(lambda v: f"{v:.1f}"),
                         textposition="outside"))
    fig.update_layout(barmode="group", xaxis_title="Score (%)", yaxis_title=None,
                      xaxis_range=[0, 112])
    return _style(fig, max(380, 46 * len(d) + 110), title, legend_bottom=True)


def student_exam_trend(marks: pd.DataFrame, student_id: str,
                       title="Exam-by-exam progression per subject") -> go.Figure:
    m = marks[marks["student_id"] == student_id]
    if m.empty:
        return empty()
    fig = px.line(m.sort_values("exam_date"), x="exam_type", y="pct", color="subject_name",
                  markers=True, category_orders={"exam_type": C.EXAM_TYPES},
                  labels={"exam_type": "", "pct": "Score (%)", "subject_name": "Subject"}, **PX_KW)
    fig.add_hline(y=C.PASS_MARK_PCT, line_dash="dot", line_color="#E03131")
    fig.update_traces(line=dict(width=2.5), marker=dict(size=8))
    return _style(fig, 420, title, legend_bottom=True)


def student_attendance_bars(attendance: pd.DataFrame, student_id: str,
                            title="Monthly attendance breakdown") -> go.Figure:
    a = attendance[attendance["student_id"] == student_id].sort_values("month_index")
    if a.empty:
        return empty()
    fig = go.Figure()
    for col, color, label in (("present_days", "#00A86B", "Present"),
                              ("late_days", "#FFB020", "Late"),
                              ("leave_days", "#4C6FFF", "Leave"),
                              ("absent_days", "#E03131", "Absent")):
        fig.add_trace(go.Bar(x=a["month_label"], y=a[col], name=label, marker_color=color))
    fig.update_layout(barmode="stack", yaxis_title="Days", xaxis_title=None)
    return _style(fig, 360, title, legend_bottom=True)


def student_percentile_gauge(row: pd.Series,
                             title="Percentile within the grade") -> go.Figure:
    val = float(row["percentile_in_grade"])
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=val,
        number={"suffix": "th pct"},
        delta={"reference": 50, "increasing": {"color": "#00A86B"}},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": "#4C6FFF"},
            "steps": [
                {"range": [0, C.IMPROVEMENT_PERCENTILE], "color": "#FFD8D8"},
                {"range": [C.IMPROVEMENT_PERCENTILE, 60], "color": "#FFF3CD"},
                {"range": [60, C.TOPPER_PERCENTILE], "color": "#D8ECFF"},
                {"range": [C.TOPPER_PERCENTILE, 100], "color": "#D3F9D8"},
            ],
            "threshold": {"line": {"color": "#212529", "width": 3}, "value": val},
        },
    ))
    return _style(fig, 300, title)


def student_ranking_position(df: pd.DataFrame, student_id: str,
                             title="Where this student sits in the cohort") -> go.Figure:
    if df.empty:
        return empty()
    me = df[df["student_id"] == student_id]
    if me.empty:
        return empty("Student not in the current selection")
    fig = go.Figure()
    fig.add_trace(go.Histogram(x=df["overall_pct"], nbinsx=40, name="Cohort",
                               marker_color="#CED4DA"))
    fig.add_vline(x=float(me.iloc[0]["overall_pct"]), line_color="#E03131", line_width=3,
                  annotation_text=f"{me.iloc[0]['name']}: {me.iloc[0]['overall_pct']:.1f}%",
                  annotation_position="top")
    fig.add_vline(x=df["overall_pct"].mean(), line_dash="dash", line_color="#4C6FFF",
                  annotation_text="cohort mean", annotation_position="bottom right")
    fig.update_layout(xaxis_title="Overall score (%)", yaxis_title="Students", showlegend=False)
    return _style(fig, 360, title)


def survey_profile(df: pd.DataFrame, row: pd.Series,
                   title="Habits vs. cohort median") -> go.Figure:
    cols = ["study_hours_per_day", "sleep_hours", "screen_time_hours",
            "extracurricular_hours", "motivation_level", "stress_level", "parent_involvement"]
    cols = [c for c in cols if c in df.columns]
    if not cols or df.empty:
        return empty()
    labels = [c.replace("_", " ").title() for c in cols]
    fig = go.Figure()
    fig.add_trace(go.Bar(y=labels, x=[float(row[c]) for c in cols], orientation="h",
                         name=str(row["name"]), marker_color="#845EF7"))
    fig.add_trace(go.Bar(y=labels, x=[float(df[c].median()) for c in cols], orientation="h",
                         name="Cohort median", marker_color="#CED4DA"))
    fig.update_layout(barmode="group", xaxis_title="Value")
    return _style(fig, 400, title, legend_bottom=True)


# --------------------------------------------------------------------- extras
def risk_scatter(df: pd.DataFrame,
                 title="Risk radar: score vs. risk score (bubble = days absent)") -> go.Figure:
    if df.empty:
        return empty()
    d = df.copy()
    d["absent_days"] = d["absent_days"].fillna(0).clip(lower=0)
    fig = px.scatter(d, x="overall_pct", y="risk_score", color="risk_level",
                     size="absent_days", size_max=28, opacity=0.7,
                     category_orders={"risk_level": ["Low", "Moderate", "High", "Critical"]},
                     color_discrete_map={"Low": "#00A86B", "Moderate": "#FFB020",
                                         "High": "#FF6B6B", "Critical": "#C92A2A"},
                     hover_data=["student_id", "name", "section", "attendance_pct",
                                 "submission_rate", "risk_reasons"],
                     labels={"overall_pct": "Overall score (%)", "risk_score": "Risk score (0-100)",
                             "risk_level": "Risk"},
                     template=C.PLOTLY_TEMPLATE)
    return _style(fig, 480, title, legend_bottom=True)


def parallel_bands(df: pd.DataFrame, sample: int = 800,
                   title="Multi-factor view of the cohort") -> go.Figure:
    if df.empty:
        return empty()
    d = df.sample(min(sample, len(df)), random_state=1)
    dims = [("attendance_pct", "Attendance %"), ("submission_rate", "Submission %"),
            ("study_hours_per_day", "Study h/day"), ("consistency_std", "Inconsistency"),
            ("overall_pct", "Overall %")]
    fig = go.Figure(go.Parcoords(
        line=dict(color=d["overall_pct"], colorscale="RdYlGn", showscale=True,
                  cmin=d["overall_pct"].min(), cmax=d["overall_pct"].max()),
        dimensions=[dict(label=lbl, values=d[col]) for col, lbl in dims if col in d.columns],
    ))
    return _style(fig, 440, title)


def gender_split(df: pd.DataFrame, title="Score distribution by gender") -> go.Figure:
    if df.empty:
        return empty()
    fig = px.violin(df, x="gender", y="overall_pct", color="gender", box=True, points=False,
                    labels={"gender": "", "overall_pct": "Overall score (%)"}, **PX_KW)
    fig.update_layout(showlegend=False)
    return _style(fig, 360, title)


def top_bottom_dumbbell(df: pd.DataFrame, n: int = 12,
                        title="Top vs. bottom students side by side") -> go.Figure:
    if df.empty:
        return empty()
    top = df.nlargest(n, "overall_pct")[["name", "overall_pct"]].assign(group="Top")
    bot = df.nsmallest(n, "overall_pct")[["name", "overall_pct"]].assign(group="Bottom")
    d = pd.concat([bot, top])
    fig = px.scatter(d, x="overall_pct", y="name", color="group", size_max=14,
                     color_discrete_map={"Top": "#00A86B", "Bottom": "#E03131"},
                     labels={"overall_pct": "Overall score (%)", "name": "", "group": ""},
                     template=C.PLOTLY_TEMPLATE)
    fig.update_traces(marker=dict(size=13, line=dict(width=1, color="white")))
    fig.add_vline(x=df["overall_pct"].mean(), line_dash="dash", line_color="#4C6FFF",
                  annotation_text="cohort mean")
    return _style(fig, max(420, 24 * len(d) + 110), title, legend_bottom=True)
