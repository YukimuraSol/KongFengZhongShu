from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Point(BaseModel):
    x: float = Field(..., description="属性值")
    y: float = Field(..., description="伤害值")


class TwoPointRequest(BaseModel):
    target: float
    x1: float
    y1: float
    x2: float
    y2: float


class LinearFitRequest(BaseModel):
    target: float
    groups: list[Point]

    @field_validator("groups")
    @classmethod
    def validate_groups(cls, v: list[Point]) -> list[Point]:
        if len(v) < 2:
            raise ValueError("线性模型至少需要2组数据")
        return v


class HpRequest(BaseModel):
    mode: Literal["normal", "em-model", "linear-model"]
    target: float | str
    r: float | str = 0.0
    hp: float | str = 0.0
    damage: float | str = 0.0
    em: float | str = 0.0
    em_c: float | str = 0.0
    em_x: float | str = 0.0
    base_other: float | str = 0.0
    global_bonus_percent: float | str = 0.0
    group_count: int = Field(1, ge=1, le=10)
    groups: list[Point] = []


class EmRequest(BaseModel):
    # multi-group：多组拟合；single-normal / single-other：新前端单组两档；
    # single-group：兼容旧客户端，与 has_other_multiplier 双轨推断单组分支。
    mode: Literal["multi-group", "single-group", "single-normal", "single-other"]
    target: float | str
    k_main: float | str
    groups: list[Point] = []
    em0: float | str = 0.0
    dmg0: float | str = 0.0
    atk_total0: float | str = 0.0
    # 单组：与流浪晚星「主C有其他倍率介入」一致
    has_other_multiplier: bool = False
    other_ratio_r: float | str = 0.0
    other_base_b: float | str = 0.0


class CalcResult(BaseModel):
    target: float
    required: float
    attr_per_damage: float
    damage_per_attr: float
    note: str
