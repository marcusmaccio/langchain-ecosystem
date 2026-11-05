# LangChain Ecosystem (`langchain-ecosystem`)

An umbrella repository organizing practical, hands-on projects across all three layers of the **LangChain Inc.** agent stack — **LangChain**, **LangGraph**, and **DeepAgents** — running locally on Apple Silicon via **LM Studio** (`qwen3.8-27b-uncensored-mlx`).

> **Centralized Documentation Hub**: All conceptual guides, *Learning on the Job* notes, and architectural deep dives are organized inside **[`docs/`](docs/README.md)**, mirroring the exact project directory structure.

---

## Repository & Documentation Structure

```text
langchain-ecosystem/
├── README.md                                  # Global ecosystem overview & subproject index (this file)
├── docs/                                      # Centralized documentation mirroring the subprojects
│   ├── README.md                              # Documentation Hub & 3-Layer Stack Overview
│   ├── langchain/
│   │   ├── lca-single-agent/                  # Stage 1 Learning Guide & Architecture
│   │   └── lca-two-agents/                    # Stage 2 Learning Guide & Architecture
│   ├── langgraph/
│   │   └── lca-langgraph-agents/              # Stage 3 Learning Guide & Architecture
│   └── deepagents/
│       ├── deep-agents-example/               # DeepAgents Bank Reconciliation Docs
│       └── lca-deepagents/                    # LangChain Academy DeepAgents Docs
│
├── langchain/                                 # Layer 1: Pure LangChain v1.x Agents & Tools
│   ├── lca-single-agent/                      # Stage 1 Subproject: Bank Transaction Agent (BTA)
│   └── lca-two-agents/                        # Stage 2 Subproject: Reused BTA + Accounting Agent (AA)
├── langgraph/                                 # Layer 2: Stateful Multi-Agent Graph Orchestration
│   └── lca-langgraph-agents/                  # Stage 3 Subproject: LangGraph StateGraph (BTA -> AA)
└── deepagents/                                # Layer 3: Autonomous Agent Harness on top of LangGraph
    ├── deep-agents-example/                   # Subproject: Multi-Agent Bank Reconciliation Harness
    └── lca-deepagents/                        # Subproject: LangChain Academy DeepAgents Course
```

---

## Overview of the Subprojects & Interactive Archify Diagrams

- **Live GitHub Pages Architecture Portal**: [**`https://marcusmaccio.github.io/langchain-ecosystem/`**](https://marcusmaccio.github.io/langchain-ecosystem/)
- **Global Ecosystem Archify Diagram**: [**Open Live Diagram**](https://marcusmaccio.github.io/langchain-ecosystem/langchain-ecosystem-architecture.html) | [Local HTML](docs/langchain-ecosystem-architecture.html)

| Subproject | Framework Layer | Project README | Detailed Docs (`docs/`) | Live Interactive Archify Diagram (GitHub Pages) |
| :--- | :--- | :--- | :--- | :--- |
| **[`lca-single-agent`](langchain/lca-single-agent/)** | **Layer 1: `langchain`** (Stage 1) | [`README.md`](langchain/lca-single-agent/README.md) | [`docs/langchain/lca-single-agent/`](docs/langchain/lca-single-agent/README.md) | [**Open Stage 1 Diagram**](https://marcusmaccio.github.io/langchain-ecosystem/langchain/lca-single-agent/lca-single-agent-architecture.html) |
| **[`lca-two-agents`](langchain/lca-two-agents/)** | **Layer 1: `langchain`** (Stage 2) | [`README.md`](langchain/lca-two-agents/README.md) | [`docs/langchain/lca-two-agents/`](docs/langchain/lca-two-agents/README.md) | [**Open Stage 2 Diagram**](https://marcusmaccio.github.io/langchain-ecosystem/langchain/lca-two-agents/lca-two-agents-architecture.html) |
| **[`lca-langgraph-agents`](langgraph/lca-langgraph-agents/)** | **Layer 2: `langgraph`** (Stage 3) | [`README.md`](langgraph/lca-langgraph-agents/README.md) | [`docs/langgraph/lca-langgraph-agents/`](docs/langgraph/lca-langgraph-agents/README.md) | [**Open Stage 3 Diagram**](https://marcusmaccio.github.io/langchain-ecosystem/langgraph/lca-langgraph-agents/lca-langgraph-agents-architecture.html) |
| **[`deep-agents-example`](deepagents/deep-agents-example/)** | **Layer 3: `deepagents`** | [`README.md`](deepagents/deep-agents-example/README.md) | [`docs/deepagents/deep-agents-example/`](docs/deepagents/deep-agents-example/README.md) | [**Open Layer 3 Diagram**](https://marcusmaccio.github.io/langchain-ecosystem/deepagents/deep-agents-example/deep-agents-example-architecture.html) |
| **[`lca-deepagents`](deepagents/lca-deepagents/)** | **Layer 3: `deepagents`** | [`README.md`](deepagents/lca-deepagents/README.md) | [`docs/deepagents/lca-deepagents/`](docs/deepagents/lca-deepagents/README.md) | — |

---

## Quick Start Across Stages 1 $\rightarrow$ 3

```bash
# Stage 1 — Single Agent (BTA Standalone)
cd /Users/marcomaccio/Documents/development/personal/langchain-ecosystem/langchain/lca-single-agent
uv run python main.py "/Users/marcomaccio/Library/CloudStorage/GoogleDrive-marcus.maccio@gmail.com/My Drive/01_Finance/Banks/Migros"

# Stage 2 — Two Agents in Pure LangChain (BTA -> AA)
cd /Users/marcomaccio/Documents/development/personal/langchain-ecosystem/langchain/lca-two-agents
uv run python main.py "/Users/marcomaccio/Library/CloudStorage/GoogleDrive-marcus.maccio@gmail.com/My Drive/01_Finance/Banks/Migros"

# Stage 3 — LangGraph StateGraph Workflow (discover_files -> bta_node -> aa_node)
cd /Users/marcomaccio/Documents/development/personal/langchain-ecosystem/langgraph/lca-langgraph-agents
uv run python main.py --graph
uv run python main.py "/Users/marcomaccio/Library/CloudStorage/GoogleDrive-marcus.maccio@gmail.com/My Drive/01_Finance/Banks/Migros"
```
