import json
import os
from datetime import datetime

class SessionManager:
    def __init__(self, user_id: str, session_id: str = None):
        self.user_id = user_id
        self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_dir = f"storage/sessions/{self.session_id}"
        os.makedirs(self.session_dir, exist_ok=True)

        self.journal_path = os.path.join(self.session_dir, "journal.jsonl")
        self.topics_touched = []
        self.user_struggles = []
        self.event_counter = 0

    def log_event(self, event_type: str, payload: dict):
        self.event_counter += 1
        event = {
            "event_id": f"evt-{self.event_counter:04d}",
            "ts": datetime.now().isoformat(),
            "session_id": self.session_id,
            "event_type": event_type,
            "payload": payload
        }
        with open(self.journal_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        return event

    def log_user_message(self, message: str):
        self.log_event("user_message", {"content": message})

    def log_assistant_message(self, message: str):
        self.log_event("assistant_message", {"content": message})

    def log_tool_call(self, tool_name: str, args: dict, result: str):
        self.log_event("tool_call", {
            "tool_name": tool_name, "arguments": args, "result": result
        })

    def log_struggle(self, topic: str, detail: str):
        self.user_struggles.append({
            "topic": topic, "detail": detail, "ts": datetime.now().isoformat()
        })
        self.log_event("user_struggle", {"topic": topic, "detail": detail})

    def get_messages_text(self) -> str:
        messages = []
        if os.path.exists(self.journal_path):
            with open(self.journal_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    event = json.loads(line)
                    if event["event_type"] in ("user_message", "assistant_message"):
                        role = "用户" if event["event_type"] == "user_message" else "助手"
                        messages.append(f"{role}: {event['payload']['content']}")
        return "\n".join(messages)
