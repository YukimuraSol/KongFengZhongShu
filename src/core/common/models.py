from dataclasses import dataclass


@dataclass
class LinearInput:
    x1: float
    d1: float
    x2: float
    d2: float
    target_d: float


@dataclass
class LinearResult:
    slope: float
    intercept: float
    required_x: float
