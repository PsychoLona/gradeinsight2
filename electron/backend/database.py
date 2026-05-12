import os
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import hashlib
import secrets

# Получаем строку подключения из переменной окружения, иначе SQLite (локально)
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./gradeinsight.db")

# Для SQLite нужно добавить check_same_thread=False
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# Функции хеширования (без bcrypt)
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    hash_obj = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return f"{salt}${hash_obj.hex()}"

def verify_password(password: str, hashed: str) -> bool:
    try:
        salt, stored_hash = hashed.split('$')
    except ValueError:
        return False
    hash_obj = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return hash_obj.hex() == stored_hash

# Модель пользователя
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String, default="employee")  # admin, hr, employee
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    is_active = Column(Boolean, default=True)

    employee = relationship("Employee", back_populates="user")

    def verify_password(self, password: str) -> bool:
        return verify_password(password, self.hashed_password)

    @staticmethod
    def hash_password(password: str) -> str:
        return hash_password(password)

# Модель сотрудника
class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    position = Column(String)
    department = Column(String, default="")
    experience = Column(Integer, default=0)
    photo_url = Column(String, default="")
    tasks_completed = Column(Integer, default=0)
    deadlines_met = Column(Float, default=0.0)
    commits_count = Column(Integer, default=0)
    code_quality_score = Column(Float, default=0.0)
    communication_score = Column(Float, default=0.0)
    grade = Column(String, default="Не определен")
    formal_grade = Column(String, default="")
    recommendation = Column(String, default="")

    user = relationship("User", back_populates="employee", uselist=False)
    history = relationship("History", back_populates="employee", cascade="all, delete-orphan")
    actions = relationship("ActionLog", back_populates="employee", cascade="all, delete-orphan")


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True)
    description = Column(String)


class Competency(Base):
    __tablename__ = "competencies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True)          # tasks, deadlines, code_quality, communication
    display_name = Column(String)               # русское название


class GradeLevel(Base):
    __tablename__ = "grade_levels"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True)          # Junior, Middle, Senior
    min_score = Column(Float)
    max_score = Column(Float)
    description = Column(String)


class CompetencyWeight(Base):
    __tablename__ = "competency_weights"

    id = Column(Integer, primary_key=True, index=True)
    role_id = Column(Integer, ForeignKey("roles.id"))
    competency_id = Column(Integer, ForeignKey("competencies.id"))
    weight = Column(Float)


class RoleTarget(Base):
    __tablename__ = "role_targets"

    id = Column(Integer, primary_key=True, index=True)
    role_id = Column(Integer, ForeignKey("roles.id"))
    competency_id = Column(Integer, ForeignKey("competencies.id"))
    target_score = Column(Float)


class History(Base):
    __tablename__ = "history"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    date = Column(DateTime, default=datetime.utcnow)
    total_score = Column(Float)
    grade = Column(String)
    tasks_completed = Column(Integer)
    deadlines_met = Column(Float)
    code_quality_score = Column(Float)
    communication_score = Column(Float)

    employee = relationship("Employee", back_populates="history")


class ActionLog(Base):
    __tablename__ = "action_logs"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    timestamp = Column(DateTime, default=datetime.utcnow)
    action_type = Column(String)          # upload_code, upload_comments, update_metrics, analyze_code, analyze_comments
    details = Column(String)              # описание действия (имя файла, изменённые метрики)
    delta_score = Column(Float)           # изменение балла
    new_score = Column(Float)             # балл после действия

    employee = relationship("Employee", back_populates="actions")


def init_db():
    """Создаёт таблицы и добавляет справочные данные и тестовых пользователей"""
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # Добавляем уровни грейдов
        if db.query(GradeLevel).count() == 0:
            db.add_all([
                GradeLevel(name="Junior", min_score=0.0, max_score=0.4, description="Начальный уровень"),
                GradeLevel(name="Middle", min_score=0.4, max_score=0.7, description="Средний уровень"),
                GradeLevel(name="Senior", min_score=0.7, max_score=1.0, description="Старший уровень"),
            ])

        # Добавляем компетенции
        if db.query(Competency).count() == 0:
            db.add_all([
                Competency(name="tasks", display_name="Выполнение задач"),
                Competency(name="deadlines", display_name="Соблюдение сроков"),
                Competency(name="code_quality", display_name="Качество кода"),
                Competency(name="communication", display_name="Коммуникации"),
            ])

        # Добавляем роли
        if db.query(Role).count() == 0:
            db.add_all([
                Role(name="Разработчик", description="Разрабатывает и поддерживает код"),
                Role(name="Аналитик", description="Анализирует требования и данные"),
                Role(name="Team Lead", description="Управляет командой разработки"),
            ])

        # Создаём тестовых пользователей, если их нет
        if db.query(User).count() == 0:
            # Администратор
            admin = User(
                username="admin",
                hashed_password=User.hash_password("admin123"),
                role="admin",
                is_active=True
            )
            db.add(admin)

            # HR-пользователь
            hr_user = User(
                username="hr_user",
                hashed_password=User.hash_password("hr123"),
                role="hr",
                is_active=True
            )
            db.add(hr_user)

            # Сотрудник для employee_user
            test_emp = Employee(
                name="Тестовый Сотрудник",
                position="Разработчик",
                experience=2
            )
            db.add(test_emp)
            db.flush()  # получаем id

            emp_user = User(
                username="employee_user",
                hashed_password=User.hash_password("emp123"),
                role="employee",
                employee_id=test_emp.id,
                is_active=True
            )
            db.add(emp_user)

            db.commit()
            print("Созданы тестовые пользователи:")
            print("  admin / admin123 (admin)")
            print("  hr_user / hr123 (hr)")
            print("  employee_user / emp123 (employee, привязан к тестовому сотруднику)")

    finally:
        db.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
