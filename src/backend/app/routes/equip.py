import json
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..schemas.equip import (
    EquipDensityEvalRequest,
    EquipDensityEvalResponse,
    EquipDensityRequest,
    EquipDensityResponse,
    EquipMergedPreviewAtkRequest,
    EquipMergedPreviewDefRequest,
    EquipMergedPreviewEmRequest,
    EquipMergedPreviewRequest,
    EquipMergedPreviewResponse,
    EquipMergedPreviewV2Response,
    EquipSearchRequest,
    EquipSearchResponse,
    IrmRevealRequest,
    IrmRevealResponse,
    IrmSettings,
    YasRevealRequest,
    YasRevealResponse,
    YasSettings,
    YasStartResponse,
)
from ..services import artifact_paths, irm_paths, irm_service, scan_export_paths, yas_paths
from ..services.database_service import (
    get_irm_settings,
    get_yas_settings,
    save_irm_settings,
    save_yas_settings,
)
from ..services.equip_service import (
    cancel_density_eval_job,
    cancel_equip_job,
    equip_density,
    equip_density_eval,
    equip_merged_preview,
    equip_merged_preview_atk,
    equip_merged_preview_def,
    equip_merged_preview_em,
    equip_merged_preview_v2,
    equip_merged_preview_v2_atk,
    equip_merged_preview_v2_def,
    equip_merged_preview_v2_em,
    equip_search,
    get_density_eval_job,
    get_equip_job,
    get_equip_snapshot,
    start_density_eval_job,
    start_equip_job,
)

router = APIRouter(prefix="/equip", tags=["equip"])


@router.post("/search", response_model=EquipSearchResponse)
def search(payload: EquipSearchRequest) -> EquipSearchResponse:
    try:
        return equip_search(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/density", response_model=EquipDensityResponse)
def density(payload: EquipDensityRequest) -> EquipDensityResponse:
    return equip_density(payload.results)


@router.post("/density-eval", response_model=EquipDensityEvalResponse)
def density_eval(payload: EquipDensityEvalRequest) -> EquipDensityEvalResponse:
    try:
        return equip_density_eval(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/density-eval/start")
def density_eval_start(payload: EquipDensityEvalRequest) -> dict:
    try:
        job_id = start_density_eval_job(payload)
        return {"ok": True, "job_id": job_id}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/density-eval/status/{job_id}")
def density_eval_status(job_id: str) -> dict:
    job = get_density_eval_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    with job.lock:
        result_dict = job.snapshot.model_dump() if job.snapshot else None
        return {
            "ok": True,
            "status": job.status,
            "stop_reason": job.stop_reason,
            "progress_meta": dict(job.progress_meta),
            "process_logs": list(job.process_logs[-200:]),
            "partial_bins": job.partial_bins,
            "partial_bins_for_chart": job.partial_bins_for_chart,
            "partial_bin_labels": job.partial_bin_labels,
            "partial_summary": job.partial_summary,
            "result": result_dict,
        }


@router.post("/density-eval/cancel/{job_id}")
def density_eval_cancel(job_id: str) -> dict:
    ok = cancel_density_eval_job(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="job not found")
    return {"ok": True}


@router.post("/merged-preview", response_model=EquipMergedPreviewResponse)
def merged_preview(payload: EquipMergedPreviewRequest) -> EquipMergedPreviewResponse:
    return equip_merged_preview(payload)


@router.post("/merged-preview-atk", response_model=EquipMergedPreviewResponse)
def merged_preview_atk(payload: EquipMergedPreviewAtkRequest) -> EquipMergedPreviewResponse:
    return equip_merged_preview_atk(payload)


@router.post("/merged-preview-def", response_model=EquipMergedPreviewResponse)
def merged_preview_def(payload: EquipMergedPreviewDefRequest) -> EquipMergedPreviewResponse:
    return equip_merged_preview_def(payload)


@router.post("/merged-preview-em", response_model=EquipMergedPreviewResponse)
def merged_preview_em(payload: EquipMergedPreviewEmRequest) -> EquipMergedPreviewResponse:
    return equip_merged_preview_em(payload)


@router.post("/merged-preview-v2", response_model=EquipMergedPreviewV2Response)
def merged_preview_v2(payload: EquipMergedPreviewRequest) -> EquipMergedPreviewV2Response:
    return equip_merged_preview_v2(payload)


@router.post("/merged-preview-v2-atk", response_model=EquipMergedPreviewV2Response)
def merged_preview_v2_atk(payload: EquipMergedPreviewAtkRequest) -> EquipMergedPreviewV2Response:
    return equip_merged_preview_v2_atk(payload)


@router.post("/merged-preview-v2-def", response_model=EquipMergedPreviewV2Response)
def merged_preview_v2_def(payload: EquipMergedPreviewDefRequest) -> EquipMergedPreviewV2Response:
    return equip_merged_preview_v2_def(payload)


@router.post("/merged-preview-v2-em", response_model=EquipMergedPreviewV2Response)
def merged_preview_v2_em(payload: EquipMergedPreviewEmRequest) -> EquipMergedPreviewV2Response:
    return equip_merged_preview_v2_em(payload)


@router.post("/search/start")
def search_start(payload: EquipSearchRequest) -> dict:
    try:
        job_id = start_equip_job(payload)
        return {"ok": True, "job_id": job_id}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/search/status/{job_id}")
def search_status(job_id: str) -> dict:
    job = get_equip_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    from core.equip.search_impl_rev import SEARCH_IMPL_REV

    return {
        "ok": True,
        "status": job.status,
        "stop_reason": job.stop_reason,
        "progress_meta": job.progress_meta,
        "process_logs": job.process_logs[-200:],
        "process_log_count": len(job.process_logs),
        "has_snapshot": job.snapshot is not None,
        "search_impl_rev": SEARCH_IMPL_REV,
    }


@router.post("/search/cancel/{job_id}")
def search_cancel(job_id: str) -> dict:
    ok = cancel_equip_job(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="job not found")
    return {"ok": True}


@router.get("/search/result/{job_id}", response_model=EquipSearchResponse)
def search_result(job_id: str) -> EquipSearchResponse:
    job = get_equip_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job.snapshot is None:
        raise HTTPException(status_code=409, detail="job not finished")
    return job.snapshot


@router.get("/search/snapshot/{job_id}", response_model=EquipSearchResponse)
def search_snapshot(job_id: str, lock: int = 0) -> EquipSearchResponse:
    try:
        return get_equip_snapshot(job_id, lock_snapshot=bool(lock))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/yas/settings")
def yas_settings() -> dict:
    return {"ok": True, "settings": get_yas_settings()}


@router.get("/yas/builtin-meta")
def yas_builtin_meta() -> dict:
    return yas_paths.builtin_meta()


@router.get("/artifact/builtin-meta")
def artifact_builtin_meta(stat: str | None = None, tier: str | None = None) -> dict:
    if stat is None or not str(stat).strip():
        return artifact_paths.list_builtin_meta()
    return artifact_paths.builtin_meta(stat, tier)


@router.get("/artifact/builtin-json")
def artifact_builtin_json(stat: str | None = None, tier: str | None = None) -> dict:
    mode = artifact_paths.normalize_builtin_stat(stat)
    if not artifact_paths.bundled_reference_exists(mode, tier):
        raise HTTPException(
            status_code=404,
            detail=(
                f"未找到内置参考库，请将 {artifact_paths.bundled_reference_filename(mode, tier)} "
                "置于 resources/reference/ 下。"
            ),
        )
    try:
        data = artifact_paths.load_reference_json(stat=mode, tier=tier)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=f"读取内置参考库失败: {exc}") from exc
    meta = artifact_paths.builtin_meta(mode, tier)
    return {
        "ok": True,
        "stat": mode,
        "tier": meta.get("tier"),
        "tier_label": meta.get("tier_label"),
        "piece_count": meta["piece_count"],
        "display_path": meta["display_path"],
        "label": meta["label"],
        "available_stars": meta.get("available_stars", [5]),
        "default_allowed_stars": meta.get("default_allowed_stars", [5]),
        "artifact_json": data,
    }


@router.get("/artifact/scan-exports")
def artifact_scan_exports() -> dict:
    """List JSON files in the shared YAS/Irm default output folder（圣遗物输出）."""
    return scan_export_paths.list_export_files()


@router.get("/artifact/scan-export-json")
def artifact_scan_export_json(name: str) -> dict:
    try:
        return scan_export_paths.load_export_json(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"未找到扫描输出：{name}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail=f"读取扫描输出失败: {exc}") from exc


@router.get("/yas/resolve-paths")
def yas_resolve_paths(
    scanner_path: str | None = None,
    output_dir: str | None = None,
) -> dict:
    """解析弹窗当前 scanner/output 的绝对路径，供 Tauri 侧 invoke 打开资源管理器。"""
    cfg = dict(get_yas_settings())
    if scanner_path is not None:
        cfg["scanner_path"] = scanner_path
    if output_dir is not None:
        cfg["output_dir"] = output_dir
    scanner = yas_paths.resolve_scanner(cfg)
    out = yas_paths.resolve_output(cfg)
    scanner_exists = scanner.is_file()
    scanner_reveal_ready = False
    try:
        scanner.parent.mkdir(parents=True, exist_ok=True)
        scanner_reveal_ready = scanner.parent.is_dir()
    except OSError:
        scanner_reveal_ready = False
    output_ready = False
    try:
        out.mkdir(parents=True, exist_ok=True)
        output_ready = out.is_dir()
    except OSError:
        output_ready = False
    return {
        "ok": True,
        "scanner_resolved": str(scanner),
        "scanner_exists": scanner_exists,
        "scanner_reveal_ready": scanner_reveal_ready,
        "output_resolved": str(out),
        "output_ready": output_ready,
    }


@router.put("/yas/settings")
def update_yas_settings(payload: YasSettings) -> dict:
    saved = save_yas_settings(payload.model_dump())
    return {"ok": True, "settings": saved}


@router.post("/yas/reveal", response_model=YasRevealResponse)
def yas_reveal(payload: YasRevealRequest) -> YasRevealResponse:
    cfg = dict(get_yas_settings())
    if payload.scanner_path is not None:
        cfg["scanner_path"] = payload.scanner_path
    if payload.output_dir is not None:
        cfg["output_dir"] = payload.output_dir
    try:
        yas_paths.reveal_in_explorer(target=payload.target, cfg=cfg)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotADirectoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return YasRevealResponse(ok=True, message="已尝试打开资源管理器。")


@router.post("/yas/start", response_model=YasStartResponse)
def start_yas(payload: YasSettings) -> YasStartResponse:
    cfg = payload.model_dump()
    scanner = yas_paths.resolve_scanner(cfg)
    if not str(cfg.get("scanner_path", "") or "").strip() and not yas_paths.bundled_scanner_exists():
        raise HTTPException(
            status_code=400,
            detail=f"未找到内置扫描器，请将 {yas_paths.YAS_BUNDLED_EXE} 置于 resources/yas/ 下或手动选择路径。",
        )
    if not scanner.exists():
        raise HTTPException(status_code=400, detail=f"扫描器路径不存在: {scanner}")
    if not scanner.is_file():
        raise HTTPException(status_code=400, detail="扫描器路径必须是可执行文件。")

    output_dir = yas_paths.resolve_output(cfg)
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [str(scanner), f"--min-star={cfg['min_star']}"]
    max_row = str(cfg.get("max_row", "")).strip()
    if max_row:
        try:
            max_row_int = int(max_row)
            if max_row_int <= 0:
                raise ValueError
            cmd.append(f"--max-row={max_row_int}")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="最大扫描行数必须是正整数。") from exc
    try:
        pop_kw: dict = {"cwd": str(output_dir)}
        if sys.platform == "win32":
            pop_kw["creationflags"] = subprocess.CREATE_NEW_CONSOLE
        subprocess.Popen(cmd, **pop_kw)
    except OSError as exc:
        detail = f"启动扫描器失败: {exc}"
        # ERROR_ELEVATION_REQUIRED：子进程要求提升，而当前控分中枢/后端未以管理员运行
        if getattr(exc, "winerror", None) == 740 or "WinError 740" in str(exc):
            detail += " 请先退出控分中枢，在桌面或开始菜单中对其右键选择「以管理员身份运行」后再启动扫描器。"
        raise HTTPException(status_code=500, detail=detail) from exc
    return YasStartResponse(ok=True, message=f"已启动扫描器，输出目录：{output_dir}")


@router.get("/yas/pick-exe")
def yas_pick_exe() -> dict:
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askopenfilename(
            title="选择YAS扫描器可执行文件",
            filetypes=[("可执行文件", "*.exe"), ("所有文件", "*.*")],
        )
        root.destroy()
        return {"ok": True, "path": path or ""}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"打开文件选择器失败: {exc}") from exc


@router.get("/yas/pick-dir")
def yas_pick_dir() -> dict:
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askdirectory(title="选择YAS输出目录")
        root.destroy()
        return {"ok": True, "path": path or ""}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"打开目录选择器失败: {exc}") from exc


@router.get("/irm/settings")
def irm_settings() -> dict:
    return {"ok": True, "settings": get_irm_settings()}


@router.put("/irm/settings")
def update_irm_settings(payload: IrmSettings) -> dict:
    saved = save_irm_settings(payload.model_dump())
    return {"ok": True, "settings": saved}


@router.get("/irm/builtin-meta")
def irm_builtin_meta() -> dict:
    return irm_paths.builtin_meta()


@router.get("/irm/resolve-paths")
def irm_resolve_paths(output_dir: str | None = None) -> dict:
    cfg = dict(get_irm_settings())
    if output_dir is not None:
        cfg["output_dir"] = output_dir
    out = irm_paths.resolve_output(cfg)
    output_ready = False
    try:
        out.mkdir(parents=True, exist_ok=True)
        output_ready = out.is_dir()
    except OSError:
        output_ready = False
    return {
        "ok": True,
        "output_resolved": str(out),
        "output_ready": output_ready,
        "scanner_resolved": str(irm_paths.resolve_scanner()),
        "scanner_exists": irm_paths.bundled_scanner_exists(),
    }


@router.post("/irm/reveal", response_model=IrmRevealResponse)
def irm_reveal(payload: IrmRevealRequest) -> IrmRevealResponse:
    cfg = dict(get_irm_settings())
    if payload.output_dir is not None:
        cfg["output_dir"] = payload.output_dir
    try:
        irm_paths.reveal_output(cfg)
    except NotADirectoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return IrmRevealResponse(ok=True, message="已尝试打开资源管理器。")


@router.get("/irm/pick-dir")
def irm_pick_dir() -> dict:
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askdirectory(title="选择 Irminsul 输出目录")
        root.destroy()
        return {"ok": True, "path": path or ""}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"打开目录选择器失败: {exc}") from exc


@router.get("/irm/status")
def irm_status(
    min_star: int | None = None,
    output_dir: str | None = None,
    auto_stop_export_on_items: bool | None = None,
) -> dict:
    runtime: dict = {}
    if min_star is not None:
        runtime["min_star"] = min_star
    if output_dir is not None:
        runtime["output_dir"] = output_dir
    if auto_stop_export_on_items is not None:
        runtime["auto_stop_export_on_items"] = auto_stop_export_on_items
    return irm_service.get_status(runtime or None)


@router.post("/irm/toggle")
def irm_toggle(payload: IrmSettings) -> dict:
    try:
        return irm_service.toggle_capture(payload.model_dump())
    except irm_service.IrmControlError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/irm/export")
def irm_export(payload: IrmSettings) -> dict:
    try:
        return irm_service.export_results(payload.model_dump())
    except irm_service.IrmControlError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/irm/quit")
def irm_quit() -> dict:
    return irm_service.quit_scanner()
