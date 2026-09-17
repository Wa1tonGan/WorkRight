# WorkRight: Local RAG and pgvector Learning Guide

This guide records our proposed setup and the learning path we will follow while building WorkRight. It is a design and learning document; the application and database have not been implemented yet.

Our goal is to understand each part of RAG, measure whether it works, and improve it using evidence. All model inference and embedding generation will run locally, without paid AI APIs.

## 1. The proposed local setup

| Component | Initial choice | Job |
| --- | --- | --- |
| Agent LLM | Qwen3 8B through Ollama | Understand requests, select tools, and explain results. |
| Embedding model | BGE-M3 through Ollama | Convert policy passages and queries into vectors. |
| Backend | Python and FastAPI | Connect the components, execute tools, and enforce rules. |
| Database | PostgreSQL with pgvector | Store business records, policy text, source metadata, and vectors. |
| Database access | SQLAlchemy | Read and write records. |
| Schema migrations | Alembic | Track changes to database tables. |
| Frontend | React, TypeScript, and Vite | Display chat, requests, approvals, and policy references. |
| Tests | pytest and a small evaluation dataset | Check retrieval, answers, and business behaviour. |

Qwen3 8B and BGE-M3 are starting candidates, not permanent choices. We will evaluate their performance on WorkRight examples, including English and Malay questions.

The development machine is an M4 MacBook Air with 24 GB of memory. We will measure memory use and response time with the backend, database, and models running together. Model download size is not the same as runtime memory use.

## 2. What RAG means

Retrieval-Augmented Generation means finding relevant information and including it in the model's input when asking it to answer.

RAG does not train the answering model on our documents. The stored documents remain external to the model.

For WorkRight:

- RAG answers: “What does the applicable policy say?”
- Employee database tools answer: “What is true for this employee?”
- Python rules answer: “Is this action valid and authorized?”
- Saved case state answers: “What has already happened to this request?”

A good answer may require all four. An employee's live leave balance should be read from a normal database table, not retrieved from an embedded document.

## 3. The two workflows

### Document preparation: when sources are added or updated

```text
Source documents
    ↓
Extract and inspect text
    ↓
Split into meaningful passages (chunks)
    ↓
Attach source and applicability metadata
    ↓
Generate embeddings locally with BGE-M3
    ↓
Store text, metadata, and vectors in PostgreSQL
```

### Retrieval: when an employee asks a question

```text
Question + trusted employee context
    ↓
Determine applicable source filters
    ↓
Generate a query embedding with the same embedding model
    ↓
Search eligible passages in PostgreSQL / pgvector
    ↓
Select useful evidence within the context budget
    ↓
Give question + evidence to Qwen3
    ↓
Return a grounded answer with source references
```

We should be able to inspect the retrieved passages before involving Qwen3. This helps distinguish a retrieval failure from an answer-generation failure.

## 4. One database, several kinds of data

pgvector is an extension inside PostgreSQL, not a second database server.

```text
PostgreSQL database: workright
├── employees
├── leave_balances
├── leave_requests
├── flexible_work_requests
├── approvals
├── agent_cases
├── case_events
├── policy_documents
└── policy_chunks       ← includes a vector column
```

The policy text remains stored as text. The embedding is an additional representation used for search; it does not replace the original passage.

Suggested document metadata:

| Field | Purpose |
| --- | --- |
| `title` | Human-readable document identity. |
| `source_uri` | Original URL or local source reference. |
| `source_type` | Law, official guidance, or company policy. |
| `jurisdiction` | Supported geographic/legal scope. |
| `company_id` | Applicable company, where relevant. |
| `version` | Document or policy revision. |
| `effective_from`, `effective_to` | Period of applicability, when verified. |
| `retrieved_at` | When we obtained the source; distinct from its effective date. |
| `content_hash` | Detect unchanged or modified content. |

Suggested chunk fields:

| Field | Purpose |
| --- | --- |
| `document_id` | Link to document metadata. |
| `text` | Original passage used as evidence. |
| `section`, `page_number` | Precise citation location, when available. |
| `chunk_order` | Position within the document. |
| `embedding` | Vector used for similarity search. |
| `embedding_model_version` | Identify the exact embedding configuration. |

Do not invent dates, page numbers, or legal applicability when the source does not establish them. Verify public legal sources during corpus preparation.

## 5. Chunking: preserve complete meaning

Start with sections and paragraphs rather than arbitrary character counts.

Our first experiment will target roughly 300–600 tokens per chunk, with about 50 tokens of overlap when a long section must be split. Tokens are model text units, not necessarily words. These values are hypotheses to test, not universal best settings.

Preserve:

- A rule together with its conditions, exceptions, limits, and deadlines.
- Headings that identify the topic.
- Table column headings alongside the relevant rows.
- Enough surrounding context to explain cross-references.

Example using fictional company policy: a carry-forward allowance should stay connected to its maximum number of days and expiry date. A fragment containing only “unused leave may be carried forward” is incomplete evidence.

Inspect PDF extraction before embedding. Broken tables, repeated page headers, missing text, and incorrect reading order cannot be fixed merely by choosing a better vector index.

## 6. Embeddings and vector configuration

An embedding is a list of numbers representing aspects of a passage's meaning. Related texts can have nearby vectors even when they use different words.

Use the same embedding model and compatible preprocessing settings for documents and queries. Pin and record the model version used. If we change embedding models, regenerate the document vectors before using the new query vectors. Equal vector length alone does not make two models compatible.

After pgvector is installed on the PostgreSQL server, enable it in the WorkRight database:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

We will generate a sample embedding and inspect its length before defining the vector column's dimension. A dimension mismatch must fail validation rather than be silently truncated or padded.

### Distance and indexing

Start with cosine distance. Smaller distance indicates greater similarity under that metric; it does not prove that a passage is applicable or correct.

For our small initial corpus, use exact search over eligible vectors. This provides a clear retrieval baseline.

Consider an HNSW index only if measured search latency requires it. HNSW trades some retrieval recall for speed and uses additional resources. Its index distance operator must match the search metric. With approximate indexes, metadata filtering can reduce the number of returned candidates, so evaluate filtered queries as well as unfiltered ones.

An index improves search execution, not the quality of the underlying policy text or embeddings.

## 7. Initial application settings

The following is an illustrative configuration we will implement later. These are our proposed application keys, not existing Ollama or pgvector configuration options.

```yaml
rag:
  embedding_model: bge-m3
  chunk_target_tokens: 450
  chunk_overlap_tokens: 50
  retrieval_top_k: 5
  distance_metric: cosine
  search_mode: exact
  hybrid_search_enabled: false
  reranker_enabled: false
```

We will also configure an evidence token budget and the LLM context size together. The complete input must leave room for system instructions, the question, tool results, conversation context, and the answer.

Increasing `retrieval_top_k` does not automatically improve answers. Extra passages can introduce duplication, unrelated rules, or conflicting versions.

## 8. Improving retrieval for WorkRight

### Apply trusted filters

Use employee facts and backend rules to determine jurisdiction, company, and the relevant effective date. Do not let a user message or model-generated argument override required access or jurisdiction restrictions.

Semantic similarity cannot decide whether an old policy or another jurisdiction applies.

### Retrieve each required source category

For questions comparing statutory requirements with company benefits, retrieve both categories deliberately. A single top-five search might otherwise return only company-policy passages.

### Add keyword search when it solves a measured problem

Vector search helps connect “work from home” with “flexible working arrangements.” Keyword search or structured-field lookup helps with exact section numbers and policy codes.

PostgreSQL has built-in full-text search. We can later combine its ranked results with vector results, for example using reciprocal rank fusion. This avoids directly adding scores that have different scales. English and Malay text-search behaviour must be evaluated separately; an English language configuration is not automatically appropriate for Malay.

### Add a reranker only when useful

A later experiment could retrieve 15–20 candidates and use a local reranking model to select the most relevant few. Measure the relevance gain against extra latency and memory use before keeping it.

### Handle missing or conflicting evidence

The application should identify missing evidence, ask for clarification, or route to HR. If applicable sources conflict, it should surface the conflict rather than invent a resolution.

A similarity score is not a probability of correctness. Do not interpret 0.85 similarity as 85% confidence or choose a universal rejection threshold without evaluation.

## 9. Grounded answers and traceability

Pass retrieved passages to the model with stable source identifiers. Keep document text clearly separated from application instructions: retrieved text is evidence, not authorization to execute actions.

For each answer, retain enough information to inspect:

- The retrieval query and applied filters.
- Retrieved chunk IDs, source metadata, and search scores.
- The evidence actually sent to the LLM.
- The answer and its source references.
- Retrieval and generation durations.

Check that cited identifiers exist and that the cited passages support the claims. A citation attached to an unsupported statement is still an incorrect answer.

Keep tool arguments, results, and case events available for debugging. Private model reasoning is not required for traceability.

## 10. Evaluate before tuning

Start with 30–50 questions and manually identify the evidence each should retrieve. Keep a separate subset for checking whether tuning generalizes.

| Category | Example |
| --- | --- |
| Direct policy question | “What annual leave does the company provide?” |
| Paraphrase | “Can I bring unused days into next year?” |
| Malay query | “Boleh saya kerja dari rumah dua hari seminggu?” |
| Source comparison | “How does company leave compare with the legal minimum?” |
| Missing evidence | A question the corpus does not answer. |
| Unsupported scope | A request outside V1 jurisdiction. |
| Policy versions | Current and superseded documents discuss the same benefit. |
| Table interpretation | The answer depends on a table row and its column headings. |

Measure:

| Metric | Question it answers |
| --- | --- |
| Retrieval recall at k | Did the returned passages contain the required evidence? |
| Evidence relevance | How much retrieved text was useful? |
| Answer grounding | Does the answer follow the evidence without unsupported additions? |
| Citation accuracy | Do the references support the associated claims? |
| Abstention | Does the system recognize missing or unsupported information? |
| Latency and memory | Is the setup practical on this Mac? |

Change one major setting at a time and record the outcome. Fix extraction and applicability problems before experimenting with larger models or more complex retrieval.

## 11. Updating the knowledge base

Track document hashes so unchanged content need not be embedded again. For changed documents, create a new version, generate and verify its chunks, and make the version available to current-policy queries only when ingestion is complete.

Preserve old sources where needed for historical cases. Superseded documents should not remain eligible for current-policy retrieval by accident.

Record the embedding model and chunking configuration so we can reproduce an index or rebuild it deliberately.

## 12. Do we need Docker?

No. RAG and pgvector work with or without Docker.

| Setup | Benefits | Tradeoffs |
| --- | --- | --- |
| Native PostgreSQL and pgvector on macOS | Direct database access and fewer infrastructure components. | We manage the installation, compatible versions, and database service. |
| PostgreSQL and pgvector in Docker Compose | A reproducible service configuration and easier environment recreation. | Adds Docker to learn and consumes additional system resources. |

Recommended starting arrangement:

- Ollama runs directly on macOS for Apple Metal acceleration.
- Python and React run directly on macOS during development.
- PostgreSQL and pgvector run in Docker Compose if we choose containerized database setup.

Docker is still an optional infrastructure choice, not a prerequisite or an already completed installation.

Compose will describe the database image, connection configuration, health check, and persistent volume. A volume preserves data across ordinary container replacement. Explicitly deleting the volume deletes that stored data; a volume is not a backup.

Choosing native PostgreSQL does not change the RAG architecture. We primarily change how the database starts and where the backend connects.

## 13. Hands-on learning sequence

We will work through these steps during development rather than building the entire pipeline at once.

| Step | Exercise | What you should understand afterward |
| --- | --- | --- |
| 1 | Read one fictional company-policy document. | What counts as source evidence. |
| 2 | Extract and inspect its text. | Why source quality matters. |
| 3 | Split it into chunks and inspect each one. | Chunk size, overlap, and semantic boundaries. |
| 4 | Generate one local embedding and inspect its length. | The relationship between text, model, and vector dimension. |
| 5 | Store text and embeddings in PostgreSQL. | How pgvector extends an ordinary table. |
| 6 | Embed a question and run an exact similarity search. | How retrieval works without an answering LLM. |
| 7 | Compare English and Malay questions and paraphrases. | Where the embedding model succeeds or fails. |
| 8 | Add source and applicability filters. | Why relevance and applicability are separate concerns. |
| 9 | Give retrieved passages to Qwen3 with citations. | How retrieval becomes RAG. |
| 10 | Run the evaluation set and tune one variable at a time. | How to improve the system using evidence. |
| 11 | Add verified legal sources and source comparisons. | How to keep law and company benefits distinguishable. |
| 12 | Test document updates and missing-evidence cases. | How to keep retrieval reliable over time. |

Phase 0 prepares the local database and Ollama connection. Phase 1 introduces employee tools. Phase 2 implements this RAG learning sequence, followed by integration into the leave and approval workflows.

## 14. Official references

- [Ollama embeddings: generation and consistency guidance](https://docs.ollama.com/capabilities/embeddings)
- [Ollama tool calling](https://docs.ollama.com/capabilities/tool-calling)
- [Ollama hardware support](https://docs.ollama.com/gpu)
- [Qwen3 8B model listing](https://ollama.com/library/qwen3:8b)
- [BGE-M3 model listing](https://ollama.com/library/bge-m3)
- [pgvector: installation, distance metrics, exact search, and indexes](https://github.com/pgvector/pgvector)
- [PostgreSQL full-text search](https://www.postgresql.org/docs/current/textsearch-intro.html)
- [Docker Compose application model](https://docs.docker.com/compose/intro/compose-application-model/)

The references were reviewed during our planning discussion on 13 September 2026. Verify package and model versions again when implementing the relevant phase.
