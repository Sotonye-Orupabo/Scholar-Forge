You are an expert Lead AI Systems Architect, Full-Stack Engineer, and Technical Academic Researcher/Writer. Execute the complete production-grade implementation specifications, technical architecture blueprint, and file structures for the ScholarForge AI application without asking for further input.
ScholarForge AI: Full Production Blueprint & Architectural Specification
System Overview
ScholarForge AI is a high-performance, cross-platform (Desktop and Mobile/PWA) academic writing and research engine. It enables academics, doctoral candidates, and researchers to author theses, dissertations, and peer-reviewed journal articles using local document stores or linked cloud services. The architecture is local-first, privacy-focused, and designed to operate entirely offline or in a hybrid offline/online mode.
1. System Architecture Diagram
+---------------------------------------------------------------------------------------+
|                                    USER INTERFACE                                     |
|   +---------------------------------------+   +-----------------------------------+   |
|   |    Desktop: React / TS + Tauri        |   |    Mobile/Web: PWA (IndexedDB)    |   |
|   +-------------------+-------------------+   +-----------------+-----------------+   |
+-----------------------|-----------------------------------------|---------------------+
                        |                                         |
                        v                                         v
+---------------------------------------------------------------------------------------+
|                                  CORE SYSTEM RUNTIME                                  |
|   +-------------------------------------------------------------------------------+   |
|   |                              Rust Core Backend                                |   |
|   |  - Daemon Services   - SQLite Metadata Engine   - File Watcher / Sync Agent    |   |
|   +-------------------+-----------------------------------------+-----------------+   |
+-----------------------|-----------------------------------------|---------------------+
                        |                                         |
                        v                                         v
+-------------------------------------------------+  +----------------------------------+
|           LOCAL EXECUTION ENVIRONMENT           |  |     REMOTE / ONLINE SERVICES     |
| +---------------------------------------------+ |  | +------------------------------+ |
| | Embedded LanceDB Engine (Native / WASM)    | |  | | Remote Cloud LLMs (APIs)     | |
| +---------------------------------------------+ |  | +------------------------------+ |
| | Local LLM Engine (llama.cpp / GGUF)        | |  | | Web Search (Tavily/SerpAPI)  | |
| +---------------------------------------------+ |  | +------------------------------+ |
| | Embedding Engine (nomic-embed / bge-small)  | |  | | Cloud Drive APIs (G-Drive)   | |
| +---------------------------------------------+ |  | +------------------------------+ |
+-------------------------------------------------+  +----------------------------------+

2. Directory Structure Blueprint
scholarforge-ai/
├── .cargo/
│   └── config.toml
├── Cargo.toml
├── package.json
├── tauri.conf.json
├── src/                                  # React/TypeScript Frontend UI
│   ├── index.html
│   ├── App.tsx
│   ├── components/
│   │   ├── Editor/
│   │   │   ├── LexicalEditor.tsx
│   │   │   └── CitationNode.tsx
│   │   ├── Sidebar/
│   │   │   ├── DocumentTree.tsx
│   │   │   └── CitationManager.tsx
│   │   └── Verification/
│   │       └── ComplianceReport.tsx
│   ├── hooks/
│   │   ├── useLLMRouter.ts
│   │   └── useSyncEngine.ts
│   └── store/
│       └── manuscriptStore.ts
├── src-tauri/                            # Rust Core Backend
│   ├── Cargo.toml
│   ├── src/
│   │   ├── main.rs
│   │   ├── lib.rs
│   │   ├── db/
│   │   │   ├── mod.rs
│   │   │   ├── sqlite.rs                 # Relational metadata & audit logs
│   │   │   └── lancedb.rs                # Vector database interface
│   │   ├── llm/
│   │   │   ├── mod.rs
│   │   │   ├── router.rs                 # Hybrid Local/Cloud execution router
│   │   │   ├── llama_cpp.rs              # Local GGUF inference engine
│   │   │   └── cloud_api.rs              # Remote LLM endpoint integration
│   │   ├── ingestion/
│   │   │   ├── mod.rs
│   │   │   ├── pdf_parser.rs             # Layout & byte-offset extraction
│   │   │   └── drive_sync.rs             # Cloud polling & hashing engine
│   │   ├── verification/
│   │   │   ├── mod.rs
│   │   │   ├── plagiarism.rs             # Shared n-gram overlap detector
│   │   │   ├── csl_engine.rs             # Citation formatting & orphan checks
│   │   │   └── style_checker.rs          # Academic style & constraint auditor
│   │   └── export/
│   │       ├── mod.rs
│   │       ├── typst_compiler.rs         # Native Typst compilation
│   │       └── pandoc_pipeline.rs        # Pandoc/LaTeX conversion pipeline
├── scripts/
│   └── verify_output.py                  # Standalone Quality Verification Script
└── templates/
    ├── institutional/
    │   ├── standard_thesis.typ
    │   └── standard_thesis.tex
    └── styles/
        └── apa7.csl

3. Comprehensive Execution Prompts
Below are five production-ready, fully detailed prompts to drive execution across the distinct operational domains of ScholarForge AI.
Prompt 1: System Infrastructure & Storage Architecture
Act as a Principal Rust & Systems Architect. Implement the complete storage, metadata, and vector database foundation for ScholarForge AI using Rust, SQLite (via rusqlite), and LanceDB embedded vector database.

System Requirements to Implement:
1. SQLite Database Schema (sqlite.rs):
   - `manuscripts`: Track manuscript ID, title, target degree, citation style, and timestamps.
   - `chapters`: Track chapter ID, manuscript ID, title, target word count, current word count, draft status, and sequence order.
   - `documents`: Track ingested PDF metadata, file hash (SHA-256), native file path, cloud URI, parse status, and ingestion date.
   - `chunks`: Track chunk ID, document ID, starting page, ending page, starting byte offset, ending byte offset, extracted text, and vector reference ID.
   - `citations`: Track citation ID, CSL-JSON payload, DOI, URL, HTTP verification status, last checked date, and orphan status.
   - `audit_logs`: Record every LLM invocation, prompt digest, model used (local vs. cloud), target text snapshot, and AI-Draft tags.
   - `draft_history`: Immutable event log capturing delta snapshots on accept/edit/regenerate operations.

2. Embedded Vector Database Engine (lancedb.rs):
   - Initialize native LanceDB engine locally on desktop (and WASM fallback for web).
   - Configure a table schema for dense embeddings generated by `nomic-embed-text` (768 dimensions) or `bge-small-en-v1.5` (384 dimensions).
   - Implement vector insertion, cosine similarity search, and source-filtered retrieval using metadata tags (document ID, section scope).

3. Edge Integration:
   - Provide clean, asynchronous Rust functions exposed via Tauri commands (`#[tauri::command]`) for indexing chunks, querying context, retrieving version snapshots, and logging audit records.
   - Ensure thread safety using Tokio async locks and pooled database connections.

Prompt 2: Hybrid Offline/Online LLM Orchestration & Router Engine
Act as an AI Systems & LLM Orchestration Engineer. Build the hybrid execution router module for ScholarForge AI in Rust (`llm/router.rs`, `llm/llama_cpp.rs`, `llm/cloud_api.rs`).

System Requirements to Implement:
1. Task Tiering & Routing Logic:
   - Draft Tier (Outlining, retrieval synthesis, rough paragraph drafting): Route strictly to local execution via llama.cpp using GGUF quantized models (e.g., Llama-3-8B-Instruct-Q4_K_M).
   - Submission Tier (Final polish, submission-ready prose): Evaluate network connectivity. If online, route to cloud APIs with zero-data-retention headers. If offline, route to local LLM, set output flag `is_offline_draft = true`, and prepend the text with an `[UNREVIEWED OFFLINE DRAFT]` tag.

2. Context Window & Sliding Anchor Management:
   - Construct context payload per generation turn:
     * System prompt enforcing academic writing constraints.
     * The last 500 words of the preceding section (sliding anchor).
     * Relevant document chunks retrieved from LanceDB (top-k = 5).
     * High-level chapter outline target.
   - Cap total token budget dynamically based on the active model's context window.

3. Execution Fallback & Error Recovery:
   - Implement graceful degradation: if cloud API times out or fails network checks, automatically fallback to local GGUF execution without losing active editor state.
   - Log all telemetry and routing decisions to `audit_logs` in SQLite.

Prompt 3: Ingestion, Cloud Sync & PDF Parsing Pipeline
Act as a Full-Stack Systems Engineer. Construct the document processing, cloud synchronizer, and precise layout-aware PDF extraction pipeline (`ingestion/pdf_parser.rs` and `ingestion/drive_sync.rs`).

System Requirements to Implement:
1. PDF Layout Extraction Engine:
   - Extract raw text streams alongside precise byte offsets, section titles, headers, footers, figure captions, table structures, and page bounds.
   - Strip running headers and page numbers from academic paper text streams to avoid vector noise.
   - Slice extracted text into structured blocks of 300 to 500 words.
   - Embed source metadata into every block: `{ doc_id, section_title, start_page, end_page, start_byte, end_byte }`.

2. Google Drive / Remote Folder Sync Daemon:
   - Implement an asynchronous polling service in Rust that monitors linked folder URLs or OAuth endpoints.
   - Compute local SHA-256 hashes of remote PDF files. Compare against `documents` table in SQLite.
   - Trigger incremental downloads for new or changed files, pass them through the PDF parser, compute dense vector embeddings, and update LanceDB indices.

3. Robust Error Handling:
   - Handle corrupted PDFs, scanned image PDFs (flag for OCR requirement), and malformed unicode characters gracefully without crashing the parsing daemon.

Prompt 4: Synthesis, Attribution, Self-Plagiarism & CSL Verification Engine
Act as an Academic Software Architect & Quality Assurance Specialist. Implement the full verification, self-plagiarism, attribution, and CSL engine (`verification/plagiarism.rs`, `verification/csl_engine.rs`, `verification/style_checker.rs`).

System Requirements to Implement:
1. Shared N-Gram & Patchwriting Detector:
   - Implement a sliding window n-gram overlap algorithm (default n=5 words).
   - Compare new prose against ingested source chunks and the author's local prior-work directory (past theses, manuscripts, term papers).
   - Flag shared 5-word or longer exact matches or close structural sequence matches.
   - Return structured warning payload indicating overlapping files, specific matching phrase samples, and precise character offsets.

2. CSL Engine & Orphan Citation Auditor:
   - Integrate a native CSL formatting engine supporting APA 7th, IEEE, Harvard, Chicago 17th, MLA 9th, and Vancouver styles.
   - Maintain a bidirectional map between in-text citations (e.g., `[Author, Year, p. X]`) and the bibliography database.
   - Identify orphan citations (in-text references missing from the bibliography) and orphan references (bibliography entries uncited in the text).
   - Provide an asynchronous HTTP auditor to check DOIs and URLs in the bibliography, flagging broken links, 404s, or redirects.

3. AI Disclosure Generator:
   - Parse `audit_logs` to construct an automated AI-Disclosure Statement Appendix conforming to institutional standards (e.g., Oxford, Princeton, Imperial College London).
   - Calculate human vs. LLM edit ratios across chapter drafts.

Prompt 5: Submission-Ready Compilation & Export Pipeline
Act as a Document Engineering Specialist. Construct the export compilation pipeline (`export/typst_compiler.rs`, `export/pandoc_pipeline.rs`) to convert Markdown manuscript drafts into publication-ready output formats.

System Requirements to Implement:
1. Multi-Engine Compilation Pipeline:
   - Target Export Formats: PDF (via Typst or Tectonic/XeLaTeX), Microsoft Word (.docx), and LaTeX source archives (.zip).
   - Integrate Typst for native, ultra-fast typesetting and LaTeX/Pandoc as secondary compilation engines.

2. Front-Matter & Cross-Reference Engine:
   - Automatically generate front-matter assets: Title Page, Abstract, Dedication, Table of Contents (TOC), List of Figures (LOF), and List of Tables (LOT).
   - Resolve dynamic cross-references (`@fig:label`, `@tbl:label`, `@eq:label`) and update numbering dynamically on document restructuring.
   - Apply institutional style constraints: 1.5-inch binding margins, double/1.5 line spacing, Roman numerals for front-matter, Arabic numerals for main body.

3. Appendices & Compliance Binding:
   - Automatically append the AI Disclosure Statement Appendix and the formatted CSL Bibliography at the end of the manuscript output.

4. Automated Quality Verification Script (scripts/verify_output.py)
Below is the standalone Python script to verify style constraints, banned vocabulary, source overlaps, orphan citations, cross-references, and self-plagiarism in generated drafts.
import re
import sys
import os
import urllib.request
import urllib.error

# Academic style guidelines: ban conversational fluff, hyperbolic jargon, and weak transitions
BANNED_WORDS = [
    "very", "really", "literally", "actually", "certainly", "probably", "basically",
    "could", "maybe", "delve", "embark", "enlightening", "esteemed", "shed light",
    "craft", "crafting", "not only", "not alone", "in a world where", "revolutionize",
    "disruptive", "utilize", "using", "dive deep", "tapestry", "unravel", "harness",
    "exciting", "groundbreaking", "cutting-edge", "remarkable", "remains to be seen",
    "glimpse into", "navigating the landscape", "stark testament", "in summary",
    "in conclusion", "moreover", "boost", "skyrocketing", "opened up", "powerful",
    "ever-evolving"
]

def verify_style_and_punct(text):
    errors = []
    # Enforce strict punctuation rules
    if "—" in text or "--" in text:
        errors.append("Punctuation Error: Em dash ('—' or '--') detected. Use standard parenthetical structure or separate sentences.")
    if ";" in text:
        errors.append("Punctuation Error: Semicolon (';') detected. Avoid semicolons in formal thesis prose.")

    for word in BANNED_WORDS:
        pattern = r"\b" + re.escape(word) + r"\b"
        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        if matches:
            errors.append(f"Style Error: Banned word/phrase found: '{word}' ({len(matches)} instance(s))")

    return errors

def verify_citations_and_orphans(text):
    errors = []
    # Match in-text citations: [Author, Year, p. X] or [Author, Year]
    in_text_citations = set(re.findall(r"\[([A-Za-z]+),\s*(\d{4})(?:,\s*p\.\s*\d+)?\]", text))
    
    # Match Bibliography entries: e.g., Author (Year)
    bib_entries = set(re.findall(r"^([A-Za-z]+)\s*\((\d{4})\)", text, re.MULTILINE))

    if not in_text_citations:
        errors.append("Citation Warning: No exact page citations matching '[Author, Year, p. X]' were detected.")

    # Check for Orphan In-Text Citations (Cited but missing in Bibliography)
    if bib_entries:
        for cite in in_text_citations:
            if cite not in bib_entries:
                errors.append(f"Orphan Citation Error: In-text citation [{cite[0]}, {cite[1]}] has no matching bibliography entry.")

        # Check for Uncited Bibliography Entries
        for bib in bib_entries:
            if bib not in in_text_citations:
                errors.append(f"Orphan Bibliography Error: Reference '{bib[0]} ({bib[1]})' is listed in bibliography but never cited in-text.")

    return errors

def verify_cross_references(text):
    errors = []
    # Identify defined anchors like {#fig:method_diagram}, {#tbl:sample_data}, {#eq:model}
    anchors = set(re.findall(r"\{\#(fig:[\w-]+|tbl:[\w-]+|eq:[\w-]+)\}", text))
    # Identify citations to anchors like @fig:method_diagram
    refs = set(re.findall(r"@(fig:[\w-]+|tbl:[\w-]+|eq:[\w-]+)\b", text))

    for ref in refs:
        if ref not in anchors:
            errors.append(f"Cross-Reference Error: Broken reference '@{ref}' (anchor definition missing in text).")

    return errors

def check_overlap(generated_text, comparison_texts, n=5, label_prefix="Source"):
    def ngrams(text):
        words = re.findall(r"\b\w+\b", text.lower())
        return set(tuple(words[i:i + n]) for i in range(len(words) - n + 1))

    gen_ngrams = ngrams(generated_text)
    flags = []
    for label, comp_text in comparison_texts.items():
        overlap = gen_ngrams & ngrams(comp_text)
        if overlap:
            sample = " ".join(next(iter(overlap)))
            flags.append(
                f"{label_prefix} Overlap Warning: {len(overlap)} shared {n}-word run(s) with '{label}' "
                f"(e.g. \"{sample}\"). Rewrite or quote directly."
            )
    return flags

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python verify_output.py <path_to_markdown_file> [--sources <dir>] [--prior-work <dir>]")
        sys.exit(1)

    file_path = sys.argv[1]
    if not os.path.exists(file_path):
        print(f"Error: File '{file_path}' not found.")
        sys.exit(1)

    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()

    print("=== ScholarForge AI Quality Verification ===")
    all_errors = []

    # 1. Style & Punctuation Audit
    all_errors.extend(verify_style_and_punct(text))

    # 2. Orphan Citation & Bibliography Audit
    all_errors.extend(verify_citations_and_orphans(text))

    # 3. Cross-Reference Audit
    all_errors.extend(verify_cross_references(text))

    # 4. External Source Overlap Check
    if "--sources" in sys.argv:
        idx = sys.argv.index("--sources")
        if idx + 1 < len(sys.argv):
            sources_dir = sys.argv[idx + 1]
            source_texts = {}
            if os.path.exists(sources_dir):
                for fname in os.listdir(sources_dir):
                    fpath = os.path.join(sources_dir, fname)
                    if os.path.isfile(fpath):
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as sf:
                            source_texts[fname] = sf.read()
                all_errors.extend(check_overlap(text, source_texts, label_prefix="Source Patchwriting"))

    # 5. Author Self-Plagiarism Check
    if "--prior-work" in sys.argv:
        idx = sys.argv.index("--prior-work")
        if idx + 1 < len(sys.argv):
            pw_dir = sys.argv[idx + 1]
            pw_texts = {}
            if os.path.exists(pw_dir):
                for fname in os.listdir(pw_dir):
                    fpath = os.path.join(pw_dir, fname)
                    if os.path.isfile(fpath):
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as pf:
                            pw_texts[fname] = pf.read()
                all_errors.extend(check_overlap(text, pw_texts, label_prefix="Self-Plagiarism"))

    if not all_errors:
        print("PASS: All verification checks passed successfully. Manuscript is compliant.")
        sys.exit(0)
    else:
        print(f"FAIL: Found {len(all_errors)} issue(s):")
        for err in all_errors:
            print(f" - {err}")
        sys.exit(1)

