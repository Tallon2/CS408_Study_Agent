#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/migrate_json_to_db.py — 将现有 JSON 状态文件迁移到 SQLite DB

用法:
    python scripts/migrate_json_to_db.py                    # 正式迁移
    python scripts/migrate_json_to_db.py --dry-run          # 仅预览，不写入
    python scripts/migrate_json_to_db.py --user-id user_001 # 指定用户ID

迁移策略（双写过渡阶段A → 阶段C）:
    - 读取现有 JSON 文件
    - 备份到 storage/backup_YYYYMMDD_HHMMSS/
    - 写入 SQLite DB（幂等，重复执行安全）
    - JSON 文件保留不删除（备份）
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime

# ── sys.path 处理（从项目根目录直接运行时） ─────────────────────────────────────
# 仅在项目根未被加入 sys.path 时才添加（pyproject.toml 安装后无需此操作）
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# ── 路径常量 ──────────────────────────────────────────────────────────────────
TASK_STATE_PATH = "storage/tasks/task_state.json"
PROFILE_PATH = "storage/user_profile/profile.json"


# ── 备份工具 ──────────────────────────────────────────────────────────────────

def backup_json_files(dry_run: bool) -> str | None:
    """将现有 JSON 文件备份到带时间戳的目录。返回备份目录路径（或 None）。"""
    files_to_backup = [p for p in (TASK_STATE_PATH, PROFILE_PATH) if os.path.exists(p)]
    if not files_to_backup:
        print("⚠️  未找到任何 JSON 文件，跳过备份。")
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join("storage", f"backup_{timestamp}")

    if dry_run:
        print(f"[dry-run] 将备份以下文件到 {backup_dir}/:")
        for p in files_to_backup:
            print(f"  • {p}")
        return backup_dir

    os.makedirs(backup_dir, exist_ok=True)
    for src in files_to_backup:
        dst = os.path.join(backup_dir, os.path.basename(src))
        shutil.copy2(src, dst)
        print(f"✅  已备份: {src}  →  {dst}")

    return backup_dir


# ── 迁移：task_state.json ─────────────────────────────────────────────────────

def migrate_task_state(db, user_id: str, dry_run: bool) -> bool:
    """从 task_state.json 迁移到 TaskState ORM。返回 True 表示成功或跳过。"""
    if not os.path.exists(TASK_STATE_PATH):
        print(f"⚠️  {TASK_STATE_PATH} 不存在，跳过任务状态迁移。")
        return True

    with open(TASK_STATE_PATH, "r", encoding="utf-8") as f:
        task_data: dict = json.load(f)

    print(f"\n── task_state 迁移预览 (user_id={user_id}) ──")
    print(f"  next_action   : {task_data.get('next_action', '')!r}")
    print(f"  blockers      : {task_data.get('blockers', [])}")
    print(f"  task_corrections: {task_data.get('task_corrections', [])}")
    print(f"  session_count : {task_data.get('session_count', 0)}")

    if dry_run:
        print("[dry-run] 跳过 DB 写入。")
        return True

    try:
        from dao.crud.task_state import save_task_state_dict
        save_task_state_dict(db, user_id, task_data)
        print("✅  task_state 已写入 DB。")
        return True
    except Exception as exc:
        print(f"❌  task_state 写入 DB 失败: {exc}")
        return False


# ── 迁移：profile.json ────────────────────────────────────────────────────────

def migrate_profile(db, user_id: str, dry_run: bool) -> bool:
    """从 profile.json 迁移到 UserProfile ORM。返回 True 表示成功或跳过。"""
    if not os.path.exists(PROFILE_PATH):
        print(f"⚠️  {PROFILE_PATH} 不存在，跳过用户画像迁移。")
        return True

    with open(PROFILE_PATH, "r", encoding="utf-8") as f:
        profile: dict = json.load(f)

    # 字段映射（与 memory/l4_profile.py save_profile() 保持一致）
    knowledge_graph = profile.get("knowledge_graph", {})
    stable_prefs = profile.get("stable_preferences", {})
    learning_style_str = json.dumps(stable_prefs, ensure_ascii=False)
    preferred_subjects = profile.get("source_sessions", [])
    total_sessions = profile.get("update_count", 0)

    print(f"\n── profile 迁移预览 (user_id={user_id}) ──")
    print(f"  knowledge_graph   : {len(knowledge_graph)} 个主题")
    print(f"  learning_style    : {learning_style_str!r}")
    print(f"  preferred_subjects: {preferred_subjects}")
    print(f"  total_sessions    : {total_sessions}")

    if dry_run:
        print("[dry-run] 跳过 DB 写入。")
        return True

    try:
        from dao.crud.profile import update_profile
        update_profile(
            db,
            user_id,
            knowledge_graph=knowledge_graph,
            learning_style=learning_style_str,
            preferred_subjects=preferred_subjects,
            total_sessions=total_sessions,
            last_active_at=datetime.utcnow(),
        )
        print("✅  profile 已写入 DB。")
        return True
    except Exception as exc:
        print(f"❌  profile 写入 DB 失败: {exc}")
        return False


# ── 主入口 ────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="将现有 JSON 状态文件迁移到 SQLite DB（Phase 7 迁移工具）"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅预览迁移内容，不实际写入数据库",
    )
    parser.add_argument(
        "--user-id",
        default="student_001",
        metavar="USER_ID",
        help="目标用户 ID（默认: student_001）",
    )
    args = parser.parse_args()

    user_id: str = args.user_id
    dry_run: bool = args.dry_run

    print("=" * 60)
    print("  JSON → SQLite 迁移工具  (Phase 7)")
    print("=" * 60)
    print(f"  用户 ID  : {user_id}")
    print(f"  Dry-run  : {dry_run}")
    print()

    # 1. 确保 DB 表存在
    try:
        from dao.database import create_tables, SessionLocal
        create_tables()
        print("✅  数据库表已就绪。")
    except Exception as exc:
        print(f"❌  无法初始化数据库: {exc}")
        return 1

    # 2. 备份 JSON 文件（写入模式下，在任何 DB 操作之前）
    backup_json_files(dry_run)

    # 3. 开启 DB 会话，执行迁移
    db = None if dry_run else SessionLocal()
    success = True
    try:
        ok1 = migrate_task_state(db, user_id, dry_run)
        ok2 = migrate_profile(db, user_id, dry_run)
        success = ok1 and ok2
    finally:
        if db is not None:
            db.close()

    print()
    if success:
        if dry_run:
            print("✅  Dry-run 完成，未写入任何数据。")
        else:
            print("✅  迁移完成！JSON 文件已保留，可手动删除。")
        return 0
    else:
        print("❌  迁移过程中出现错误，请检查以上日志。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
