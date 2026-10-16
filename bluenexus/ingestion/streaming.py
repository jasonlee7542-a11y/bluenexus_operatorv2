import math
from dataclasses import dataclass

import numpy as np


@dataclass
class Welford:
    """Online population statistics with constant state per signal."""

    count: int = 0
    mean: float = 0.0
    m2: float = 0.0

    def update(self, value: float | None) -> None:
        if value is None or not math.isfinite(value):
            return
        self.count += 1
        delta = value - self.mean
        self.mean += delta / self.count
        self.m2 += delta * (value - self.mean)

    def merge(self, other: "Welford") -> None:
        if not other.count:
            return
        if not self.count:
            self.count, self.mean, self.m2 = other.count, other.mean, other.m2
            return
        total = self.count + other.count
        delta = other.mean - self.mean
        self.m2 += other.m2 + delta * delta * self.count * other.count / total
        self.mean += delta * other.count / total
        self.count = total

    def update_batch(self, values: np.ndarray) -> None:
        values = np.asarray(values, dtype=float)
        values = values[np.isfinite(values)]
        if len(values):
            center = float(np.mean(values))
            self.merge(Welford(len(values), center, float(np.sum((values - center) ** 2))))

    @property
    def variance(self) -> float | None:
        return self.m2 / self.count if self.count else None


class SwingingDoor:
    """Endpoint-constrained SDT: interpolated retained points stay within deadband.

    The endpoint constraint is stricter than some SDT variants, ensuring the exact
    retained endpoint cannot violate earlier corridor bounds. State is O(1).
    """

    def __init__(self, deadband: float):
        if not math.isfinite(deadband) or deadband < 0:
            raise ValueError("Deadband must be finite and nonnegative")
        self.deadband = deadband
        self.anchor: tuple[float, float] | None = None
        self.previous: tuple[float, float] | None = None
        self.lower = -math.inf
        self.upper = math.inf
        self.last_emitted: tuple[float, float] | None = None

    def update(self, timestamp: float, value: float) -> list[tuple[float, float]]:
        if not math.isfinite(timestamp) or not math.isfinite(value):
            raise ValueError("SDT inputs must be finite; gaps must be handled explicitly")
        point = (timestamp, value)
        if self.anchor is None:
            self.anchor = self.previous = self.last_emitted = point
            return [point]
        if timestamp <= self.previous[0]:
            raise ValueError("SDT timestamps must strictly increase")
        elapsed = timestamp - self.anchor[0]
        slope = (value - self.anchor[1]) / elapsed
        emitted = []
        if slope < self.lower or slope > self.upper:
            self.anchor = self.previous
            if self.anchor != self.last_emitted:
                emitted.append(self.anchor)
                self.last_emitted = self.anchor
            self.lower, self.upper = -math.inf, math.inf
            elapsed = timestamp - self.anchor[0]
        self.lower = max(self.lower, (value - self.anchor[1] - self.deadband) / elapsed)
        self.upper = min(self.upper, (value - self.anchor[1] + self.deadband) / elapsed)
        self.previous = point
        return emitted

    def flush(self) -> list[tuple[float, float]]:
        if self.previous is not None and self.previous != self.last_emitted:
            self.last_emitted = self.previous
            return [self.previous]
        return []
