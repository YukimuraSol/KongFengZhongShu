from dataclasses import dataclass
from itertools import product

from .solver import Candidate


@dataclass
class CandidateWithVariants(Candidate):
    variants: list[float] | None = None
    has_multi: bool = False


def expand_variants(pieces: list[CandidateWithVariants]) -> list[float]:
    variant_lists: list[list[float]] = []
    for piece in pieces:
        if piece.has_multi and piece.variants:
            variant_lists.append(piece.variants)
        else:
            variant_lists.append([piece.score])
    totals = [sum(values) for values in product(*variant_lists)]
    return sorted(set(totals))
