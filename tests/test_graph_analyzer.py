import pytest
from pathlib import Path
from src.analytics.graph_analyzer import GraphAnalyzer


@pytest.fixture
def analyzer():
    return GraphAnalyzer(profiles_path="data/processed/profiles.json")


def test_build_graph(analyzer):
    G = analyzer.build_graph()
    assert G.number_of_nodes() == 10
    assert G.number_of_edges() >= 13

    # Check node attributes
    for node, data in G.nodes(data=True):
        assert "name" in data
        assert "department" in data
        assert "job_title" in data
        assert "skills" in data

    # Check edge attributes
    for u, v, data in G.edges(data=True):
        assert "weight" in data
        assert "relationship_type" in data
        assert data["weight"] > 0


def test_centralities(analyzer):
    analyzer.build_graph()
    centralities = analyzer.compute_centralities()

    assert "metrics_per_node" in centralities
    assert "key_influencers" in centralities

    metrics = centralities["metrics_per_node"]
    assert len(metrics) == 10

    for node, m in metrics.items():
        assert 0.0 <= m["degree_centrality"] <= 1.0
        assert 0.0 <= m["betweenness_centrality"] <= 1.0
        assert 0.0 <= m["closeness_centrality"] <= 1.0

    # Top broker / bridge check
    top_broker = centralities["key_influencers"]["top_broker_bridge"]
    assert top_broker is not None
    assert top_broker[1]["betweenness_centrality"] > 0.0


def test_clustering(analyzer):
    analyzer.build_graph()
    clusters = analyzer.cluster_roles_and_skills(n_clusters=3)

    assert "kmeans" in clusters
    assert "graph_communities" in clusters

    kmeans_res = clusters["kmeans"]
    assert kmeans_res["n_clusters"] == 3
    assert len(kmeans_res["cluster_assignments"]) == 10
    assert -1.0 <= kmeans_res["silhouette_score"] <= 1.0

    communities = clusters["graph_communities"]["communities"]
    assert len(communities) >= 2


def test_export_analysis(analyzer, tmp_path):
    analyzer.build_graph()
    out_json = tmp_path / "graph_analysis.json"
    rel_json = tmp_path / "relationships.json"
    graph_json = tmp_path / "graph.json"
    report_md = tmp_path / "report.md"

    res = analyzer.export_analysis(
        output_json_path=str(out_json),
        relationships_json_path=str(rel_json),
        graph_json_path=str(graph_json),
        report_md_path=str(report_md),
    )

    assert out_json.exists()
    assert rel_json.exists()
    assert graph_json.exists()
    assert report_md.exists()
    assert res["graph_summary"]["total_nodes"] == 10

    # Validate graph.json structure
    import json
    with open(graph_json, "r", encoding="utf-8") as f:
        gdata = json.load(f)
    assert "nodes" in gdata
    assert "edges" in gdata
    assert len(gdata["nodes"]) == 10
    assert len(gdata["edges"]) >= 13
    for node in gdata["nodes"]:
        assert "id" in node
        assert "name" in node
        assert "job_title" in node
        assert "department" in node
        assert "cluster_id" in node
        assert "centrality" in node
        assert "degree" in node["centrality"]
        assert "betweenness" in node["centrality"]
        assert "closeness" in node["centrality"]

    # Validate report.md
    with open(report_md, "r", encoding="utf-8") as f:
        report_text = f.read()
    assert "Anthony Moi" in report_text
    assert "Betweenness" in report_text
    assert "خوشه‌بندی" in report_text


def test_visualize_graph(analyzer, tmp_path):
    analyzer.build_graph()
    png_path = tmp_path / "graph.png"
    result = analyzer.visualize_graph(output_png_path=str(png_path))
    assert result == str(png_path)
    assert png_path.exists()
    assert png_path.stat().st_size > 10000
