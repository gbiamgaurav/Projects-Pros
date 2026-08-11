# MOSAIC — Multi-Agent Clinical Trial Intelligence

Multi-agent system for clinical trial intelligence, built on **LangGraph** (orchestration), **LangMem** (long-term agent memory), and **Google Cloud Platform** (deployment).

> **Status:** scaffold. Directory layout is in place; module implementations are pending.

## Why

Clinical trial intelligence spans heterogeneous sources — registry records, protocol documents, publications, regulatory filings. A single-prompt LLM call collapses under that breadth. MOSAIC splits the work across specialized agents coordinated by a LangGraph state machine, with LangMem retaining cross-session context (prior findings, user focus areas, entity resolutions) so repeat questions don't restart from zero.

## Architecture

```
Sources ──> ingestion ──> processing ──> vector / structured store
                                              │
                              ┌───────────────┴───────────────┐
                              │        graph (LangGraph)      │
                              │  router → agents → synthesis  │
                              └───────────────┬───────────────┘
                                              │
                                   memory (LangMem)  ⇄  tools
                                              │
                                        api (FastAPI)
```

## Layout

Application code lives under the `mosaic/` package directory; paths below are relative to it.

| Path | Purpose |
| --- | --- |
| `config/` | Settings, env loading, model and GCP config |
| `ingestion/` | Source connectors — trial registries, documents, feeds |
| `processing/` | Parsing, chunking, normalization, embedding |
| `memory/` | LangMem stores — semantic, episodic, procedural |
| `agents/` | Specialized agents (retrieval, eligibility, comparison, critic) |
| `tools/` | Tool definitions bound to agents |
| `graph/` | LangGraph state schema, nodes, edges, checkpointing |
| `api/routers/` | FastAPI routes |
| `evaluation/` | Eval harness, datasets, LLM-judge scoring |
| `tests/` | Unit and integration tests |
| `deployment/gcp/` | Cloud Run / Vertex AI deploy config |
| `data/raw/` | Unprocessed source dumps (gitignored) |
| `data/processed/` | Derived artifacts, embeddings (gitignored) |
| `notebooks/` | Exploration and prototyping |

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in keys
```

### Scaffold the tree

Run from inside `mosaic/`:

```bash
mkdir -p {config,ingestion,processing,memory,agents,tools,graph,evaluation,tests,notebooks} api/routers deployment/gcp data/{raw,processed}
```

> Watch the flag — `mkdir - p` (space after the dash) creates directories literally named `-` and `p` instead of recursing.

## Environment



## Run

```bash
uvicorn api.main:app --reload --port 8000
```

## Test

```bash
pytest tests/ -v
```

## Deploy

Deployment manifests live in `deployment/gcp/`. Target is Cloud Run for the API, with Vertex AI for hosted model and embedding endpoints.

## License

See [LICENSE](../LICENSE) in the repository root.
