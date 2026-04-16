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

    return f"[工具指令] 未知工具: {name}"
