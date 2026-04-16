from agent.main_agent import LearningAgent


def main():
    print("=" * 50)
    print("  📚 个人学习助手 Agent")
    print("=" * 50)
    print("  输入你想学的内容，或直接提问")
    print("  输入 'quit' 或 'exit' 退出")
    print("=" * 50)
    print()

    agent = LearningAgent(user_id="student_001")
    print()

    while True:
        try:
            user_input = input("你: ").strip()
        except (KeyboardInterrupt, EOFError):
            # 处理 Ctrl+C 强制退出
            print("\n\n👋 检测到退出信号...")
            agent.on_session_end()
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit", "退出"):
            agent.on_session_end()   # 预留 hook，阶段2生效
            print("\n👋 本次学习结束，下次见！")
            break

        response = agent.chat(user_input)
        print(f"\n助手: {response}\n")


if __name__ == "__main__":
    main()
