import threading
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..schemas.equip import (
    EquipDensityEvalRequest,
    EquipDensityEvalResponse,
    EquipDensityResponse,
    EquipMergedPreviewAtkRequest,
    EquipMergedPreviewDefRequest,
    EquipMergedPreviewEmRequest,
    EquipMergedPreviewRequest,
    EquipMergedPreviewResponse,
    EquipMergedPreviewV2Response,
    EquipResult,
    EquipSearchRequest,
    EquipSearchResponse,
)
from .database_service import get_equip_rules, get_hp_equip_database
from core.equip.artifact_json_guard import validate_artifact_json_stat
from core.equip.artifact_parser import normalize_pools
from core.equip.atk_def_bundle import ALL_STAR_RATINGS, AtkDefEquipEngine, format_atk_def_artifact_line
from core.equip.atk_def_density_runner import run_density_eval
from core.equip.density_richness import normalize_richness_step
from core.equip.em_density_runner import run_em_density_eval
from core.equip.hp_density_runner import run_hp_density_eval
from core.equip.atk_def_search_runner import run_atk_def_equip_search
from core.equip.em_search_runner import run_em_equip_search
from core.equip.em_equip_engine import format_em_artifact_line, process_artifacts_for_em
from core.equip.disable_filter import filter_artifacts_by_disable
from core.equip.merged_preview_v2 import build_merged_preview_v2_by_slot
from core.equip.legacy_shengxian.process_artifacts import process_artifacts
from core.equip.legacy_shengxian.constants import ui_positions_to_legacy_positions
from core.equip.legacy_shengxian.display_format import format_artifact_info
from core.equip.legacy_shengxian.search import build_prelude_logs_from_process, run_shengxian_hp_search

_LEGACY_SLOTS = ("flower", "feather", "sand", "cup", "head")


def _allowed_stars_from_payload(payload: EquipSearchRequest) -> frozenset[int]:
    raw = getattr(payload, "allowed_stars", None)
    if raw is None:
        return ALL_STAR_RATINGS
    stars = frozenset(int(s) for s in raw if 1 <= int(s) <= 5)
    return stars if stars else frozenset({5})


def _filter_artifact_json_by_stars(
    artifact_json: dict[str, Any],
    allowed_stars: frozenset[int],
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for pos in _LEGACY_SLOTS:
        if pos not in artifact_json:
            continue
        out[pos] = [
            piece
            for piece in artifact_json[pos]
            if int(piece.get("star") or 0) in allowed_stars
        ]
    return out
from core.equip.multi_solution import CandidateWithVariants
from core.equip.search_engine import run_search


_LEGACY_SLOT_ORDER = ["flower", "feather", "sand", "cup", "head"]
_LEGACY_SLOT_TO_UI = {
    "flower": "flower",
    "feather": "plume",
    "sand": "sands",
    "cup": "goblet",
    "head": "circlet",
}


def _artifact_display_text(artifact: dict[str, Any]) -> str:
    return format_artifact_info(artifact, show_multi=True)


def _filter_legacy_artifacts_by_disabled_text(
    artifacts_by_position: dict[str, list[dict[str, Any]]],
    disabled_artifacts: list[str] | None,
    disabled_loose_pieces: list[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    return filter_artifacts_by_disable(
        artifacts_by_position,
        disabled_artifacts=disabled_artifacts,
        disabled_loose_pieces=disabled_loose_pieces,
        format_line=lambda art: _artifact_display_text(art),
    )


def _build_em_merged_preview_by_slot(
    artifacts_by_position: dict[str, list[dict[str, Any]]],
) -> dict[str, list[str]]:
    by_slot: dict[str, list[str]] = {v: [] for v in _LEGACY_SLOT_TO_UI.values()}
    for legacy_pos in _LEGACY_SLOT_ORDER:
        ui_slot = _LEGACY_SLOT_TO_UI[legacy_pos]
        rows: list[str] = []
        for art in artifacts_by_position.get(legacy_pos, []):
            if art.get("main_type") == "empty":
                continue
            rows.append(format_em_artifact_line(art, show_multi=True))
        by_slot[ui_slot] = rows
    return by_slot


def _build_atk_merged_preview_by_slot(
    artifacts_by_position: dict[str, list[dict[str, Any]]],
    *,
    is_atk_line: bool = True,
) -> dict[str, list[str]]:
    by_slot: dict[str, list[str]] = {v: [] for v in _LEGACY_SLOT_TO_UI.values()}
    for legacy_pos in _LEGACY_SLOT_ORDER:
        ui_slot = _LEGACY_SLOT_TO_UI[legacy_pos]
        rows: list[str] = []
        for art in artifacts_by_position.get(legacy_pos, []):
            if art.get("main_type") == "empty":
                continue
            rows.append(format_atk_def_artifact_line(art, is_atk_line, show_multi=True))
        by_slot[ui_slot] = rows
    return by_slot


def _build_legacy_merged_preview_by_slot(
    artifacts_by_position: dict[str, list[dict[str, Any]]],
) -> dict[str, list[str]]:
    by_slot: dict[str, list[str]] = {v: [] for v in _LEGACY_SLOT_TO_UI.values()}
    for legacy_pos in _LEGACY_SLOT_ORDER:
        ui_slot = _LEGACY_SLOT_TO_UI[legacy_pos]
        rows: list[str] = []
        for art in artifacts_by_position.get(legacy_pos, []):
            if art.get("main_type") == "empty":
                continue
            rows.append(_artifact_display_text(art))
        by_slot[ui_slot] = rows
    return by_slot


def _pool_search(
    payload: EquipSearchRequest,
    on_progress,
    should_cancel,
) -> EquipSearchResponse:
    pools = {
        slot: [
            CandidateWithVariants(
                slot=item.slot,
                name=item.name,
                score=item.score,
                set_name=item.set_name,
                variants=item.variants or [],
                has_multi=item.has_multi,
            )
            for item in items
        ]
        for slot, items in payload.pools.items()
    }
    disabled = {str(x).strip() for x in (payload.disabled_artifacts or []) if str(x).strip()}
    if disabled:
        pools = {
            slot: [item for item in items if str(item.name) not in disabled]
            for slot, items in pools.items()
        }
    pools = normalize_pools(pools, ["flower", "plume", "sands", "goblet", "circlet"], use_empty_placeholder=True)
    equip_rules = get_equip_rules()
    bonus_by_set = payload.bonus_by_set or equip_rules.get("bonus_by_set", {})
    output = run_search(
        pools=pools,
        target=payload.target,
        mode=payload.mode,
        best_n=payload.best_n,
        max_diff=payload.max_diff,
        bonus_by_set=bonus_by_set,
        algorithm=payload.algorithm,
        step=payload.step,
        auto_step=payload.auto_step,
        multi_solution_mode=payload.multi_solution_mode,
        on_progress=on_progress,
        should_cancel=should_cancel,
    )
    results = [
        EquipResult(
            key=item.key,
            total=item.total,
            diff=item.diff,
            is_multi=any(getattr(p, "has_multi", False) for p in item.pieces),
            set_effects=[],
            hp_variants=[float(item.total)],
            artifact_lines=[],
            pieces=[
                {
                    "slot": p.slot,
                    "name": p.name,
                    "score": p.score,
                    "set_name": p.set_name,
                }
                for p in item.pieces
            ],
        )
        for item in output.results
    ]
    return EquipSearchResponse(
        results=results,
        tried=output.tried,
        truncated=output.truncated,
        stop_reason=output.stop_reason,
        progress_meta=output.progress_meta,
        process_logs=output.process_logs,
    )


def _atk_def_shengxian_search(
    payload: EquipSearchRequest,
    on_progress,
    should_cancel,
    on_result,
) -> EquipSearchResponse:
    assert payload.artifact_json is not None
    stat = getattr(payload, "stat", "hp")
    if stat == "def":
        assert payload.base_def is not None and payload.no_artifact_def is not None
        base_atk_f = 0.0
        no_artifact_atk_f = 0.0
        base_def_f = float(payload.base_def)
        no_artifact_def_f = float(payload.no_artifact_def)
        target_mode = "def"
        include_mains = bool(payload.include_def_percent)
    else:
        assert payload.base_atk is not None and payload.no_artifact_atk is not None
        base_atk_f = float(payload.base_atk)
        no_artifact_atk_f = float(payload.no_artifact_atk)
        base_def_f = 0.0
        no_artifact_def_f = 0.0
        target_mode = "atk"
        include_mains = bool(payload.include_atk_percent)

    positions_legacy = ui_positions_to_legacy_positions(payload.positions)
    pos_enabled = {p: bool(positions_legacy.get(p, True)) for p in _LEGACY_SLOT_ORDER}

    def _on_prog(meta: dict[str, Any]) -> None:
        if on_progress:
            on_progress(meta)

    rows, tried, truncated, stop, meta, prelude = run_atk_def_equip_search(
        artifact_json=payload.artifact_json,
        target=float(payload.target),
        base_atk=base_atk_f,
        no_artifact_atk=no_artifact_atk_f,
        base_def=base_def_f,
        no_artifact_def=no_artifact_def_f,
        target_mode=target_mode,
        tolerance=float(payload.max_diff),
        hp_step=float(payload.step),
        result_precision=float(payload.result_precision or 0.01),
        algorithm=payload.algorithm,
        multi_solution_mode=payload.multi_solution_mode,
        positions_enabled=pos_enabled,
        best_n=int(payload.best_n),
        auto_step=float(payload.auto_step if payload.auto_step is not None else payload.step or 0.0),
        include_percent_mains=include_mains,
        allowed_stars=_allowed_stars_from_payload(payload),
        on_progress=_on_prog,
        should_cancel=should_cancel,
        on_result=on_result,
        disabled_artifacts=payload.disabled_artifacts,
        disabled_loose_pieces=payload.disabled_loose_pieces,
    )
    results = [
        EquipResult(
            key=r.key,
            total=r.total,
            diff=r.diff,
            total_count=r.total_count,
            is_multi=r.is_multi,
            set_effects=r.set_effects,
            hp_variants=r.hp_variants,
            artifact_lines=r.artifact_lines,
            pieces=r.pieces,
        )
        for r in rows
    ]
    full_logs = prelude + [f"stop={stop}, tried={tried}"]
    return EquipSearchResponse(
        results=results,
        tried=tried,
        truncated=truncated,
        stop_reason=stop,
        progress_meta=meta,
        process_logs=full_logs,
    )


def _em_shengxian_search(
    payload: EquipSearchRequest,
    on_progress,
    should_cancel,
    on_result,
) -> EquipSearchResponse:
    assert payload.artifact_json is not None
    assert payload.no_artifact_em is not None
    positions_legacy = ui_positions_to_legacy_positions(payload.positions)
    pos_enabled = {p: bool(positions_legacy.get(p, True)) for p in _LEGACY_SLOT_ORDER}

    def _on_prog(meta: dict[str, Any]) -> None:
        if on_progress:
            on_progress(meta)

    rows, tried, truncated, stop, meta, prelude = run_em_equip_search(
        artifact_json=payload.artifact_json,
        target=float(payload.target),
        no_artifact_em=float(payload.no_artifact_em),
        extra_base_em=float(payload.extra_base_em or 0.0),
        tolerance=float(payload.max_diff),
        hp_step=float(payload.step),
        result_precision=float(payload.result_precision or 0.01),
        algorithm=payload.algorithm,
        multi_solution_mode=payload.multi_solution_mode,
        positions_enabled=pos_enabled,
        best_n=int(payload.best_n),
        auto_step=float(payload.auto_step if payload.auto_step is not None else payload.step or 0.0),
        include_em_main=bool(payload.include_em_main),
        allowed_stars=_allowed_stars_from_payload(payload),
        on_progress=_on_prog,
        should_cancel=should_cancel,
        on_result=on_result,
        disabled_artifacts=payload.disabled_artifacts,
        disabled_loose_pieces=payload.disabled_loose_pieces,
    )
    results = [
        EquipResult(
            key=r.key,
            total=r.total,
            diff=r.diff,
            total_count=r.total_count,
            is_multi=r.is_multi,
            set_effects=r.set_effects,
            hp_variants=r.hp_variants,
            artifact_lines=r.artifact_lines,
            pieces=r.pieces,
        )
        for r in rows
    ]
    full_logs = prelude + [f"stop={stop}, tried={tried}"]
    return EquipSearchResponse(
        results=results,
        tried=tried,
        truncated=truncated,
        stop_reason=stop,
        progress_meta=meta,
        process_logs=full_logs,
    )


def _legacy_shengxian_search(
    payload: EquipSearchRequest,
    on_progress,
    should_cancel,
    on_result,
) -> EquipSearchResponse:
    assert payload.artifact_json is not None
    assert payload.base_hp is not None and payload.no_artifact_hp is not None
    db = get_hp_equip_database()
    filtered_json = _filter_artifact_json_by_stars(
        payload.artifact_json,
        _allowed_stars_from_payload(payload),
    )
    arts, finfo = process_artifacts(
        filtered_json,
        payload.base_hp,
        payload.include_hp_percent,
        [],
        db,
    )
    arts = _filter_legacy_artifacts_by_disabled_text(
        arts, payload.disabled_artifacts, payload.disabled_loose_pieces
    )
    positions_legacy = ui_positions_to_legacy_positions(payload.positions)
    positions_to_calc = [p for p, en in positions_legacy.items() if en]
    prelude_logs = build_prelude_logs_from_process(arts, positions_to_calc, finfo)
    out = run_shengxian_hp_search(
        positions_legacy=positions_legacy,
        artifacts_by_position=arts,
        base_hp=payload.base_hp,
        no_artifact_hp=payload.no_artifact_hp,
        target_hp=payload.target,
        tolerance=payload.max_diff,
        hp_step=payload.step,
        algorithm=payload.algorithm,
        auto_step=payload.auto_step,
        multi_solution_mode=payload.multi_solution_mode,
        mode=payload.mode,
        best_n=payload.best_n,
        include_hp_percent=payload.include_hp_percent,
        result_precision=float(payload.result_precision or 0.01),
        on_progress=on_progress,
        on_result=on_result,
        should_cancel=should_cancel,
        prelude_logs=prelude_logs,
    )
    results = [
        EquipResult(
            key=h.key,
            total=h.hp,
            diff=h.diff,
            total_count=h.total_count,
            is_multi=h.is_multi,
            set_effects=h.set_effects,
            hp_variants=h.hp_variants,
            artifact_lines=h.artifact_lines,
            pieces=h.pieces,
        )
        for h in out.results
    ]
    return EquipSearchResponse(
        results=results,
        tried=out.tried,
        truncated=out.truncated,
        stop_reason=out.stop_reason,
        progress_meta=out.progress_meta,
        process_logs=out.process_logs,
    )


def _validate_search_artifact_json(payload: EquipSearchRequest) -> None:
    if payload.artifact_json is None:
        return
    validate_artifact_json_stat(payload.artifact_json, getattr(payload, "stat", "hp"))


def equip_search(payload: EquipSearchRequest) -> EquipSearchResponse:
    if payload.artifact_json is not None:
        _validate_search_artifact_json(payload)
        st = getattr(payload, "stat", "hp")
        if st in ("atk", "def"):
            return _atk_def_shengxian_search(payload, None, None, None)
        if st == "em":
            return _em_shengxian_search(payload, None, None, None)
        return _legacy_shengxian_search(payload, None, None, None)
    return _pool_search(payload, None, None)


def equip_density(results: list[EquipResult]) -> EquipDensityResponse:
    bucket: dict[str, int] = {}
    for item in results:
        k = f"{int(item.diff // 5) * 5}-{int(item.diff // 5) * 5 + 4}"
        bucket[k] = bucket.get(k, 0) + 1
    return EquipDensityResponse(bucket=bucket)


def _density_positions_enabled(payload: EquipDensityEvalRequest) -> dict[str, bool]:
    pl = ui_positions_to_legacy_positions(payload.positions)
    return {p: bool(pl.get(p, True)) for p in _LEGACY_SLOT_ORDER}


def _density_richness_step(payload: EquipDensityEvalRequest) -> float:
    return normalize_richness_step(float(payload.richness_step))


def _density_allowed_stars(payload: EquipDensityEvalRequest) -> frozenset[int] | None:
    raw = getattr(payload, "allowed_stars", None)
    if raw is None:
        return None
    stars = frozenset(int(s) for s in raw if 1 <= int(s) <= 5)
    return stars if stars else frozenset({5})


def _density_artifact_json(payload: EquipDensityEvalRequest) -> dict[str, Any]:
    data = payload.artifact_json
    stars = _density_allowed_stars(payload)
    if stars is None:
        return data
    return _filter_artifact_json_by_stars(data, stars)


def equip_density_eval(payload: EquipDensityEvalRequest) -> EquipDensityEvalResponse:
    pos_en = _density_positions_enabled(payload)
    richness_step = _density_richness_step(payload)
    artifact_json = _density_artifact_json(payload)
    if payload.target_mode == "hp":
        db = get_hp_equip_database()
        out = run_hp_density_eval(
            artifact_json=artifact_json,
            base_hp=float(payload.base_hp),
            no_artifact_hp=float(payload.no_artifact_hp),
            include_hp_percent=bool(payload.include_hp_percent),
            bins_count=payload.bins_count,
            range_min=payload.range_min,
            range_max=payload.range_max,
            multi_solution_mode=payload.multi_solution_mode,
            positions_enabled=pos_en,
            database_settings=db,
            richness_step=richness_step,
        )
    elif payload.target_mode == "em":
        out = run_em_density_eval(
            artifact_json=artifact_json,
            no_artifact_em=float(payload.no_artifact_em),
            extra_base_em=float(payload.extra_base_em),
            include_em_main=bool(payload.include_em_main),
            bins_count=payload.bins_count,
            range_min=payload.range_min,
            range_max=payload.range_max,
            multi_solution_mode=payload.multi_solution_mode,
            positions_enabled=pos_en,
            richness_step=richness_step,
        )
    else:
        out = run_density_eval(
            artifact_json=artifact_json,
            target_mode=payload.target_mode,
            base_atk=payload.base_atk,
            no_artifact_atk=payload.no_artifact_atk,
            base_def=payload.base_def,
            no_artifact_def=payload.no_artifact_def,
            bins_count=payload.bins_count,
            range_min=payload.range_min,
            range_max=payload.range_max,
            multi_solution_mode=payload.multi_solution_mode,
            positions_enabled=pos_en,
            include_percent_mains=payload.include_percent_mains,
            richness_step=richness_step,
        )
    return EquipDensityEvalResponse(
        bins=out.bins,
        bins_for_chart=out.bins_for_chart,
        bin_labels=out.bin_labels,
        summary=out.summary,
        log_lines=out.log_lines,
        range_min=out.range_min,
        range_max=out.range_max,
        display_offset=out.display_offset,
        out_low=out.out_low,
        out_high=out.out_high,
        total_in_range=out.total_in_range,
    )


@dataclass
class DensityEvalJob:
    job_id: str
    status: str = "running"
    progress_meta: dict = field(default_factory=dict)
    process_logs: list = field(default_factory=list)
    cancel_event: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    snapshot: EquipDensityEvalResponse | None = None
    stop_reason: str = ""
    partial_bins: list | None = None
    partial_bins_for_chart: list | None = None
    partial_bin_labels: list[str] | None = None
    partial_summary: str = ""


_DENSITY_JOBS: dict[str, DensityEvalJob] = {}
_DENSITY_LOCK = threading.Lock()


def _run_density_eval_job_thread(payload: EquipDensityEvalRequest, job: DensityEvalJob) -> None:
    pos_en = _density_positions_enabled(payload)

    def on_prog(meta: dict[str, Any]) -> None:
        with job.lock:
            if "enumeration_progress" in meta:
                job.progress_meta["enumeration_progress"] = float(meta["enumeration_progress"])
            if "processed" in meta:
                job.progress_meta["tried"] = int(meta["processed"])
            if "total" in meta:
                job.progress_meta["total_combos"] = int(meta["total"])
            if meta.get("bins") is not None:
                job.partial_bins = list(meta["bins"])
            if meta.get("bins_for_chart") is not None:
                job.partial_bins_for_chart = list(meta["bins_for_chart"])
            if meta.get("bin_labels"):
                job.partial_bin_labels = list(meta["bin_labels"])
            if meta.get("summary"):
                job.partial_summary = str(meta["summary"])
            lt = meta.get("log_tail")
            if isinstance(lt, list):
                job.process_logs.extend(str(x) for x in lt)

    def should_cancel() -> bool:
        return job.cancel_event.is_set()

    try:
        richness_step = _density_richness_step(payload)
        artifact_json = _density_artifact_json(payload)
        if payload.target_mode == "hp":
            db = get_hp_equip_database()
            out = run_hp_density_eval(
                artifact_json=artifact_json,
                base_hp=float(payload.base_hp),
                no_artifact_hp=float(payload.no_artifact_hp),
                include_hp_percent=bool(payload.include_hp_percent),
                bins_count=payload.bins_count,
                range_min=payload.range_min,
                range_max=payload.range_max,
                multi_solution_mode=payload.multi_solution_mode,
                positions_enabled=pos_en,
                database_settings=db,
                richness_step=richness_step,
                should_cancel=should_cancel,
                on_progress=on_prog,
            )
        elif payload.target_mode == "em":
            out = run_em_density_eval(
                artifact_json=artifact_json,
                no_artifact_em=float(payload.no_artifact_em),
                extra_base_em=float(payload.extra_base_em),
                include_em_main=bool(payload.include_em_main),
                bins_count=payload.bins_count,
                range_min=payload.range_min,
                range_max=payload.range_max,
                multi_solution_mode=payload.multi_solution_mode,
                positions_enabled=pos_en,
                richness_step=richness_step,
                should_cancel=should_cancel,
                on_progress=on_prog,
            )
        else:
            out = run_density_eval(
                artifact_json=artifact_json,
                target_mode=payload.target_mode,
                base_atk=payload.base_atk,
                no_artifact_atk=payload.no_artifact_atk,
                base_def=payload.base_def,
                no_artifact_def=payload.no_artifact_def,
                bins_count=payload.bins_count,
                range_min=payload.range_min,
                range_max=payload.range_max,
                multi_solution_mode=payload.multi_solution_mode,
                positions_enabled=pos_en,
                include_percent_mains=payload.include_percent_mains,
                richness_step=richness_step,
                should_cancel=should_cancel,
                on_progress=on_prog,
            )
        job.snapshot = EquipDensityEvalResponse(
            bins=out.bins,
            bins_for_chart=out.bins_for_chart,
            bin_labels=out.bin_labels,
            summary=out.summary,
            log_lines=out.log_lines,
            range_min=out.range_min,
            range_max=out.range_max,
            display_offset=out.display_offset,
            out_low=out.out_low,
            out_high=out.out_high,
            total_in_range=out.total_in_range,
        )
        job.status = "finished"
        job.stop_reason = "cancelled" if job.cancel_event.is_set() else "finished"
    except Exception as exc:  # pragma: no cover
        job.status = "failed"
        job.stop_reason = str(exc)
        job.process_logs.append(f"密度评估失败：{exc}")


def start_density_eval_job(payload: EquipDensityEvalRequest) -> str:
    job_id = uuid.uuid4().hex
    job = DensityEvalJob(job_id=job_id)
    with _DENSITY_LOCK:
        _DENSITY_JOBS[job_id] = job

    def _runner() -> None:
        _run_density_eval_job_thread(payload, job)

    threading.Thread(target=_runner, daemon=True).start()
    return job_id


def get_density_eval_job(job_id: str) -> DensityEvalJob | None:
    with _DENSITY_LOCK:
        return _DENSITY_JOBS.get(job_id)


def cancel_density_eval_job(job_id: str) -> bool:
    job = get_density_eval_job(job_id)
    if not job:
        return False
    job.cancel_event.set()
    with job.lock:
        job.progress_meta["cancel_requested"] = 1
    return True


def equip_merged_preview(payload: EquipMergedPreviewRequest) -> EquipMergedPreviewResponse:
    db = get_hp_equip_database()
    arts, _ = process_artifacts(
        payload.artifact_json,
        payload.base_hp,
        payload.include_hp_percent,
        [],
        db,
    )
    return EquipMergedPreviewResponse(by_slot=_build_legacy_merged_preview_by_slot(arts))


def equip_merged_preview_atk(payload: EquipMergedPreviewAtkRequest) -> EquipMergedPreviewResponse:
    p = payload
    engine = AtkDefEquipEngine()
    engine.load_database_json()
    arts, _ = engine.process_artifacts(
        p.artifact_json,
        float(p.base_atk),
        0.0,
        allowed_stars=ALL_STAR_RATINGS,
        include_percent_mains=p.include_atk_percent,
        target_mode="atk",
        avoid_chars=None,
    )
    return EquipMergedPreviewResponse(by_slot=_build_atk_merged_preview_by_slot(arts))


def equip_merged_preview_def(payload: EquipMergedPreviewDefRequest) -> EquipMergedPreviewResponse:
    p = payload
    engine = AtkDefEquipEngine()
    engine.load_database_json()
    arts, _ = engine.process_artifacts(
        p.artifact_json,
        0.0,
        float(p.base_def),
        allowed_stars=ALL_STAR_RATINGS,
        include_percent_mains=p.include_def_percent,
        target_mode="def",
        avoid_chars=None,
    )
    return EquipMergedPreviewResponse(by_slot=_build_atk_merged_preview_by_slot(arts, is_atk_line=False))


def equip_merged_preview_em(payload: EquipMergedPreviewEmRequest) -> EquipMergedPreviewResponse:
    p = payload
    engine = AtkDefEquipEngine()
    engine.load_database_json()
    arts, _ = process_artifacts_for_em(
        engine,
        p.artifact_json,
        allowed_stars=ALL_STAR_RATINGS,
        include_em_main=p.include_em_main,
        avoid_chars=None,
    )
    return EquipMergedPreviewResponse(by_slot=_build_em_merged_preview_by_slot(arts))


def equip_merged_preview_v2(payload: EquipMergedPreviewRequest) -> EquipMergedPreviewV2Response:
    db = get_hp_equip_database()
    arts, _ = process_artifacts(
        payload.artifact_json,
        payload.base_hp,
        payload.include_hp_percent,
        [],
        db,
    )
    by_slot = build_merged_preview_v2_by_slot(arts, format_line=format_artifact_info, target_mode="hp")
    return EquipMergedPreviewV2Response(by_slot=by_slot)


def equip_merged_preview_v2_atk(payload: EquipMergedPreviewAtkRequest) -> EquipMergedPreviewV2Response:
    p = payload
    engine = AtkDefEquipEngine()
    engine.load_database_json()
    arts, _ = engine.process_artifacts(
        p.artifact_json,
        float(p.base_atk),
        0.0,
        allowed_stars=ALL_STAR_RATINGS,
        include_percent_mains=p.include_atk_percent,
        target_mode="atk",
        avoid_chars=None,
    )
    by_slot = build_merged_preview_v2_by_slot(
        arts,
        format_line=format_atk_def_artifact_line,
        format_kwargs={"is_atk_mode": True},
        target_mode="atk",
    )
    return EquipMergedPreviewV2Response(by_slot=by_slot)


def equip_merged_preview_v2_def(payload: EquipMergedPreviewDefRequest) -> EquipMergedPreviewV2Response:
    p = payload
    engine = AtkDefEquipEngine()
    engine.load_database_json()
    arts, _ = engine.process_artifacts(
        p.artifact_json,
        0.0,
        float(p.base_def),
        allowed_stars=ALL_STAR_RATINGS,
        include_percent_mains=p.include_def_percent,
        target_mode="def",
        avoid_chars=None,
    )
    by_slot = build_merged_preview_v2_by_slot(
        arts,
        format_line=format_atk_def_artifact_line,
        format_kwargs={"is_atk_mode": False},
        target_mode="def",
    )
    return EquipMergedPreviewV2Response(by_slot=by_slot)


def equip_merged_preview_v2_em(payload: EquipMergedPreviewEmRequest) -> EquipMergedPreviewV2Response:
    p = payload
    engine = AtkDefEquipEngine()
    engine.load_database_json()
    arts, _ = process_artifacts_for_em(
        engine,
        p.artifact_json,
        allowed_stars=ALL_STAR_RATINGS,
        include_em_main=p.include_em_main,
        avoid_chars=None,
    )
    by_slot = build_merged_preview_v2_by_slot(arts, format_line=format_em_artifact_line, target_mode="em")
    return EquipMergedPreviewV2Response(by_slot=by_slot)


@dataclass
class EquipJob:
    job_id: str
    status: str = "running"
    progress_meta: dict = field(default_factory=lambda: {"enumeration_progress": 0.0, "target_collect_progress": 0.0, "tried": 0})
    stop_reason: str = ""
    process_logs: list[str] = field(default_factory=list)
    snapshot: EquipSearchResponse | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    current_results_dict: dict[str, dict[str, Any]] = field(default_factory=dict)
    snapshot_results: list[EquipResult] = field(default_factory=list)
    snapshot_locked: bool = False


_JOBS: dict[str, EquipJob] = {}
_LOCK = threading.Lock()


def start_equip_job(payload: EquipSearchRequest) -> str:
    _validate_search_artifact_json(payload)
    job_id = uuid.uuid4().hex
    job = EquipJob(job_id=job_id)
    with job.lock:
        job.progress_meta["search_target"] = float(payload.target)
        job.progress_meta["search_stat"] = payload.stat
    with _LOCK:
        _JOBS[job_id] = job

    def _runner() -> None:
        try:
            resp = equip_search_with_progress(payload, job)
            with job.lock:
                final_meta = dict(resp.progress_meta)
                for k in ("search_target", "search_stat", "best_diff", "best_total", "tried", "enumeration_progress"):
                    if k in job.progress_meta:
                        final_meta[k] = job.progress_meta[k]
                job.progress_meta = final_meta
                if job.snapshot_locked and job.snapshot_results:
                    job.snapshot = EquipSearchResponse(
                        results=list(job.snapshot_results),
                        tried=resp.tried,
                        truncated=resp.truncated,
                        stop_reason=resp.stop_reason,
                        progress_meta=dict(final_meta),
                        process_logs=list(resp.process_logs),
                    )
                else:
                    job.snapshot = EquipSearchResponse(
                        results=list(resp.results),
                        tried=resp.tried,
                        truncated=resp.truncated,
                        stop_reason=resp.stop_reason,
                        progress_meta=dict(final_meta),
                        process_logs=list(resp.process_logs),
                    )
            job.status = "finished"
            job.stop_reason = resp.stop_reason
            job.process_logs = list(resp.process_logs)
        except Exception as exc:  # pragma: no cover
            job.status = "failed"
            job.stop_reason = str(exc)
            job.process_logs.append(f"搜索失败：{exc}")

    threading.Thread(target=_runner, daemon=True).start()
    return job_id


def equip_search_with_progress(payload: EquipSearchRequest, job: EquipJob) -> EquipSearchResponse:
    if payload.artifact_json is not None:
        st = getattr(payload, "stat", "hp")
        if st in ("atk", "def"):
            return _atk_def_shengxian_search(
                payload,
                on_progress=lambda meta: _update_job_progress(job, meta),
                on_result=lambda data: _update_job_result(job, data),
                should_cancel=lambda: job.cancel_event.is_set(),
            )
        if st == "em":
            return _em_shengxian_search(
                payload,
                on_progress=lambda meta: _update_job_progress(job, meta),
                should_cancel=lambda: job.cancel_event.is_set(),
                on_result=lambda data: _update_job_result(job, data),
            )
        return _legacy_shengxian_search(
            payload,
            on_progress=lambda meta: _update_job_progress(job, meta),
            on_result=lambda data: _update_job_result(job, data),
            should_cancel=lambda: job.cancel_event.is_set(),
        )
    return _pool_search(
        payload,
        on_progress=lambda meta: _update_job_progress(job, meta),
        should_cancel=lambda: job.cancel_event.is_set(),
    )


def _apply_monotonic_best(job: EquipJob, prev_meta: dict[str, Any]) -> None:
    """搜索线程推送的 meta 不得覆盖已记录的更近 interim 结果。"""
    try:
        prev_diff = prev_meta.get("best_diff")
        new_diff = job.progress_meta.get("best_diff")
        prev_total = prev_meta.get("best_total")
        if prev_diff is not None and new_diff is not None and float(new_diff) > float(prev_diff):
            job.progress_meta["best_diff"] = prev_diff
            if prev_total is not None:
                job.progress_meta["best_total"] = prev_total
    except (TypeError, ValueError):
        pass


def _sync_job_best_from_total(job: EquipJob, total: float) -> bool:
    target = job.progress_meta.get("search_target")
    if target is None:
        return False
    try:
        tgt = float(target)
        t = float(total)
        new_diff = abs(t - tgt)
        prev = job.progress_meta.get("best_diff")
        if prev is not None and new_diff >= float(prev):
            return False
        job.progress_meta["best_diff"] = float(new_diff)
        job.progress_meta["best_total"] = t
        return True
    except (TypeError, ValueError):
        return False


def _update_job_progress(job: EquipJob, meta: dict) -> None:
    with job.lock:
        prev_meta = dict(job.progress_meta)
        job.progress_meta.update(meta)
        _apply_monotonic_best(job, prev_meta)
        lines = meta.get("process_logs")
        if isinstance(lines, list):
            incoming = [str(x) for x in lines]
            if not job.process_logs:
                job.process_logs = incoming
            elif len(incoming) > len(job.process_logs):
                job.process_logs = incoming
        line = meta.get("process_log_line")
        if isinstance(line, str) and line:
            if not job.process_logs or job.process_logs[-1] != line:
                job.process_logs.append(line)
        tsa = meta.get("target_step_activated")
        if isinstance(tsa, (int, float)):
            job.progress_meta["target_step_activated"] = int(tsa)


def _update_job_result(job: EquipJob, data: dict[str, Any]) -> None:
    key = str(data.get("key", ""))
    if not key:
        return
    with job.lock:
        prev = job.current_results_dict.get(key, {})
        merged = dict(prev)
        merged.update(data)
        job.current_results_dict[key] = merged
        try:
            _sync_job_best_from_total(job, float(data.get("total", 0)))
        except (TypeError, ValueError):
            pass

def _build_snapshot_results_from_current(job: EquipJob) -> list[EquipResult]:
    items: list[EquipResult] = []
    for key, data in job.current_results_dict.items():
        try:
            total = float(data.get("total", 0))
        except Exception:
            total = 0.0
        try:
            diff = float(data.get("diff", 0))
        except Exception:
            diff = abs(total - float(data.get("target", 0) or 0))
        items.append(
            EquipResult(
                key=key,
                total=total,
                diff=diff,
                total_count=int(data.get("total_count", 1) or 1),
                is_multi=bool(data.get("is_multi", False)),
                set_effects=list(data.get("set_effects") or []),
                hp_variants=list(data.get("hp_variants") or [total]),
                artifact_lines=list(data.get("artifact_lines") or []),
                pieces=list(data.get("pieces") or []),
            )
        )
    target_raw = job.progress_meta.get("search_target")
    stat = str(job.progress_meta.get("search_stat") or "")
    if job.status == "running" and stat in ("atk", "def", "em") and target_raw is not None:
        try:
            tgt = float(target_raw)
            items.sort(key=lambda r: (abs(r.total - tgt), r.total, r.key))
        except (TypeError, ValueError):
            items.sort(key=lambda r: r.total)
    else:
        items.sort(key=lambda r: r.total)  # HP 升序（对齐原版）
    return items


def get_equip_snapshot(job_id: str, lock_snapshot: bool) -> EquipSearchResponse:
    job = get_equip_job(job_id)
    if not job:
        raise ValueError("job not found")
    with job.lock:
        if lock_snapshot:
            snap = _build_snapshot_results_from_current(job)
            job.snapshot_results = list(snap)
            job.snapshot_locked = True
            resp = EquipSearchResponse(
                results=list(job.snapshot_results),
                tried=int(job.progress_meta.get("tried", 0) or 0),
                truncated=True,
                stop_reason=job.stop_reason or "running",
                progress_meta=dict(job.progress_meta),
                process_logs=list(job.process_logs),
            )
            # v27 parity: after finish, clicking "获取最终结果" should overwrite second cache each time.
            if job.snapshot is not None:
                job.snapshot = resp
            return resp
        if job.snapshot is not None:
            if job.snapshot_locked and job.snapshot_results:
                return EquipSearchResponse(
                    results=list(job.snapshot_results),
                    tried=int(job.progress_meta.get("tried", 0) or 0),
                    truncated=True,
                    stop_reason=job.stop_reason or "running",
                    progress_meta=dict(job.progress_meta),
                    process_logs=list(job.process_logs),
                )
            return job.snapshot
        if job.snapshot_locked:
            return EquipSearchResponse(
                results=list(job.snapshot_results),
                tried=int(job.progress_meta.get("tried", 0) or 0),
                truncated=True,
                stop_reason=job.stop_reason or "running",
                progress_meta=dict(job.progress_meta),
                process_logs=list(job.process_logs),
            )
        snap = _build_snapshot_results_from_current(job)
        job.snapshot_results = list(snap)
        return EquipSearchResponse(
            results=snap,
            tried=int(job.progress_meta.get("tried", 0) or 0),
            truncated=True,
            stop_reason=job.stop_reason or "running",
            progress_meta=dict(job.progress_meta),
            process_logs=list(job.process_logs),
        )


def get_equip_job(job_id: str) -> EquipJob | None:
    with _LOCK:
        return _JOBS.get(job_id)


def cancel_equip_job(job_id: str) -> bool:
    job = get_equip_job(job_id)
    if not job:
        return False
    job.cancel_event.set()
    with job.lock:
        job.progress_meta["cancel_requested"] = 1
    return True
