from __future__ import annotations

import hashlib
from typing import Iterable

MASK_64 = (1 << 64) - 1


def _to_bytes(parts: Iterable[object]) -> bytes:
    return "|".join(str(p) for p in parts).encode("utf-8")


def domain_seed(*parts: object) -> int:
    digest = hashlib.sha256(_to_bytes(parts)).digest()
    return int.from_bytes(digest[:8], "big")


class SplitMix64:
    def __init__(self, seed: int):
        self.state = seed & MASK_64

    def next_u64(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & MASK_64
        z = self.state
        z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9 & MASK_64
        z = (z ^ (z >> 27)) * 0x94D049BB133111EB & MASK_64
        return z ^ (z >> 31)

    def randint(self, low: int, high: int) -> int:
        if low > high:
            raise ValueError("low must be <= high")
        span = high - low + 1
        return low + (self.next_u64() % span)

    def coin_flip(self) -> int:
        return self.next_u64() & 1


def deterministic_rng(*parts: object) -> SplitMix64:
    return SplitMix64(domain_seed(*parts))
