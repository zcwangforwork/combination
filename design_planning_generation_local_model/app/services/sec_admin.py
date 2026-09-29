"""
sec_admin — 保密密级管理域核心逻辑（2026-09-28 新增）

依据方案 §4.3 / §4.4 / §8.2，提供管理端五功能中的后端原语：
  1. 密级台账（list_sec_ledger）—— 全部入库文件的密级状态清单视图
  2. 高频拦截清单（sec_audit.query_denied_top，本模块不重复）
  3. 批量标注 / 单文件密级变更（set_source_sec_level / set_sources_sec_level）
  4. 存量回填（backfill_all_collections，幂等可断点续传）
  5. 审计查询（sec_audit.query_*，本模块不重复）

变更完整性保障（§4.4）：
  按 source_file 一次性更新其全部 chunk；更新后执行方差校验（该文件全部
  chunk 的 sec_level 方差应为 0），失败自动重试一次，仍失败则抛错告警——
  杜绝"一份文档一半旧密级一半新密级"的中间态。

所有管理动作由调用方（路由层）负责：ADMIN 鉴权 + sec_admin_audit 留痕。
"""
import datetime
import json
from pathlib import Path

from app.services.rag import sec_filter
from app.services import kb_scope

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_PROGRESS_DIR = _PROJECT_ROOT / "temp"


# ── 目标 collection 枚举（台账 / 变更 / 回填共用）──

def iter_target_collections(admin_scope: bool = True):
    """枚举管理操作的目标 (client, collection_name) 对。

    ADMIN 视角：共享库标准库 + 共享 uploads + 全部个人库 uploads
    （与 kb_scope ADMIN 检索作用域一致；管理动作仅 ADMIN 可发起）。
    """
    from app.services.rag.vector_store import VectorStore
    targets = []
    # 共享库（BASE_DIR）
    store = VectorStore(collection_name="uploads")
    base_client = store.client
    for coll_name in kb_scope.SHARED_QUERY_COLLECTIONS:
        targets.append((base_client, coll_name))
    # 个人库（ADMIN = 全部）
    if admin_scope:
        for d in kb_scope.list_user_kb_dirs():
            targets.append((VectorStore._get_client_for_path(d),
                            kb_scope.UPLOADS_COLLECTION))
    return targets


def _now_iso() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _audit(operator: str, action: str, target: str, detail: str) -> None:
    from app.services import sec_audit
    sec_audit.enqueue_admin_audit({
        "ts": _now_iso(), "operator": operator or "(unknown)",
        "action": action, "target": target, "detail": detail,
    })


# ── 1. 密级台账（§8.2.1）──

def list_sec_ledger() -> list:
    """全部入库文件的密级台账：按 source_file 聚合，跨 collection 合并。

    Returns:
        [{source_file, sec_level, sec_label, sec_source, chunk_count,
          sec_updated_at, collections, mixed}] — mixed=True 表示该文件
        各 chunk 密级不一致（数据异常，应立即修复）。
    """
    files: dict = {}
    for client, coll_name in iter_target_collections(admin_scope=True):
        try:
            coll = client.get_collection(name=coll_name)
            result = coll.get(include=["metadatas"])
        except Exception:  # noqa: BLE001 — 库/collection 不存在时跳过
            continue
        for meta in result.get("metadatas", []) or []:
            if not meta:
                continue
            sf = meta.get("source_file", "")
            if not sf:
                continue
            lvl = sec_filter.normalize_sec_level(meta.get("sec_level"))
            entry = files.setdefault(sf, {
                "source_file": sf,
                "sec_level": lvl if lvl is not None else sec_filter.SEC_MAX_LEVEL,
                "sec_label": sec_filter.sec_label(lvl) if lvl is not None else "未标注",
                "sec_source": meta.get("sec_source", "") or "",
                "chunk_count": 0,
                "sec_updated_at": meta.get("sec_updated_at", "") or "",
                "collections": set(),
                "_levels": set(),
            })
            entry["chunk_count"] += 1
            entry["collections"].add(coll_name)
            entry["_levels"].add(lvl)
            ts = meta.get("sec_updated_at", "") or ""
            if ts > entry["sec_updated_at"]:
                entry["sec_updated_at"] = ts
    out = []
    for entry in files.values():
        levels = entry.pop("_levels")
        entry["collections"] = sorted(entry["collections"])
        entry["mixed"] = len(levels) > 1
        out.append(entry)
    out.sort(key=lambda x: (-x["chunk_count"], x["source_file"]))
    return out


# ── 3. 密级变更（§4.4 单文件 / 批量）──

def _update_chunks_sec(client, coll_name: str, ids: list, new_level: int,
                        acl_version: str) -> int:
    """对指定 chunk ids 原地更新密级五字段（保留其余 metadata 不变）"""
    if not ids:
        return 0
    coll = client.get_collection(name=coll_name)
    updated = 0
    BATCH = 500
    for i in range(0, len(ids), BATCH):
        part = ids[i:i + BATCH]
        got = coll.get(ids=part, include=["metadatas"])
        metas = []
        for meta in got.get("metadatas", []) or []:
            meta = dict(meta or {})
            sec_filter.stamp_sec_meta(meta, sec_level=new_level, sec_source="manual",
                                      acl_version=acl_version)
            metas.append(meta)
        coll.update(ids=part, metadatas=metas)
        updated += len(part)
    return updated


def _variance_ok(client, coll_name: str, source_file: str, new_level: int) -> bool:
    """方差校验：该文件全部 chunk 的 sec_level 应一致且等于 new_level（§4.4）"""
    try:
        coll = client.get_collection(name=coll_name)
        result = coll.get(where={"source_file": source_file}, include=["metadatas"])
        for meta in result.get("metadatas", []) or []:
            if sec_filter.normalize_sec_level((meta or {}).get("sec_level")) != new_level:
                return False
        return True
    except Exception:  # noqa: BLE001
        return False


def set_source_sec_level(source_file: str, new_level: int, reason: str,
                         operator: str) -> dict:
    """单文件密级变更（升密/降密）：定位全部 chunk → 原子变更 → 方差校验。

    只改 metadata，不重嵌入、不换 id，秒级生效（§4.4）；
    跨共享库与全部个人库查找该 source_file（ADMIN 视角）。
    """
    lvl = sec_filter.normalize_sec_level(new_level)
    if lvl is None:
        raise ValueError(f"非法密级值: {new_level}")
    acl_version = f"chg-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
    total_updated = 0
    touched = []
    for client, coll_name in iter_target_collections(admin_scope=True):
        try:
            coll = client.get_collection(name=coll_name)
            result = coll.get(where={"source_file": source_file}, include=["metadatas"])
            ids = result.get("ids", []) or []
        except Exception:  # noqa: BLE001
            continue
        if not ids:
            continue
        _update_chunks_sec(client, coll_name, ids, lvl, acl_version)
        # 方差校验失败自动重试一次，仍失败抛错（杜绝半新半旧）
        if not _variance_ok(client, coll_name, source_file, lvl):
            _update_chunks_sec(client, coll_name, ids, lvl, acl_version + "-retry")
            if not _variance_ok(client, coll_name, source_file, lvl):
                raise RuntimeError(
                    f"密级变更方差校验失败: {source_file}@{coll_name}（已重试），"
                    "请检查后重跑")
        total_updated += len(ids)
        touched.append(coll_name)
    _audit(operator, "sec_level_change", source_file,
           f"new_level={lvl}({sec_filter.sec_label(lvl)}) chunks={total_updated}"
           f" collections={touched} reason={reason}")
    if total_updated == 0:
        raise LookupError(f"未找到 source_file={source_file} 的任何 chunk")
    # 密级变更后 BM25 缓存无需失效（打分器只含语料与打分，§5.4 复核机制天然兼容）
    return {"source_file": source_file, "new_level": lvl,
            "sec_label": sec_filter.sec_label(lvl), "chunk_count": total_updated,
            "collections": touched, "acl_version": acl_version}


def set_sources_sec_level(source_files: list, new_level: int, reason: str,
                          operator: str) -> dict:
    """批量密级标注（§8.2.3）：按文件列表逐个执行，单个失败不中断整体。"""
    results = []
    failures = []
    for sf in source_files:
        try:
            results.append(set_source_sec_level(sf, new_level, reason, operator))
        except Exception as e:  # noqa: BLE001
            failures.append({"source_file": sf, "error": str(e)})
    _audit(operator, "sec_level_batch", f"{len(source_files)} files",
           f"new_level={new_level} ok={len(results)} failed={len(failures)}")
    return {"ok": results, "failed": failures}


# ── 4. 存量回填（§4.3：先全量保守 sec_level=3，后批量精标降级）──

def _progress_file(acl_version: str) -> Path:
    _PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
    return _PROGRESS_DIR / f"sec_backfill_{acl_version}.json"


def backfill_all_collections(*, acl_version: str, level: int = None,
                             sec_source: str = "inherit", operator: str = "(script)",
                             dry_run: bool = False) -> dict:
    """存量回填：为缺密级字段的 chunk 补 sec_level（缺省 3，fail-closed 起步）。

    幂等：已带本 acl_version 标记的 chunk 跳过；重跑自动跳过已回填。
    断点续传：进度文件记录每个 collection 已处理到的 offset，中断后重跑续传。
    每 500 chunk 一批更新。
    """
    lvl = sec_filter.normalize_sec_level(level)
    if lvl is None:
        lvl = sec_filter.cfg_default_level()
    prog_path = _progress_file(acl_version)
    progress = {}
    if prog_path.exists():
        try:
            progress = json.loads(prog_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            progress = {}

    stats = {"acl_version": acl_version, "level": lvl, "collections": {},
             "total_updated": 0, "total_scanned": 0, "dry_run": dry_run}
    for client, coll_name in iter_target_collections(admin_scope=True):
        try:
            coll = client.get_collection(name=coll_name)
            result = coll.get(include=["metadatas"])
            ids = result.get("ids", []) or []
            metas = result.get("metadatas", []) or []
        except Exception as e:  # noqa: BLE001
            stats["collections"][coll_name] = {"error": str(e)}
            continue
        start_off = int(progress.get(coll_name, 0))
        stats["total_scanned"] += len(ids)
        pending_ids, pending_metas = [], []
        updated = 0
        for idx in range(start_off, len(ids)):
            meta = metas[idx] or {}
            need = ("sec_level" not in meta) or (meta.get("acl_version") != acl_version)
            if need:
                pending_ids.append(ids[idx])
                pending_metas.append(meta)
            if len(pending_ids) >= 500 or (idx == len(ids) - 1 and pending_ids):
                if not dry_run:
                    new_metas = []
                    for m in pending_metas:
                        m = dict(m)
                        sec_filter.stamp_sec_meta(
                            m, sec_level=lvl, sec_source=sec_source,
                            acl_version=acl_version)
                        new_metas.append(m)
                    coll.update(ids=pending_ids, metadatas=new_metas)
                updated += len(pending_ids)
                pending_ids, pending_metas = [], []
                progress[coll_name] = idx + 1
                _dump_progress(prog_path, progress)
        progress[coll_name] = len(ids)
        _dump_progress(prog_path, progress)
        stats["collections"][coll_name] = {
            "chunks": len(ids), "updated": updated,
            "resumed_from": start_off}
        stats["total_updated"] += updated

    _audit(operator, "sec_backfill", f"acl_version={acl_version}",
           f"level={lvl} updated={stats['total_updated']}"
           f" scanned={stats['total_scanned']} dry_run={dry_run}")
    return stats


def _dump_progress(path: Path, progress: dict) -> None:
    try:
        path.write_text(json.dumps(progress, ensure_ascii=False), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print(f"[sec_admin] 回填进度写入失败: {e}")
