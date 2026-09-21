# ScholarForge AI: Architecture Specification

Derived from `docs/blueprint_v3.md`. This document says what each component does, which file implements it today, and what is still open.

## 1. Components and status

| Blueprint section | Component | Implemented in | Status |
|---|---|---|---|
| 1.1 | Tauri desktop shell, React UI | `app/` | Scaffold, not compiled here |
| 1.1 | PWA for mobile | `app/src/api.ts` browser fallback | Mock only |
| 1.2 | Vector store, SQLite metadata, FTS | `prototype/scholarforge/store.py` | Working (SQLite, hashed embeddings) |
| 1.3 | Local/cloud router | `router.py`, `app/src-tauri/src/router.rs` | Working, tested |
| 2 | Ingestion, chunking, hash-based sync | `store.py`, `chunk.py` | Working for txt/md, PDF via `pypdf` |
| 3.1 | Patchwriting and fact retention | `integrity.py` | Working |
| 3.2 | Self-plagiarism | `integrity.py` | Working |
| 3.3 | CSL formatting, orphan checks | `cite.py`, `tools/verify_output.py` | 3 styles, orphan check working |
| 3.4 | Provenance and disclosure | `provenance.py` | Working, 3 presets |
| 1.3, 4.1 | LLM providers, block generation, checkpoint session | `llm.py`, `privacy.py`, `generate.py` | Working against mock servers, 9 tests. Not yet run against a real model |
| 4.1 | Checkpoint UI | `app/src/App.tsx` | UI stub, not wired to the Python core |
| 4.2 | Versioned draft history | not built | Schema below |
| 4.3 | Cross-reference engine | `verify_cross_refs` only | Checker only, no renumbering |
| 5 | Pandoc/Typst/LaTeX export | not built | Design below |
| 6 | Privacy boundaries | this document | Policy plus tests to add |
| 7 | Verification script | `tools/verify_output.py` | Rewritten |

## 2. Data model (SQLite)

```sql
docs(id, path, sha256, title, csl_id)
chunks(id, doc_id, ordinal, section, page, text, vec)      -- vec moves to LanceDB in production
chunks_fts(text)                                            -- FTS5 over chunks
csl_records(id, json)                                       -- CSL JSON per source
manuscript(id, title, kind)                                 -- thesis, paper
sections(id, manuscript_id, parent_id, ordinal, title, target_words)
draft_events(id, section_id, parent_event_id, ts, kind, delta, text_hash)
  -- kind in {generate, accept, edit, regenerate, restore}; parent_event_id gives branching
ai_events(id, ts, model, tier, prompt, output, final_text, section)
anchors(label, kind, section_id)                            -- @fig:x, @tbl:y, @eq:z
prior_work(id, title, path, sha256)                         -- self-plagiarism index
```

Rollback restores a section from the event chain and writes a `restore` event, so history is never rewritten.

## 3. Retrieval

1. Parse to pages, then paragraphs, keeping section header and page.
2. Chunk to 300-500 words, splitting oversized paragraphs at sentence boundaries.
3. Embed each chunk. Production: `bge-small-en-v1.5` (384-d) via ONNX Runtime. Prototype: signed feature hashing (same dimension, no dependencies).
4. Query: dense cosine plus FTS5 BM25, merged with reciprocal rank fusion (k = 60).
5. Every hit carries `csl_id`, `page`, `section`, so any generated claim can cite `[Author, Year, p. X]`.

## 4. Generation loop

```
outline (Evans et al. chapter template) -> allocate words per section
for each block:
    anchor = last 500 words + section outline + top-k chunks
    route(tier, online) -> local or cloud
    draft -> integrity gate -> user checkpoint (accept / edit / regenerate)
    log to ai_events and draft_events
```

Integrity gate, in order: shared 5-word runs, sentence-order similarity, numbers absent from retrieved chunks, reuse against prior work, style rules from `verify_output.py`. Any failure returns the block to the user with the reason. Nothing is auto-fixed silently.

### 4.1 LLM layer details

- **Local:** `LlamaServerProvider` calls `llama-server -m model.gguf` (llama.cpp) over its OpenAI-compatible endpoint. The Rust shell should launch and supervise that process.
- **Cloud:** `AnthropicProvider` calls the Messages API. The key is read from `ANTHROPIC_API_KEY`. The model defaults to `claude-sonnet-5` and can be changed with `SCHOLARFORGE_CLOUD_MODEL`.
- **Fallback:** any `ProviderError` from the cloud triggers a local retry, and the output is labelled `unreviewed, offline draft`.
- **Outbound filter:** cloud prompts are built by `privacy.build_prompt`. Sources marked local-only are withheld, file paths, emails and key-shaped strings are redacted, and history is never included.
- **Gate:** the checks in section 4 run on every block, and the findings are shown to the user. Retries are the user's choice, through `Session.propose(feedback=...)`.
- **Provenance:** every call is logged with its outcome (proposed, accepted, discarded), and accepted blocks record the author's final text so edit ratios are real.

## 5. Routing rules

| Tier | Online | Target | Label |
|---|---|---|---|
| draft | any | local | AI-DRAFT |
| submission | yes | cloud | AI-DRAFT |
| submission | no | local | unreviewed, offline draft |

The offline label clears only after an online pass or a human review event.

## 6. Export pipeline (design)

Markdown source with Pandoc citeproc and CSL, then Typst or Tectonic per template. Templates declare margins, spacing, fonts, and page-number schemes (roman front matter, arabic body). The disclosure appendix and bibliography append automatically. A pre-flight step runs `verify_output.py` and refuses to compile on errors unless the user overrides, and the override is logged.

## 7. Privacy boundaries

Leaves the device in online mode: the active prompt, the retrieved snippets needed for that block, and the target section text. Never leaves: credentials, uncited PDFs, draft history, prior-work index. Add an automated test that captures outbound payloads and asserts this.

## 8. Risks and open questions found while building

1. **LanceDB in WebAssembly.** I could not confirm a supported embedded WASM build. Validate early. Fallbacks: sqlite-vec compiled to WASM, or a small HNSW index in Rust to WASM.
2. **PDF page numbers.** PDF page index and printed page number differ (roman front matter, offsets). Citations need a per-document offset map, or citations will be wrong by several pages.
3. **Zero-retention headers.** Retention is a contract term with the provider, not something a header guarantees. State it as "requested, and covered by the provider agreement" in the product.
4. **Sending snippets of licensed PDFs to a cloud model** may breach publisher terms. Add a per-source "local only" flag.
5. **Verifier vocabulary.** `using` and `could` are on the banned list and hit ordinary academic prose constantly. Keep as configured, but expose the list as a per-project setting.
6. **iOS PWA storage.** Safari can evict IndexedDB for unused sites. Prompt users to export backups.
7. **Quantized 8B local models** are weak at long-context synthesis. Keep local output tagged as scaffolding, as the router does.
8. **Institutional policy varies.** Some programs restrict AI-drafted thesis prose. The disclosure presets help, but the app should show the user's institution rules before generating chapter text.
