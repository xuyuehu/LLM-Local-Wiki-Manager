#!/usr/bin/env python3
"""
生成本地知识库的可视化图谱。

用法:
    python tools/build_graph.py               # 构建全量知识图谱
    python tools/build_graph.py --no-infer    # 跳过 LLM 的隐性语义关联预测 (执行更快)
    python tools/build_graph.py --open        # 构建完成后直接使用浏览器打开 graph.html

输出文件:
    graph/graph.json    — 节点和边的导出结构数据
    graph/graph.html    — 使用 vis.js 渲染的可交互页面

边关联类型说明:
    EXTRACTED   — 直接基于页面中的 [[wikilink]] 所产生的关联
    INFERRED    — Gemini 所预测揭示出来的隐藏关联
    AMBIGUOUS   — 低置信度下的可能性关联
"""

import re
import json
import hashlib
import argparse
import webbrowser
import os
from dotenv import load_dotenv
load_dotenv()
from pathlib import Path
from datetime import date

import google.generativeai as genai

try:
    import networkx as nx
    from networkx.algorithms import community as nx_community
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False
    print("提示: 尚未安装 networkx。因此基于 Louvain 的聚类算法被禁用。可使用 pip install networkx 补全。")

REPO_ROOT = Path(__file__).parent.parent
WIKI_DIR = REPO_ROOT / "wiki"
LOG_DIR = REPO_ROOT / "logs"

GRAPH_DIR = REPO_ROOT / "graph"
GRAPH_JSON = GRAPH_DIR / "graph.json"
GRAPH_HTML = GRAPH_DIR / "graph.html"
CACHE_FILE = GRAPH_DIR / ".cache.json"

WIKI_LOG = WIKI_DIR / "log.md"
SYSTEM_LOG = LOG_DIR / "log.md"

# 定义页面和节点的颜色映射
TYPE_COLORS = {
    "source": "#4CAF50",
    "concept": "#FF9800",
    "synthesis": "#9C27B0",
    "output": "#03A9F4",
    "unknown": "#9E9E9E",
}

EDGE_COLORS = {
    "EXTRACTED": "#555555",
    "INFERRED": "#FF5722",
    "AMBIGUOUS": "#BDBDBD",
}

def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""

def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()

def all_wiki_pages() -> list[Path]:
    return [p for p in WIKI_DIR.rglob("*.md")
            if p.name not in ("index.md", "log.md", "lint-report.md")]

def extract_wikilinks(content: str) -> list[str]:
    return list(set(re.findall(r'\[\[([^\]]+)\]\]', content)))

def extract_frontmatter_type(content: str) -> str:
    # 例如：以 type: 开头，推导它究竟是 source、concept、synthesis还是 output
    match = re.search(r'^type:\s*(\S+)', content, re.MULTILINE)
    if match:
        return match.group(1).strip('"\'')
    if "sources/" in content or "tags: [source" in content:
        return "source"
    if "tags: [concept" in content or "concepts/" in content:
        return "concept"
    return "unknown"

def page_id(path: Path) -> str:
    return path.relative_to(WIKI_DIR).as_posix().replace(".md", "")

def load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except (json.JSONDecodeError, IOError):
            return {}
    return {}

def save_cache(cache: dict):
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, indent=2))

def build_nodes(pages: list[Path]) -> list[dict]:
    nodes = []
    for p in pages:
        content = read_file(p)
        node_type = extract_frontmatter_type(content)
        if node_type == "unknown":
            # 根据其父层路径直接划分
            category = p.relative_to(WIKI_DIR).parts[0] if len(p.relative_to(WIKI_DIR).parts) > 1 else ""
            if category == "sources": node_type = "source"
            elif category == "concepts": node_type = "concept"
            elif category == "syntheses": node_type = "synthesis"
            elif category == "outputs": node_type = "output"

        title_match = re.search(r'^title:\s*"?([^"\n]+)"?', content, re.MULTILINE)
        label = title_match.group(1).strip() if title_match else p.stem
        
        category_match = re.search(r'^category:\s*"?([^"\n]+)"?', content, re.MULTILINE)
        node_category = category_match.group(1).strip() if category_match else ""

        nodes.append({
            "id": page_id(p),
            "label": label,
            "type": node_type,
            "category": node_category,
            "color": TYPE_COLORS.get(node_type, TYPE_COLORS["unknown"]),
            "path": str(p.relative_to(REPO_ROOT)),
        })
    return nodes

def build_extracted_edges(pages: list[Path]) -> list[dict]:
    stem_map = {p.stem.lower(): page_id(p) for p in pages}
    edges = []
    seen = set()
    for p in pages:
        content = read_file(p)
        src = page_id(p)
        for link in extract_wikilinks(content):
            target = stem_map.get(link.lower())
            if target and target != src:
                key = (src, target)
                if key not in seen:
                    seen.add(key)
                    edges.append({
                        "from": src,
                        "to": target,
                        "type": "EXTRACTED",
                        "color": EDGE_COLORS["EXTRACTED"],
                        "confidence": 1.0,
                    })
    return edges

def build_inferred_edges(pages: list[Path], existing_edges: list[dict], cache: dict) -> list[dict]:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("  无 GEMINI_API_KEY 环境变量，跳过推测式的逻辑关联生成。")
        return []
    
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    new_edges = []
    changed_pages = []
    for p in pages:
        content = read_file(p)
        h = sha256(content)
        if cache.get(str(p)) != h:
            changed_pages.append(p)
            cache[str(p)] = h

    if not changed_pages:
        print("  自上一次运行来没有新文件改动，跳过推演环节。")
        return []

    print(f"  正在预测与分析 {len(changed_pages)} 个变动内容的逻辑关联...")
    node_list = "\n".join(f"- {page_id(p)}" for p in pages)
    existing_edge_summary = "\n".join(f"- {e['from']} → {e['to']} (显性引用)" for e in existing_edges[:30])

    for p in changed_pages:
        content = read_file(p)[:2000] 
        src = page_id(p)

        prompt = f"""你现在负责增强一张网络知识图谱。请详细分析当前的这个 wiki 文件，并自动推导出其中潜藏和暗示的、但是并未真正由使用者手动利用双链明确拉出来的语义从属及关联。
当前主题文件: {src}
页面文本:
{content}

我们的整个知识库里目前包含的其他页面如下：
{node_list}

已经被直接用 wikilink 进行关联拉在一起的网络(以防过度重复推导):
{existing_edge_summary}

任务：只能并且只允许产生有效的纯 JSON 对象数组列表。为该页面与现存的其他哪些页面可能存在有价值的连接赋予其权重。
格式如下:
[
  {{"to": "要建立的关联目标的page-id", "relationship": "简短短语解释关联原因", "confidence": 0.0-1.0, "type": "INFERRED(如果是确定的) / AMBIGUOUS(如果不确定)"}}
]

要求:
- 不要包含已经处于显性关联的那些边
- 请判断是否高于 0.7 置信度，是的话归为 INFERRED。
- 如果没有任何建议，返回空列表 []
"""
        
        try:
            response = model.generate_content(prompt)
            raw = response.text.strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)

            inferred = json.loads(raw)
            for rel in inferred:
                if isinstance(rel, dict) and "to" in rel:
                    new_edges.append({
                        "from": src,
                        "to": rel["to"],
                        "type": rel.get("type", "INFERRED"),
                        "label": rel.get("relationship", ""),
                        "color": EDGE_COLORS.get(rel.get("type", "INFERRED"), EDGE_COLORS["INFERRED"]),
                        "confidence": rel.get("confidence", 0.7),
                    })
        except Exception:
            pass

    return new_edges


def detect_communities(nodes: list[dict], edges: list[dict]) -> dict[str, int]:
    if not HAS_NETWORKX: return {}

    G = nx.Graph()
    for n in nodes: G.add_node(n["id"])
    for e in edges: G.add_edge(e["from"], e["to"])

    if G.number_of_edges() == 0: return {}

    try:
        communities = nx_community.louvain_communities(G, seed=42)
        node_to_community = {}
        for i, comm in enumerate(communities):
            for node in comm:
                node_to_community[node] = i
        return node_to_community
    except Exception:
        return {}


COMMUNITY_COLORS = [
    "#E91E63", "#00BCD4", "#8BC34A", "#FF5722", "#673AB7",
    "#FFC107", "#009688", "#F44336", "#3F51B5", "#CDDC39",
]

def render_html(nodes: list[dict], edges: list[dict]) -> str:
    nodes_json = json.dumps(nodes, indent=2)
    edges_json = json.dumps(edges, indent=2)

    legend_items = "".join(
        f'<span style="background:{color};padding:3px 8px;margin:2px;border-radius:3px;font-size:12px">{t}</span>'
        for t, color in TYPE_COLORS.items() if t != "unknown"
    )

    unique_categories = sorted(list({n.get("category") for n in nodes if n.get("category")}))
    category_options = '<option value="">(全部分类 - 自由查看)</option>'
    for cat in unique_categories:
        category_options += f'<option value="{cat}">{cat}</option>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>知识库图谱概览</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
  body {{ margin: 0; background: #1a1a2e; font-family: sans-serif; color: #eee; }}
  #graph {{ width: 100vw; height: 100vh; }}
  #controls {{
    position: fixed; top: 10px; left: 10px; background: rgba(0,0,0,0.7);
    padding: 12px; border-radius: 8px; z-index: 10; max-width: 260px;
  }}
  #controls h3 {{ margin: 0 0 8px; font-size: 14px; }}
  #search {{ width: 100%; padding: 4px; margin-bottom: 8px; background: #333; color: #eee; border: 1px solid #555; border-radius: 4px; }}
  #info {{
    position: fixed; bottom: 10px; left: 10px; background: rgba(0,0,0,0.8);
    padding: 12px; border-radius: 8px; z-index: 10; max-width: 320px;
    display: none;
  }}
  #stats {{ position: fixed; top: 10px; right: 10px; background: rgba(0,0,0,0.7); padding: 10px; border-radius: 8px; font-size: 12px; }}
</style>
</head>
<body>
<div id="controls">
  <h3>Obsidian 知识库图谱总览</h3>
  <input id="search" type="text" placeholder="检索节点资源..." oninput="applyFilters()">
  <select id="categoryFilter" onchange="applyFilters()" style="width: 100%; padding: 4px; margin-bottom: 8px; background: #333; color: #eee; border: 1px solid #555; border-radius: 4px;">
    {category_options}
  </select>
  <div>{legend_items}</div>
  <div style="margin-top:8px;font-size:11px;color:#aaa">
    <span style="background:#555;padding:2px 6px;border-radius:3px;margin-right:4px">──</span> 明确引用双链<br>
    <span style="background:#FF5722;padding:2px 6px;border-radius:3px;margin-right:4px">──</span> LLM深度推测补全
  </div>
</div>
<div id="graph"></div>
<div id="info">
  <b id="info-title"></b><br>
  <span id="info-type" style="font-size:12px;color:#aaa"></span><br>
  <span id="info-path" style="font-size:11px;color:#666"></span>
</div>
<div id="stats"></div>
<script>
const nodes = new vis.DataSet({nodes_json});
const edges = new vis.DataSet({edges_json});

const container = document.getElementById("graph");
const network = new vis.Network(container, {{ nodes, edges }}, {{
  nodes: {{
    shape: "dot",
    size: 13,
    font: {{ color: "#eee", size: 14, face: 'sans-serif' }},
    borderWidth: 2,
  }},
  edges: {{
    width: 1.2,
    smooth: {{ type: "continuous" }},
    arrows: {{ to: {{ enabled: true, scaleFactor: 0.5 }} }},
  }},
  physics: {{
    stabilization: {{ iterations: 150 }},
    barnesHut: {{ gravitationalConstant: -9000, springLength: 140 }},
  }},
  interaction: {{ hover: true, tooltipDelay: 200 }},
}});

network.on("click", params => {{
  if (params.nodes.length > 0) {{
    const node = nodes.get(params.nodes[0]);
    document.getElementById("info").style.display = "block";
    document.getElementById("info-title").textContent = node.label;
    
    let infoType = "类别类型：" + node.type;
    if (node.category) {{
      infoType += " | 概念层级：" + node.category;
    }}
    document.getElementById("info-type").textContent = infoType;
    document.getElementById("info-path").textContent = "文件路径：" + node.path;
  }} else {{
    document.getElementById("info").style.display = "none";
  }}
}});

document.getElementById("stats").textContent =
  `共收录 ${{nodes.length}} 个页面节点，连接了 ${{edges.length}} 条关系。`;

function applyFilters() {{
  const q = document.getElementById("search").value.toLowerCase();
  const cat = document.getElementById("categoryFilter").value;
  nodes.forEach(n => {{
    let matchSearch = !q || n.label.toLowerCase().includes(q) || n.id.toLowerCase().includes(q);
    let matchCat = !cat || n.category === cat;
    nodes.update({{ id: n.id, opacity: (matchSearch && matchCat) ? 1 : 0.15 }});
  }});
}}
</script>
</body>
</html>"""


def append_log(entry: str):
    existing_wiki = read_file(WIKI_LOG)
    WIKI_LOG.write_text(entry.strip() + "\n\n" + existing_wiki, encoding="utf-8")
    existing_sys = read_file(SYSTEM_LOG)
    SYSTEM_LOG.write_text(entry.strip() + "\n\n" + existing_sys, encoding="utf-8")


def build_graph(infer: bool = True, open_browser: bool = False):
    pages = all_wiki_pages()
    today = date.today().isoformat()

    if not pages:
        print("知识库没有文件内容。")
        return

    print(f"正在进行知识图谱运算 ({len(pages)} 节点)...")
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)

    cache = load_cache()

    print("  一阶段：提取基础连接...")
    nodes = build_nodes(pages)
    edges = build_extracted_edges(pages)
    print(f"  > 检测到了 {len(edges)} 条显性双链关系")

    if infer:
        print("  二阶段：分析潜在关联...")
        inferred = build_inferred_edges(pages, edges, cache)
        edges.extend(inferred)
        print(f"  > 新捕获到了 {len(inferred)} 条推演出来的联系")
        save_cache(cache)

    print("  计算群落分布...")
    communities = detect_communities(nodes, edges)
    for node in nodes:
        comm_id = communities.get(node["id"], -1)
        if comm_id >= 0:
            node["color"] = COMMUNITY_COLORS[comm_id % len(COMMUNITY_COLORS)]
        node["group"] = comm_id

    graph_data = {"nodes": nodes, "edges": edges, "built": today}
    GRAPH_JSON.write_text(json.dumps(graph_data, indent=2))
    print(f"  已记录图谱数据: graph/graph.json")

    html = render_html(nodes, edges)
    GRAPH_HTML.write_text(html, encoding="utf-8")
    print(f"  生成的页面地图已保存: graph/graph.html")

    append_log(f"## [{today}] graph | 更新了知识图谱数据\n\n统计到 {len(nodes)} 个节点，{len(edges)} 份边关系 ({len([e for e in edges if e['type']=='EXTRACTED'])} 项直接关联, {len([e for e in edges if e['type']=='INFERRED'])} 项分析得出)。")

    if open_browser:
        webbrowser.open(f"file://{GRAPH_HTML.resolve()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="绘制分析全部知识和双向链接形成可视化地图")
    parser.add_argument("--no-infer", action="store_true", help="由于 AI 访问慢或太贵，跳过预测。")
    parser.add_argument("--open", action="store_true", help="运算结束后在默认浏览器展示报告网页。")
    args = parser.parse_args()
    build_graph(infer=not args.no_infer, open_browser=args.open)
