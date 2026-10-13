# arXiv Paper Curator

> An API-first research assistant for discovering, searching, and asking grounded questions about arXiv papers in Computer Science, Artificial Intelligence, and Machine Learning.

arXiv Paper Curator is a full-stack Retrieval-Augmented Generation (RAG) platform. It fetches papers from arXiv, downloads and parses their PDFs, stores metadata in PostgreSQL, indexes searchable chunks in OpenSearch, and generates citation-oriented answers with a local Ollama model.

The project includes both:

- **Traditional RAG**: retrieve relevant content and generate an answer.
- **Agentic RAG**: validate scope, decide whether retrieval is needed, grade retrieved documents, rewrite weak queries, and expose reasoning steps.

The implementation was developed incrementally in the week-by-week notebooks under [`notebooks/`](./notebooks/).

---

## Why this project?

Researchers and engineers often need to keep up with a rapidly growing technical literature. This project explores a practical workflow for turning arXiv into a searchable, observable, and conversational research knowledge base.

It can be used as:

- A personal AI/ML paper search assistant.
- A citation-backed research Q&A API.
- A foundation for automated literature reviews.
- A paper monitoring and digest service.
- A private research knowledge base for a lab or R&D team.
- A self-hosted research API using local inference through Ollama.

The current repository is a backend and infrastructure project. Authentication, billing, multi-tenancy, and a customer-facing web application are natural next product layers.

---

## Features

### Paper ingestion

- Fetch paper metadata from the arXiv API.
- Apply rate limiting and retry handling.
- Download and cache PDFs locally.
- Parse scientific PDFs with Docling.
- Extract sections, tables, figures, abstracts, authors, categories, and metadata.
- Persist paper records in PostgreSQL.
- Orchestrate ingestion tasks with Apache Airflow.

### Search and retrieval

- BM25 keyword search over titles, abstracts, and paper chunks.
- Vector similarity search with Jina AI embeddings.
- Hybrid search combining lexical and semantic results.
- Reciprocal Rank Fusion (RRF) for hybrid ranking.
- Category filtering, pagination, highlighting, and score filtering.
- A single OpenSearch chunk index for BM25, vector, and hybrid retrieval.
- Graceful fallback to BM25 when embeddings are unavailable.

### Traditional RAG

- Retrieve relevant chunks from OpenSearch.
- Build compact prompts from retrieved context.
- Generate answers with Ollama.
- Return source paper URLs and retrieval metadata.
- Stream answers through a streaming endpoint.
- Cache exact repeated requests in Redis.

### Agentic RAG

- Guardrail validation for CS/AI/ML research scope.
- Direct response for queries that do not require paper retrieval.
- Retrieval for research-oriented questions.
- Document relevance grading.
- Query rewriting when retrieved documents are not relevant.
- Bounded iterative retrieval.
- Reasoning steps and retrieval-attempt metadata in the response.
- LangGraph workflow orchestration.

### Observability and integrations

- Langfuse traces for requests, retrieval, prompt construction, and generation.
- Redis exact-match response caching.
- Self-hosted Langfuse stack in Docker Compose.
- OpenSearch Dashboards for index and search inspection.
- Airflow UI for scheduled ingestion jobs.
- Optional Telegram bot interface.
- Optional Gradio interface for interactive testing.

---

## Architecture

```text
                         ┌────────────────────┐
                         │  Notebook / Client │
                         └─────────┬──────────┘
                                   │
                      ┌────────────▼────────────┐
                      │       FastAPI API        │
                      │  traditional + agentic   │
                      └──────┬──────┬──────┬─────┘
                             │      │      │
                       ┌─────▼──┐ ┌─▼────┐ ┌▼─────────┐
                       │ Redis  │ │Langfuse│ │ Ollama  │
                       │ Cache  │ │Tracing │ │  LLM    │
                       └────────┘ └───────┘ └──────────┘
                             │
                       ┌─────▼─────────────┐
                       │    OpenSearch     │
                       │ BM25 + vector +   │
                       │ hybrid retrieval  │
                       └─────▲─────────────┘
                             │
                  ┌──────────┴──────────┐
                  │ PostgreSQL / Airflow│
                  │ metadata + ingestion│
                  └──────────▲──────────┘
                             │
                        ┌────┴────┐
                        │ arXiv  │
                        │ PDFs   │
                        └────────┘
```

### Traditional RAG flow

```text
Question
  → Redis cache lookup
  → optional Jina query embedding
  → BM25/vector/hybrid OpenSearch retrieval
  → compact RAG prompt
  → Ollama generation
  → citations and response
  → cache store + Langfuse trace
```

### Agentic RAG flow

```text
Question
  → guardrail validation
      ├─ out of scope → helpful scope response
      └─ in scope
           → retrieve papers
           → grade document relevance
               ├─ relevant → generate answer
               └─ weak results → rewrite query → retrieve again
```

---

## Technology stack

| Component | Role |
|---|---|
| Python 3.13+ | Application runtime |
| FastAPI | REST API |
| Pydantic Settings | Configuration |
| PostgreSQL | Paper and application metadata |
| OpenSearch 2.19 | BM25, vector, and hybrid search |
| OpenSearch Dashboards | Search/index dashboard |
| Apache Airflow | Ingestion orchestration |
| Ollama | Local LLM inference |
| LangChain | LLM abstractions and structured output |
| LangGraph | Agentic workflow orchestration |
| Jina AI | 1024-dimensional retrieval embeddings |
| Docling | Scientific PDF parsing |
| Redis | Exact-match response cache |
| Langfuse | Tracing and RAG observability |
| Telegram Bot API | Optional conversational interface |
| Gradio | Optional interactive UI |
| uv | Python dependency and environment management |
| Docker Compose | Local service orchestration |

---

## Requirements

- Docker Desktop with Docker Compose.
- Python 3.13 or newer.
- [`uv`](https://docs.astral.sh/uv/).
- Git.
- At least 8 GB RAM; 16 GB is recommended for OpenSearch, Airflow, and local LLM inference.
- At least 20 GB free disk space, depending on PDF and Ollama model storage.
- A Jina AI API key for vector/hybrid search.
- An Ollama model downloaded into the Ollama container.

The repository currently declares Python `>=3.13` in [`pyproject.toml`](./pyproject.toml).

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/kshitijkumrawat20/ArxivPaperCurator.git
cd ArxivPaperCurator
```

### 2. Create the Python environment

```bash
uv sync
```

### 3. Create the environment file

```bash
cp .env.example .env
```

On Windows PowerShell, use:

```powershell
Copy-Item .env.example .env
```

Update `.env` with your own values. Do not commit `.env`.

At minimum, configure:

```dotenv
JINA_API_KEY=your_jina_api_key
OLLAMA_MODEL=qwen2.5-coder:1.5b
OLLAMA_TIMEOUT=300
```

The repository's Docker Compose configuration overrides service-to-service hostnames for the containers, including:

```dotenv
OLLAMA_HOST=http://ollama:11434
OPENSEARCH__HOST=http://opensearch:9200
REDIS__HOST=redis
```

### 4. Start the stack

```bash
docker compose up --build -d
```

Check service status:

```bash
docker compose ps
```

Check API logs:

```bash
docker compose logs -f api
```

### 5. Download an Ollama model

The model name in the request must exist inside the Ollama container. For the default configuration:

```bash
docker compose exec ollama ollama pull qwen2.5-coder:1.5b
docker compose exec ollama ollama list
```

You can use another installed model, for example:

```bash
docker compose exec ollama ollama pull llama3.2:1b
```

Keep the request model, `OLLAMA_MODEL`, and the downloaded model name consistent.

### 6. Verify the API

```bash
curl http://localhost:8000/api/v1/health
```

Open the interactive API documentation:

```text
http://localhost:8000/docs
```

---

## Service URLs and ports

| Service | Host URL/port | Use |
|---|---:|---|
| FastAPI Swagger UI | [localhost:8000/docs](http://localhost:8000/docs) | API testing |
| FastAPI ReDoc | [localhost:8000/redoc](http://localhost:8000/redoc) | API reference |
| FastAPI health | [localhost:8000/api/v1/health](http://localhost:8000/api/v1/health) | Health checks |
| OpenSearch REST API | [localhost:9200](http://localhost:9200) | Index and search API |
| OpenSearch Dashboards | [localhost:5601](http://localhost:5601) | Search/index dashboard |
| Airflow | [localhost:8080](http://localhost:8080) | DAG and ingestion dashboard |
| Ollama API | [localhost:11434](http://localhost:11434) | Local LLM API |
| Langfuse dashboard | [localhost:3001](http://localhost:3001) | Traces and observations |
| Main PostgreSQL | `localhost:5432` | Paper metadata database |
| Redis | `localhost:6379` | Application cache |
| Langfuse worker | `localhost:3030` | Langfuse worker service |
| Langfuse PostgreSQL | `localhost:5433` | Langfuse database |
| Langfuse Redis | `localhost:6380` | Langfuse internal Redis |
| RustFS/MinIO API | `localhost:19000` | Langfuse object storage |
| RustFS/MinIO console | `localhost:19001` | Object-storage dashboard |

Internal Docker service names are different from host URLs. For example, the API uses `http://ollama:11434` inside the Compose network, while a notebook running on the host uses `http://localhost:11434`.

---

## API reference

### Traditional RAG

`POST /api/v1/ask`

```json
{
  "query": "What are attention mechanisms?",
  "top_k": 3,
  "use_hybrid": true,
  "model": "qwen2.5-coder:1.5b",
  "categories": ["cs.AI"]
}
```

Example:

```bash
curl -X POST http://localhost:8000/api/v1/ask \
  -H "Content-Type: application/json" \
  -d "{\"query\":\"What are attention mechanisms?\",\"top_k\":3,\"use_hybrid\":true,\"model\":\"qwen2.5-coder:1.5b\"}"
```

The response includes:

```json
{
  "query": "What are attention mechanisms?",
  "answer": "Answer grounded in retrieved papers...",
  "sources": [
    "https://arxiv.org/pdf/1706.03762.pdf"
  ],
  "chunks_used": 3,
  "search_mode": "hybrid"
}
```

### Streaming RAG

`POST /api/v1/stream`

This endpoint returns Server-Sent Event-style output for interactive clients.

```bash
curl -N -X POST http://localhost:8000/api/v1/stream \
  -H "Content-Type: application/json" \
  -d "{\"query\":\"Explain transformer architectures\",\"top_k\":3,\"use_hybrid\":true,\"model\":\"qwen2.5-coder:1.5b\"}"
```

### Hybrid search

`POST /api/v1/search/`

Use this endpoint when you need retrieved papers/chunks without answer generation.

```json
{
  "query": "retrieval augmented generation",
  "use_hybrid": true,
  "size": 5,
  "from": 0,
  "categories": ["cs.AI", "cs.LG"],
  "min_score": 0.0
}
```

### Agentic RAG

`POST /api/v1/ask-agentic`

```json
{
  "query": "How does BERT differ from GPT?",
  "top_k": 3,
  "use_hybrid": true,
  "model": "qwen2.5-coder:1.5b"
}
```

The response adds:

- `reasoning_steps`
- `retrieval_attempts`
- `trace_id`

Typical scenarios:

| Query | Expected behavior |
|---|---|
| `What is a dog?` | Scope rejection without retrieval |
| `What is 2+2?` | Direct/out-of-scope response |
| `How does BERT differ from GPT?` | Retrieval and grounded answer |
| `Tell me about ML stuff` | Possible retrieval and query refinement |

### Paper endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/papers/` | List/search stored papers |
| `GET /api/v1/papers/{arxiv_id}` | Retrieve paper details |

### Agentic feedback

`POST /api/v1/feedback`

Submit a score for an agentic response using its `trace_id`. This requires Langfuse to be configured and available.

---

## Langfuse configuration

The Compose file contains a self-hosted Langfuse deployment. Configure the application credentials and server secrets in `.env`.

Important values include:

```dotenv
LANGFUSE_ENABLED=true
LANGFUSE_HOST=http://localhost:3001
LANGFUSE__PUBLIC_KEY=pk-lf-your-public-key
LANGFUSE__SECRET_KEY=sk-lf-your-secret-key
LANGFUSE_NEXTAUTH_SECRET=replace-with-a-long-secret
LANGFUSE_SALT=replace-with-a-long-secret
LANGFUSE_ENCRYPTION_KEY=<64 hexadecimal characters>
```

Generate a valid encryption key with:

```bash
openssl rand -hex 32
```

`LANGFUSE_ENCRYPTION_KEY` must be exactly 64 hexadecimal characters. After changing `.env`, recreate containers because environment variables are injected when containers are created:

```bash
docker compose up -d --force-recreate api langfuse-web langfuse-worker
```

For source or dependency changes, rebuild as well:

```bash
docker compose up -d --build --force-recreate api
```

Open the dashboard at [http://localhost:3001](http://localhost:3001). RAG traces contain observations such as:

- `rag_request`
- `agentic_rag_request`
- `query_embedding`
- `search_retrieval`
- `guardrail_validation`
- `query_rewriting`
- `answer_generation`

---

## Redis caching

The traditional RAG endpoint uses parameter-aware exact-match caching. A cache key includes the query and relevant request options, so changing the model, search mode, category, or retrieval size does not incorrectly reuse an unrelated response.

Typical flow:

```text
First request  → cache miss → retrieval + generation → cache store
Repeated query → cache hit  → fast response
```

Useful configuration:

```dotenv
REDIS__HOST=redis
REDIS__PORT=6379
REDIS__TTL_HOURS=6
```

Check Redis:

```bash
docker compose exec redis redis-cli ping
```

---

## Data ingestion

The ingestion pipeline is designed to run through Airflow:

```text
arXiv API
  → metadata fetch
  → PDF download/cache
  → Docling parsing
  → PostgreSQL storage
  → section-aware chunking
  → Jina embeddings
  → OpenSearch indexing
  → daily report
```

Open the Airflow UI at [http://localhost:8080](http://localhost:8080) and inspect the configured DAGs.

The main Airflow code is under [`airflow/`](./airflow/), with reusable ingestion tasks under [`airflow/dags/arxiv_ingestion/`](./airflow/dags/arxiv_ingestion/).

---

## Chunking and search design

The default chunking strategy is section-aware:

| Setting | Default |
|---|---:|
| Target chunk size | 600 words |
| Chunk overlap | 100 words |
| Minimum chunk size | 100 words |
| Embedding dimension | 1024 |
| Index | `arxiv-papers-chunks` |

Section-based chunking preserves document structure where available and falls back to paragraph-oriented processing for unstructured content.

Search modes:

| Mode | Description |
|---|---|
| BM25 | Fast lexical search for exact technical terms and identifiers |
| Vector | Semantic similarity using embeddings |
| Hybrid | BM25 + vector results combined with RRF |

---

## Notebook curriculum

The notebooks document the project’s progression and can be used as an implementation guide.

### Week 1 — Infrastructure setup

[`notebooks/week1_setup.ipynb`](./notebooks/week1_setup.ipynb)

- Python and uv environment validation.
- Docker Compose infrastructure.
- FastAPI, PostgreSQL, OpenSearch, Airflow, and Ollama service setup.
- Basic health and connectivity checks.

### Week 2 — arXiv integration and PDF processing

[`notebooks/week2_arxiv_integration.ipynb`](./notebooks/week2_arxiv_integration.ipynb)

- arXiv API client with rate limiting and retries.
- PDF downloading and local caching.
- Docling scientific PDF parsing.
- Structured sections, tables, and figures.
- PostgreSQL persistence.
- End-to-end ingestion preparation for Airflow.

### Week 3 — OpenSearch and BM25 keyword search

[`notebooks/week3/week3_opensearch.ipynb`](./notebooks/week3/week3_opensearch.ipynb)

- OpenSearch client and factory integration.
- Academic-paper index mappings and analyzers.
- Multi-field BM25 search with field boosting.
- Highlighting, pagination, filtering, and fuzzy matching.
- Migration from PostgreSQL records to OpenSearch.
- Search API and health monitoring.

### Week 4 — Chunking and hybrid retrieval

[`notebooks/week4/week4_hybrid_search.ipynb`](./notebooks/week4/week4_hybrid_search.ipynb)

- Section-based chunking with overlap.
- Jina AI embeddings.
- Unified BM25, vector, and hybrid index.
- RRF ranking.
- Automatic BM25 fallback when vector search is unavailable.

### Week 5 — Complete RAG system

[`notebooks/week5/week5_complete_rag_system.ipynb`](./notebooks/week5/week5_complete_rag_system.ipynb)

- Ollama generation.
- Prompt compaction and source deduplication.
- Standard and streaming RAG endpoints.
- Gradio interactive interface.
- Performance optimization and response-size controls.

### Week 6 — Caching and observability

[`notebooks/week6/week6_cache_testing.ipynb`](./notebooks/week6/week6_cache_testing.ipynb)

- Langfuse pipeline tracing.
- Redis exact-match caching.
- Cache hit/miss performance comparison.
- Health and monitoring checks.

### Week 7 — Agentic RAG and Telegram

[`notebooks/week7/week7_agentic_rag.ipynb`](./notebooks/week7/week7_agentic_rag.ipynb)

- LangGraph workflow orchestration.
- Guardrail scope validation.
- Retrieval, grading, and query rewriting.
- Reasoning transparency.
- Telegram conversational interface and commands.

Each week also has a focused README with additional implementation notes:

- [`week3/README.md`](./notebooks/week3/README.md)
- [`week4/README.md`](./notebooks/week4/README.md)
- [`week5/README.md`](./notebooks/week5/README.md)
- [`week6/README.md`](./notebooks/week6/README.md)
- [`week7/README.md`](./notebooks/week7/README.md)

Run a notebook with:

```bash
uv run jupyter lab
```

Then open the required notebook from the Jupyter interface. The notebooks expect the Docker services to be running.

---

## Optional interfaces

### Gradio

The project includes a Gradio application for interactive traditional RAG testing:

```bash
uv run python gradio_launcher.py
```

The launcher commonly uses port `7861`; confirm the actual port in the launcher output.

### Telegram

Set the Telegram configuration in `.env`:

```dotenv
TELEGRAM__ENABLED=true
TELEGRAM__BOT_TOKEN=your_bot_token
```

Create a bot with BotFather, then start the application stack. The bot supports research questions and commands described in [`notebooks/week7/README.md`](./notebooks/week7/README.md).

---

## Testing

Run the test suite with:

```bash
uv run pytest
```

Run a focused test file:

```bash
uv run pytest tests/unit/services/test_ollama_langchain_model.py -q
```

The repository contains unit, API, and integration tests under [`tests/`](./tests/).

Before testing live generation, verify:

```bash
docker compose ps
docker compose exec ollama ollama list
curl http://localhost:8000/api/v1/health
```

---

## Troubleshooting

### Ollama returns `model not found`

Pull the exact requested model into the container:

```bash
docker compose exec ollama ollama pull qwen2.5-coder:1.5b
docker compose exec ollama ollama list
```

### API source changes are not visible

Rebuild and recreate the API container:

```bash
docker compose up -d --build --force-recreate api
```

An `.env`-only change normally needs recreation, not rebuilding:

```bash
docker compose up -d --force-recreate api
```

### OpenSearch says the index already exists

This usually means the persistent OpenSearch volume already contains `arxiv-papers-chunks`. Existing data should not be deleted casually. Inspect the index first through OpenSearch Dashboards or:

```bash
curl http://localhost:9200/arxiv-papers-chunks/_stats
```

### Langfuse worker rejects `ENCRYPTION_KEY`

The key must be exactly 64 hexadecimal characters:

```bash
openssl rand -hex 32
```

Update `.env` and recreate the Langfuse services:

```bash
docker compose up -d --force-recreate langfuse-web langfuse-worker api
```

### No Langfuse traces appear

Check:

1. `LANGFUSE_ENABLED=true`.
2. Public and secret keys match the self-hosted Langfuse project.
3. `LANGFUSE_HOST` is `http://langfuse-web:3000` inside the API container, or `http://localhost:3001` for host-side clients.
4. The Langfuse worker is not crashing.
5. The API was recreated after changing `.env`.

```bash
docker compose logs --tail=200 langfuse-web langfuse-worker api
```

### Hybrid search falls back to BM25

Check the Jina key and embedding service logs:

```bash
docker compose logs --tail=200 api
```

BM25 fallback is intentional when vector generation fails, but hybrid retrieval requires a valid `JINA_API_KEY`.

### Clean development reset

This removes persistent database, OpenSearch, Redis, Ollama, and Langfuse volumes. It destroys local data:

```bash
docker compose down -v
docker compose up --build -d
```

Use this only when a clean environment is required.

---

## Project structure

```text
.
├── airflow/
│   └── dags/                  # Scheduled arXiv ingestion workflows
├── notebooks/
│   ├── week1_setup.ipynb
│   ├── week2_arxiv_integration.ipynb
│   ├── week3/                 # OpenSearch and BM25
│   ├── week4/                 # Chunking and hybrid search
│   ├── week5/                 # Complete RAG
│   ├── week6/                 # Caching and monitoring
│   └── week7/                 # Agentic RAG and Telegram
├── src/
│   ├── config.py              # Application settings
│   ├── main.py                # FastAPI application and lifespan
│   ├── routers/               # API routes
│   ├── schema/                # Pydantic request/response schemas
│   ├── services/
│   │   ├── agents/            # LangGraph agentic RAG
│   │   ├── arxiv/             # arXiv API and PDF downloads
│   │   ├── embeddings/        # Jina embeddings
│   │   ├── indexing/          # Chunking and indexing
│   │   ├── langfuse/          # Tracing wrapper
│   │   ├── ollama/            # Local LLM client
│   │   ├── opensearch/        # Search and index operations
│   │   ├── pdf_parser/        # Docling parser
│   │   ├── telegram/          # Telegram integration
│   │   └── cache/              # Redis cache
│   └── db/                    # PostgreSQL database layer
├── tests/                     # Unit, API, and integration tests
├── compose.yml                # Local multi-service stack
├── Dockerfile                 # API image
├── .env.example               # Configuration template
├── pyproject.toml             # Python dependencies and project metadata
└── gradio_launcher.py         # Optional Gradio entry point
```

---

## Product roadmap

The current backend can become a subscription research application by adding a product layer around the RAG core.

### Individual researcher plan

- Saved topics and paper collections.
- Daily or weekly arXiv digests.
- Citation-backed literature summaries.
- Paper comparison and reading lists.
- Markdown and BibTeX export.

### Team plan

- Shared workspaces.
- Private PDF and document uploads.
- Tenant-scoped OpenSearch indexes.
- Team collections and permissions.
- Slack, email, Telegram, or webhook alerts.
- Usage analytics and Langfuse-based quality monitoring.

### Enterprise/self-hosted plan

- Local Ollama inference.
- SSO and audit logs.
- Custom ingestion sources.
- Dedicated indexes and retention policies.
- Private deployment and support.

The most natural first product is a **personalized AI research monitoring service**: users select topics, receive new-paper digests, and ask citation-backed questions over the latest literature.

---

## Security and operational notes

- Never commit `.env`, API keys, bot tokens, Langfuse secrets, or database passwords.
- Replace all development/default secrets before exposing services outside localhost.
- The Compose development stack disables OpenSearch security for local use; production deployments require authentication and TLS.
- Add authentication, rate limiting, tenant isolation, and billing checks before exposing the API as a public subscription service.
- Scope uploaded documents and OpenSearch queries by user or organization before supporting private workspaces.
- Keep Langfuse encryption keys stable; changing them can make previously encrypted data unreadable.

---

## License

No license file is currently included. Add a license before distributing the project or accepting external contributions.
