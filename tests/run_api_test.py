"""Week3 FastAPI 端到端测试脚本"""
import urllib.request, json, time, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = 'http://localhost:8002'

def call(method, path, body=None, token=None):
    url = BASE + path
    data = json.dumps(body, ensure_ascii=False).encode('utf-8') if body else None
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode('utf-8'))
    except Exception as e:
        return 0, {"error": str(e)}

results = []

def check(label, cond, extra=""):
    icon = "✅" if cond else "❌"
    print(f"  {icon} {label}{(' → ' + str(extra)) if extra else ''}")
    results.append(cond)

print("=" * 50)
print("  Week3 FastAPI 端到端测试")
print("=" * 50)

# 1. 健康检查
s, r = call('GET', '/health')
check("GET /health", s == 200, r)

# 2. 注册
uname = f"user{int(time.time()) % 100000}"
s, r = call('POST', '/api/v1/auth/register', {'username': uname, 'password': 'pass1234'})
token = r.get('access_token', '')
check(f"POST /register ({uname})", s == 201, f"token={token[:20]}...")

# 3. 登录
s, r = call('POST', '/api/v1/auth/login', {'username': uname, 'password': 'pass1234'})
token = r.get('access_token', token)
check("POST /login", s == 200, f"token={token[:20]}...")

# 4. GET /me
s, r = call('GET', '/api/v1/auth/me', token=token)
check("GET /auth/me", s == 200, r)

# 5. 对话历史（空）
s, r = call('GET', '/api/v1/chat/history', token=token)
check("GET /chat/history", s == 200, f"count={r.get('count')}")

# 6. 重复注册 → 409
s, r = call('POST', '/api/v1/auth/register', {'username': uname, 'password': 'pass1234'})
check("重复注册 → 409 Conflict", s == 409, r.get('detail', ''))

# 7. 错误密码 → 401
s, r = call('POST', '/api/v1/auth/login', {'username': uname, 'password': 'wrong_pw'})
check("错误密码 → 401", s == 401)

# 8. 创建学习计划
s, r = call('POST', '/api/v1/plan/', {'title': '408两周冲刺', 'description': '数据结构+OS'}, token=token)
plan_id = r.get('id', '')
check("POST /plan/ 创建计划", s in (200, 201), f"id={plan_id[:12]}...")

# 9. 获取计划列表
s, r = call('GET', '/api/v1/plan/', token=token)
check("GET /plan/ 列表", s == 200, f"count={len(r) if isinstance(r, list) else r}")

# 10. 新增任务
task_id = ''
if plan_id:
    s, r = call('POST', f'/api/v1/plan/{plan_id}/tasks',
                {'title': '复习快速排序', 'subject': '数据结构'}, token=token)
    task_id = r.get('id', '')
    check("POST /plan/{id}/tasks 新增任务", s in (200, 201), f"id={task_id[:12]}...")

# 11. 标记任务完成
if task_id:
    s, r = call('PATCH', f'/api/v1/plan/{plan_id}/tasks/{task_id}/done', token=token)
    check("PATCH /tasks/{id}/done 完成任务", s == 200, f"is_done={r.get('is_done')}")

# 12. 无 token 访问 → 401
s, r = call('GET', '/api/v1/auth/me')
check("无 token 访问 → 401", s == 401)

# 汇总
passed = sum(results)
total  = len(results)
print(f"\n  {'=' * 40}")
print(f"  测试结果：{passed}/{total} 通过")
print(f"  {'=' * 40}")
sys.exit(0 if passed == total else 1)
