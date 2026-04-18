# 🧠 LLM Local Wiki Manager

基于大语言模型（Gemini API）和 Markdown 打造的全自动化、本地化知识库管理助手脚手架。
专为 Obsidian、Logseq 或任何支持 Markdown 的本地知识库软件设计，帮助您实现知识的 **自动萃取、自动分类、自动图谱链接及自动总结输出**。

## 🌟 核心特性

- **📥 知识萃取 (Ingest)**：自动将零散的文献（Markdown 或 PDF）提取出核心论点，结构化归档入库。
- **🔍 智能检索与综合 (Query)**：自然语言提问，AI 将查阅您的整个知识库，并提供带有准确来源引用的总结。
- **🩺 知识库体检 (Lint)**：自动检测知识库中的矛盾点、孤立页面和未文档化的概念缺失。
- **🕸 自动化关系图谱 (Graph)**：由 AI 推导概念间未直接声明的隐性联系，快速建立并弹出一个属于您本地知识的三维互联图。
- **📤 定向产出 (Output)**：从已有知识网中抽取结构化内容，直接生成对外演讲的大纲、Q&A 问答或成体系的学习报告。
- **🗂 目录收纳降噪 (Organize)**：像一名严格的图书管理员，用大语言模型梳理归档您的乱七八糟的源文件及词条到预先设定的类别中。

---

## 🛠 安装与部署

本工具包主要通过 Python 在您的终端（Terminal）运行脚本。数据均保留在您自己的机器本地。

### 1. 环境准备

确保您的电脑上已安装 **Python 3.8+**。然后在工作目录下安装所需依赖：

```bash
pip install -r requirements.txt
```

### 2. 配置 API Key

打开提供的 `.env.example`，将其重命名为 `.env`。
然后，进入 [Google AI Studio](https://aistudio.google.com/app/apikey) 申请一个免费的 Gemini API Key，并将其填入 `.env` 文件中：

```env
GEMINI_API_KEY="您的_API_KEY"
```

> **注意：** `.env` 文件已经被加入到 `.gitignore` 中，您大可放心将此工程放到您的私有 GitHub 等代码托管平台上，API Key 不会遭到泄露。

---

## 🚀 终端操作指令总览

请在包含 `tools/` 的主工作目录（也是您的 Obsidian Vault 仓库主目录）下调出终端，执行以下自动化脚本：

### 1. 录入与萃取新知识
自动解析放入 `raw/` 中的源资料文本或 PDF 并完成结构化建档。
```bash
# 单文件自动处理提取
python3 tools/ingest.py raw/测试笔记.md

# 批量文件夹自动化提取，处理后自动沉淀源文件
python3 tools/ingest.py raw/new
```

### 2. 自动聚合解答与问答生成
用自然语言提问您的第二大脑。
```bash
python3 tools/query.py "当前知识库涵盖的主要信息节点有哪些？"
```

### 3. 长篇报告与工作成果投产
不仅帮你找知识，更帮你写输出物。
```bash
# 自动生成学习笔记摘要
python3 tools/output.py "提取知识库中某一核心概念的完整笔记" --type notes

# 生成用于演讲汇报的逐点结构
python3 tools/output.py "整理核心数据的分析报告演示文档" --type presentation
```

### 4. 知识库健康诊断与防腐
检查断裂的双向链接、孤岛页面以及 AI 所能察觉到的内容深层矛盾。
```bash
python3 tools/lint.py --save
```

### 5. 一键建立并查看隐式交互关系图谱
AI 根据文本上下文自动推断知识卡片之间的连接。
```bash
python3 tools/build_graph.py --open
```

### 6. 一键分类、归档、降噪
当您的概念词条增多，或收集的原始文献混乱不堪时。
```bash
# 规整概念词条
python3 tools/organize_folders.py 

# 规整杂乱的初始资料
python3 tools/organize_raw.py
```

---

## 📂 推荐的知识库目录架构

为获得最佳自动化体验，建议您的库遵循此规范：

```text
您的知识库目录/
├── raw/               # 您收集来的原始文献（只读存放）
│   └── new/           # 未处理的新文献丢进这里
├── wiki/              # 结构化知识库（AI 管理核心区）
│   ├── overview.md    # 核心总览摘要
│   ├── concepts/      # AI 汲取出来的信息专有名词与概念卡片
│   ├── sources/       # AI 读取 raw 后的提炼结构化摘要页
│   └── syntheses/     # query 工具生成的综合分析固定保存地
├── outputs/           # output 工具生成的成果对外分发展示区
├── graph/             # 关系图缓存与展示网页
└── tools/             # 本工具包所有的 Python 引擎代码
```

## 🤝 贡献与修改许可

您可以在 `tools/organize_folders.py` 以及 `tools/categorize.py` 脚本上方自定义修改属于您**特定业务**的 12 级分类逻辑树，目前默认代码中提供了一个通用的分类体系：如“基础理论”、“业务场景”等。

欢迎 Fork 此工具包，探索使用更强大的局部大语言模型（如 Llama 3）进行完全断网的私有化部署。
