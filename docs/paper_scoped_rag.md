# Paper-scoped question answering (Phase 3A)

`POST /api/v1/papers/{arxiv_id}/ask` accepts the existing RAG controls (`query`,
`top_k`, `use_hybrid`, and `model`) through a paper-specific request schema. It
looks up that exact stored arXiv ID/version in PostgreSQL and then probes the
chunk index for one matching record. The probe is bounded to one chunk; actual
retrieval is limited to `top_k` (1–10).

The exact ID is passed to OpenSearch as a `term` filter in the BM25 query and in
the vector branch. For hybrid search, both lexical and kNN candidate queries
receive the filter before RRF combines them. Returned hits are also checked
against the requested ID before they are sent to Ollama. If embeddings are
unavailable, retrieval may degrade to BM25, but that BM25 query remains scoped
to the selected paper. Search errors do not trigger a global-corpus retry.

The answer-generation prompt explicitly limits evidence to excerpts from the
selected paper and tells the model to state when the excerpts are insufficient.
Responses include the exact paper ID and stored source URL, retrieval mode,
chunk count, and available chunk ID/index/section title plus excerpt. The index
does not retain page provenance, so page numbers are not returned.

Responses distinguish:

- `404`: no PostgreSQL metadata record exists for this exact ID.
- `409` with `code: full_text_not_indexed`: metadata exists but no chunk is
  indexed; full-text processing is required. No PDF download or parsing is
  started by this endpoint.
- `200` with an explicit no-evidence answer and empty evidence: chunks exist,
  but the query retrieved no relevant chunk from that paper.
- `503`: chunk search or answer generation is unavailable.

Successful answers can use the existing Redis cache. Paper-scoped cache keys
include the paper scope, exact versioned arXiv ID, question, top-k, model, and
retrieval mode. Global `/ask` keys retain their existing key shape, and global
answers cannot collide with paper-scoped entries.

Versioned IDs continue to be treated as separate stored identities, matching
the repository's current policy. The API does not strip or canonicalize version
suffixes. Chunk references are limited to fields currently retained by the
chunk index; no page or unsupported citation locator is fabricated.
