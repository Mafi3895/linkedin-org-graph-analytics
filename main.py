"""
================================================================================
Hugging Face Organizational Network & ML Analysis Pipeline
Unified Execution Script (main.py)
================================================================================
Description:
    Reads raw LinkedIn HTML snapshots (data/raw/profiles/*.html), parses and validates
    profiles via Pydantic schemas, constructs the multi-relational organizational graph,
    computes centrality metrics (Degree, Betweenness, Closeness), performs role & skill
    clustering (K-Means & Modularity), and exports all artifacts to outputs/:
      - outputs/graph.png: Publication-ready network visualization (Node size = Betweenness Centrality)
      - outputs/graph.json: Complete node & edge topology with centrality & cluster metadata
      - outputs/report.md: Concise executive report interpreting network dynamics
      - outputs/graph_analysis.json: Full metrics and community breakdown
      - data/processed/relationships.json: Verified relationship matrix
================================================================================
"""

import sys
import os
import json
import logging
from pathlib import Path

# Ensure UTF-8 output encoding across Windows consoles
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.collectors.linkedin_collector import LinkedInCollector
from src.analytics.graph_analyzer import GraphAnalyzer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main_pipeline")

PROFILES_REGISTRY = [
    {"person_id": "hf_001", "name": "Anton Lozhkov", "url": "https://www.linkedin.com/in/anton-lozhkov/"},
    {"person_id": "hf_002", "name": "Dario Salvati", "url": "https://www.linkedin.com/in/dwarez/"},
    {"person_id": "hf_003", "name": "Nouamane Tazi", "url": "https://www.linkedin.com/in/nouamanetazi/"},
    {"person_id": "hf_004", "name": "Anthony Moi", "url": "https://www.linkedin.com/in/anthonymoi/"},
    {"person_id": "hf_005", "name": "Assaf Vayner", "url": "https://www.linkedin.com/in/assafvayner/"},
    {"person_id": "hf_006", "name": "Xuan-Son Nguyen", "url": "https://www.linkedin.com/in/ngxson/"},
    {"person_id": "hf_007", "name": "Clément Delangue", "url": "https://www.linkedin.com/in/clementdelangue/"},
    {"person_id": "hf_008", "name": "Irene Solaiman", "url": "https://www.linkedin.com/in/irene-solaiman/"},
    {"person_id": "hf_009", "name": "Jeff Boudier", "url": "https://www.linkedin.com/in/jeffboudier/"},
    {"person_id": "hf_010", "name": "Alejandro AO", "url": "https://www.linkedin.com/in/alejandro-ao/"},
]


def run_pipeline():
    print("=" * 80)
    print(" Hugging Face Organizational Network & ML Analysis Pipeline")
    print("=" * 80)

    raw_dir = Path("data/raw/profiles")
    processed_dir = Path("data/processed")
    outputs_dir = Path("outputs")

    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # Stage 1: Read & Parse Raw Data Snapshots
    # -------------------------------------------------------------------------
    print("\n[Phase 1/4] Reading raw profile snapshots and validating schema...")
    collector = LinkedInCollector(
        raw_data_dir=str(raw_dir),
        processed_data_dir=str(processed_dir),
        timeout=15,
    )

    available_snapshots = []
    for item in PROFILES_REGISTRY:
        pid = item["person_id"]
        raw_file = raw_dir / f"{pid}.html"
        if raw_file.exists():
            available_snapshots.append(item)
        else:
            logger.warning("Raw snapshot missing for %s at %s", pid, raw_file)

    if not available_snapshots:
        raise FileNotFoundError(f"No raw profile snapshots found in {raw_dir}")

    print(f"  -> Found {len(available_snapshots)} / {len(PROFILES_REGISTRY)} raw HTML snapshots.")
    for item in available_snapshots:
        collector.collect_and_save(
            person_id=item["person_id"],
            profile_url=item["url"],
            use_cached_raw=True,
        )
    print(f"  -> Successfully processed and saved profile records to '{processed_dir}'.")

    # -------------------------------------------------------------------------
    # Stage 2: Organizational Graph Construction
    # -------------------------------------------------------------------------
    print("\n[Phase 2/4] Constructing organizational network graph...")
    profiles_dataset_path = processed_dir / "profiles.json"
    analyzer = GraphAnalyzer(profiles_path=str(profiles_dataset_path))
    G = analyzer.build_graph(min_skill_similarity=0.15)

    density = round(float(G.number_of_edges() / (G.number_of_nodes() * (G.number_of_nodes() - 1) / 2)), 4)
    print(f"  -> Graph Topology: {G.number_of_nodes()} Nodes, {G.number_of_edges()} Edges")
    print(f"  -> Network Density: {density}")

    # -------------------------------------------------------------------------
    # Stage 3: Centrality Metrics & ML Clustering
    # -------------------------------------------------------------------------
    print("\n[Phase 3/4] Computing centrality measures and ML clustering...")
    centralities = analyzer.compute_centralities()
    clusters = analyzer.cluster_roles_and_skills(n_clusters=3)

    key_influencers = centralities["key_influencers"]
    print(f"  -> Top Network Hub (Degree):      {key_influencers['top_hub'][1]['name']} ({key_influencers['top_hub'][0]})")
    print(f"  -> Top Broker / Bridge:           {key_influencers['top_broker_bridge'][1]['name']} ({key_influencers['top_broker_bridge'][0]})")
    print(f"  -> Top Communicator (Closeness):   {key_influencers['top_communicator'][1]['name']} ({key_influencers['top_communicator'][0]})")
    print(f"  -> K-Means Clustering: {clusters['kmeans']['n_clusters']} clusters (Silhouette Score: {clusters['kmeans']['silhouette_score']})")

    # -------------------------------------------------------------------------
    # Stage 4: Export All Visual and Textual Artifacts to outputs/
    # -------------------------------------------------------------------------
    print("\n[Phase 4/4] Generating and exporting all outputs to 'outputs/'...")

    # 1. Structured graph.json and analysis
    analyzer.export_analysis(
        output_json_path=str(outputs_dir / "graph_analysis.json"),
        relationships_json_path=str(processed_dir / "relationships.json"),
        graph_json_path=str(outputs_dir / "graph.json"),
        report_md_path=str(outputs_dir / "report.md"),
    )

    # 2. Visual network graph (node size based on Betweenness Centrality)
    png_path = analyzer.visualize_graph(output_png_path=str(outputs_dir / "graph.png"))

    # -------------------------------------------------------------------------
    # Execution Summary
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print(" Pipeline Execution Complete - Generated Artifacts:")
    print("=" * 80)
    print(f"  [1] outputs/graph.png   -> Publication network diagram (Node size = Betweenness Centrality)")
    print(f"  [2] outputs/graph.json  -> Nodes, edges, centrality scores, and cluster IDs")
    print(f"  [3] outputs/report.md   -> Executive analytical report with role interpretations")
    print(f"  [4] outputs/graph_analysis.json -> Full statistical and community breakdown")
    print(f"  [5] data/processed/relationships.json -> Verified relationship evidence matrix")

    print("\n--- Centrality Ranking (Top Influencers) ---")
    sorted_nodes = sorted(
        centralities["metrics_per_node"].items(),
        key=lambda x: (x[1]["betweenness_centrality"], x[1]["degree_centrality"]),
        reverse=True,
    )
    for pid, c in sorted_nodes:
        print(f"  [{pid}] {c['name']:<22} | {c['job_title']:<38} | Deg: {c['degree_centrality']:.4f} | Bet: {c['betweenness_centrality']:.4f} | Close: {c['closeness_centrality']:.4f}")

    print("\n--- Functional Technical Clusters ---")
    for pid, cl in clusters["kmeans"]["cluster_assignments"].items():
        print(f"  [{pid}] {cl['name']:<22} -> Cluster {cl['cluster_id']}: {cl['cluster_label']}")

    print("=" * 80)
    return {
        "graph": G,
        "centralities": centralities,
        "clusters": clusters,
        "outputs": {
            "graph_png": outputs_dir / "graph.png",
            "graph_json": outputs_dir / "graph.json",
            "report_md": outputs_dir / "report.md",
        },
    }


if __name__ == "__main__":
    run_pipeline()
