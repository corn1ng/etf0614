"""State loading for the NiceGUI workbench."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import RLock
import time

import pandas as pd

from etf_trading.data.index_catalog import (
    IndexCatalogEntry,
    catalog_definitions,
    catalog_entries_from_frame,
    default_index_catalog,
)
from etf_trading.data.indexes import DEFAULT_INDEXES, IndexDefinition
from etf_trading.data.quality import (
    assess_price_history,
    expected_latest_trade_date,
    history_readiness_label,
    read_failed_assessment,
)
from etf_trading.data.storage import ParquetStore, SQLiteStore
from etf_trading.research.atomic_indicators import ATOMIC_INDICATOR_COLUMNS, build_etf_atomic_indicator_snapshot
from etf_trading.research.index_health_snapshot import (
    INDEX_ATOMIC_DETAIL_COLUMNS,
    INDEX_ATOMIC_SUMMARY_COLUMNS,
    build_index_atomic_snapshot,
)
from etf_trading.research.index_etf_universe import build_index_etf_universe
from etf_trading.research.regime import TrendRegimeClassifier, add_trend_regime_features
from etf_trading.strategy.features import add_technical_features
from etf_trading.ui.chart_renderer import build_lightweight_chart_payload
from etf_trading.ui.data_coverage import (
    build_data_coverage_summary,
    build_data_gap_detail,
    build_etf_data_overview,
)

from .view_models import PlatformSnapshot

SNAPSHOT_CACHE_TTL_SECONDS = 600.0
_SNAPSHOT_CACHE: dict[tuple[str, str], tuple[float, PlatformSnapshot]] = {}
_SNAPSHOT_CACHE_LOCK = RLock()
ATOMIC_SNAPSHOT_CACHE_SCHEMA_VERSION = 2
_ATOMIC_SNAPSHOT_CACHE: dict[str, tuple[str, pd.DataFrame, datetime | None]] = {}
_ATOMIC_SNAPSHOT_ERRORS: dict[str, str] = {}
_ATOMIC_SNAPSHOT_CACHE_LOCK = RLock()
ATOMIC_SNAPSHOT_BUILD_MARKER_MAX_AGE_SECONDS = 600.0
INDEX_ATOMIC_SNAPSHOT_CACHE_SCHEMA_VERSION = 1
_INDEX_ATOMIC_SNAPSHOT_LOCK = RLock()


@dataclass(frozen=True)
class AtomicSnapshotCacheResult:
    frame: pd.DataFrame
    status: str
    generated_at: datetime | None = None
    message: str = ""


@dataclass(frozen=True)
class IndexAtomicSnapshotCacheResult:
    summary: pd.DataFrame
    details: pd.DataFrame
    status: str
    generated_at: datetime | None = None
    current_latest_date: str | None = None
    message: str = ""
    task_result_id: int | None = None


# Temporary UI compatibility while Task 5 migrates the market page.  The
# legacy trend/valuation cache contract is deliberately not retained.
IndexHealthSnapshotCacheResult = IndexAtomicSnapshotCacheResult


def create_store(db_path: str | Path | None = None) -> SQLiteStore:
    return SQLiteStore() if db_path is None else SQLiteStore(db_path)


def create_parquet_store(root: str | Path | None = None) -> ParquetStore:
    return ParquetStore() if root is None else ParquetStore(root)


def load_snapshot(store: SQLiteStore, parquet_store: ParquetStore) -> PlatformSnapshot:
    store.initialize_schema()
    raw_master = store.list_etf_master()
    watchlist = store.list_watchlist()
    catalog_entries = _snapshot_catalog_entries(store)
    core_entries = tuple(entry for entry in catalog_entries if entry.pool == "core")
    history_coverage = store.list_index_history_coverage()
    index_summary = build_index_trend_summary(
        parquet_store,
        catalog_definitions(catalog_entries),
        coverage=history_coverage,
    )
    universe = build_index_etf_universe(raw_master, parquet_store, entries=core_entries)
    store.replace_index_etf_mappings(
        universe,
        index_codes=[entry.index_code for entry in core_entries],
    )
    index_summary = _attach_index_etf_mapping_count(index_summary, universe)
    etf_overview = build_etf_data_overview(raw_master, watchlist, parquet_store, universe)
    gaps = build_data_gap_detail(raw_master, watchlist, index_summary, universe, parquet_store)
    coverage = build_data_coverage_summary(gaps, raw_master, watchlist, index_summary, universe)
    return PlatformSnapshot(
        master=etf_overview,
        watchlist=watchlist,
        index_summary=index_summary,
        universe=universe,
        gaps=gaps,
        coverage=coverage,
        generated_at=datetime.now(),
    )


def _snapshot_catalog_entries(store: SQLiteStore) -> tuple[IndexCatalogEntry, ...]:
    catalog = store.list_index_catalog()
    if catalog.empty:
        entries = default_index_catalog()
        store.upsert_index_catalog(entries)
        return tuple(entry for entry in entries if entry.pool != "reserve")
    return catalog_entries_from_frame(catalog)


def _attach_index_etf_mapping_count(index_summary: pd.DataFrame, universe: pd.DataFrame) -> pd.DataFrame:
    result = index_summary.copy()
    if result.empty:
        result["etf_mapping_count"] = pd.Series(dtype=int)
        return result
    if universe.empty or "index_code" not in universe:
        result["etf_mapping_count"] = 0
        return result
    counts = universe.groupby("index_code")["etf_code"].nunique()
    result["etf_mapping_count"] = result["index_code"].astype(str).map(counts).fillna(0).astype(int)
    return result


def load_snapshot_cached(
    store: SQLiteStore,
    parquet_store: ParquetStore,
    *,
    now: float | None = None,
    ttl_seconds: float = SNAPSHOT_CACHE_TTL_SECONDS,
) -> PlatformSnapshot:
    cache_key = _snapshot_cache_key(store, parquet_store)
    timestamp = time.monotonic() if now is None else now
    with _SNAPSHOT_CACHE_LOCK:
        cached = _SNAPSHOT_CACHE.get(cache_key)
        if cached is not None:
            cached_at, snapshot = cached
            if timestamp - cached_at <= ttl_seconds:
                return snapshot

    snapshot = load_snapshot(store, parquet_store)
    with _SNAPSHOT_CACHE_LOCK:
        _SNAPSHOT_CACHE[cache_key] = (timestamp, snapshot)
    return snapshot


def invalidate_snapshot_cache(store: SQLiteStore | None = None, parquet_store: ParquetStore | None = None) -> None:
    with _SNAPSHOT_CACHE_LOCK:
        if store is None or parquet_store is None:
            _SNAPSHOT_CACHE.clear()
            return
        _SNAPSHOT_CACHE.pop(_snapshot_cache_key(store, parquet_store), None)


def load_atomic_snapshot_cached(
    master: pd.DataFrame,
    parquet_store: ParquetStore,
    *,
    force_refresh: bool = False,
) -> AtomicSnapshotCacheResult:
    source_signature = _atomic_snapshot_source_signature(master, parquet_store)
    cache_key = _atomic_snapshot_cache_key(parquet_store)

    if not force_refresh:
        with _ATOMIC_SNAPSHOT_CACHE_LOCK:
            cached = _ATOMIC_SNAPSHOT_CACHE.get(cache_key)
            if cached is not None:
                cached_signature, frame, generated_at = cached
                if cached_signature == source_signature:
                    return AtomicSnapshotCacheResult(frame=frame.copy(), status="ready", generated_at=generated_at)

    disk_cache = _read_atomic_snapshot_disk_cache(parquet_store)
    if disk_cache is not None:
        disk_signature, frame, generated_at = disk_cache
        if disk_signature == source_signature and not force_refresh:
            with _ATOMIC_SNAPSHOT_CACHE_LOCK:
                _ATOMIC_SNAPSHOT_CACHE[cache_key] = (disk_signature, frame.copy(), generated_at)
            return AtomicSnapshotCacheResult(frame=frame.copy(), status="ready", generated_at=generated_at)

        _start_atomic_snapshot_build(master, parquet_store, source_signature)
        return AtomicSnapshotCacheResult(
            frame=frame.copy(),
            status="stale",
            generated_at=generated_at,
            message="原子指标缓存正在后台刷新",
        )

    _start_atomic_snapshot_build(master, parquet_store, source_signature)
    with _ATOMIC_SNAPSHOT_CACHE_LOCK:
        error_message = _ATOMIC_SNAPSHOT_ERRORS.get(cache_key, "")
    if error_message:
        return AtomicSnapshotCacheResult(
            frame=pd.DataFrame(columns=ATOMIC_INDICATOR_COLUMNS),
            status="failed",
            message=error_message,
        )
    return AtomicSnapshotCacheResult(
        frame=pd.DataFrame(columns=ATOMIC_INDICATOR_COLUMNS),
        status="building",
        message="原子指标缓存正在后台生成",
    )


def invalidate_atomic_snapshot_cache(parquet_store: ParquetStore | None = None) -> None:
    with _ATOMIC_SNAPSHOT_CACHE_LOCK:
        if parquet_store is None:
            _ATOMIC_SNAPSHOT_CACHE.clear()
            _ATOMIC_SNAPSHOT_ERRORS.clear()
            return
        cache_key = _atomic_snapshot_cache_key(parquet_store)
        _ATOMIC_SNAPSHOT_CACHE.pop(cache_key, None)
        _ATOMIC_SNAPSHOT_ERRORS.pop(cache_key, None)


def index_atomic_snapshot_inputs(store: SQLiteStore) -> tuple[tuple[IndexDefinition, ...], pd.DataFrame]:
    """Load the persistent non-reserve index catalogue and coverage facts."""

    entries = catalog_entries_from_frame(store.list_index_catalog(include_reserve=False))
    return catalog_definitions(entries), store.list_index_history_coverage()


def load_index_atomic_snapshot_readonly(
    parquet_store: ParquetStore,
    definitions: tuple[IndexDefinition, ...] = DEFAULT_INDEXES,
    *,
    coverage: pd.DataFrame | None = None,
) -> IndexAtomicSnapshotCacheResult:
    """Read a maintenance-produced snapshot without calculating or fetching data."""

    current_latest_date = _index_atomic_snapshot_current_latest_date(definitions, coverage)
    with _INDEX_ATOMIC_SNAPSHOT_LOCK:
        summary_file, details_file, meta_file = _index_atomic_snapshot_cache_paths(parquet_store)
        if not all(path.exists() for path in (summary_file, details_file, meta_file)):
            return _empty_index_atomic_snapshot_result("missing", current_latest_date=current_latest_date)

        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            _validate_index_atomic_snapshot_meta(meta)
            summary = pd.read_parquet(summary_file)
            details = pd.read_parquet(details_file)
            generated_at = _parse_cache_datetime(meta["generated_at"])
            if generated_at is None:
                raise ValueError("generated_at 无法解析")
        except Exception as exc:  # noqa: BLE001 - cache corruption must not break page rendering
            return _empty_index_atomic_snapshot_result(
                "failed",
                current_latest_date=current_latest_date,
                message=f"读取指数原子快照失败：{exc}",
            )

        source_signature = _index_atomic_snapshot_source_signature(parquet_store, definitions, coverage)
        coverage_signature = _index_atomic_snapshot_coverage_signature(coverage)
        status = (
            "ready"
            if meta["source_signature"] == source_signature and meta["coverage_signature"] == coverage_signature
            else "stale"
        )
        return IndexAtomicSnapshotCacheResult(
            summary=summary,
            details=details,
            status=status,
            generated_at=generated_at,
            current_latest_date=current_latest_date,
            task_result_id=_index_atomic_snapshot_task_result_id(meta.get("task_result_id")),
        )


def write_index_atomic_snapshot(
    summary: pd.DataFrame,
    details: pd.DataFrame,
    source_signature: str,
    generated_at: datetime,
    parquet_store: ParquetStore,
    *,
    definitions: tuple[IndexDefinition, ...] = (),
    coverage: pd.DataFrame | None = None,
    task_result_id: int | None = None,
) -> None:
    """Persist already-calculated index atoms without rebuilding them.

    The process-local lock prevents in-process readers from observing the
    publication window. Individual file replacements are atomic, and a failed
    publication restores backed-up live files. Cross-process transactions are
    intentionally not claimed.
    """

    with _INDEX_ATOMIC_SNAPSHOT_LOCK:
        summary_file, details_file, meta_file = _index_atomic_snapshot_cache_paths(parquet_store)
        summary_file.parent.mkdir(parents=True, exist_ok=True)
        token = f"{os.getpid()}_{time.time_ns()}"
        tmp_summary = summary_file.with_name(f".{summary_file.stem}.{token}.tmp{summary_file.suffix}")
        tmp_details = details_file.with_name(f".{details_file.stem}.{token}.tmp{details_file.suffix}")
        tmp_meta = meta_file.with_name(f".{meta_file.stem}.{token}.tmp{meta_file.suffix}")
        try:
            _index_atomic_cache_safe_summary(summary).to_parquet(tmp_summary, index=False)
            _index_atomic_cache_safe_details(details).to_parquet(tmp_details, index=False)
            tmp_meta.write_text(
                json.dumps(
                    {
                        "schema_version": INDEX_ATOMIC_SNAPSHOT_CACHE_SCHEMA_VERSION,
                        "catalog_signature": _index_atomic_snapshot_catalog_signature(definitions),
                        "source_signature": str(source_signature),
                        "generated_at": generated_at.isoformat(timespec="seconds"),
                        "data_status_counts": _index_atomic_snapshot_status_counts(summary),
                        "task_result_id": task_result_id,
                        "coverage_signature": _index_atomic_snapshot_coverage_signature(coverage),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            _verify_index_atomic_snapshot_temporary_files(tmp_summary, tmp_details, tmp_meta)
            _publish_index_atomic_snapshot(
                (summary_file, details_file, meta_file),
                (tmp_summary, tmp_details, tmp_meta),
                token,
            )
        finally:
            _safe_unlink(tmp_summary)
            _safe_unlink(tmp_details)
            _safe_unlink(tmp_meta)


def load_index_health_snapshot_cached(
    parquet_store: ParquetStore,
    definitions: tuple[IndexDefinition, ...] = DEFAULT_INDEXES,
    *,
    coverage: pd.DataFrame | None = None,
    force_refresh: bool = False,
) -> IndexAtomicSnapshotCacheResult:
    """Temporary read-only forwarder until the market page adopts the new name."""

    del force_refresh
    return load_index_atomic_snapshot_readonly(parquet_store, definitions, coverage=coverage)


def invalidate_index_health_snapshot_cache(parquet_store: ParquetStore | None = None) -> None:
    """Temporary no-op: maintenance owns writes and pages keep no index cache."""

    del parquet_store


def _snapshot_cache_key(store: SQLiteStore, parquet_store: ParquetStore) -> tuple[str, str]:
    db_path = Path(getattr(store, "db_path", "")).resolve()
    parquet_root = Path(getattr(parquet_store, "root", "")).resolve()
    return (str(db_path), str(parquet_root))


def _atomic_snapshot_cache_key(parquet_store: ParquetStore) -> str:
    return str(Path(getattr(parquet_store, "root", "data/parquet")).resolve())


def _atomic_snapshot_cache_paths(parquet_store: ParquetStore) -> tuple[Path, Path]:
    cache_dir = Path(getattr(parquet_store, "root", "data/parquet")).resolve() / "cache"
    return cache_dir / "atomic_indicators.parquet", cache_dir / "atomic_indicators.meta.json"


def _index_atomic_snapshot_cache_paths(parquet_store: ParquetStore) -> tuple[Path, Path, Path]:
    cache_dir = Path(getattr(parquet_store, "root", "data/parquet")).resolve() / "cache"
    return (
        cache_dir / "index_atomic_snapshot.parquet",
        cache_dir / "index_atomic_snapshot_details.parquet",
        cache_dir / "index_atomic_snapshot.meta.json",
    )


def _publish_index_atomic_snapshot(
    live_files: tuple[Path, Path, Path],
    temporary_files: tuple[Path, Path, Path],
    token: str,
) -> None:
    """Publish a complete snapshot, restoring the prior generation on failure.

    Callers must hold ``_INDEX_ATOMIC_SNAPSHOT_LOCK``. This provides a
    coherent protocol for one Python process; it is not a cross-process
    transaction.
    """

    backups = [(live, live.with_name(f".{live.name}.{token}.backup")) for live in live_files if live.exists()]
    moved_backups: list[tuple[Path, Path]] = []
    published_files: list[Path] = []
    try:
        for live, backup in backups:
            live.replace(backup)
            moved_backups.append((live, backup))
        for temporary, live in zip(temporary_files, live_files, strict=True):
            temporary.replace(live)
            published_files.append(live)
    except Exception:
        for live in published_files:
            _safe_unlink(live)
        for live, backup in reversed(moved_backups):
            backup.replace(live)
        raise
    else:
        for _, backup in moved_backups:
            _safe_unlink(backup)


def _verify_index_atomic_snapshot_temporary_files(
    summary_file: Path,
    details_file: Path,
    meta_file: Path,
) -> None:
    """Ensure a complete temporary generation is readable before publishing it."""

    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    _validate_index_atomic_snapshot_meta(meta)
    pd.read_parquet(summary_file)
    pd.read_parquet(details_file)


def _atomic_snapshot_build_marker_path(parquet_store: ParquetStore) -> Path:
    cache_file, _ = _atomic_snapshot_cache_paths(parquet_store)
    return cache_file.with_name("atomic_indicators.building")


def _atomic_snapshot_source_signature(master: pd.DataFrame, parquet_store: ParquetStore) -> str:
    digest = hashlib.sha256()
    digest.update(_atomic_master_signature_bytes(master))

    price_dir = Path(getattr(parquet_store, "root", "data/parquet")).resolve() / "prices"
    existing_count = 0
    missing_count = 0
    total_size = 0
    total_mtime_ns = 0
    max_mtime_ns = 0
    for code in _atomic_master_codes(master):
        path = price_dir / f"{code}.parquet"
        try:
            stat = path.stat()
        except OSError:
            missing_count += 1
            continue
        existing_count += 1
        total_size += stat.st_size
        total_mtime_ns += stat.st_mtime_ns
        max_mtime_ns = max(max_mtime_ns, stat.st_mtime_ns)

    digest.update(f"|files={existing_count}|missing={missing_count}|size={total_size}|mtime_sum={total_mtime_ns}|mtime_max={max_mtime_ns}".encode())
    return digest.hexdigest()


def _index_atomic_snapshot_source_signature(
    parquet_store: ParquetStore,
    definitions: tuple[IndexDefinition, ...],
    coverage: pd.DataFrame | None = None,
) -> str:
    digest = hashlib.sha256()
    root = Path(getattr(parquet_store, "root", "data/parquet")).resolve()
    selected_definitions = _non_reserve_index_definitions(definitions)
    digest.update(f"schema_version={INDEX_ATOMIC_SNAPSHOT_CACHE_SCHEMA_VERSION}".encode())
    digest.update(_index_atomic_snapshot_catalog_signature(selected_definitions).encode())
    digest.update(_index_coverage_signature_bytes(coverage))
    for definition in selected_definitions:
        path = root / "indexes" / f"{definition.index_code}.parquet"
        try:
            stat = path.stat()
        except OSError:
            digest.update(f"|{definition.index_code}|exists=0".encode())
        else:
            digest.update(
                f"|{definition.index_code}|exists=1|size={stat.st_size}|mtime_ns={stat.st_mtime_ns}".encode()
            )
    return digest.hexdigest()


def _index_coverage_signature_bytes(coverage: pd.DataFrame | None) -> bytes:
    if coverage is None or coverage.empty or "index_code" not in coverage:
        return b"|coverage=empty"
    columns = sorted(str(column) for column in coverage.columns)
    normalized = coverage.loc[:, columns].fillna("").astype(str).sort_values("index_code")
    return ("|coverage=" + normalized.to_csv(index=False)).encode()


def _index_atomic_snapshot_coverage_signature(coverage: pd.DataFrame | None) -> str:
    return hashlib.sha256(_index_coverage_signature_bytes(coverage)).hexdigest()


def _non_reserve_index_definitions(definitions: tuple[IndexDefinition, ...]) -> tuple[IndexDefinition, ...]:
    return tuple(definition for definition in definitions if definition.pool != "reserve")


def _index_atomic_snapshot_catalog_signature(definitions: tuple[IndexDefinition, ...]) -> str:
    digest = hashlib.sha256()
    for order, definition in enumerate(_non_reserve_index_definitions(definitions)):
        base_date = definition.index_base_date.isoformat() if definition.index_base_date is not None else ""
        digest.update(
            "|".join(
                (
                    str(order),
                    definition.index_code,
                    definition.name,
                    definition.market,
                    definition.category,
                    definition.provider_symbol,
                    str(definition.pool or ""),
                    base_date,
                    definition.baseline_source,
                )
            ).encode()
        )
    return digest.hexdigest()


def _atomic_master_signature_bytes(master: pd.DataFrame) -> bytes:
    if master.empty:
        return b"empty-master"
    preferred_columns = [
        "etf_code",
        "ETF代码",
        "name",
        "ETF名称",
        "category",
        "分类",
        "exchange",
        "交易所",
        "tradability_status",
        "本地历史",
        "历史长度",
        "最新日期",
    ]
    columns = [column for column in preferred_columns if column in master.columns]
    if not columns:
        columns = sorted(str(column) for column in master.columns)
    frame = master.loc[:, columns].fillna("").astype(str).sort_index(axis=1)
    return frame.to_csv(index=False).encode()


def _atomic_master_codes(master: pd.DataFrame) -> list[str]:
    code_column = ""
    for candidate in ("etf_code", "ETF代码"):
        if candidate in master.columns:
            code_column = candidate
            break
    if not code_column:
        return []

    codes: list[str] = []
    for value in master[code_column].dropna().tolist():
        code = _format_atomic_code(value)
        if code:
            codes.append(code)
    return sorted(set(codes))


def _format_atomic_code(value: object) -> str:
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() else text


def _read_atomic_snapshot_disk_cache(parquet_store: ParquetStore) -> tuple[str, pd.DataFrame, datetime | None] | None:
    cache_file, meta_file = _atomic_snapshot_cache_paths(parquet_store)
    if not cache_file.exists() or not meta_file.exists():
        return None
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        if int(meta.get("schema_version", 0)) != ATOMIC_SNAPSHOT_CACHE_SCHEMA_VERSION:
            return None
        frame = pd.read_parquet(cache_file)
    except Exception:  # noqa: BLE001 - a broken cache should not break the page
        return None
    generated_at = _parse_cache_datetime(meta.get("generated_at"))
    return str(meta.get("source_signature", "")), frame, generated_at


def _parse_cache_datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _start_atomic_snapshot_build(master: pd.DataFrame, parquet_store: ParquetStore, source_signature: str) -> bool:
    cache_key = _atomic_snapshot_cache_key(parquet_store)
    cache_file, _ = _atomic_snapshot_cache_paths(parquet_store)
    marker_file = _atomic_snapshot_build_marker_path(parquet_store)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with _ATOMIC_SNAPSHOT_CACHE_LOCK:
        if marker_file.exists() and not _is_stale_build_marker(marker_file):
            return False
        _ATOMIC_SNAPSHOT_ERRORS.pop(cache_key, None)
        marker_file.write_text(datetime.now().isoformat(timespec="seconds"), encoding="utf-8")

    parquet_root = Path(getattr(parquet_store, "root", "data/parquet")).resolve()
    master_file = cache_file.with_name(f"atomic_master_{os.getpid()}_{int(time.time() * 1000)}.parquet")
    try:
        master.to_parquet(master_file, index=False)
        _spawn_atomic_snapshot_process(master_file, parquet_root, source_signature, marker_file)
    except Exception as exc:  # noqa: BLE001 - report launch failures on the next page render
        with _ATOMIC_SNAPSHOT_CACHE_LOCK:
            _ATOMIC_SNAPSHOT_ERRORS[cache_key] = str(exc)
        _safe_unlink(master_file)
        _safe_unlink(marker_file)
        return False
    return True


def _is_stale_build_marker(marker_file: Path) -> bool:
    try:
        age = time.time() - marker_file.stat().st_mtime
    except OSError:
        return False
    if age <= ATOMIC_SNAPSHOT_BUILD_MARKER_MAX_AGE_SECONDS:
        return False
    _safe_unlink(marker_file)
    return True


def _spawn_atomic_snapshot_process(master_file: Path, parquet_root: Path, source_signature: str, marker_file: Path) -> None:
    project_root = Path(__file__).resolve().parents[3]
    src_root = project_root / "src"
    env = dict(os.environ)
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(src_root) if not existing_pythonpath else f"{src_root}{os.pathsep}{existing_pythonpath}"
    code = (
        "from etf_trading.nicegui_app.state import _build_atomic_snapshot_subprocess; "
        f"_build_atomic_snapshot_subprocess({str(master_file)!r}, {str(parquet_root)!r}, {source_signature!r}, {str(marker_file)!r})"
    )
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    subprocess.Popen(
        [sys.executable, "-c", code],
        cwd=project_root,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )


def _build_atomic_snapshot_subprocess(master_file: str, parquet_root: str, source_signature: str, marker_file: str) -> None:
    master_path = Path(master_file)
    marker_path = Path(marker_file)
    try:
        master = pd.read_parquet(master_path)
        _build_atomic_snapshot_worker(master, Path(parquet_root), source_signature)
    finally:
        _safe_unlink(master_path)
        _safe_unlink(marker_path)


def _build_atomic_snapshot_worker(master: pd.DataFrame, parquet_root: Path, source_signature: str) -> None:
    worker_store = ParquetStore(parquet_root)
    frame = build_etf_atomic_indicator_snapshot(master, worker_store)
    generated_at = datetime.now()
    _write_atomic_snapshot_disk_cache(frame, source_signature, generated_at, worker_store)


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return


def _write_atomic_snapshot_disk_cache(
    frame: pd.DataFrame,
    source_signature: str,
    generated_at: datetime,
    parquet_store: ParquetStore,
) -> None:
    cache_file, meta_file = _atomic_snapshot_cache_paths(parquet_store)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_cache_file = cache_file.with_name(f"{cache_file.stem}.tmp{cache_file.suffix}")
    tmp_meta_file = meta_file.with_name(f"{meta_file.stem}.tmp{meta_file.suffix}")
    frame.to_parquet(tmp_cache_file, index=False)
    tmp_cache_file.replace(cache_file)
    tmp_meta_file.write_text(
        json.dumps(
            {
                "schema_version": ATOMIC_SNAPSHOT_CACHE_SCHEMA_VERSION,
                "source_signature": source_signature,
                "generated_at": generated_at.isoformat(timespec="seconds"),
                "rows": int(len(frame)),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    tmp_meta_file.replace(meta_file)


def _empty_index_atomic_snapshot_result(
    status: str,
    *,
    current_latest_date: str | None,
    message: str = "",
) -> IndexAtomicSnapshotCacheResult:
    return IndexAtomicSnapshotCacheResult(
        summary=pd.DataFrame(columns=INDEX_ATOMIC_SUMMARY_COLUMNS),
        details=pd.DataFrame(columns=INDEX_ATOMIC_DETAIL_COLUMNS),
        status=status,
        current_latest_date=current_latest_date,
        message=message,
    )


def _validate_index_atomic_snapshot_meta(meta: object) -> None:
    if not isinstance(meta, dict):
        raise ValueError("元数据不是对象")
    if meta.get("schema_version") != INDEX_ATOMIC_SNAPSHOT_CACHE_SCHEMA_VERSION:
        raise ValueError("快照 schema 版本不匹配")
    required = (
        "catalog_signature",
        "source_signature",
        "coverage_signature",
        "generated_at",
        "data_status_counts",
        "task_result_id",
    )
    missing = [key for key in required if key not in meta]
    if missing:
        raise ValueError(f"元数据缺少字段：{', '.join(missing)}")
    if not all(isinstance(meta[key], str) for key in ("catalog_signature", "source_signature", "coverage_signature")):
        raise ValueError("元数据签名无效")
    if not isinstance(meta["data_status_counts"], dict):
        raise ValueError("数据状态统计无效")


def _index_atomic_snapshot_current_latest_date(
    definitions: tuple[IndexDefinition, ...],
    coverage: pd.DataFrame | None,
) -> str | None:
    if coverage is None or coverage.empty or "index_code" not in coverage or "latest_trade_date" not in coverage:
        return None
    codes = {definition.index_code for definition in _non_reserve_index_definitions(definitions)}
    values = pd.to_datetime(
        coverage.loc[coverage["index_code"].astype(str).isin(codes), "latest_trade_date"], errors="coerce"
    ).dropna()
    return None if values.empty else values.max().strftime("%Y-%m-%d")


def _index_atomic_snapshot_task_result_id(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _index_atomic_snapshot_status_counts(summary: pd.DataFrame) -> dict[str, int]:
    for column in ("snapshot_status", "history_status", "data_status"):
        if column in summary:
            counts = summary[column].fillna("missing").astype(str).value_counts()
            return {str(status): int(count) for status, count in counts.items()}
    return {}


_INDEX_ATOMIC_SUMMARY_TEXT_COLUMNS = {
    "index_code",
    "index_name",
    "market",
    "category",
    "pool",
    "index_base_date",
    "history_completeness_status",
    "history_completeness_message",
    "history_status",
    "history_reason",
    "latest_date",
    "data_source",
    "error_text",
    "snapshot_status",
    "snapshot_reason",
    "close_status",
    "ma_20_status",
    "ma_60_status",
    "ma_120_status",
    "ma_250_status",
    "range_20_status",
    "return_20_status",
}


def _index_atomic_cache_safe_summary(summary: pd.DataFrame) -> pd.DataFrame:
    result = summary.copy()
    for column in _INDEX_ATOMIC_SUMMARY_TEXT_COLUMNS.intersection(result.columns):
        result[column] = result[column].astype("string")
    for column in {"close_above_ma_20", "close_above_ma_60", "close_above_ma_120", "close_above_ma_250"}.intersection(result.columns):
        result[column] = result[column].astype("boolean")
    for column in set(result.columns).difference(_INDEX_ATOMIC_SUMMARY_TEXT_COLUMNS).difference(
        {"close_above_ma_20", "close_above_ma_60", "close_above_ma_120", "close_above_ma_250"}
    ):
        result[column] = pd.to_numeric(result[column], errors="coerce")
    return result


def _index_atomic_cache_safe_details(details: pd.DataFrame) -> pd.DataFrame:
    result = details.copy()
    for column in set(result.columns).difference({"value", "sample_count"}):
        result[column] = result[column].astype("string")
    if "value" in result:
        result["value"] = result["value"].astype("string")
    if "sample_count" in result:
        result["sample_count"] = pd.to_numeric(result["sample_count"], errors="coerce")
    return result


def build_index_trend_summary(
    parquet_store: ParquetStore,
    definitions: tuple[IndexDefinition, ...] = DEFAULT_INDEXES,
    *,
    coverage: pd.DataFrame | None = None,
    today: date | pd.Timestamp | None = None,
    holidays: tuple[date | pd.Timestamp | str, ...] = (),
) -> pd.DataFrame:
    classifier = TrendRegimeClassifier()
    expected = expected_latest_trade_date(today, holidays)
    coverage_by_code = _coverage_by_index_code(coverage)
    rows: list[dict[str, object]] = []
    for definition in definitions:
        coverage_row = coverage_by_code.get(definition.index_code, {})
        base_date = definition.index_base_date
        base_text = base_date.isoformat() if base_date is not None else ""
        row = {
            "index_code": definition.index_code,
            "index_name": definition.name,
            "market": definition.market,
            "category": definition.category,
            "pool": definition.pool or "core",
            "index_base_date": base_text,
            "history_completeness_status": str(coverage_row.get("completeness_status") or "NOT_VALIDATED"),
            "history_completeness_message": str(coverage_row.get("completeness_message") or "尚未校验历史完整性"),
            "large_trend": "UNKNOWN",
            "medium_trend": "UNKNOWN",
            "small_trend": "UNKNOWN",
            "allows_new_position": False,
            "latest_date": "",
            "history_rows": 0,
            "data_status": "历史缺失",
            "expected_trade_date": expected.strftime("%Y-%m-%d"),
            "trading_day_lag": pd.NA,
        }
        try:
            prices = parquet_store.read_index_prices(definition.index_code)
        except Exception:  # noqa: BLE001 - one unreadable index must not break the full market snapshot
            assessment = read_failed_assessment(expected)
            row.update(
                {
                    "data_status": history_readiness_label(assessment.readiness),
                    "expected_trade_date": assessment.expected_trade_date,
                    "trading_day_lag": pd.NA,
                }
            )
            rows.append(row)
            continue

        assessment = assess_price_history(prices, expected, min_history_rows=252, holidays=holidays)
        row.update(
            {
                "latest_date": assessment.latest_trade_date,
                "history_rows": assessment.history_rows,
                "data_status": history_readiness_label(assessment.readiness),
                "expected_trade_date": assessment.expected_trade_date,
                "trading_day_lag": assessment.trading_day_lag if assessment.trading_day_lag is not None else pd.NA,
            }
        )
        if prices.empty:
            rows.append(row)
            continue

        featured = add_trend_regime_features(prices)
        if featured.empty:
            rows.append(row)
            continue

        last = featured.iloc[-1]
        regime = classifier.classify(last)
        row.update(
            {
                "large_trend": regime.large_trend,
                "medium_trend": regime.medium_trend,
                "small_trend": regime.small_trend,
                "allows_new_position": _allows_new_index_position(row, definition, regime.allows_new_position),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def _coverage_by_index_code(coverage: pd.DataFrame | None) -> dict[str, dict[str, object]]:
    if coverage is None or coverage.empty or "index_code" not in coverage:
        return {}
    result: dict[str, dict[str, object]] = {}
    for row in coverage.fillna("").to_dict("records"):
        code = str(row.get("index_code") or "").strip()
        if code:
            result[code] = row
    return result


def _allows_new_index_position(row: dict[str, object], definition: IndexDefinition, regime_allows: object) -> bool:
    if not bool(regime_allows):
        return False
    if definition.pool is None:
        return True
    return bool(
        definition.pool == "core"
        and row.get("history_completeness_status") == "COMPLETE"
        and row.get("data_status") == "数据可用"
    )


def index_chart_payload(parquet_store: ParquetStore, index_code: str) -> list[dict]:
    prices = parquet_store.read_index_prices(index_code)
    if prices.empty:
        return build_lightweight_chart_payload(prices)
    featured = add_technical_features(prices.rename(columns={"index_code": "etf_code"}))
    return build_lightweight_chart_payload(featured, chart_type="candlestick", price_scale_mode="normal")


def etf_chart_payload(parquet_store: ParquetStore, etf_code: str) -> list[dict]:
    prices = parquet_store.read_prices(etf_code)
    if prices.empty:
        return build_lightweight_chart_payload(prices)
    featured = add_technical_features(prices)
    return build_lightweight_chart_payload(featured, chart_type="candlestick", price_scale_mode="normal")
