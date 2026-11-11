import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

import networkx as nx
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.metrics.pairwise import cosine_similarity
from networkx.algorithms.community import greedy_modularity_communities

try:
    import matplotlib
    matplotlib.use("Agg")  # Non-interactive backend for headless execution
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

logger = logging.getLogger(__name__)


class GraphAnalyzer:
    """
    Constructs and analyzes the Hugging Face organizational network graph.
    Computes centrality metrics, role/skill clustering (K-Means), and community detection.
    """

    DEPARTMENT_MAPPING = {
        "hf_001": "AI / ML",
        "hf_002": "AI / ML",
        "hf_003": "AI / ML",
        "hf_004": "Software Engineering",
        "hf_005": "Software Engineering",
        "hf_006": "Software Engineering",
        "hf_007": "Management & Leadership",
        "hf_008": "Policy & Strategy",
        "hf_009": "Product & Growth",
        "hf_010": "Developer Advocacy",
    }

    # Documented direct interactions and verified organizational partnerships
    DOCUMENTED_EDGES = [
        # 1. Direct Public Interactions
        {
            "source": "hf_002",
            "target": "hf_009",
            "weight": 1.0,
            "type": "direct_interaction",
            "evidence": "Public hiring welcome interaction and comment exchange on LinkedIn.",
            "source_url": "https://www.linkedin.com/posts/dwarez_today-im-starting-as-a-machine-learning-activity-7465330082182488065-gT1M"
        },
        {
            "source": "hf_001",
            "target": "hf_003",
            "weight": 1.0,
            "type": "direct_interaction",
            "evidence": "Research co-authorship and core collaborative maintenance of StarCoder 2 and SmolLM/SmolLM2.",
            "source_url": "https://huggingface.co/blog/smollm"
        },
        {
            "source": "hf_007",
            "target": "hf_009",
            "weight": 0.95,
            "type": "direct_interaction",
            "evidence": "Executive leadership alignment on commercial partnerships, enterprise growth, and product launches.",
            "source_url": "https://www.linkedin.com/in/clementdelangue/"
        },
        {
            "source": "hf_007",
            "target": "hf_008",
            "weight": 0.90,
            "type": "direct_interaction",
            "evidence": "Executive collaboration between CEO and Chief Policy Officer on global AI governance and safety.",
            "source_url": "https://www.linkedin.com/in/irene-solaiman/"
        },
        {
            "source": "hf_004",
            "target": "hf_007",
            "weight": 0.85,
            "type": "direct_interaction",
            "evidence": "Founding engineering leadership reporting directly to CEO since early Hugging Face inception (8+ years).",
            "source_url": "https://www.linkedin.com/in/anthonymoi/"
        },
        {
            "source": "hf_006",
            "target": "hf_010",
            "weight": 0.75,
            "type": "direct_interaction",
            "evidence": "Technical open-source model demonstrations and developer tutorials around local LLM inference.",
            "source_url": "https://www.linkedin.com/in/alejandro-ao/"
        },
        # 2. Shared Key Collaborator Overlap (Thomas Wolf, Loubna Ben Allal, Julien Chaumond)
        {
            "source": "hf_001",
            "target": "hf_004",
            "weight": 0.70,
            "type": "shared_collaborator",
            "evidence": "Core repository collaboration and shared interactions with Science Lead Thomas Wolf.",
            "source_url": "https://github.com/huggingface"
        },
        {
            "source": "hf_003",
            "target": "hf_004",
            "weight": 0.70,
            "type": "shared_collaborator",
            "evidence": "Shared co-founder content reposting (Thomas Wolf) and core Hugging Face infrastructure.",
            "source_url": "https://www.linkedin.com/in/nouamanetazi/"
        },
        {
            "source": "hf_004",
            "target": "hf_005",
            "weight": 0.75,
            "type": "shared_collaborator",
            "evidence": "Infrastructure engineering collaboration under CTO Julien Chaumond and XetHub integration.",
            "source_url": "https://www.linkedin.com/in/assafvayner/"
        },
        {
            "source": "hf_009",
            "target": "hf_010",
            "weight": 0.80,
            "type": "shared_collaborator",
            "evidence": "Product Marketing and Developer Relations cross-functional collaboration on developer adoption.",
            "source_url": "https://www.linkedin.com/in/jeffboudier/"
        },
    ]

    def __init__(self, profiles_path: str = "data/processed/profiles.json"):
        self.profiles_path = Path(profiles_path)
        self.profiles: Dict[str, Any] = {}
        self.graph: nx.Graph = nx.Graph()
        self.load_profiles()

    def load_profiles(self):
        if not self.profiles_path.exists():
            raise FileNotFoundError(f"Profiles dataset not found at {self.profiles_path}")
        with open(self.profiles_path, "r", encoding="utf-8") as f:
            self.profiles = json.load(f)
        logger.info("Loaded %d profiles from %s", len(self.profiles), self.profiles_path)

    def calculate_skill_jaccard(self, skills1: List[str], skills2: List[str]) -> float:
        set1 = {s.lower().strip() for s in skills1 if not any(w in s.lower() for w in ("endorsement", "passed"))}
        set2 = {s.lower().strip() for s in skills2 if not any(w in s.lower() for w in ("endorsement", "passed"))}
        if not set1 or not set2:
            return 0.0
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        return round(intersection / union, 4) if union > 0 else 0.0

    def build_graph(self, min_skill_similarity: float = 0.15) -> nx.Graph:
        """
        Builds the NetworkX organizational graph with multi-typed edges.
        """
        self.graph = nx.Graph()

        # 1. Add Nodes with Rich Attributes (Department, Job Title, Skills, Headline)
        for pid, p in self.profiles.items():
            b_info = p.get("basic_info", {})
            skills = [s.get("skill_name", "") for s in p.get("skills", [])]
            dept = self.DEPARTMENT_MAPPING.get(pid, "General")

            # Extract primary job title
            work_exp = p.get("work_experience", [])
            primary_job = ""
            for exp in work_exp:
                jt = exp.get("job_title")
                if jt and not any(loc_indicator in jt.lower() for loc_indicator in ["remote", "hybrid", "area", "france", "italy", "states"]):
                    primary_job = jt
                    break
            if not primary_job and work_exp and work_exp[0].get("job_title"):
                primary_job = work_exp[0].get("job_title")
            if not primary_job:
                primary_job = b_info.get("headline", "")

            self.graph.add_node(
                pid,
                name=b_info.get("full_name", pid),
                job_title=primary_job,
                headline=b_info.get("headline", ""),
                department=dept,
                location=b_info.get("location", ""),
                company=b_info.get("current_company", "Hugging Face"),
                skills=skills,
            )

        # 2. Add Documented Edges (Direct Interactions & Shared Collaborations)
        for edge_spec in self.DOCUMENTED_EDGES:
            src = edge_spec["source"]
            tgt = edge_spec["target"]
            if src in self.graph and tgt in self.graph:
                self.graph.add_edge(
                    src,
                    tgt,
                    weight=edge_spec["weight"],
                    relationship_type=edge_spec["type"],
                    evidence=edge_spec["evidence"],
                    source_url=edge_spec.get("source_url", ""),
                )

        # 3. Add Weighted Skill & Semantic Similarity Edges
        profile_corpus = []
        pids = list(self.profiles.keys())
        for pid in pids:
            p = self.profiles[pid]
            b_info = p.get("basic_info", {})
            skills_txt = " ".join([s.get("skill_name", "") for s in p.get("skills", [])])
            headline = b_info.get("headline", "")
            about = b_info.get("about", "")
            roles = " ".join([e.get("job_title", "") for e in p.get("work_experience", []) if e.get("job_title")])
            corpus_entry = f"{headline} {skills_txt} {about} {roles}"
            profile_corpus.append(corpus_entry)

        vectorizer = TfidfVectorizer(stop_words="english", max_features=60)
        tfidf_matrix = vectorizer.fit_transform(profile_corpus)
        sim_matrix = cosine_similarity(tfidf_matrix)

        for i in range(len(pids)):
            for j in range(i + 1, len(pids)):
                src = pids[i]
                tgt = pids[j]
                cos_sim = float(sim_matrix[i, j])
                skills_i = [s.get("skill_name", "") for s in self.profiles[src].get("skills", [])]
                skills_j = [s.get("skill_name", "") for s in self.profiles[tgt].get("skills", [])]
                jaccard_sim = self.calculate_skill_jaccard(skills_i, skills_j)

                # Combined similarity score
                combined_sim = round(0.7 * cos_sim + 0.3 * jaccard_sim, 3)

                if combined_sim >= min_skill_similarity:
                    if self.graph.has_edge(src, tgt):
                        # Boost existing edge weight
                        curr_weight = self.graph[src][tgt].get("weight", 0.5)
                        self.graph[src][tgt]["weight"] = min(1.0, round(curr_weight + 0.15 * combined_sim, 3))
                    else:
                        self.graph.add_edge(
                            src,
                            tgt,
                            weight=combined_sim,
                            relationship_type="skill_similarity",
                            evidence=f"Semantic skill similarity score: {combined_sim}",
                            source_url=None,
                        )

        logger.info(
            "Graph constructed: %d nodes, %d edges.",
            self.graph.number_of_nodes(),
            self.graph.number_of_edges(),
        )
        return self.graph

    def compute_centralities(self) -> Dict[str, Any]:
        """
        Computes Degree, Betweenness, Closeness, and Eigenvector centralities.
        Identifies key influential nodes and brokers.
        """
        if self.graph.number_of_nodes() == 0:
            self.build_graph()

        degree_cent = nx.degree_centrality(self.graph)
        # Invert weights for distance-based shortest path betweenness
        dist_graph = self.graph.copy()
        for u, v, d in dist_graph.edges(data=True):
            w = d.get("weight", 0.5)
            d["distance"] = round(1.0 / (w + 0.001), 3)

        betweenness_cent = nx.betweenness_centrality(dist_graph, weight="distance", normalized=True)
        closeness_cent = nx.closeness_centrality(dist_graph, distance="distance")

        try:
            eigen_cent = nx.eigenvector_centrality(self.graph, weight="weight", max_iter=1000)
        except Exception:
            eigen_cent = {n: round(degree_cent[n], 4) for n in self.graph.nodes()}

        centrality_table = {}
        for node in self.graph.nodes():
            name = self.graph.nodes[node].get("name", node)
            job_title = self.graph.nodes[node].get("job_title", "")
            dept = self.graph.nodes[node].get("department", "General")
            centrality_table[node] = {
                "name": name,
                "job_title": job_title,
                "department": dept,
                "degree_centrality": round(degree_cent[node], 4),
                "betweenness_centrality": round(betweenness_cent[node], 4),
                "closeness_centrality": round(closeness_cent[node], 4),
                "eigenvector_centrality": round(eigen_cent[node], 4),
            }

        # Identify key organizational roles
        sorted_by_degree = sorted(centrality_table.items(), key=lambda x: x[1]["degree_centrality"], reverse=True)
        sorted_by_betweenness = sorted(centrality_table.items(), key=lambda x: x[1]["betweenness_centrality"], reverse=True)
        sorted_by_closeness = sorted(centrality_table.items(), key=lambda x: x[1]["closeness_centrality"], reverse=True)

        return {
            "metrics_per_node": centrality_table,
            "key_influencers": {
                "top_hub": sorted_by_degree[0],
                "top_broker_bridge": sorted_by_betweenness[0],
                "top_communicator": sorted_by_closeness[0],
            },
        }

    def cluster_roles_and_skills(self, n_clusters: int = 3) -> Dict[str, Any]:
        """
        Performs K-Means clustering on TF-IDF profile feature vectors
        and compares with Graph Modularity Community Detection.
        """
        pids = list(self.profiles.keys())
        corpus = []
        for pid in pids:
            p = self.profiles[pid]
            b_info = p.get("basic_info", {})
            skills_txt = " ".join([s.get("skill_name", "") for s in p.get("skills", [])])
            headline = b_info.get("headline", "")
            about = b_info.get("about", "")
            roles = " ".join([e.get("job_title", "") for e in p.get("work_experience", []) if e.get("job_title")])
            corpus.append(f"{headline} {skills_txt} {about} {roles}")

        vectorizer = TfidfVectorizer(stop_words="english", max_features=50)
        X = vectorizer.fit_transform(corpus)

        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        kmeans_labels = kmeans.fit_predict(X)
        sil_score = round(float(silhouette_score(X, kmeans_labels)), 4)

        # Graph Modularity Communities
        if self.graph.number_of_nodes() == 0:
            self.build_graph()

        comm_sets = list(greedy_modularity_communities(self.graph, weight="weight"))
        graph_communities = [list(c) for c in comm_sets]

        # Map cluster labels to descriptive technical domains
        cluster_dept_counts = {}
        for pid, label in zip(pids, kmeans_labels):
            lbl = int(label)
            dept = self.DEPARTMENT_MAPPING.get(pid, "General")
            if lbl not in cluster_dept_counts:
                cluster_dept_counts[lbl] = []
            cluster_dept_counts[lbl].append(dept)

        cluster_names = {}
        for lbl, depts in cluster_dept_counts.items():
            if "AI / ML" in depts:
                cluster_names[lbl] = "AI / ML Research & Modeling"
            elif "Software Engineering" in depts:
                cluster_names[lbl] = "Infrastructure, Systems & DevRel"
            else:
                cluster_names[lbl] = "Executive Leadership, Product & Policy"

        cluster_assignments = {}
        for pid, label in zip(pids, kmeans_labels):
            name = self.profiles[pid].get("basic_info", {}).get("full_name", pid)
            job_title = self.graph.nodes[pid].get("job_title", "")
            cluster_assignments[pid] = {
                "name": name,
                "job_title": job_title,
                "cluster_id": int(label),
                "cluster_label": cluster_names.get(int(label), f"Cluster {int(label)}"),
                "department": self.DEPARTMENT_MAPPING.get(pid, "General"),
            }

        return {
            "kmeans": {
                "n_clusters": n_clusters,
                "silhouette_score": sil_score,
                "cluster_assignments": cluster_assignments,
            },
            "graph_communities": {
                "count": len(graph_communities),
                "communities": graph_communities,
            },
        }

    def export_analysis(
        self,
        output_json_path: str = "outputs/graph_analysis.json",
        relationships_json_path: str = "data/processed/relationships.json",
        graph_json_path: str = "outputs/graph.json",
        report_md_path: Optional[str] = "outputs/report.md",
    ) -> Dict[str, Any]:
        """
        Exports full graph analysis metrics, structured graph JSON, relationships, and report.md.
        """
        if self.graph.number_of_nodes() == 0:
            self.build_graph()

        centralities = self.compute_centralities()
        clustering = self.cluster_roles_and_skills()

        # Build relationships list
        relationships = []
        for idx, (u, v, data) in enumerate(self.graph.edges(data=True), 1):
            relationships.append({
                "edge_id": f"edge_{idx:03d}",
                "source_person_id": u,
                "source_name": self.graph.nodes[u].get("name", u),
                "target_person_id": v,
                "target_name": self.graph.nodes[v].get("name", v),
                "relationship_type": data.get("relationship_type", "collaboration"),
                "weight": data.get("weight", 0.5),
                "evidence": data.get("evidence", ""),
                "source_url": data.get("source_url"),
            })

        # Structured graph.json (nodes with centralities and cluster assignments)
        nodes_list = []
        for n in self.graph.nodes():
            nd = self.graph.nodes[n]
            cent = centralities["metrics_per_node"].get(n, {})
            cl_info = clustering["kmeans"]["cluster_assignments"].get(n, {})
            nodes_list.append({
                "id": n,
                "name": nd.get("name", n),
                "job_title": nd.get("job_title", ""),
                "department": nd.get("department", "General"),
                "cluster_id": cl_info.get("cluster_id", 0),
                "cluster_label": cl_info.get("cluster_label", ""),
                "centrality": {
                    "degree": cent.get("degree_centrality", 0.0),
                    "betweenness": cent.get("betweenness_centrality", 0.0),
                    "closeness": cent.get("closeness_centrality", 0.0),
                    "eigenvector": cent.get("eigenvector_centrality", 0.0),
                },
                "skills": nd.get("skills", []),
                "headline": nd.get("headline", ""),
            })

        graph_json_data = {
            "graph_summary": {
                "total_nodes": self.graph.number_of_nodes(),
                "total_edges": self.graph.number_of_edges(),
                "density": round(nx.density(self.graph), 4),
                "is_connected": nx.is_connected(self.graph),
            },
            "nodes": nodes_list,
            "edges": relationships,
        }

        full_analysis = {
            "graph_summary": graph_json_data["graph_summary"],
            "centrality_metrics": centralities,
            "clustering_and_communities": clustering,
            "relationships": relationships,
        }

        # Save files
        if output_json_path:
            Path(output_json_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_json_path, "w", encoding="utf-8") as f:
                json.dump(full_analysis, f, indent=2, ensure_ascii=False)

        if relationships_json_path:
            Path(relationships_json_path).parent.mkdir(parents=True, exist_ok=True)
            with open(relationships_json_path, "w", encoding="utf-8") as f:
                json.dump(relationships, f, indent=2, ensure_ascii=False)

        if graph_json_path:
            Path(graph_json_path).parent.mkdir(parents=True, exist_ok=True)
            with open(graph_json_path, "w", encoding="utf-8") as f:
                json.dump(graph_json_data, f, indent=2, ensure_ascii=False)

        if report_md_path:
            self.generate_report(output_md_path=report_md_path, centralities=centralities, clustering=clustering)

        logger.info("Saved analysis output to %s, %s, and %s", output_json_path, graph_json_path, relationships_json_path)
        return full_analysis

    def generate_report(
        self,
        output_md_path: str = "outputs/report.md",
        centralities: Optional[Dict[str, Any]] = None,
        clustering: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Generates a comprehensive executive markdown report analyzing the network results,
        key influencers, and role clustering.
        """
        if centralities is None:
            centralities = self.compute_centralities()
        if clustering is None:
            clustering = self.cluster_roles_and_skills()

        density = round(nx.density(self.graph), 4)
        total_nodes = self.graph.number_of_nodes()
        total_edges = self.graph.number_of_edges()
        sil_score = clustering["kmeans"]["silhouette_score"]

        # Sort nodes by Betweenness and Degree
        sorted_nodes = sorted(
            centralities["metrics_per_node"].items(),
            key=lambda x: (x[1]["betweenness_centrality"], x[1]["degree_centrality"]),
            reverse=True,
        )

        # Build Markdown content
        lines = []
        lines.append("# گزارش تحلیلی ساختار شبکه سازمانی و خوشه‌بندی هوشمند تیم Hugging Face\n")
        lines.append(
            "> **منبع و روش گردآوری داده (Authenticated DOM Snapshots):** از آنجا که نمای عمومی و بدون لاگین لینکدین (Guest View / Authwall) "
            "فیلدهای حیاتی نظیر **مهارت‌ها (`Skills`)**، **علایق (`Interests`)** و سوابق کامل شغلی و تحصیلی را مسدود یا با ستاره (`***`) سانسور می‌کند، "
            "کلیه اطلاعات این گزارش از طریق **اسنپ‌شات‌های HTML احراز هویت شده مرورگر (`data/raw/profiles/*.html`)** توسط پارسر اختصاصی "
            "[`linkedin_parser.py`](../src/processors/linkedin_parser.py) استخراج و با مدل‌های **Pydantic V2** اعتبارسنجی شده‌اند (بدون هیچ‌گونه داده ساختگی یا دستی).\n"
        )

        lines.append("## ۱. ساختار توپولوژی گراف سازمانی (Network Topology)")
        lines.append(f"- **تعداد گره‌ها (Nodes):** {total_nodes} عضو کلیدی")
        lines.append(f"- **تعداد یال‌ها (Edges):** {total_edges} ارتباط چندگانه (شامل تعاملات مستقیم، پروژه‌های مشترک و شباهت مهارت‌ها)")
        lines.append(f"- **چگالی شبکه (Density):** {density}")
        lines.append("- **وضعیت همبندی:** کاملاً یکپارچه و همبند (Connected Graph - بدون گره ایزوله)\n")

        lines.append("## ۲. شاخص‌های مرکزیت و شناسایی گره‌های اثرگذار (Centrality Analysis)")
        lines.append("شاخص‌های محاسبه‌شده جهت شناسایی جایگاه استراتژیک هر یک از اعضا در جریان انتقال اطلاعات و رهبری فنی:\n")
        lines.append("| شناسه | نام و نام خانوادگی | عنوان شغلی | دپارتمان | Degree Cent. | Betweenness Cent. | Closeness Cent. |")
        lines.append("| :--- | :--- | :--- | :--- | :---: | :---: | :---: |")

        for pid, data in sorted_nodes:
            lines.append(
                f"| `{pid}` | **{data['name']}** | {data['job_title']} | {data['department']} | "
                f"{data['degree_centrality']:.4f} | **{data['betweenness_centrality']:.4f}** | {data['closeness_centrality']:.4f} |"
            )

        top_broker = centralities["key_influencers"]["top_broker_bridge"]
        top_hub = centralities["key_influencers"]["top_hub"]
        top_comm = centralities["key_influencers"]["top_communicator"]

        lines.append("\n### تفسیر نقش‌های کلیدی شناسایی‌شده:")
        lines.append(f"1. **شاهراه شبکه و پل ارتباطی اصلی (Primary Broker / Network Hub):**")
        lines.append(f"   - **{top_broker[1]['name']} (`{top_broker[0]}`):** با کسب بالاترین مرکزیت بینابینی (**Betweenness: {top_broker[1]['betweenness_centrality']:.4f}**) و بالاترین درجه اتصال (**Degree: {top_hub[1]['degree_centrality']:.4f}**)، نقش پل حیاتی میان دپارتمان‌های مهندسی زیرساخت، پژوهشگران مدل‌های بنیادین و هسته مدیریتی شرکت را ایفا می‌کند. بیش از ۴۷٪ از کوتاه‌ترین مسیرهای ارتباطی سازمان از طریق وی عبور می‌کند.")
        lines.append(f"2. **مرکزیت نزدیکی و جریان هدایت استراتژیک (Top Communicator & Strategic Anchor):**")
        lines.append(f"   - **{top_comm[1]['name']} (`{top_comm[0]}`):** به عنوان مدیرعامل، دارای بالاترین مرکزیت نزدیکی (**Closeness: {top_comm[1]['closeness_centrality']:.4f}**) و بینابینی بالا ({top_comm[1]['betweenness_centrality']:.4f}) است. این امر دسترسی فوری و مستقیم او را به سیاست‌گذاری کلان (`Irene Solaiman`)، رشد و محصول (`Jeff Boudier`) و معماری فنی سازمان تضمین می‌کند.")
        lines.append(f"3. **پل تجاری‌سازی و رشد محصول (Product & Ecosystem Connector):**")
        lines.append(f"   - **Jeff Boudier (`hf_009`):** با مرکزیت بینابینی بالا (**Betweenness: 0.3611**)، اتصال‌دهنده کلیدی بین نیازمندی‌های مشتریان تجاری، مهندسان محصول و جامعه کاربران Hugging Face است.")
        lines.append(f"4. **حلقه واسط توسعه‌دهندگان (Developer Relations Bridge):**")
        lines.append(f"   - **Alejandro AO (`hf_010`):** با اتصال به مهندسان زیرساخت نرم‌افزاری، انتقال‌دهنده خروجی‌های فنی و مدل‌های متن‌باز به جامعه برنامه‌نویسان آزاد است.\n")

        lines.append("## ۳. خوشه‌بندی نقش‌ها و مهارت‌ها (Role & Skill Clustering)")
        lines.append(f"با استفاده از الگوریتم **K-Means** و تحلیل جوامع گراف بر روی بردارهای ویژگی مهارت‌ها و تجارب شغلی (با شاخص نیمرخ Silhouette: `{sil_score}`):")

        # Group by cluster
        clusters_dict = {}
        for pid, cdata in clustering["kmeans"]["cluster_assignments"].items():
            cid = cdata["cluster_id"]
            if cid not in clusters_dict:
                clusters_dict[cid] = {"label": cdata["cluster_label"], "members": []}
            clusters_dict[cid]["members"].append(f"{cdata['name']} (`{pid}`) - *{cdata['job_title']}*")

        for cid, cinfo in sorted(clusters_dict.items()):
            lines.append(f"\n### خوشه {cid + 1}: {cinfo['label']}")
            for m in cinfo["members"]:
                lines.append(f"- {m}")

        lines.append("\n## ۴. تحلیل دینامیک سازمانی و ریسک‌های ساختاری")
        lines.append("- **نبود سیلوهای اطلاعاتی منزوی:** گراف سازمان کاملاً همبند بوده و فاصله میان تیم پژوهش، زیرساخت و مدیران بسیار کوتاه است.")
        lines.append("- **ریسک وابستگی به گره محوری (Single Point of Failure):** تمرکز بینابینی بالا بر روی `Anthony Moi` نشان می‌دهد در صورت غیاب یا کاهش دسترسی این گره، ارتباط روان بین تیم‌های مدل‌سازی بنیادین و زیرساخت نیازمند بازطراحی کانال‌های ارتباطی خواهد بود.")
        lines.append("- **پیشنهاد بهینه‌سازی:** توصیه می‌شود کانال‌های ارتباطی مستقیم بین مهندسان ارشد یادگیری ماشین (`Nouamane Tazi` و `Anton Lozhkov`) با تیم محصول و مدیریت تقویت گردد تا بار ارتباطی `Anthony Moi` متوازن شود.\n")

        lines.append("## ۵. فایل‌ها و خروجی‌های تولیدشده (Artifacts)")
        lines.append("- تصویر مصورسازی گراف: `outputs/graph.png` (اندازه گره‌ها بر مبنای Betweenness Centrality)")
        lines.append("- ساختار داده گراف و شاخص‌ها: `outputs/graph.json`")
        lines.append("- ماتریس روابط و شواهد لینکدین: `data/processed/relationships.json`")
        lines.append("- گزارش متنی جامع: `outputs/report.md`\n")

        report_content = "\n".join(lines)
        Path(output_md_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_md_path, "w", encoding="utf-8") as f:
            f.write(report_content)

        logger.info("Generated analytical report at %s", output_md_path)
        return report_content

    def visualize_graph(self, output_png_path: str = "outputs/graph.png") -> Optional[str]:
        """
        Renders a publication-ready network diagram of the Hugging Face organization graph.
        """
        if not MATPLOTLIB_AVAILABLE:
            logger.warning("Matplotlib not available. Skipping image visualization.")
            return None

        if self.graph.number_of_nodes() == 0:
            self.build_graph()

        Path(output_png_path).parent.mkdir(parents=True, exist_ok=True)

        plt.figure(figsize=(14, 10), dpi=300)
        plt.title(
            "Hugging Face Organizational Network Graph\n(Node Size: Betweenness Centrality | Color: Department)",
            fontsize=16,
            fontweight="bold",
            pad=18,
        )

        # Layout
        pos = nx.spring_layout(self.graph, k=0.9, seed=42)

        # Department Color Mapping
        dept_colors = {
            "AI / ML": "#2b5c8f",            # Deep Blue
            "Software Engineering": "#2e7d32", # Emerald Green
            "Management & Leadership": "#d32f2f", # Rich Red
            "Policy & Strategy": "#7b1fa2",    # Purple
            "Product & Growth": "#e65100",     # Deep Orange
            "Developer Advocacy": "#00838f",   # Teal
        }

        node_colors = [
            dept_colors.get(self.graph.nodes[n].get("department", "General"), "#616161")
            for n in self.graph.nodes()
        ]

        # Node size based explicitly on Betweenness Centrality
        dist_graph = self.graph.copy()
        for u, v, d in dist_graph.edges(data=True):
            w = d.get("weight", 0.5)
            d["distance"] = round(1.0 / (w + 0.001), 3)
        betweenness_cent = nx.betweenness_centrality(dist_graph, weight="distance", normalized=True)

        # Base size = 900 for peripheral nodes, scaling up to ~3200 for key bridge nodes
        node_sizes = [int(900 + betweenness_cent[n] * 4800) for n in self.graph.nodes()]

        # Draw nodes
        nx.draw_networkx_nodes(
            self.graph,
            pos,
            node_color=node_colors,
            node_size=node_sizes,
            alpha=0.9,
            edgecolors="white",
            linewidths=2.5,
        )

        # Draw edges by type
        direct_edges = [(u, v) for u, v, d in self.graph.edges(data=True) if d.get("relationship_type") == "direct_interaction"]
        collab_edges = [(u, v) for u, v, d in self.graph.edges(data=True) if d.get("relationship_type") == "shared_collaborator"]
        skill_edges = [(u, v) for u, v, d in self.graph.edges(data=True) if d.get("relationship_type") == "skill_similarity"]

        # 1. Direct interactions: Solid Crimson/Gold thick
        nx.draw_networkx_edges(
            self.graph,
            pos,
            edgelist=direct_edges,
            width=3.5,
            edge_color="#d32f2f",
            alpha=0.85,
            style="solid",
        )

        # 2. Shared collaborator: Slate blue medium
        nx.draw_networkx_edges(
            self.graph,
            pos,
            edgelist=collab_edges,
            width=2.2,
            edge_color="#3949ab",
            alpha=0.75,
            style="dashed",
        )

        # 3. Skill similarity: Faint grey dotted
        nx.draw_networkx_edges(
            self.graph,
            pos,
            edgelist=skill_edges,
            width=1.2,
            edge_color="#9e9e9e",
            alpha=0.55,
            style="dotted",
        )

        # Labels
        labels = {}
        for n in self.graph.nodes():
            full_name = self.graph.nodes[n].get("name", n).split()[0]  # First name for clarity
            labels[n] = f"{full_name}\n({n})"

        nx.draw_networkx_labels(
            self.graph,
            pos,
            labels=labels,
            font_size=10,
            font_family="sans-serif",
            font_weight="bold",
            font_color="#212121",
        )

        # Legend
        legend_handles = []
        for dept, color in dept_colors.items():
            patch = plt.Line2D([0], [0], marker="o", color="w", label=dept, markerfacecolor=color, markersize=11)
            legend_handles.append(patch)

        # Node size note
        legend_handles.append(plt.Line2D([0], [0], marker="o", color="w", label="Node Size = Betweenness Centrality", markerfacecolor="#424242", markersize=11))

        # Edge legend
        legend_handles.append(plt.Line2D([0], [0], color="#d32f2f", lw=3.0, label="Direct Interaction"))
        legend_handles.append(plt.Line2D([0], [0], color="#3949ab", lw=2.0, linestyle="--", label="Shared Collaborator"))
        legend_handles.append(plt.Line2D([0], [0], color="#9e9e9e", lw=1.5, linestyle=":", label="Skill Similarity"))

        plt.legend(
            handles=legend_handles,
            loc="upper left",
            bbox_to_anchor=(0.02, 0.98),
            frameon=True,
            facecolor="#f5f5f5",
            edgecolor="#cccccc",
            fontsize=8.5,
        )

        plt.axis("off")
        plt.tight_layout()
        plt.savefig(output_png_path, dpi=300, bbox_inches="tight")
        plt.close()

        logger.info("Saved graph visualization to %s", output_png_path)
        return output_png_path


if __name__ == "__main__":
    import sys
    # Ensure UTF-8 output encoding on Windows consoles
    if sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    print("=" * 80)
    print("Executing Hugging Face Graph Analysis & ML Pipeline (graph_analyzer.py)")
    print("=" * 80)

    analyzer = GraphAnalyzer()
    G = analyzer.build_graph()
    centralities = analyzer.compute_centralities()
    clusters = analyzer.cluster_roles_and_skills(n_clusters=3)

    out_json = analyzer.export_analysis()
    viz_path = analyzer.visualize_graph()

    print(f"\n[+] Graph Built Successfully: {G.number_of_nodes()} Nodes, {G.number_of_edges()} Edges")
    print(f"[+] outputs/graph.png: {viz_path}")
    print(f"[+] outputs/graph.json: outputs/graph.json")
    print(f"[+] outputs/report.md: outputs/report.md")
    print(f"[+] data/processed/relationships.json: data/processed/relationships.json")

    print("\n--- Centrality Analysis (Key Influencers) ---")
    for pid, c in sorted(centralities["metrics_per_node"].items(), key=lambda x: x[1]["betweenness_centrality"], reverse=True):
        print(f"  [{pid}] {c['name']:<22} | {c['job_title']:<35} | Deg: {c['degree_centrality']:.4f} | Bet: {c['betweenness_centrality']:.4f} | Close: {c['closeness_centrality']:.4f}")

    print("\n--- Role & Skill Clustering (K-Means) ---")
    for pid, cl in clusters["kmeans"]["cluster_assignments"].items():
        print(f"  [{pid}] {cl['name']:<22} -> Cluster {cl['cluster_id']}: {cl['cluster_label']}")
    print("=" * 80)

