"""
GradeInsight API — интеллектуальная система поддержки принятия решений при грейдировании персонала
"""

import sys
import os
import traceback
from sqlalchemy import text

# Добавляем папку backend в путь поиска модулей
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Для отладки – сразу выведем сообщение
print("=== Starting main.py ===")
print(f"Python version: {sys.version}")
print(f"Current directory: {os.getcwd()}")
print(f"Files in directory: {os.listdir('.')}")
print(f"sys.path: {sys.path[:5]}...")

try:
    print("Importing libraries...")
    from contextlib import asynccontextmanager
    from datetime import datetime, timedelta
    from io import BytesIO, StringIO
    from typing import List, Optional
    import csv
    import io
    import json
    import re
    import secrets
    import string

    import openpyxl
    import pandas as pd
    from fastapi import FastAPI, Depends, HTTPException, File, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import StreamingResponse
    from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
    from jose import JWTError, jwt
    from passlib.context import CryptContext
    from sqlalchemy.orm import Session
    from fastapi import Request
    print("Libraries imported")

    print("Importing database module...")
    from database import (
        get_db, Employee, init_db, Role, Competency, GradeLevel,
        CompetencyWeight, RoleTarget, History, ActionLog, User
    )
    print("Database imported")

    print("Importing grade_calculator...")
    from grade_calculator import calculate_grade, get_recommendation
    print("grade_calculator imported")

    print("Importing code_analyzer...")
    from code_analyzer import analyze_code_from_text
    print("code_analyzer imported")

    print("Importing text_analyzer...")
    from text_analyzer import analyze_comments
    print("text_analyzer imported")

except Exception as e:
    print(f"!!! Import error: {e}")
    traceback.print_exc()
    sys.exit(1)

# ==================== Конфигурация ====================

DEFAULT_WEIGHTS = {
    "tasks": 0.25,
    "deadlines": 0.25,
    "code_quality": 0.25,
    "communication": 0.25
}

SECRET_KEY = "your-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

PASSWORDS_FILE = "passwords.json"

# ==================== Утилиты для генерации логинов и паролей ====================

def transliterate(name: str) -> str:
    mapping = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
        'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
    }
    name = name.lower()
    result = ''
    for ch in name:
        if ch in mapping:
            result += mapping[ch]
        elif ch.isalpha():
            result += ch
        else:
            result += '_'
    result = re.sub(r'_+', '_', result)
    return result.strip('_')

def generate_password(length=8) -> str:
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def save_passwords(users_data):
    with open(PASSWORDS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users_data, f, ensure_ascii=False, indent=2)

# ==================== Жизненный цикл приложения ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Запуск GradeInsight API...")
    init_db()
    print("База данных готова")
    yield
    print("Завершение работы GradeInsight API")

app = FastAPI(
    title="GradeInsight API",
    description="Интеллектуальная система поддержки принятия решений при грейдировании персонала",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
# Определяем путь к папке frontend (относительно расположения main.py)
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../frontend"))
print(f"Frontend directory: {frontend_dir}")
print(f"Frontend exists: {os.path.exists(frontend_dir)}")
if os.path.exists(frontend_dir):
    print(f"Files in frontend: {os.listdir(frontend_dir)}")
    # Монтируем статику
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")
else:
    print("ERROR: Frontend folder not found!")

@app.get("/")
@app.get("/standalone.html")
async def serve_frontend():
    index_path = os.path.join(frontend_dir, "standalone.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    # Если файл не найден, возвращаем JSON с пояснением
    return {"message": "GradeInsight API v2.0", "error": "standalone.html not found"}

@app.get("/employee.html")
async def serve_employee():
    emp_path = os.path.join(frontend_dir, "employee.html")
    if os.path.exists(emp_path):
        return FileResponse(emp_path)
    raise HTTPException(status_code=404, detail="employee.html not found")
# ==================== Аутентификация и авторизация ====================

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(
    request: Request,
    token: Optional[str] = None,
    db: Session = Depends(get_db)
):
    # Сначала пытаемся взять токен из заголовка
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
    # Если нет, то из query-параметра (для экспорта)
    elif token is None:
        token = request.query_params.get("token")
    
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user

def require_role(required_roles: List[str]):
    def role_checker(current_user: User = Depends(get_current_user)):
        if current_user.role == "super_admin":
            return current_user
        if current_user.role not in required_roles:
            raise HTTPException(status_code=403, detail="Not enough permissions")
        return current_user
    return role_checker

def get_company_filter(current_user: User, db: Session):
    """Возвращает фильтр по company_id для запросов"""
    if current_user.role == "super_admin":
        return None  # super_admin видит всех
    return current_user.company_id  # остальные только свою компанию
# ==================== Вспомогательные функции ====================

def get_competency_weights_from_db(role_name: str, db: Session):
    role = db.query(Role).filter(Role.name == role_name).first()
    if not role:
        return DEFAULT_WEIGHTS

    weights = {}
    comp_weights = db.query(CompetencyWeight).filter(CompetencyWeight.role_id == role.id).all()
    for cw in comp_weights:
        comp = db.query(Competency).filter(Competency.id == cw.competency_id).first()
        if comp:
            weights[comp.name] = cw.weight

    if not weights:
        return DEFAULT_WEIGHTS
    return weights

def get_grade_levels_from_db(db: Session):
    levels = db.query(GradeLevel).order_by(GradeLevel.min_score).all()
    return [{"name": l.name, "min_score": l.min_score, "max_score": l.max_score} for l in levels]

def save_history_entry(employee: Employee, db: Session, action_type: str = None, details: str = None):
    emp_data = {
        "tasks_completed": employee.tasks_completed,
        "deadlines_met": employee.deadlines_met,
        "code_quality_score": employee.code_quality_score,
        "communication_score": employee.communication_score
    }
    weights = get_competency_weights_from_db(employee.position, db)
    grade_levels = get_grade_levels_from_db(db)
    new_result = calculate_grade(emp_data, weights, grade_levels)
    new_score = new_result["total_score"]

    prev_history = db.query(History).filter(History.employee_id == employee.id).order_by(History.date.desc()).first()
    old_score = prev_history.total_score if prev_history else 0.0
    delta = new_score - old_score

    history = History(
        employee_id=employee.id,
        total_score=new_score,
        grade=new_result["grade"],
        tasks_completed=employee.tasks_completed,
        deadlines_met=employee.deadlines_met,
        code_quality_score=employee.code_quality_score,
        communication_score=employee.communication_score
    )
    db.add(history)

    if action_type:
        action_log = ActionLog(
            employee_id=employee.id,
            action_type=action_type,
            details=details,
            delta_score=round(delta, 3),
            new_score=new_score
        )
        db.add(action_log)

    db.commit()

def check_employee_access(employee_id: int, current_user: User, db: Session) -> Employee:
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    if current_user.role not in ["admin", "hr"] and current_user.employee_id != employee_id:
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    return employee

# ==================== Эндпоинты аутентификации ====================

@app.post("/token", response_model=dict)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not user.verify_password(form_data.password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user.username}, expires_delta=access_token_expires)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user.role,
        "employee_id": user.employee_id,
        "company_id": user.company_id
    }

@app.post("/register")
def register(username: str, password: str, role: str = "employee", employee_id: int = None, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="Username already registered")
    hashed = User.hash_password(password)
    user = User(username=username, hashed_password=hashed, role=role, employee_id=employee_id)
    db.add(user)
    db.commit()
    return {"message": "User created"}

# ==================== Компании ====================
@app.post("/register_company")
def register_company(
    username: str,
    password: str,
    company_name: str,
    db: Session = Depends(get_db)
):
    # Проверка, существует ли компания
    existing_company = db.query(Company).filter(Company.name == company_name).first()
    if existing_company:
        raise HTTPException(status_code=400, detail="Компания с таким названием уже существует")
    
    # Проверка пользователя
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="Username already registered")
    
    # Создаём компанию
    company = Company(name=company_name, is_active=True)
    db.add(company)
    db.flush()
    
    # Создаём администратора компании
    hashed = User.hash_password(password)
    admin_user = User(
        username=username,
        hashed_password=hashed,
        role="admin",
        company_id=company.id,
        is_active=True
    )
    db.add(admin_user)
    db.commit()
    return {"message": f"Company '{company_name}' created successfully"}
# ==================== Сотрудники (только admin/hr) ====================

@app.get("/employees")
def get_employees(
    department: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Employee)
    
    # Фильтр по компании (для всех, кроме super_admin)
    company_id = get_company_filter(current_user, db)
    if company_id is not None:
        query = query.filter(Employee.company_id == company_id)
    
    if department:
        query = query.filter(Employee.department == department)
    
    employees = query.all()
    result = []
    grade_levels = get_grade_levels_from_db(db)

    for emp in employees:
        emp_data = {
            "tasks_completed": emp.tasks_completed,
            "deadlines_met": emp.deadlines_met,
            "code_quality_score": emp.code_quality_score,
            "communication_score": emp.communication_score
        }
        weights = get_competency_weights_from_db(emp.position, db)
        grade_result = calculate_grade(emp_data, weights, grade_levels)
        recommendation = get_recommendation(grade_result["grade"], emp.formal_grade)

        result.append({
            "id": emp.id,
            "name": emp.name,
            "position": emp.position,
            "experience": emp.experience,
            "metrics": emp_data,
            "grade_result": grade_result,
            "formal_grade": emp.formal_grade,
            "recommendation": recommendation
        })
    return result

@app.get("/employees/{employee_id}")
def get_employee(employee_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    employee = check_employee_access(employee_id, current_user, db)

    emp_data = {
        "tasks_completed": employee.tasks_completed,
        "deadlines_met": employee.deadlines_met,
        "code_quality_score": employee.code_quality_score,
        "communication_score": employee.communication_score
    }
    weights = get_competency_weights_from_db(employee.position, db)
    grade_levels = get_grade_levels_from_db(db)
    grade_result = calculate_grade(emp_data, weights, grade_levels)

    return {
        "id": employee.id,
        "name": employee.name,
        "position": employee.position,
        "experience": employee.experience,
        "metrics": emp_data,
        "grade_result": grade_result
    }

@app.get("/employees/{employee_id}/actions")
def get_actions(employee_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    employee = check_employee_access(employee_id, current_user, db)
    actions = db.query(ActionLog).filter(ActionLog.employee_id == employee_id).order_by(ActionLog.timestamp.desc()).all()
    return [{
        "timestamp": a.timestamp.isoformat(),
        "action_type": a.action_type,
        "details": a.details,
        "delta_score": a.delta_score,
        "new_score": a.new_score
    } for a in actions]

@app.get("/employees/{employee_id}/history")
def get_history(employee_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    employee = check_employee_access(employee_id, current_user, db)
    history = db.query(History).filter(History.employee_id == employee_id).order_by(History.date.asc()).all()
    return [{
        "date": h.date.isoformat(),
        "total_score": h.total_score,
        "grade": h.grade,
        "tasks": h.tasks_completed,
        "deadlines": h.deadlines_met,
        "code_quality": h.code_quality_score,
        "communication": h.communication_score
    } for h in history]

@app.get("/employees/{employee_id}/gap_analysis")
def gap_analysis(employee_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    employee = check_employee_access(employee_id, current_user, db)

    role = db.query(Role).filter(Role.name == employee.position).first()
    if not role:
        return {"error": "Роль не найдена в системе", "gaps": []}

    targets = db.query(RoleTarget).filter(RoleTarget.role_id == role.id).all()
    target_dict = {}
    for t in targets:
        comp = db.query(Competency).filter(Competency.id == t.competency_id).first()
        if comp:
            target_dict[comp.name] = t.target_score

    if not target_dict:
        target_dict = {
            "tasks": 0.8,
            "deadlines": 0.8,
            "code_quality": 0.8,
            "communication": 0.7
        }

    current = {
        "tasks": min(employee.tasks_completed / 100, 1.0),
        "deadlines": employee.deadlines_met / 100,
        "code_quality": employee.code_quality_score / 100,
        "communication": employee.communication_score / 100
    }

    gaps = []
    for comp_name, target in target_dict.items():
        curr = current.get(comp_name, 0)
        gaps.append({
            "competency": comp_name,
            "current": round(curr, 2),
            "target": target,
            "gap": round(target - curr, 2),
            "status": "good" if curr >= target else "need_improvement"
        })

    return {
        "employee_name": employee.name,
        "role": employee.position,
        "gaps": gaps
    }

# ==================== Управление данными сотрудников (только admin/hr) ====================

@app.post("/upload")
async def upload_employees(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "hr"]))
):
    try:
        filename = file.filename
        contents = await file.read()

        try:
            if filename.endswith('.csv'):
                df = pd.read_csv(BytesIO(contents))
            elif filename.endswith('.xlsx'):
                df = pd.read_excel(BytesIO(contents))
            else:
                raise HTTPException(status_code=400, detail="Поддерживаются только .csv и .xlsx")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Ошибка чтения файла: {str(e)}")

        required_columns = ['name', 'position', 'experience']
        for col in required_columns:
            if col not in df.columns:
                raise HTTPException(status_code=400, detail=f"Отсутствует колонка: {col}")
                
       
        db.query(History).delete()
        db.query(ActionLog).delete()
        db.query(User).update({User.employee_id: None}, synchronize_session=False)
        db.query(Employee).delete()
        created_users = []

        for _, row in df.iterrows():
            formal_grade = row.get('formal_grade', '')
            emp = Employee(
                name=row['name'],
                position=row['position'],
                department=row.get('department', ''),
                experience=int(row.get('experience', 0)),
                formal_grade=formal_grade,
                photo_url=row.get('photo_url', '')
            )
            db.add(emp)
            db.flush()

            username = transliterate(emp.name)
            existing_user = db.query(User).filter(User.username == username).first()
            if not existing_user:
                password = generate_password()
                hashed = User.hash_password(password)
                new_user = User(
                    username=username,
                    hashed_password=hashed,
                    role="employee",
                    employee_id=emp.id,
                    is_active=True
                )
                db.add(new_user)
                created_users.append({
                    "name": emp.name,
                    "login": username,
                    "password": password
                })
            else:
                existing_user.employee_id = emp.id
                if existing_user.role != "employee":
                    existing_user.role = "employee"
                created_users.append({
                    "name": emp.name,
                    "login": existing_user.username,
                    "password": "already exists"
                })

        db.commit()

        new_passwords = [u for u in created_users if u.get('password') and u['password'] != 'already exists']
        if new_passwords:
            save_passwords(new_passwords)

        return {
            "message": f"Загружено {len(df)} сотрудников",
            "users": created_users
        }
    except Exception as e:
        print("=== ERROR in /upload ===", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")
        
@app.delete("/employees")
def delete_all_employees(db: Session = Depends(get_db), current_user: User = Depends(require_role(["admin"]))):
    try:
        db.query(History).delete()
        db.query(ActionLog).delete()
        db.query(User).update({User.employee_id: None}, synchronize_session=False)
        count = db.query(Employee).count()
        db.query(Employee).delete()
        if os.path.exists(PASSWORDS_FILE):
            os.remove(PASSWORDS_FILE)
        db.commit()
        return {"message": f"Удалено {count} сотрудников"}
    except Exception as e:
        db.rollback()
        print("=== ERROR in DELETE /employees ===", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

@app.delete("/full-clear")
def full_clear_database(db: Session = Depends(get_db), current_user: User = Depends(require_role(["admin"]))):
    """Полностью очищает базу данных: удаляет всех сотрудников, их историю, логи и учётные записи (только admin)"""
    try:
        db.query(History).delete()
        db.query(ActionLog).delete()
        db.query(User).update({User.employee_id: None}, synchronize_session=False)
        db.query(Employee).delete()
        db.query(User).filter(User.role == "employee").delete()
        if os.path.exists(PASSWORDS_FILE):
            os.remove(PASSWORDS_FILE)
        db.commit()
        return {"message": "База данных полностью очищена (сотрудники и учётные записи удалены)"}
    except Exception as e:
        db.rollback()
        print("=== ERROR in /full-clear ===", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

@app.get("/check-accounts")
def check_accounts(current_user: User = Depends(require_role(["admin"]))):
    return {"exists": os.path.exists(PASSWORDS_FILE)}

@app.get("/export/accounts")
def export_accounts(current_user: User = Depends(require_role(["admin"]))):
    if not os.path.exists(PASSWORDS_FILE):
        raise HTTPException(status_code=404, detail="Нет созданных учётных записей")
    with open(PASSWORDS_FILE, 'r', encoding='utf-8') as f:
        users_data = json.load(f)
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Имя сотрудника", "Логин", "Пароль"])
    for u in users_data:
        writer.writerow([u['name'], u['login'], u['password']])
    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=accounts.csv"}
    )

# ==================== Обновление метрик ====================

@app.put("/employees/{employee_id}/metrics")
def update_metrics(
    employee_id: int,
    tasks_completed: int = None,
    deadlines_met: float = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    employee = check_employee_access(employee_id, current_user, db)

    if tasks_completed is not None:
        employee.tasks_completed = tasks_completed
    if deadlines_met is not None:
        employee.deadlines_met = deadlines_met
    db.commit()
    details = f"Задачи: {tasks_completed}, дедлайны: {deadlines_met}%"
    save_history_entry(employee, db, action_type="update_metrics", details=details)
    return {"message": "Метрики обновлены"}

# ==================== Анализ кода и текста ====================

@app.post("/upload/code/{employee_id}")
async def upload_code(
    employee_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    employee = check_employee_access(employee_id, current_user, db)

    contents = await file.read()
    code_text = contents.decode('utf-8')
    result = analyze_code_from_text(code_text)
    employee.code_quality_score = result["code_quality_score"]
    db.commit()
    details = f"Файл: {file.filename}, качество кода: {result['code_quality_score']}"
    save_history_entry(employee, db, action_type="upload_code", details=details)
    return result

@app.post("/upload/comments/{employee_id}")
async def upload_comments(
    employee_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    employee = check_employee_access(employee_id, current_user, db)

    contents = await file.read()
    comments_text = contents.decode('utf-8')
    result = analyze_comments(comments_text)
    employee.communication_score = result["communication_score"]
    db.commit()
    details = f"Файл: {file.filename}, оценка коммуникации: {result['communication_score']}"
    save_history_entry(employee, db, action_type="upload_comments", details=details)
    return result

@app.post("/analyze/code/{employee_id}")
async def analyze_employee_code(
    employee_id: int,
    code_text: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    employee = check_employee_access(employee_id, current_user, db)

    result = analyze_code_from_text(code_text)
    employee.code_quality_score = result["code_quality_score"]
    db.commit()
    details = f"Анализ кода (прямой ввод), качество кода: {result['code_quality_score']}"
    save_history_entry(employee, db, action_type="analyze_code", details=details)
    return result

@app.post("/analyze/comments/{employee_id}")
async def analyze_employee_comments(
    employee_id: int,
    comments_text: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    employee = check_employee_access(employee_id, current_user, db)

    result = analyze_comments(comments_text)
    employee.communication_score = result["communication_score"]
    db.commit()
    details = f"Анализ текста (прямой ввод), оценка коммуникации: {result['communication_score']}"
    save_history_entry(employee, db, action_type="analyze_comments", details=details)
    return result

# ==================== Дашборд (только admin/hr) ====================

@app.get("/dashboard")
def get_dashboard(
    department: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "hr"]))
):
    query = db.query(Employee)
    if department:
        query = query.filter(Employee.department == department)
    employees = query.all()
    grades_count = {"Junior": 0, "Middle": 0, "Senior": 0}
    hipo_list = []

    grade_levels = get_grade_levels_from_db(db)

    for emp in employees:
        emp_data = {
            "tasks_completed": emp.tasks_completed,
            "deadlines_met": emp.deadlines_met,
            "code_quality_score": emp.code_quality_score,
            "communication_score": emp.communication_score
        }
        weights = get_competency_weights_from_db(emp.position, db)
        result = calculate_grade(emp_data, weights, grade_levels)

        grades_count[result["grade"]] = grades_count.get(result["grade"], 0) + 1

        if result["total_score"] > 0.85:
            hipo_list.append({
                "id": emp.id,
                "name": emp.name,
                "position": emp.position,
                "score": result["total_score"],
                "grade": result["grade"]
            })

    return {
        "grades_count": grades_count,
        "hipo_employees": hipo_list,
        "total_employees": len(employees)
    }

@app.get("/departments")
def get_departments(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "hr"]))
):
    departments = db.query(Employee.department).distinct().all()
    return [d[0] for d in departments if d[0]]
# ==================== Экспорт в Excel (только admin/hr) ====================

@app.get("/export/excel")
def export_to_excel(db: Session = Depends(get_db), current_user: User = Depends(require_role(["admin", "hr"]))):
    employees = db.query(Employee).all()
    grade_levels = get_grade_levels_from_db(db)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Сотрудники"

    headers = ["ID", "Имя", "Должность", "Задач выполнено", "Соблюдение дедлайнов, %",
               "Коммитов", "Качество кода", "Коммуникации", "Грейд", "Итоговый балл"]
    ws.append(headers)

    for emp in employees:
        emp_data = {
            "tasks_completed": emp.tasks_completed,
            "deadlines_met": emp.deadlines_met,
            "code_quality_score": emp.code_quality_score,
            "communication_score": emp.communication_score
        }
        weights = get_competency_weights_from_db(emp.position, db)
        result = calculate_grade(emp_data, weights, grade_levels)

        ws.append([
            emp.id, emp.name, emp.position,
            emp.tasks_completed, emp.deadlines_met, emp.commits_count,
            emp.code_quality_score, emp.communication_score,
            result["grade"], result["total_score"]
        ])

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=gradeinsight_report.xlsx"}
    )

# ==================== Управление компетенциями (только admin) ====================

@app.get("/settings/roles")
def get_roles(db: Session = Depends(get_db), current_user: User = Depends(require_role(["admin"]))):
    roles = db.query(Role).all()
    return roles

@app.get("/settings/competencies")
def get_competencies(db: Session = Depends(get_db), current_user: User = Depends(require_role(["admin"]))):
    comps = db.query(Competency).all()
    return comps

@app.get("/settings/grade_levels")
def get_grade_levels_api(db: Session = Depends(get_db), current_user: User = Depends(require_role(["admin"]))):
    levels = db.query(GradeLevel).all()
    return levels

@app.get("/settings/weights/{role_id}")
def get_weights(role_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_role(["admin"]))):
    weights = db.query(CompetencyWeight).filter(CompetencyWeight.role_id == role_id).all()
    result = []
    for w in weights:
        comp = db.query(Competency).filter(Competency.id == w.competency_id).first()
        result.append({
            "competency_id": w.competency_id,
            "competency_name": comp.name if comp else "unknown",
            "weight": w.weight
        })
    return result

@app.put("/settings/weights/{role_id}")
def update_weights(role_id: int, weights_data: dict, db: Session = Depends(get_db), current_user: User = Depends(require_role(["admin"]))):
    for comp_name, weight in weights_data.items():
        comp = db.query(Competency).filter(Competency.name == comp_name).first()
        if comp:
            existing = db.query(CompetencyWeight).filter(
                CompetencyWeight.role_id == role_id,
                CompetencyWeight.competency_id == comp.id
            ).first()
            if existing:
                existing.weight = weight
            else:
                new_weight = CompetencyWeight(role_id=role_id, competency_id=comp.id, weight=weight)
                db.add(new_weight)
    db.commit()
    return {"message": "Веса обновлены"}

@app.put("/settings/grade_levels/{level_id}")
def update_grade_level(level_id: int, min_score: float, max_score: float, db: Session = Depends(get_db), current_user: User = Depends(require_role(["admin"]))):
    level = db.query(GradeLevel).filter(GradeLevel.id == level_id).first()
    if level:
        level.min_score = min_score
        level.max_score = max_score
        db.commit()
    return {"message": "Пороги обновлены"}

@app.post("/settings/role_targets")
def set_role_targets(role_id: int, targets: dict, db: Session = Depends(get_db), current_user: User = Depends(require_role(["admin"]))):
    for comp_name, target_score in targets.items():
        comp = db.query(Competency).filter(Competency.name == comp_name).first()
        if comp:
            existing = db.query(RoleTarget).filter(
                RoleTarget.role_id == role_id,
                RoleTarget.competency_id == comp.id
            ).first()
            if existing:
                existing.target_score = target_score
            else:
                new_target = RoleTarget(role_id=role_id, competency_id=comp.id, target_score=target_score)
                db.add(new_target)
    db.commit()
    return {"message": "Целевые значения установлены"}
    
@app.get("/migrate/add_grade_columns")
async def add_grade_columns(db: Session = Depends(get_db)):
    try:
        # Проверяем, существует ли колонка formal_grade
        from sqlalchemy import inspect, text
        inspector = inspect(db.get_bind())
        columns = [col['name'] for col in inspector.get_columns('employees')]
        
        if 'formal_grade' not in columns:
            db.execute(text("ALTER TABLE employees ADD COLUMN formal_grade VARCHAR(50) DEFAULT ''"))
            db.commit()
        if 'recommendation' not in columns:
            db.execute(text("ALTER TABLE employees ADD COLUMN recommendation VARCHAR(50) DEFAULT ''"))
            db.commit()
        
        return {"message": "Columns 'formal_grade' and 'recommendation' added successfully"}
    except Exception as e:
        db.rollback()
        return {"error": str(e)}

@app.get("/migrate/add_company_support")
def migrate_add_company_support(db: Session = Depends(get_db)):
    """Временный эндпоинт для миграции БД (добавление company_id)"""
    try:
        from sqlalchemy import text
        
        # Создаём таблицу companies
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS companies (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                is_active BOOLEAN DEFAULT TRUE
            )
        """))
        
        # Добавляем колонку company_id в users
        db.execute(text("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)
        """))
        
        # Добавляем колонку company_id в employees
        db.execute(text("""
            ALTER TABLE employees ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)
        """))
        
        db.commit()
        return {"message": "Migration completed successfully"}
    except Exception as e:
        db.rollback()
        return {"error": str(e)}
# ==================== Запуск ====================

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
