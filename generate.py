"""Block generation with routing, cloud fallback, integrity gate and a human checkpoint."""
import os
import sys
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .integrity import fact_retention, patchwriting_check
from .llm import Provider, ProviderError
from .privacy import build_prompt
from .provenance import ProvenanceLog
from .router import route
from .store import Store

# The style gate lives in tools/verify_output.py at the repository root.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from tools import verify_output as vo  # noqa: E402

SYSTEM = """You are an academic writing assistant for a thesis author.
Rules:
- Synthesize across the provided sources. Compare and connect claims. Do not restate one source at a time.
- Use only facts, numbers and names found in the provided sources. If a needed fact is missing, write [NEEDS SOURCE].
- Cite every claim with the exact citation tag shown on its source, for example [Smith, 2020, p. 14].
- Never copy five or more consecutive words from a source. Quote directly, in quotation marks, only when wording matters.
- Do not use em dashes, semicolons, or filler and hype vocabulary (for example: very, really, moreover, delve, utilize, using, could, powerful).
- Write in plain, precise academic prose. Return only the prose of the requested block."""


@dataclass
class BlockResult:
    text: str
    route_label: str
    provider: str
    findings: List[str]
    event_id: int
    fell_back: bool = False
    withheld_local_only: int = 0

    @property
    def clean(self) -> bool:
        return not self.findings


class BlockGenerator:
    def __init__(self, store: Store, log: ProvenanceLog, local: Provider, cloud: Optional[Provider] = None,
                 online_check: Callable[[], bool] = lambda: True, prefer_local: bool = False,
                 csl: Optional[Dict[str, dict]] = None, max_tokens: int = 1200):
        self.store, self.log, self.local, self.cloud = store, log, local, cloud
        self.online_check, self.prefer_local, self.csl, self.max_tokens = online_check, prefer_local, csl, max_tokens

    def generate(self, section: str, outline: str, instruction: str, prior_text: str = "",
                 tier: str = "draft", k: int = 6) -> BlockResult:
        hits = self.store.search(f"{section} {instruction}", k=k)
        anchor = " ".join(prior_text.split()[-500:])
        decision = route(tier, self.online_check(), self.prefer_local)
        use_cloud = decision.target == "cloud" and self.cloud is not None
        label, fell_back = decision.label, False

        text, provider_name, withheld, prompt_text = "", "", 0, ""
        if use_cloud:
            p = build_prompt(SYSTEM, section, outline, instruction, anchor, hits, self.csl, for_cloud=True)
            withheld, prompt_text = p.local_only_withheld, p.user
            try:
                text, provider_name = self.cloud.generate(p.system, p.user, self.max_tokens), self.cloud.name
            except ProviderError:
                use_cloud, fell_back, label = False, True, "unreviewed, offline draft"
        if not use_cloud:
            if decision.target == "cloud" and self.cloud is None:
                label = "unreviewed, offline draft"
            p = build_prompt(SYSTEM, section, outline, instruction, anchor, hits, self.csl, for_cloud=False)
            prompt_text = p.user
            text, provider_name = self.local.generate(p.system, p.user, self.max_tokens), self.local.name

        findings = self.gate(text, hits)
        event_id = self.log.record(provider_name, tier, instruction, text, section)
        return BlockResult(text, label, provider_name, findings, event_id, fell_back, withheld)

    def gate(self, text: str, hits: List[dict]) -> List[str]:
        """Blueprint 3.1 and section 7 checks. Findings go back to the user, nothing is auto-fixed."""
        out: List[str] = []
        sources = {}
        for h in hits:
            sources.setdefault(h["csl_id"], "")
            sources[h["csl_id"]] += " " + h["text"]
        out += [f"Patchwriting ({f.kind}, {f.source}): {f.detail}" for f in patchwriting_check(text, sources)]
        out += [f"Unsupported number: {f.detail}" for f in fact_retention(text, [h["text"] for h in hits])]
        if "[NEEDS SOURCE]" in text:
            out.append("Model flagged a claim with no supporting source.")
        if not vo.CITE.search(text):
            out.append("No [Author, Year, p. X] citation found in the block.")
        out += vo.verify_style(text)
        return out


class Session:
    """Human checkpoint: each block is accepted (optionally edited) or rejected before the next."""

    def __init__(self, generator: BlockGenerator):
        self.gen, self.accepted = generator, []

    @property
    def text(self) -> str:
        return "\n\n".join(self.accepted)

    def propose(self, section: str, outline: str, instruction: str, tier: str = "draft",
                feedback: str = "") -> BlockResult:
        task = instruction + (f"\nAuthor feedback on the previous attempt: {feedback}" if feedback else "")
        return self.gen.generate(section, outline, task, prior_text=self.text, tier=tier)

    def accept(self, result: BlockResult, edited_text: Optional[str] = None) -> str:
        final = edited_text if edited_text is not None else result.text
        self.gen.log.finalize(result.event_id, final)
        self.accepted.append(final)
        return final

    def reject(self, result: BlockResult) -> None:
        self.gen.log.discard(result.event_id)
