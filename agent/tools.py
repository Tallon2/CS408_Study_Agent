import json

# ============================================================
# 工具定义：告诉 LLM "你有哪些工具可以用，每个工具是干什么的"
# 类比 Java：这就是接口定义（Interface），LLM 看这个决定调哪个
# ============================================================
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "explain_concept",
            "description": "解释一个编程知识点，可指定难度深度",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "知识点名称，例如：装饰器、闭包、列表推导式"
                    },
                    "depth": {
                        "type": "string",
                        "enum": ["beginner", "intermediate", "advanced"],
                        "description": "讲解深度"
                    }
                },
                "required": ["topic"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_quiz",
            "description": "针对某个知识点生成一道练习题，帮助用户检验掌握程度",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "出题的知识点"
                    },
                    "difficulty": {
                        "type": "string",
                        "enum": ["easy", "medium", "hard"],
                        "description": "题目难度"
                    }
                },
                "required": ["topic"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_answer",
            "description": "检查用户对某道题的回答是否正确，给出详细反馈",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "题目内容"
                    },
                    "user_answer": {
                        "type": "string",
                        "description": "用户的回答"
                    }
                },
                "required": ["question", "user_answer"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "recommend_next",
            "description": "根据当前学习情况，推荐用户接下来应该学什么",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_study_plan",
            "description": "保存或更新用户的学习/复习计划",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_name": {
                        "type": "string",
                        "description": "计划名称，如：408总复习计划、数据结构第一轮"
                    },
                    "tasks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "task": {"type": "string", "description": "任务内容"},
                                "deadline": {"type": "string", "description": "截止日期，如 2026-05-01"},
                                "priority": {"type": "string", "enum": ["high", "medium", "low"]}
                            },
                            "required": ["task"]
                        },
                        "description": "任务列表"
                    }
                },
                "required": ["plan_name", "tasks"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_study_plan",
            "description": "读取用户当前的学习计划，查看进度",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_name": {
                        "type": "string",
                        "description": "要查看的计划名称，不填则查看所有计划"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": "将学习计划中的某个任务标记为已完成",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_name": {"type": "string", "description": "计划名称"},
                    "task_index": {"type": "integer", "description": "任务序号（从1开始）"}
                },
                "required": ["plan_name", "task_index"]
            }
        }
    }
]


# ============================================================
# 工具执行：LLM 决定调哪个工具后，这里负责真正"执行"
# 阶段1：工具只返回一段提示语，让 LLM 去生成实际内容
# 阶段3之后：这里会注入用户画像、历史记录等真实数据
# ============================================================
def execute_tool(name: str, arguments: str) -> str:
    """
    执行工具调用，返回结果字符串给 LLM。

    类比 Java：这是接口的实现类（Impl），
    name 是方法名，arguments 是 JSON 格式的参数。
    """
    args = json.loads(arguments) if arguments else {}

    if name == "explain_concept":
        topic = args.get("topic", "")
        depth = args.get("depth", "beginner")
        depth_map = {
            "beginner": "入门级（用生活比喻，配简单代码示例）",
            "intermediate": "进阶级（讲原理，配实际使用场景）",
            "advanced": "深入级（讲底层机制和边界情况）"
        }
        depth_desc = depth_map.get(depth, depth_map["beginner"])
        return (
            f"[工具指令] 请用{depth_desc}方式，为用户讲解「{topic}」。"
            f"要求：先给一个生活中的类比，再给代码示例，最后总结一句话。"
        )

    elif name == "generate_quiz":
        topic = args.get("topic", "")
        difficulty = args.get("difficulty", "easy")
        diff_map = {
            "easy": "简单（概念理解题）",
            "medium": "中等（代码阅读/填空题）",
            "hard": "困难（代码编写/综合应用题）"
        }
        diff_desc = diff_map.get(difficulty, diff_map["easy"])
        return (
            f"[工具指令] 请出一道关于「{topic}」的{diff_desc}练习题。"
            f"格式要求：先给题目，如果是选择题给出4个选项，"
            f"最后用 --- 分隔后给出答案和解析。"
        )

    elif name == "check_answer":
        question = args.get("question", "")
        user_answer = args.get("user_answer", "")
        return (
            f"[工具指令] 请判断用户的回答是否正确并给出详细反馈。\n"
            f"题目：{question}\n"
            f"用户答案：{user_answer}\n"
            f"要求：先给出对/错判断，再解释原因，如果错了给出正确答案和关键知识点。"
        )

    elif name == "recommend_next":
        return (
            "[工具指令] 请根据本次对话中用户的表现，推荐接下来应该学习的内容。"
            "给出 2~3 个具体的学习建议，按优先级排列。"
        )

    elif name == "save_study_plan":
        return _save_study_plan(args)

    elif name == "read_study_plan":
        return _read_study_plan(args)

    elif name == "complete_task":
        return _complete_task(args)

    return f"[工具指令] 未知工具: {name}"


# ============================================================
# 学习计划管理（文件存储在 storage/plans/）
# ============================================================
import os
from datetime import datetime

PLANS_DIR = "storage/plans"


def _save_study_plan(args: dict) -> str:
    """保存学习计划到 JSON 文件"""
    plan_name = args.get("plan_name", "默认计划")
    tasks = args.get("tasks", [])

    os.makedirs(PLANS_DIR, exist_ok=True)
    safe_name = plan_name.replace(" ", "_").replace("/", "_")
    plan_path = os.path.join(PLANS_DIR, f"{safe_name}.json")

    # 为每个任务添加状态
    plan_data = {
        "plan_name": plan_name,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "tasks": []
    }
    for i, t in enumerate(tasks):
        plan_data["tasks"].append({
            "index": i + 1,
            "task": t.get("task", ""),
            "deadline": t.get("deadline", ""),
            "priority": t.get("priority", "medium"),
            "completed": False,
            "completed_at": None
        })

    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan_data, f, ensure_ascii=False, indent=2)

    total = len(plan_data["tasks"])
    return (
        f"[工具结果] ✅ 学习计划「{plan_name}」已保存，共 {total} 个任务。\n"
        f"请向用户确认计划内容，并鼓励ta按计划执行。"
    )


def _read_study_plan(args: dict) -> str:
    """读取学习计划"""
    os.makedirs(PLANS_DIR, exist_ok=True)
    plan_name = args.get("plan_name", "")

    if plan_name:
        # 读取指定计划
        safe_name = plan_name.replace(" ", "_").replace("/", "_")
        plan_path = os.path.join(PLANS_DIR, f"{safe_name}.json")
        if not os.path.exists(plan_path):
            return f"[工具结果] ❌ 未找到计划「{plan_name}」，可以创建一个新的。"
        with open(plan_path, "r", encoding="utf-8") as f:
            plan = json.load(f)
        return _format_plan(plan)
    else:
        # 列出所有计划
        files = [f for f in os.listdir(PLANS_DIR) if f.endswith(".json")]
        if not files:
            return "[工具结果] 📋 当前没有任何学习计划，建议为用户创建一个。"
        all_plans = []
        for fname in files:
            with open(os.path.join(PLANS_DIR, fname), "r", encoding="utf-8") as f:
                plan = json.load(f)
            all_plans.append(_format_plan(plan))
        return "\n\n---\n\n".join(all_plans)


def _complete_task(args: dict) -> str:
    """标记任务为已完成"""
    plan_name = args.get("plan_name", "")
    task_index = args.get("task_index", 0)

    safe_name = plan_name.replace(" ", "_").replace("/", "_")
    plan_path = os.path.join(PLANS_DIR, f"{safe_name}.json")
    if not os.path.exists(plan_path):
        return f"[工具结果] ❌ 未找到计划「{plan_name}」"

    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)

    for t in plan["tasks"]:
        if t["index"] == task_index:
            t["completed"] = True
            t["completed_at"] = datetime.now().isoformat()
            break
    else:
        return f"[工具结果] ❌ 未找到第 {task_index} 个任务"

    plan["updated_at"] = datetime.now().isoformat()
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    done = sum(1 for t in plan["tasks"] if t["completed"])
    total = len(plan["tasks"])
    return (
        f"[工具结果] ✅ 已完成任务 #{task_index}！\n"
        f"当前进度：{done}/{total}（{done*100//total}%）\n"
        f"请鼓励用户继续努力！"
    )


def _format_plan(plan: dict) -> str:
    """格式化计划为可读文本"""
    tasks = plan.get("tasks", [])
    done = sum(1 for t in tasks if t.get("completed"))
    total = len(tasks)
    pct = (done * 100 // total) if total > 0 else 0

    lines = [f"[工具结果] 📋 计划「{plan['plan_name']}」 进度：{done}/{total}（{pct}%）"]
    for t in tasks:
        status = "✅" if t.get("completed") else "⬜"
        priority_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(t.get("priority", ""), "")
        deadline = f" (截止: {t['deadline']})" if t.get("deadline") else ""
        lines.append(f"  {status} {t['index']}. {priority_icon} {t['task']}{deadline}")

    return "\n".join(lines)
