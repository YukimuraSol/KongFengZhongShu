from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class EquipCandidate(BaseModel):
    slot: str
    name: str
    score: float
    set_name: str = Field("", alias="set")
    variants: list[float] = []
    has_multi: bool = False


class EquipSearchRequest(BaseModel):
    """target：生命=面板生命；攻击=面板攻击；防御=面板防御；精通=面板总精通（stat=em，加和模型）。"""
    target: float
    stat: Literal["hp", "atk", "def", "em"] = "hp"
    mode: Literal["single", "all", "best-n"] = "single"
    algorithm: Literal["optimized", "brute_force"] = "optimized"
    best_n: int = 1
    max_diff: float = 100.0
    step: float = 1.0
    auto_step: float = 0.0
    result_precision: float = 0.01
    multi_solution_mode: Literal["exclude", "skip_progress", "normal"] = "exclude"
    disabled_artifacts: list[str] = []
    disabled_loose_pieces: list[str] = []
    positions: dict[str, bool] = {}
    bonus_by_set: dict[str, float] = {}
    pools: dict[str, list[EquipCandidate]] = Field(default_factory=dict)
    artifact_json: dict[str, Any] | None = None
    base_hp: float | None = None
    no_artifact_hp: float | None = None
    include_hp_percent: bool = True
    base_atk: float | None = None
    no_artifact_atk: float | None = None
    include_atk_percent: bool = True
    base_def: float | None = None
    no_artifact_def: float | None = None
    include_def_percent: bool = True
    no_artifact_em: float | None = None
    extra_base_em: float = 0.0
    include_em_main: bool = True
    allowed_stars: list[int] | None = None

    @model_validator(mode="after")
    def _validate_search_source(self) -> "EquipSearchRequest":
        if self.artifact_json is not None:
            if self.stat == "hp":
                if self.base_hp is None or self.no_artifact_hp is None:
                    raise ValueError("使用 artifact_json 且 stat=hp 时必须同时提供 base_hp 与 no_artifact_hp")
            elif self.stat == "atk":
                if self.base_atk is None or self.no_artifact_atk is None:
                    raise ValueError("使用 artifact_json 且 stat=atk 时必须同时提供 base_atk 与 no_artifact_atk")
            elif self.stat == "def":
                if self.base_def is None or self.no_artifact_def is None:
                    raise ValueError("使用 artifact_json 且 stat=def 时必须同时提供 base_def 与 no_artifact_def")
            elif self.stat == "em":
                if self.no_artifact_em is None:
                    raise ValueError("使用 artifact_json 且 stat=em 时必须提供 no_artifact_em（卸圣遗物面板精通）")
        elif not self.pools:
            raise ValueError("请提供 pools（旧版候选池）或 artifact_json（圣显 JSON）")
        return self


class EquipPiece(BaseModel):
    slot: str
    name: str
    score: float
    set_name: str
    level: int = 0
    star: int = 0
    main_tag: str = ""
    sub_tags: list[str] = Field(default_factory=list)
    is_empty: bool = False
    piece_key: str = ""
    instance_key: str = ""
    merge_key: str = ""
    merge_line: str = ""
    preview_index: int = 0
    preview_pieces: list[dict[str, Any]] = Field(default_factory=list)


class EquipResult(BaseModel):
    key: str
    total: float
    diff: float
    total_count: int = 1
    is_multi: bool = False
    set_effects: list[str] = Field(default_factory=list)
    hp_variants: list[float] = Field(default_factory=list)
    artifact_lines: list[str] = Field(default_factory=list)
    pieces: list[EquipPiece]


class EquipSearchResponse(BaseModel):
    results: list[EquipResult]
    tried: int
    truncated: bool
    stop_reason: str
    # progress_meta in v27 parity may include non-numeric fields (e.g. closest_hp, process_log_line),
    # so keep it permissive to avoid response validation failures during running snapshots.
    progress_meta: dict[str, Any]
    process_logs: list[str] = []


class EquipDensityRequest(BaseModel):
    results: list[EquipResult]


class EquipDensityResponse(BaseModel):
    bucket: dict[str, int]


class EquipMergedPreviewRequest(BaseModel):
    artifact_json: dict[str, Any]
    base_hp: float
    include_hp_percent: bool = True


class EquipMergedPreviewResponse(BaseModel):
    by_slot: dict[str, list[str]]


class MergedPreviewPiece(BaseModel):
    instance_key: str = ""
    piece_key: str = ""
    set_name: str = ""
    level: int = 0
    star: int = 0
    main_tag: str = ""
    sub_tags: list[str] = Field(default_factory=list)
    is_empty: bool = False
    icon_url: str | None = None
    set_chs: str = ""
    stat_line_no_set: str = ""
    stat_line_with_set: str = ""


class MergedPreviewEntry(BaseModel):
    merge_key: str
    slot: str
    count: int
    display_line: str
    display_line_no_set: str
    display_line_picker: str = ""
    piece_keys: list[str] = Field(default_factory=list)
    preview_pieces: list[MergedPreviewPiece] = Field(default_factory=list)


class EquipMergedPreviewV2Response(BaseModel):
    by_slot: dict[str, list[MergedPreviewEntry]]


class EquipMergedPreviewAtkRequest(BaseModel):
    artifact_json: dict[str, Any]
    base_atk: float
    include_atk_percent: bool = True


class EquipMergedPreviewDefRequest(BaseModel):
    artifact_json: dict[str, Any]
    base_def: float
    include_def_percent: bool = True


class EquipMergedPreviewEmRequest(BaseModel):
    artifact_json: dict[str, Any]
    include_em_main: bool = True


class EquipDensityEvalRequest(BaseModel):
    """独立密度评估（从 JSON 全量枚举分箱），不依赖配装搜索结果。"""
    artifact_json: dict[str, Any]
    target_mode: Literal["atk", "def", "hp", "em"] = "atk"
    base_atk: float = 0.0
    no_artifact_atk: float = 0.0
    base_def: float = 0.0
    no_artifact_def: float = 0.0
    base_hp: float = 0.0
    no_artifact_hp: float = 0.0
    no_artifact_em: float = 0.0
    extra_base_em: float = 0.0
    bins_count: int = 30
    range_min: float = 0.0
    range_max: float = 1000.0
    multi_solution_mode: Literal["exclude", "skip_progress", "normal"] = "exclude"
    positions: dict[str, bool] = Field(default_factory=dict)
    include_percent_mains: bool = True
    include_hp_percent: bool = True
    include_em_main: bool = True
    richness_step: float = 0.01
    allowed_stars: list[int] | None = None


class EquipDensityEvalResponse(BaseModel):
    bins: list[int]
    bins_for_chart: list[float]
    bin_labels: list[str]
    summary: str
    log_lines: list[str]
    range_min: float
    range_max: float
    display_offset: float
    out_low: int
    out_high: int
    total_in_range: int


class YasSettings(BaseModel):
    scanner_path: str = ""
    output_dir: str = ""
    min_star: int = 1
    max_row: str = ""


class YasStartResponse(BaseModel):
    ok: bool
    message: str


class YasRevealRequest(BaseModel):
    target: Literal["scanner", "output"]
    # 与弹窗当前输入一致时可传，避免未点「保存设置」时「打开」仍用旧配置
    scanner_path: str | None = None
    output_dir: str | None = None


class YasRevealResponse(BaseModel):
    ok: bool
    message: str = ""


class IrmSettings(BaseModel):
    output_dir: str = ""
    min_star: int = 1
    auto_stop_export_on_items: bool = True


class IrmRevealRequest(BaseModel):
    output_dir: str | None = None


class IrmRevealResponse(BaseModel):
    ok: bool
    message: str = ""
