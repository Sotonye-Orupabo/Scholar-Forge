"""Embedders. Production: OnnxEmbedder with bge-small-en-v1.5. Fallback: HashingEmbedder.

Every embedder exposes `id` (stored with the index so a model change is detected), `dim`,
`embed`, `embed_query` (retrieval models use a different prefix for queries) and `embed_many`.
"""
import hashlib
import math
import os
import re
import unicodedata
from typing import Dict, List, Optional, Protocol, Sequence

BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class Embedder(Protocol):
    id: str
    dim: int

    def embed(self, text: str) -> List[float]: ...
    def embed_query(self, text: str) -> List[float]: ...
    def embed_many(self, texts: Sequence[str]) -> List[List[float]]: ...


class HashingEmbedder:
    """Signed feature hashing over word unigrams and bigrams. No dependencies, no semantics."""

    def __init__(self, dim: int = 384):
        self.dim, self.id = dim, f"hashing-{dim}"

    def _features(self, text: str):
        words = re.findall(r"[a-z0-9]+", text.lower())
        yield from words
        yield from (f"{a}_{b}" for a, b in zip(words, words[1:]))

    def embed(self, text: str) -> List[float]:
        vec = [0.0] * self.dim
        for feat in self._features(text):
            h = int.from_bytes(hashlib.blake2b(feat.encode(), digest_size=8).digest(), "big")
            vec[h % self.dim] += 1.0 if (h >> 63) & 1 else -1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    embed_query = embed

    def embed_many(self, texts: Sequence[str]) -> List[List[float]]:
        return [self.embed(t) for t in texts]


def cosine(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class WordPieceTokenizer:
    """BERT uncased WordPiece, enough for bge-small. Reads the model's vocab.txt."""

    def __init__(self, vocab: Dict[str, int], max_length: int = 512):
        for tok in ("[CLS]", "[SEP]", "[PAD]", "[UNK]"):
            if tok not in vocab:
                raise ValueError(f"vocab is missing {tok}")
        self.vocab, self.max_length = vocab, max_length
        self.cls, self.sep, self.pad, self.unk = (vocab[t] for t in ("[CLS]", "[SEP]", "[PAD]", "[UNK]"))

    @classmethod
    def from_file(cls, path: str, max_length: int = 512) -> "WordPieceTokenizer":
        with open(path, encoding="utf-8") as fh:
            return cls({line.rstrip("\n"): i for i, line in enumerate(fh)}, max_length)

    @staticmethod
    def _basic(text: str) -> List[str]:
        text = unicodedata.normalize("NFD", text.lower())
        text = "".join(c for c in text if unicodedata.category(c) != "Mn")
        return re.findall(r"[^\W_]+|[^\s\w]|_", text)

    def _wordpiece(self, word: str) -> List[int]:
        if len(word) > 100:
            return [self.unk]
        pieces, start = [], 0
        while start < len(word):
            end, found = len(word), None
            while start < end:
                sub = ("##" if start else "") + word[start:end]
                if sub in self.vocab:
                    found = self.vocab[sub]
                    break
                end -= 1
            if found is None:
                return [self.unk]
            pieces.append(found)
            start = end
        return pieces

    def encode(self, text: str) -> List[int]:
        ids: List[int] = []
        for word in self._basic(text):
            ids.extend(self._wordpiece(word))
        return [self.cls] + ids[: self.max_length - 2] + [self.sep]


class OnnxEmbedder:
    """Runs an exported sentence-embedding model with ONNX Runtime.

    Expected layout: <model_dir>/model.onnx (or onnx/model.onnx) and <model_dir>/vocab.txt,
    as published for BAAI/bge-small-en-v1.5. bge uses CLS pooling and L2 normalisation.
    `session` and `tokenizer` can be injected for tests.
    """

    def __init__(self, model_dir: str, pooling: str = "cls", max_length: int = 512, batch_size: int = 16,
                 query_prefix: str = BGE_QUERY_PREFIX, session=None, tokenizer: Optional[WordPieceTokenizer] = None):
        if pooling not in ("cls", "mean"):
            raise ValueError("pooling must be 'cls' or 'mean'")
        self.pooling, self.batch_size, self.query_prefix = pooling, batch_size, query_prefix
        self.id = f"onnx:{os.path.basename(os.path.normpath(model_dir))}"
        self.tokenizer = tokenizer or WordPieceTokenizer.from_file(os.path.join(model_dir, "vocab.txt"), max_length)
        if session is None:
            import onnxruntime as ort
            path = next((p for p in (os.path.join(model_dir, "model.onnx"), os.path.join(model_dir, "onnx", "model.onnx"))
                         if os.path.exists(p)), None)
            if path is None:
                raise FileNotFoundError(f"no model.onnx under {model_dir}")
            session = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
        self.session = session
        self._input_names = {i.name for i in session.get_inputs()}
        self._dim: Optional[int] = None

    @property
    def dim(self) -> int:
        if self._dim is None:
            self._dim = len(self.embed("dimension probe"))
        return self._dim

    def _run(self, texts: Sequence[str]) -> List[List[float]]:
        import numpy as np
        enc = [self.tokenizer.encode(t) for t in texts]
        width = max(len(e) for e in enc)
        ids = np.full((len(enc), width), self.tokenizer.pad, dtype=np.int64)
        mask = np.zeros((len(enc), width), dtype=np.int64)
        for i, e in enumerate(enc):
            ids[i, : len(e)], mask[i, : len(e)] = e, 1
        feeds = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self._input_names:
            feeds["token_type_ids"] = np.zeros_like(ids)
        hidden = np.asarray(self.session.run(None, feeds)[0], dtype=np.float32)  # (batch, tokens, hidden)
        if self.pooling == "cls":
            pooled = hidden[:, 0]
        else:
            m = mask[:, :, None].astype(np.float32)
            pooled = (hidden * m).sum(1) / np.maximum(m.sum(1), 1e-9)
        pooled = pooled / np.maximum(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12)
        return pooled.tolist()

    def embed_many(self, texts: Sequence[str]) -> List[List[float]]:
        out: List[List[float]] = []
        for i in range(0, len(texts), self.batch_size):
            out.extend(self._run(texts[i:i + self.batch_size]))
        return out

    def embed(self, text: str) -> List[float]:
        return self.embed_many([text])[0]

    def embed_query(self, text: str) -> List[float]:
        return self.embed(self.query_prefix + text)


def get_embedder(spec: str = "hashing") -> Embedder:
    """'hashing', 'hashing:256', or 'onnx:/path/to/bge-small-en-v1.5'."""
    kind, _, arg = spec.partition(":")
    if kind == "hashing":
        return HashingEmbedder(int(arg) if arg else 384)
    if kind == "onnx" and arg:
        return OnnxEmbedder(arg)
    raise ValueError(f"unknown embedder spec: {spec!r}")
