from __future__ import annotations

import html
from collections import Counter, deque

import networkx as nx
import plotly.graph_objects as go


COLORS = {"document": "#2563eb", "page": "#0891b2", "chunk": "#64748b", "entity": "#d97706"}


def _safe(value, length=500):
    return html.escape(str(value)[:length], quote=True)


def _provenance(data):
    return "<br>".join(f"{label}: {_safe(data[key])}" for key, label in (
        ("source", "Source"), ("page", "Page"), ("grade_band", "Grade band"),
        ("extraction_kind", "Extraction"), ("evidence", "Evidence"),
    ) if data.get(key) not in (None, ""))


def evidence_graph(graph, chunks=None, document_ids=None, compact=False):
    if chunks is not None:
        chunk_ids = {"chunk:" + c["id"] for c in chunks}
        pages = {(c["document_id"], c["page"]) for c in chunks}
        documents = {c["document_id"] for c in chunks}
        selected = set(chunk_ids)
        for node in chunk_ids & set(graph):
            selected.update(graph.successors(node))
        selected.update(node for node, attrs in graph.nodes(data=True)
                        if (attrs.get("kind") == "document" and attrs.get("id") in documents)
                        or (attrs.get("kind") == "page" and (attrs.get("document_id"), attrs.get("page")) in pages))
        view = graph.subgraph(selected).copy()
        for u, v, key, attrs in list(view.edges(keys=True, data=True)):
            if (attrs.get("document_id"), attrs.get("page")) not in pages:
                view.remove_edge(u, v, key)
    elif document_ids is not None:
        view = nx.MultiDiGraph()
        for u, v, key, attrs in graph.edges(keys=True, data=True):
            if attrs.get("document_id") in document_ids:
                view.add_node(u, **graph.nodes[u])
                view.add_node(v, **graph.nodes[v])
                view.add_edge(u, v, key=key, **attrs)
    else:
        view = graph.copy()
    if compact:
        for node, attrs in list(view.nodes(data=True)):
            if attrs.get("kind") != "chunk":
                continue
            parents = [p for p in view.predecessors(node) if view.nodes[p].get("kind") == "page"]
            for _, target, edge in list(view.out_edges(node, data=True)):
                for parent in parents:
                    view.add_edge(parent, target, **dict(edge, chunk_id=attrs.get("id")))
            view.remove_node(node)
    return view


def select_graph_view(graph, focus="", max_nodes=120):
    cap = max(1, min(int(max_nodes), 500))
    if graph is None or not len(graph):
        return nx.MultiDiGraph()
    ordered = sorted(graph.nodes, key=str)
    needle = str(focus).strip().casefold()
    matches = [node for node in ordered if needle and needle in (
        str(graph.nodes[node].get("label", "")) + " " + str(graph.nodes[node].get("text", "")) + " " + str(node)).casefold()]
    if needle and not matches:
        return graph.subgraph([]).copy()
    seeds = sorted(matches, key=lambda n: (str(graph.nodes[n].get("label", "")).casefold() != needle,
                                          graph.nodes[n].get("kind") != "entity", str(n))) if needle else [
        n for n in ordered if graph.nodes[n].get("kind") in ("document", "entity")]
    queue = deque((n, 0) for n in (seeds or ordered[:1]))
    selected, seen = [], set()
    while queue and len(selected) < cap:
        node, depth = queue.popleft()
        if node in seen:
            continue
        seen.add(node)
        selected.append(node)
        if needle and depth >= 2:
            continue
        adjacent = set(graph.neighbors(node))
        if graph.is_directed():
            adjacent.update(graph.predecessors(node))
        queue.extend((n, depth + 1) for n in sorted(adjacent, key=str) if n not in seen)
    return graph.subgraph(selected).copy()


def graph_figure(graph, focus: str = "", max_nodes: int = 120) -> go.Figure:
    """Bounded deterministic view; mentions are not asserted relationships."""
    cap = max(1, min(int(max_nodes), 500))
    figure = go.Figure()
    figure.update_layout(
        template="plotly_white", height=650, margin=dict(l=15, r=15, t=55, b=25),
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        hovermode="closest", showlegend=True,
        legend=dict(orientation="h", y=-0.02),
        title="PDF provenance and relationships",
    )
    if graph is None or graph.number_of_nodes() == 0:
        figure.add_annotation(text="Upload a PDF to explore its provenance graph.",
                              x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False)
        return figure
    needle = str(focus).strip().casefold()
    view = select_graph_view(graph, focus, cap)
    if not len(view):
        figure.add_annotation(text="No matching evidence nodes. Clear or broaden the focus.",
                              x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False)
        return figure
    kinds = [kind for kind in ("document", "page", "chunk", "entity")
             if any(attrs.get("kind") == kind for _, attrs in view.nodes(data=True))]
    positions = {}
    for x, kind in enumerate(kinds):
        nodes = sorted((n for n in view if view.nodes[n].get("kind") == kind),
                       key=lambda n: (str(view.nodes[n].get("document_id", "")), view.nodes[n].get("page", 0), str(n)))
        for row, node in enumerate(nodes):
            positions[node] = (x * 2, (len(nodes) - 1) / 2 - row)
    for node in view:
        positions.setdefault(node, (len(kinds) * 2, 0))
    figure.update_layout(height=max(650, min(1400, 38 * max(Counter(d.get("kind") for _, d in view.nodes(data=True)).values()))))
    edges = sorted(view.edges(data=True), key=lambda item: (
        str(item[0]), str(item[1]), str(item[2].get("kind", "")),
        str(item[2].get("relation", "")), str(item[2].get("evidence", "")),
    ))[:4000]
    styles = {
        "contains": ("Document structure", "#cbd5e1", "solid"),
        "mentions": ("Text mentions (not assertions)", "#d97706", "dot"),
        "llm_assertion": ("LLM-extracted assertions (verify)", "#7c3aed", "dash"),
        "explicit_relation": ("Explicit reporting line in PDF", "#0f766e", "solid"),
    }
    for kind, (label, color, dash) in styles.items():
        xs, ys, hover_x, hover_y, hover = [], [], [], [], []
        for source, target, data in edges:
            if data.get("kind", "contains") != kind:
                continue
            x0, y0 = positions[source]
            x1, y1 = positions[target]
            xs.extend([x0, x1, None])
            ys.extend([y0, y1, None])
            hover_x.append((x0 + x1) / 2)
            hover_y.append((y0 + y1) / 2)
            hover.append(
                f"{_safe(view.nodes[source].get('label', source), 100)} → "
                f"{_safe(view.nodes[target].get('label', target), 100)}<br>"
                f"{_safe(data.get('relation', kind))}<br>{_provenance(data)}"
            )
        if xs:
            figure.add_trace(go.Scatter(x=xs, y=ys, mode="lines", name=label,
                                       line=dict(color=color, width=1.4, dash=dash), hoverinfo="skip"))
            figure.add_trace(go.Scatter(x=hover_x, y=hover_y, mode="markers", showlegend=False,
                                       marker=dict(size=9, color=color, opacity=0.3), text=hover,
                                       hovertemplate="%{text}<extra></extra>"))
    for kind in sorted({str(data.get("kind", "entity")) for _, data in view.nodes(data=True)}):
        nodes = sorted((n for n in view if str(view.nodes[n].get("kind", "entity")) == kind), key=str)
        labels, hover = [], []
        for node in nodes:
            data = view.nodes[node]
            label = data.get("label", node)
            labels.append(_safe(label, 32) if kind != "chunk" else "")
            detail = _provenance(data)
            if kind == "chunk":
                detail += "<br>Text: " + _safe(data.get("text", ""))
            hover.append(f"<b>{_safe(label, 100)}</b><br>Type: {_safe(kind)}<br>{detail}")
        figure.add_trace(go.Scatter(
            x=[positions[n][0] for n in nodes], y=[positions[n][1] for n in nodes],
            mode="markers+text", name=_safe(kind.title()), text=labels, textposition="top center",
            hovertext=hover, hovertemplate="%{hovertext}<extra></extra>",
            marker=dict(size=16 if kind == "document" else 10, color=COLORS.get(kind, "#64748b"),
                        line=dict(width=1, color="white")), textfont=dict(size=10),
        ))
    suffix = f"Showing {len(view)} of {graph.number_of_nodes()} nodes"
    if needle:
        suffix += f" · Focus: {_safe(focus, 70)}"
    figure.update_layout(title=f"PDF provenance and relationships<br><sup>{suffix}</sup>")
    return figure
