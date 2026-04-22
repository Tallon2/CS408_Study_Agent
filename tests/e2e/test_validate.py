import sys, os
sys.path.insert(0, r'E:\DEMO')
os.chdir(r'E:\DEMO')

passed = 0
total = 0

def run_test(name, fn):
    global passed, total
    total += 1
    try:
        fn()
        print(f'  ✅ {name}')
        passed += 1
    except Exception as e:
        print(f'  ❌ {name}: {e}')

def test_server():
    from server import app
    assert app.title == '408 学习 Agent API'

def test_auth():
    from api.v1.auth import router, create_token, verify_token
    t = create_token('123', 'test')
    p = verify_token(t)
    assert p['sub'] == '123'

def test_chat():
    from api.v1.chat import router

def test_plan():
    from api.v1.plan import router

def test_deps():
    from api.deps import get_db, get_current_user, get_agent

def test_models():
    from dao.models import User, ChatSession, ChatMessage, StudyPlan, StudyTask

def test_db():
    from dao.database import create_tables
    create_tables()

run_test('server app', test_server)
run_test('auth router', test_auth)
run_test('chat router', test_chat)
run_test('plan router', test_plan)
run_test('deps', test_deps)
run_test('db models', test_models)
run_test('db create', test_db)

print(f'\n{passed}/{total} 验证通过')
