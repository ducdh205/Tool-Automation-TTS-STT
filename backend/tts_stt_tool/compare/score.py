"""WER / CER scoring with word-level alignment."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

import jiwer

from tts_stt_tool.compare.normalize import normalize

OpKind = Literal["equal", "sub", "del", "ins"]
_JIWER_KIND = {"equal": "equal", "substitute": "sub", "delete": "del", "insert": "ins"}


@dataclass
class WordOp:
    op: OpKind
    ref: str | None
    hyp: str | None


@dataclass
class CompareResult:
    wer: float
    cer: float
    correct: bool
    ref_norm: str
    hyp_norm: str
    ops: list[WordOp] = field(default_factory=list)

    def ops_as_dicts(self) -> list[dict]:
        return [asdict(o) for o in self.ops]


def _align(ref_words: list[str], hyp_words: list[str]) -> list[WordOp]:
    out = jiwer.process_words(" ".join(ref_words), " ".join(hyp_words))
    ops: list[WordOp] = []
    for chunk in out.alignments[0]:
        kind = _JIWER_KIND[chunk.type]
        r = ref_words[chunk.ref_start_idx : chunk.ref_end_idx]
        h = hyp_words[chunk.hyp_start_idx : chunk.hyp_end_idx]
        if kind == "del":
            ops += [WordOp("del", w, None) for w in r]
        elif kind == "ins":
            ops += [WordOp("ins", None, w) for w in h]
        else:
            ops += [WordOp(kind, a, b) for a, b in zip(r, h, strict=True)]
    return ops


def compare(ref: str, hyp: str, wer_threshold: float = 0.0) -> CompareResult:
    """Score ``hyp`` against ``ref``. ``correct`` is ``wer <= wer_threshold``."""
    ref_norm = normalize(ref)
    hyp_norm = normalize(hyp)
    if not ref_norm:
        raise ValueError("reference text is empty after normalization")
    ref_words = ref_norm.split()
    if not hyp_norm:
        ops = [WordOp("del", w, None) for w in ref_words]
        return CompareResult(1.0, 1.0, False, ref_norm, hyp_norm, ops)
    wer = float(jiwer.wer(ref_norm, hyp_norm))
    cer = float(jiwer.cer(ref_norm, hyp_norm))
    ops = _align(ref_words, hyp_norm.split())
    return CompareResult(wer, cer, wer <= wer_threshold, ref_norm, hyp_norm, ops)
