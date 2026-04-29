"""
Task Management System - FastAPI Backend
=========================================
A high-performance, secure task management API with:
- Task CRUD operations
- Custom columns management
- Drag & drop support
- Team assignment
- Tagging & filtering
- File attachments
- JWT authentication
- Auto-save to SQLite database
"""

import os
import uuid
import json
from datetime import datetime, timedelta
from typing import List, Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException, Depends, status, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import create_engine, Column, String, Text, DateTime, ForeignKey, Boolean, Integer
from sqlalchemy.orm import sessionmaker, Session, relationship, declarative_base
from passlib.context import CryptContext
import jwt

# ==================== CONFIGURATION ====================
SECRET_KEY = "your-super-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days
DATABASE_URL = "sqlite:///./taskmanager.db"
UPLOAD_DIR = Path("./uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# ==================== DATABASE SETUP ====================
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ==================== MODELS ====================
class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String)
    avatar_url = Column(String, default=None)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    tasks = relationship("Task", back_populates="assignee", foreign_keys="Task.assignee_id")
    created_tasks = relationship("Task", back_populates="creator", foreign_keys="Task.creator_id")

class ColumnModel(Base):
    __tablename__ = "columns"
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    color = Column(String, default="#6366f1")
    position = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    tasks = relationship("Task", back_populates="column")

class Tag(Base):
    __tablename__ = "tags"
    id = Column(String, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    color = Column(String, default="#6366f1")
    
    tasks = relationship("TaskTag", back_populates="tag")

class TaskTag(Base):
    __tablename__ = "task_tags"
    task_id = Column(String, ForeignKey("tasks.id"), primary_key=True)
    tag_id = Column(String, ForeignKey("tags.id"), primary_key=True)
    
    tag = relationship("Tag", back_populates="tasks")
    task = relationship("Task", back_populates="tags")

class Task(Base):
    __tablename__ = "tasks"
    id = Column(String, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, default="")
    column_id = Column(String, ForeignKey("columns.id"))
    assignee_id = Column(String, ForeignKey("users.id"), nullable=True)
    creator_id = Column(String, ForeignKey("users.id"), nullable=False)
    position = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    column = relationship("ColumnModel", back_populates="tasks")
    assignee = relationship("User", back_populates="tasks", foreign_keys="Task.assignee_id")
    creator = relationship("User", back_populates="created_tasks", foreign_keys="Task.creator_id")
    tags = relationship("TaskTag", back_populates="task")
    attachments = relationship("Attachment", back_populates="task")

class Attachment(Base):
    __tablename__ = "attachments"
    id = Column(String, primary_key=True, index=True)
    task_id = Column(String, ForeignKey("tasks.id"), nullable=False)
    filename = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    file_type = Column(String)
    file_size = Column(Integer)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    
    task = relationship("Task", back_populates="attachments")

# Create tables
Base.metadata.create_all(bind=engine)

# ==================== PYDANTIC SCHEMAS ====================
class UserBase(BaseModel):
    username: str
    email: str
    full_name: Optional[str] = None

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: str
    avatar_url: Optional[str] = None
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

class ColumnCreate(BaseModel):
    name: str
    color: Optional[str] = "#6366f1"

class ColumnUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    position: Optional[int] = None

class ColumnResponse(ColumnCreate):
    id: str
    position: int
    created_at: datetime
    tasks: List["TaskResponse"] = []
    
    model_config = ConfigDict(from_attributes=True)

class TagCreate(BaseModel):
    name: str
    color: Optional[str] = "#6366f1"

class TagResponse(TagCreate):
    id: str
    
    model_config = ConfigDict(from_attributes=True)

class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = ""
    column_id: str
    assignee_id: Optional[str] = None
    tag_ids: List[str] = []

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    column_id: Optional[str] = None
    assignee_id: Optional[str] = None
    position: Optional[int] = None
    tag_ids: Optional[List[str]] = None

class TaskResponse(BaseModel):
    id: str
    title: str
    description: str
    column_id: str
    assignee_id: Optional[str] = None
    creator_id: str
    position: int
    created_at: datetime
    updated_at: datetime
    assignee: Optional[UserResponse] = None
    tags: List[TagResponse] = []
    attachments: List["AttachmentResponse"] = []
    
    model_config = ConfigDict(from_attributes=True)

class AttachmentResponse(BaseModel):
    id: str
    task_id: str
    filename: str
    original_filename: str
    file_type: Optional[str] = None
    file_size: Optional[int] = None
    uploaded_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class FilterRequest(BaseModel):
    tag_ids: Optional[List[str]] = None
    assignee_id: Optional[str] = None
    search: Optional[str] = None

# Update forward references
ColumnResponse.model_rebuild()
TaskResponse.model_rebuild()

# ==================== SECURITY ====================
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    return user

# ==================== FASTAPI APP ====================
app = FastAPI(
    title="Task Management System API",
    description="High-performance task management with drag & drop, team collaboration, and file attachments",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# ==================== AUTH ENDPOINTS ====================
@app.post("/register", response_model=UserResponse)
def register(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = get_password_hash(user.password)
    db_user = User(
        id=str(uuid.uuid4()),
        username=user.username,
        email=user.email,
        full_name=user.full_name or user.username,
        hashed_password=hashed_password
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@app.post("/token", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "user": user}

@app.get("/me", response_model=UserResponse)
def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

@app.put("/me", response_model=UserResponse)
def update_current_user(
    full_name: Optional[str] = Form(None),
    avatar: UploadFile = File(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if full_name:
        current_user.full_name = full_name
    if avatar:
        avatar_filename = f"{current_user.id}_{avatar.filename}"
        avatar_path = UPLOAD_DIR / avatar_filename
        with open(avatar_path, "wb") as f:
            f.write(avatar.file.read())
        current_user.avatar_url = f"/uploads/{avatar_filename}"
    db.commit()
    db.refresh(current_user)
    return current_user

# ==================== USER/TEAM ENDPOINTS ====================
@app.get("/users", response_model=List[UserResponse])
def get_users(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(User).all()

@app.get("/users/{user_id}", response_model=UserResponse)
def get_user(user_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

# ==================== COLUMN ENDPOINTS ====================
@app.post("/columns", response_model=ColumnResponse)
def create_column(column: ColumnCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    max_position = db.query(ColumnModel).order_by(ColumnModel.position.desc()).first()
    new_position = (max_position.position + 1) if max_position else 0
    
    db_column = ColumnModel(
        id=str(uuid.uuid4()),
        name=column.name,
        color=column.color,
        position=new_position
    )
    db.add(db_column)
    db.commit()
    db.refresh(db_column)
    return db_column

@app.get("/columns", response_model=List[ColumnResponse])
def get_columns(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    columns = db.query(ColumnModel).order_by(ColumnModel.position).all()
    return columns

@app.put("/columns/{column_id}", response_model=ColumnResponse)
def update_column(column_id: str, column: ColumnUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_column = db.query(ColumnModel).filter(ColumnModel.id == column_id).first()
    if not db_column:
        raise HTTPException(status_code=404, detail="Column not found")
    
    if column.name is not None:
        db_column.name = column.name
    if column.color is not None:
        db_column.color = column.color
    if column.position is not None:
        db_column.position = column.position
    
    db.commit()
    db.refresh(db_column)
    return db_column

@app.delete("/columns/{column_id}")
def delete_column(column_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_column = db.query(ColumnModel).filter(ColumnModel.id == column_id).first()
    if not db_column:
        raise HTTPException(status_code=404, detail="Column not found")
    
    # Move tasks to first column or delete
    first_column = db.query(ColumnModel).filter(ColumnModel.id != column_id).first()
    if first_column:
        db.query(Task).filter(Task.column_id == column_id).update({"column_id": first_column.id})
    
    db.delete(db_column)
    db.commit()
    return {"message": "Column deleted"}

@app.put("/columns/reorder")
def reorder_columns(column_ids: List[str], db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    for position, col_id in enumerate(column_ids):
        db_column = db.query(ColumnModel).filter(ColumnModel.id == col_id).first()
        if db_column:
            db_column.position = position
    db.commit()
    return {"message": "Columns reordered"}

# ==================== TAG ENDPOINTS ====================
@app.post("/tags", response_model=TagResponse)
def create_tag(tag: TagCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    existing = db.query(Tag).filter(Tag.name == tag.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Tag already exists")
    
    db_tag = Tag(id=str(uuid.uuid4()), name=tag.name, color=tag.color)
    db.add(db_tag)
    db.commit()
    db.refresh(db_tag)
    return db_tag

@app.get("/tags", response_model=List[TagResponse])
def get_tags(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(Tag).all()

@app.delete("/tags/{tag_id}")
def delete_tag(tag_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not db_tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    
    db.query(TaskTag).filter(TaskTag.tag_id == tag_id).delete()
    db.delete(db_tag)
    db.commit()
    return {"message": "Tag deleted"}

# ==================== TASK ENDPOINTS ====================
@app.post("/tasks", response_model=TaskResponse)
def create_task(task: TaskCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Verify column exists
    column = db.query(ColumnModel).filter(ColumnModel.id == task.column_id).first()
    if not column:
        raise HTTPException(status_code=404, detail="Column not found")
    
    # Verify assignee if provided
    if task.assignee_id:
        assignee = db.query(User).filter(User.id == task.assignee_id).first()
        if not assignee:
            raise HTTPException(status_code=404, detail="Assignee not found")
    
    # Get max position in column
    max_pos = db.query(Task).filter(Task.column_id == task.column_id).order_by(Task.position.desc()).first()
    new_position = (max_pos.position + 1) if max_pos else 0
    
    db_task = Task(
        id=str(uuid.uuid4()),
        title=task.title,
        description=task.description or "",
        column_id=task.column_id,
        assignee_id=task.assignee_id,
        creator_id=current_user.id,
        position=new_position
    )
    db.add(db_task)
    
    # Add tags
    for tag_id in task.tag_ids:
        tag = db.query(Tag).filter(Tag.id == tag_id).first()
        if tag:
            task_tag = TaskTag(task_id=db_task.id, tag_id=tag_id)
            db.add(task_tag)
    
    db.commit()
    db.refresh(db_task)
    return db_task

@app.get("/tasks", response_model=List[TaskResponse])
def get_tasks(
    tag_ids: Optional[str] = None,
    assignee_id: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Task)
    
    # Filter by tags
    if tag_ids:
        tag_id_list = tag_ids.split(",")
        query = query.join(TaskTag).filter(TaskTag.tag_id.in_(tag_id_list))
    
    # Filter by assignee
    if assignee_id:
        query = query.filter(Task.assignee_id == assignee_id)
    
    # Search in title/description
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Task.title.like(search_term)) | (Task.description.like(search_term))
        )
    
    tasks = query.order_by(Task.position).all()
    return tasks

@app.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@app.put("/tasks/{task_id}", response_model=TaskResponse)
def update_task(task_id: str, task_update: TaskUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_task = db.query(Task).filter(Task.id == task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task_update.title is not None:
        db_task.title = task_update.title
    if task_update.description is not None:
        db_task.description = task_update.description
    if task_update.column_id is not None:
        # Verify column exists
        column = db.query(ColumnModel).filter(ColumnModel.id == task_update.column_id).first()
        if not column:
            raise HTTPException(status_code=404, detail="Column not found")
        db_task.column_id = task_update.column_id
    if task_update.assignee_id is not None:
        if task_update.assignee_id:
            assignee = db.query(User).filter(User.id == task_update.assignee_id).first()
            if not assignee:
                raise HTTPException(status_code=404, detail="Assignee not found")
        db_task.assignee_id = task_update.assignee_id
    if task_update.position is not None:
        db_task.position = task_update.position
    
    # Update tags if provided
    if task_update.tag_ids is not None:
        db.query(TaskTag).filter(TaskTag.task_id == task_id).delete()
        for tag_id in task_update.tag_ids:
            tag = db.query(Tag).filter(Tag.id == tag_id).first()
            if tag:
                task_tag = TaskTag(task_id=task_id, tag_id=tag_id)
                db.add(task_tag)
    
    db_task.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(db_task)
    return db_task

@app.delete("/tasks/{task_id}")
def delete_task(task_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_task = db.query(Task).filter(Task.id == task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Delete attachments
    attachments = db.query(Attachment).filter(Attachment.task_id == task_id).all()
    for att in attachments:
        try:
            (UPLOAD_DIR / att.filename).unlink(missing_ok=True)
        except:
            pass
    
    db.query(Attachment).filter(Attachment.task_id == task_id).delete()
    db.query(TaskTag).filter(TaskTag.task_id == task_id).delete()
    db.delete(db_task)
    db.commit()
    return {"message": "Task deleted"}

# ==================== DRAG & DROP ENDPOINTS ====================
@app.put("/tasks/{task_id}/move")
def move_task(
    task_id: str,
    column_id: str,
    position: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Move a task to a new column/position (drag & drop)"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    column = db.query(ColumnModel).filter(ColumnModel.id == column_id).first()
    if not column:
        raise HTTPException(status_code=404, detail="Column not found")
    
    # Update positions of other tasks
    db.query(Task).filter(
        Task.column_id == column_id,
        Task.position >= position,
        Task.id != task_id
    ).update({Task.position: Task.position + 1})
    
    task.column_id = column_id
    task.position = position
    task.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(task)
    return task

@app.put("/tasks/reorder")
def reorder_tasks(
    task_orders: List[dict],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Reorder multiple tasks at once (batch drag & drop)"""
    for order in task_orders:
        task = db.query(Task).filter(Task.id == order["task_id"]).first()
        if task:
            task.column_id = order["column_id"]
            task.position = order["position"]
            task.updated_at = datetime.utcnow()
    
    db.commit()
    return {"message": "Tasks reordered"}

# ==================== FILE ATTACHMENT ENDPOINTS ====================
@app.post("/tasks/{task_id}/attachments", response_model=AttachmentResponse)
async def upload_attachment(
    task_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Upload a file attachment to a task"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Generate unique filename
    file_ext = os.path.splitext(file.filename)[1]
    filename = f"{task_id}_{uuid.uuid4()}{file_ext}"
    file_path = UPLOAD_DIR / filename
    
    # Save file
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)
    
    # Create attachment record
    attachment = Attachment(
        id=str(uuid.uuid4()),
        task_id=task_id,
        filename=filename,
        original_filename=file.filename,
        file_type=file.content_type,
        file_size=len(content)
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    
    return attachment

@app.get("/tasks/{task_id}/attachments", response_model=List[AttachmentResponse])
def get_attachments(task_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get all attachments for a task"""
    return db.query(Attachment).filter(Attachment.task_id == task_id).all()

@app.delete("/attachments/{attachment_id}")
def delete_attachment(attachment_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Delete an attachment"""
    attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    
    # Delete file
    try:
        (UPLOAD_DIR / attachment.filename).unlink(missing_ok=True)
    except:
        pass
    
    db.delete(attachment)
    db.commit()
    return {"message": "Attachment deleted"}

@app.get("/attachments/{attachment_id}/download")
def download_attachment(attachment_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Download an attachment"""
    attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    
    return {
        "filename": attachment.filename,
        "original_filename": attachment.original_filename,
        "download_url": f"/uploads/{attachment.filename}"
    }

# ==================== FILTER ENDPOINTS ====================
@app.post("/tasks/filter", response_model=List[TaskResponse])
def filter_tasks(
    tag_ids: Optional[List[str]] = None,
    assignee_id: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Filter tasks by tags, assignee, or search term"""
    query = db.query(Task)
    
    if tag_ids:
        query = query.join(TaskTag).filter(TaskTag.tag_id.in_(tag_ids))
    
    if assignee_id:
        query = query.filter(Task.assignee_id == assignee_id)
    
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Task.title.like(search_term)) | (Task.description.like(search_term))
        )
    
    return query.order_by(Task.position).all()

# ==================== BOARD STATE ENDPOINTS ====================
@app.get("/board")
def get_board_state(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get complete board state (columns, tasks, users, tags)"""
    columns = db.query(ColumnModel).order_by(ColumnModel.position).all()
    tasks = db.query(Task).order_by(Task.position).all()
    users = db.query(User).all()
    tags = db.query(Tag).all()
    
    # Build response
    column_data = []
    for col in columns:
        col_tasks = [t for t in tasks if t.column_id == col.id]
        column_data.append({
            "id": col.id,
            "name": col.name,
            "color": col.color,
            "position": col.position,
            "tasks": [
                {
                    "id": t.id,
                    "title": t.title,
                    "description": t.description,
                    "position": t.position,
                    "assignee_id": t.assignee_id,
                    "creator_id": t.creator_id,
                    "created_at": t.created_at.isoformat(),
                    "updated_at": t.updated_at.isoformat(),
                    "assignee": {
                        "id": t.assignee.id,
                        "username": t.assignee.username,
                        "full_name": t.assignee.full_name,
                        "avatar_url": t.assignee.avatar_url
                    } if t.assignee else None,
                    "tags": [
                        {"id": tt.tag.id, "name": tt.tag.name, "color": tt.tag.color}
                        for tt in t.tags
                    ],
                    "attachments": [
                        {
                            "id": a.id,
                            "filename": a.filename,
                            "original_filename": a.original_filename,
                            "file_type": a.file_type,
                            "file_size": a.file_size
                        }
                        for a in t.attachments
                    ]
                }
                for t in sorted(col_tasks, key=lambda x: x.position)
            ]
        })
    
    return {
        "columns": column_data,
        "users": [
            {
                "id": u.id,
                "username": u.username,
                "full_name": u.full_name,
                "avatar_url": u.avatar_url
            }
            for u in users
        ],
        "tags": [
            {
                "id": t.id,
                "name": t.name,
                "color": t.color
            }
            for t in tags
        ]
    }

# ==================== HEALTH CHECK ====================
@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

# ==================== INITIAL DATA SEED ====================
def seed_initial_data():
    """Seed initial columns and tags for new installations"""
    db = SessionLocal()
    try:
        # Check if data exists
        if db.query(ColumnModel).first():
            return
        
        # Create default columns
        default_columns = [
            {"name": "Backlog", "color": "#64748b", "position": 0},
            {"name": "To Do", "color": "#3b82f6", "position": 1},
            {"name": "In Progress", "color": "#f59e0b", "position": 2},
            {"name": "Review", "color": "#8b5cf6", "position": 3},
            {"name": "Done", "color": "#10b981", "position": 4},
        ]
        
        for col_data in default_columns:
            col = ColumnModel(id=str(uuid.uuid4()), **col_data)
            db.add(col)
        
        # Create default tags
        default_tags = [
            {"name": "UX", "color": "#ec4899"},
            {"name": "Engineering", "color": "#3b82f6"},
            {"name": "QA", "color": "#10b981"},
            {"name": "Bug", "color": "#ef4444"},
            {"name": "Feature", "color": "#8b5cf6"},
            {"name": "Documentation", "color": "#f59e0b"},
        ]
        
        for tag_data in default_tags:
            tag = Tag(id=str(uuid.uuid4()), **tag_data)
            db.add(tag)
        
        db.commit()
        print("✓ Initial data seeded successfully")
    except Exception as e:
        print(f"Error seeding data: {e}")
        db.rollback()
    finally:
        db.close()

# Run seed on startup
seed_initial_data()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)