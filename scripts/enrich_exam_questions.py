"""
enrich_exam_questions.py — 真题数据增强脚本

功能：
    1. fill_answers     : 对 answer 为空的题目，调用智谱 GLM-4-Flash 自动补全答案和简短解析
    2. annotate_subjects: 对 subject/chapter/topic 为「待标注」的题目，批量打标科目/章节

使用方法（在项目根目录下执行）：
    python scripts/enrich_exam_questions.py              # 两个功能都执行
    python scripts/enrich_exam_questions.py --only-answers   # 只补全答案
    python scripts/enrich_exam_questions.py --only-annotate  # 只打标科目

执行流程：
    1. 读取 storage/knowledge_base/exam_questions.jsonl
    2. fill_answers：补全空答案（每50题保存一次中间结果）
    3. annotate_subjects：批量打标科目/章节（每批10题，每50题保存一次）
    4. 保存最终结果
    5. 清空旧 ChromaDB 集合，重新入库
"""

import os
import sys
import json
import re
import time
import argparse

# ──────────────────────────────────────────────
# 将项目根目录加入 sys.path，确保能 import config 和 memory
# ──────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.llm_client import get_llm_client

# ──────────────────────────────────────────────
# 常量
# ──────────────────────────────────────────────
JSONL_PATH = "storage/knowledge_base/exam_questions.jsonl"
INTERIM_PATH = "storage/knowledge_base/exam_questions_interim.jsonl"  # 中间保存路径
API_SLEEP = 0.3          # API 调用间隔（秒），防止限速
SAVE_EVERY = 50          # 每处理多少题保存一次中间结果
BATCH_SIZE = 10          # annotate_subjects 每批题数

# 初始化 LLM 客户端
client = get_llm_client()


# ============================================================
# 工具函数：JSONL 读写
# ============================================================

def load_jsonl(path: str) -> list[dict]:
    """
    读取 JSONL 文件，返回题目列表。
    每行一个 JSON 对象，跳过空行和解析失败的行。
    """
    questions = []
    abs_path = os.path.abspath(path)
    if not os.path.exists(abs_path):
        print(f"[错误] 文件不存在：{abs_path}")
        return questions

    with open(abs_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                questions.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"[警告] 第 {line_num} 行 JSON 解析失败，跳过：{e}")

    print(f"[读取] 共加载 {len(questions)} 道题 ← {abs_path}")
    return questions


def save_jsonl(questions: list[dict], path: str) -> None:
    """
    将题目列表写回 JSONL 文件（UTF-8 编码，每行一个 JSON 对象）。
    ensure_ascii=False 保证中文不被转义。
    """
    abs_path = os.path.abspath(path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "w", encoding="utf-8") as f:
        for q in questions:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    print(f"[保存] {len(questions)} 道题 → {abs_path}")


# ============================================================
# 工具函数：调用 LLM
# ============================================================

def call_llm(prompt: str, max_tokens: int = 200) -> str:
    """
    调用智谱 GLM-4-Flash，返回模型回复的纯文本。
    失败时返回空字符串，不抛出异常。
    """
    try:
        resp = client.chat.completions.create(
            model=client.default_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,   # 低温度，减少随机性，提高准确率
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"  [LLM错误] API 调用失败：{e}")
        return ""


# ============================================================
# 功能1：补全答案
# ============================================================

def fill_answers(questions: list[dict]) -> list[dict]:
    """
    对 answer 为空的题目，调用 LLM 补全答案，并生成简短解析。

    处理流程：
        1. 筛选出 answer == "" 的题目
        2. 构造 Prompt，让 LLM 只输出一个字母（A/B/C/D）
        3. 用正则提取答案字母；失败则保留空，打印警告
        4. 若答案提取成功，再调用 LLM 生成 1-2 句解析
        5. 每处理 SAVE_EVERY 题，保存中间结果

    Args:
        questions: 全量题目列表（会原地修改答案字段）

    Returns:
        修改后的题目列表
    """
    # 找出所有需要补全答案的题目（保留原始索引，便于更新）
    todo = [(i, q) for i, q in enumerate(questions) if q.get("answer", "") == ""]
    total_todo = len(todo)

    if total_todo == 0:
        print("[fill_answers] 所有题目均已有答案，跳过。")
        return questions

    print(f"\n{'='*60}")
    print(f"[fill_answers] 共 {total_todo} 道题需要补全答案")
    print(f"{'='*60}")

    success_count = 0
    processed = 0

    for idx, (orig_idx, q) in enumerate(todo):
        year = q.get("year", "未知")
        number = q.get("number", "?")
        question_text = q.get("question", "")
        options = q.get("options", {})

        # ── Step 1：请 LLM 给出答案字母 ──────────────────────
        answer_prompt = (
            "你是计算机考研408专家。请回答以下选择题，"
            "只需给出正确选项字母（A/B/C/D），不需要解释。\n\n"
            f"题目：{question_text}\n"
            f"A. {options.get('A', '')}\n"
            f"B. {options.get('B', '')}\n"
            f"C. {options.get('C', '')}\n"
            f"D. {options.get('D', '')}\n\n"
            "直接输出一个字母，如：A"
        )

        llm_reply = call_llm(answer_prompt, max_tokens=10)
        time.sleep(API_SLEEP)

        # 用正则从回复中提取第一个 A/B/C/D（大小写均可，取大写）
        match = re.search(r'[A-Da-d]', llm_reply)
        if not match:
            print(f"  [警告] {year}年第{number}题 答案提取失败，回复：{repr(llm_reply[:50])}")
            processed += 1
            # 每 SAVE_EVERY 题保存中间结果
            if processed % SAVE_EVERY == 0:
                save_jsonl(questions, INTERIM_PATH)
                print(f"[进度] 已处理 {processed}/{total_todo}，成功 {success_count} 题（中间保存）")
            continue

        answer = match.group(0).upper()
        questions[orig_idx]["answer"] = answer

        # ── Step 2：生成简短解析 ──────────────────────────────
        explanation_prompt = (
            "你是计算机考研408专家。请用1-2句话解释以下题目答案的原因。\n\n"
            f"题目：{question_text}\n"
            f"答案：{answer}\n\n"
            "直接输出解释，不超过100字。"
        )

        explanation = call_llm(explanation_prompt, max_tokens=150)
        time.sleep(API_SLEEP)

        # 只有当前解析为空时才写入（不覆盖已有解析）
        if explanation and not questions[orig_idx].get("explanation", "").strip():
            questions[orig_idx]["explanation"] = explanation

        success_count += 1
        processed += 1

        # 打印逐题进度
        print(f"  ✅ {year}年第{number}题 → 答案：{answer}")

        # 每 SAVE_EVERY 题打印进度并保存中间结果
        if processed % SAVE_EVERY == 0:
            save_jsonl(questions, INTERIM_PATH)
            print(f"[进度] 已处理 {processed}/{total_todo}，成功 {success_count} 题（中间保存）")

    # 处理完成后打印汇总
    print(f"\n[fill_answers] 完成：成功补全 {success_count}/{total_todo} 道题的答案")
    return questions


# ============================================================
# 功能2：打标科目/章节
# ============================================================

def annotate_subjects(questions: list[dict]) -> list[dict]:
    """
    对 subject == "待标注" 的题目，批量调用 LLM 打标科目/章节/考点。

    处理流程：
        1. 筛选出 subject == "待标注" 的题目
        2. 每 BATCH_SIZE 道题组成一批，构造 Prompt
        3. 让 LLM 返回 JSON 数组，包含 number/subject/chapter/topic
        4. 解析 JSON，按 number 匹配并更新对应题目
        5. 解析失败的题目保留「待标注」，继续处理其他批次

    Args:
        questions: 全量题目列表（会原地修改 subject/chapter/topic 字段）

    Returns:
        修改后的题目列表
    """
    # 筛选待标注题目，保留 (原始索引, 题目) 映射
    todo = [(i, q) for i, q in enumerate(questions) if q.get("subject", "") == "待标注"]
    total_todo = len(todo)

    if total_todo == 0:
        print("[annotate_subjects] 所有题目均已打标，跳过。")
        return questions

    print(f"\n{'='*60}")
    print(f"[annotate_subjects] 共 {total_todo} 道题需要打标")
    print(f"{'='*60}")

    # 构建 number → 原始索引 映射表，便于后续按 number 更新
    # 注意：同一 number 可能出现在不同年份，用 (year, number) 作为联合键
    # 为简化，先用 number 映射，若有冲突则以最后一个为准（实际数据中同批题号不冲突）
    number_to_orig_idx = {}
    for orig_idx, q in todo:
        key = (q.get("year"), q.get("number"))
        number_to_orig_idx[key] = orig_idx

    success_count = 0
    processed_batches = 0
    total_processed_questions = 0

    # 按 BATCH_SIZE 分批处理
    for batch_start in range(0, total_todo, BATCH_SIZE):
        batch = todo[batch_start: batch_start + BATCH_SIZE]

        # ── 构造批量 Prompt ─────────────────────────────────
        question_list_str = ""
        batch_keys = []  # 记录本批的 (year, number) 顺序，用于匹配结果

        for seq, (orig_idx, q) in enumerate(batch, start=1):
            question_text = q.get("question", "")
            # 只显示题目前100字，防止 prompt 过长
            short_q = question_text[:150] + "..." if len(question_text) > 150 else question_text
            question_list_str += f"{seq}. {short_q}\n"
            batch_keys.append((q.get("year"), q.get("number"), orig_idx))

        annotate_prompt = (
            "你是计算机考研408专家。请为以下选择题标注科目和章节。\n\n"
            "408四个科目：数据结构、计算机组成原理、操作系统、计算机网络\n\n"
            "请对每道题输出JSON数组，格式：\n"
            '[{"number":1,"subject":"数据结构","chapter":"排序","topic":"快速排序"},...]\n\n'
            "要求：\n"
            "- number 对应题目前的序号（1开始）\n"
            "- subject 必须是四个科目之一\n"
            "- chapter 只写大类（如「排序」「进程管理」「TCP/IP」），不超过6个字\n"
            "- topic 写具体考点，不超过10个字\n"
            "- 只输出 JSON 数组，不要其他文字\n\n"
            f"题目列表：\n{question_list_str}"
        )

        llm_reply = call_llm(annotate_prompt, max_tokens=800)
        time.sleep(API_SLEEP)

        # ── 解析 LLM 返回的 JSON ────────────────────────────
        parsed_annotations = _parse_annotation_json(llm_reply, len(batch))

        # ── 按序号匹配并更新题目 ─────────────────────────────
        batch_success = 0
        for ann in parsed_annotations:
            seq = ann.get("number")         # 序号（1-based，对应本批内编号）
            subject = ann.get("subject", "").strip()
            chapter = ann.get("chapter", "").strip()
            topic = ann.get("topic", "").strip()

            # 校验序号范围
            if not isinstance(seq, int) or seq < 1 or seq > len(batch):
                print(f"  [警告] 无效序号 {seq}，跳过该条标注")
                continue

            # 校验 subject 是否合法
            valid_subjects = {"数据结构", "计算机组成原理", "操作系统", "计算机网络"}
            if subject not in valid_subjects:
                print(f"  [警告] 序号 {seq} 科目无效：{repr(subject)}，跳过")
                continue

            # 根据序号找到对应的原始题目索引
            _, _, orig_idx = batch_keys[seq - 1]

            # 更新字段
            questions[orig_idx]["subject"] = subject
            questions[orig_idx]["chapter"] = chapter if chapter else "待标注"
            questions[orig_idx]["topic"] = topic if topic else "待标注"
            batch_success += 1

        success_count += batch_success
        processed_batches += 1
        total_processed_questions += len(batch)

        # 每批打印简要进度
        print(f"  批次 {processed_batches}（{batch_start+1}~{batch_start+len(batch)}）："
              f"解析成功 {batch_success}/{len(batch)} 题")

        # 每 SAVE_EVERY 题保存中间结果
        if total_processed_questions % SAVE_EVERY == 0 or total_processed_questions >= total_todo:
            save_jsonl(questions, INTERIM_PATH)
            print(f"[进度] 已处理 {total_processed_questions}/{total_todo}，成功 {success_count} 题（中间保存）")

    print(f"\n[annotate_subjects] 完成：成功打标 {success_count}/{total_todo} 道题")
    return questions


def _parse_annotation_json(llm_reply: str, expected_count: int) -> list[dict]:
    """
    从 LLM 回复中提取 JSON 数组。

    LLM 可能在 JSON 前后有多余文字，用正则找到第一个 [...] 块。
    解析失败时返回空列表，不抛出异常。

    Args:
        llm_reply      : LLM 返回的原始文本
        expected_count : 本批预期题数（仅用于日志）

    Returns:
        解析出的字典列表；失败时返回 []
    """
    if not llm_reply:
        print(f"  [警告] LLM 返回为空，跳过本批")
        return []

    # 用正则提取第一个 JSON 数组块 [...]
    match = re.search(r'\[[\s\S]*?\]', llm_reply)
    if not match:
        print(f"  [警告] LLM 回复中未找到 JSON 数组，原始回复：{repr(llm_reply[:200])}")
        return []

    json_str = match.group(0)
    try:
        data = json.loads(json_str)
        if not isinstance(data, list):
            print(f"  [警告] JSON 解析结果不是数组，类型：{type(data)}")
            return []
        return data
    except json.JSONDecodeError as e:
        print(f"  [警告] JSON 解析失败：{e}，原始 JSON：{repr(json_str[:300])}")
        return []


# ============================================================
# 主函数
# ============================================================

def main():
    """
    主执行流程：
        1. 解析命令行参数
        2. 读取 JSONL 文件
        3. 按参数选择执行 fill_answers / annotate_subjects
        4. 保存最终结果
        5. 清空旧 ChromaDB 集合，重新入库
    """
    # ── 解析命令行参数 ────────────────────────────────────────
    parser = argparse.ArgumentParser(
        description="408真题数据增强：补全答案 & 打标科目章节"
    )
    parser.add_argument(
        "--only-answers",
        action="store_true",
        help="只执行补全答案功能（fill_answers），跳过打标"
    )
    parser.add_argument(
        "--only-annotate",
        action="store_true",
        help="只执行打标科目功能（annotate_subjects），跳过补全答案"
    )
    args = parser.parse_args()

    # 确定要执行的功能
    do_fill = not args.only_annotate       # 不带 --only-annotate 时执行
    do_annotate = not args.only_answers    # 不带 --only-answers 时执行

    print("=" * 60)
    print("408 真题数据增强脚本")
    print(f"  补全答案  : {'✅ 开启' if do_fill else '⏭ 跳过'}")
    print(f"  打标科目  : {'✅ 开启' if do_annotate else '⏭ 跳过'}")
    print("=" * 60)

    # ── Step 1：读取 JSONL ───────────────────────────────────
    questions = load_jsonl(JSONL_PATH)
    if not questions:
        print("[错误] 未能加载任何题目，脚本退出。")
        sys.exit(1)

    total_questions = len(questions)

    # 记录初始状态（用于最终统计）
    initial_empty_answers = sum(1 for q in questions if q.get("answer", "") == "")
    initial_unannotated = sum(1 for q in questions if q.get("subject", "") == "待标注")
    print(f"\n[统计] 答案为空：{initial_empty_answers} 道 / 科目待标注：{initial_unannotated} 道")

    # ── Step 2：补全答案 ─────────────────────────────────────
    if do_fill:
        questions = fill_answers(questions)
        # 补全答案后立即保存中间结果，防止后续 annotate 失败丢失进度
        print("\n[中间保存] 补全答案阶段完成，保存当前结果...")
        save_jsonl(questions, INTERIM_PATH)
        save_jsonl(questions, JSONL_PATH)   # 同时更新主文件
    else:
        print("\n[跳过] fill_answers")

    # ── Step 3：打标科目章节 ──────────────────────────────────
    if do_annotate:
        questions = annotate_subjects(questions)
    else:
        print("\n[跳过] annotate_subjects")

    # ── Step 4：保存最终结果 ──────────────────────────────────
    print("\n[最终保存] 写入主文件...")
    save_jsonl(questions, JSONL_PATH)

    # 删除中间文件（任务完成后清理）
    interim_abs = os.path.abspath(INTERIM_PATH)
    if os.path.exists(interim_abs):
        os.remove(interim_abs)
        print(f"[清理] 已删除中间文件：{interim_abs}")

    # ── Step 5：统计结果 ──────────────────────────────────────
    final_empty_answers = sum(1 for q in questions if q.get("answer", "") == "")
    final_unannotated = sum(1 for q in questions if q.get("subject", "") == "待标注")

    filled_count = initial_empty_answers - final_empty_answers
    annotated_count = initial_unannotated - final_unannotated

    print(f"\n{'='*60}")
    print("📊 执行结果统计")
    print(f"{'='*60}")
    if do_fill:
        print(f"  答案补全  : {filled_count}/{initial_empty_answers} 道成功")
    if do_annotate:
        print(f"  科目打标  : {annotated_count}/{initial_unannotated} 道成功")
        print(f"  仍待标注  : {final_unannotated}/{total_questions} 道")
    print(f"{'='*60}")

    # ── Step 6：重新入库 ChromaDB ────────────────────────────
    print("\n[入库] 开始重新入库 ChromaDB...")
    try:
        import chromadb
        from memory.rag.indexer import index_exam_jsonl

        # 先删除旧集合，再重新写入（确保数据一致）
        chroma_path = os.path.abspath("storage/chroma_db")
        c = chromadb.PersistentClient(path=chroma_path)

        # 尝试删除旧集合（不存在时忽略错误）
        try:
            c.delete_collection("exam_questions")
            print("[入库] 已清空旧的 exam_questions 集合")
        except Exception as e:
            print(f"[入库] 清空旧集合时遇到提示（可忽略）：{e}")

        # 重新入库
        index_exam_jsonl(os.path.abspath(JSONL_PATH))
        print("[入库] ✅ 重新入库完成！")

    except ImportError as e:
        print(f"[入库] ⚠️  导入模块失败，跳过入库：{e}")
        print("      请手动运行：python scripts/index_exam_questions.py")
    except Exception as e:
        print(f"[入库] ❌ 入库失败：{e}")
        print("      请手动运行：python scripts/index_exam_questions.py")

    print("\n✅ 所有任务完成！")


if __name__ == "__main__":
    main()
