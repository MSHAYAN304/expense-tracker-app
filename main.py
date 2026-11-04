import os
import csv
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from jose import jwt

import models, schemas
from database import engine, get_db

models.Base.metadata.create_all(bind=engine)

SECRET_KEY = "super-secret-key-change-this-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI(title="Pro Expense Tracker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure upload directory exists and serve statically
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

@app.post("/signup", response_model=dict)
def signup(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    hashed_pwd = get_password_hash(user.password)
    new_user = models.User(username=user.username, hashed_password=hashed_pwd, role=user.role)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "User created successfully", "user_id": new_user.id, "role": new_user.role}

@app.post("/login")
def login(user: schemas.UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.username == user.username).first()
    if not db_user or not verify_password(user.password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    access_token = create_access_token(data={"sub": db_user.username, "role": db_user.role})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "id": db_user.id,
        "username": db_user.username,
        "role": db_user.role
    }

@app.post("/projects", status_code=status.HTTP_201_CREATED)
def create_project(project: schemas.ProjectCreate, db: Session = Depends(get_db)):
    db_project = db.query(models.Project).filter(models.Project.name == project.name).first()
    if db_project:
        raise HTTPException(status_code=400, detail="Project already exists")
    new_project = models.Project(name=project.name, description=project.description, budget=project.budget)
    db.add(new_project)
    db.commit()
    db.refresh(new_project)
    return new_project

@app.get("/projects")
def get_projects(db: Session = Depends(get_db)):
    projects = db.query(models.Project).all()
    result = []
    for p in projects:
        spent = sum(exp.amount for exp in p.expenses)
        result.append({
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "budget": p.budget,
            "total_spent": spent
        })
    return result

# --- NEW: Category Budget Endpoints ---
@app.post("/category-budgets", status_code=status.HTTP_201_CREATED)
def set_category_budget(data: schemas.CategoryBudgetCreate, db: Session = Depends(get_db)):
    existing = db.query(models.CategoryBudget).filter(
        models.CategoryBudget.project_id == data.project_id,
        models.CategoryBudget.category == data.category
    ).first()
    
    if existing:
        existing.limit_amount = data.limit_amount
    else:
        new_limit = models.CategoryBudget(
            project_id=data.project_id,
            category=data.category,
            limit_amount=data.limit_amount
        )
        db.add(new_limit)
    db.commit()
    return {"message": "Category budget limit saved successfully"}

@app.get("/projects/{project_id}/summary")
def get_project_summary(project_id: int, db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    limits = {cb.category: cb.limit_amount for cb in project.category_budgets}
    
    category_spending = {}
    for exp in project.expenses:
        category_spending[exp.category] = category_spending.get(exp.category, 0.0) + exp.amount

    summary = []
    alerts = []
    for cat, spent in category_spending.items():
        limit = limits.get(cat, 0.0)
        is_over = limit > 0 and spent > limit
        if is_over:
            alerts.append(f"⚠️ Alert: Category '{cat}' has exceeded its budget limit! Spent: Rs. {spent} / Limit: Rs. {limit}")
        summary.append({
            "category": cat,
            "spent": spent,
            "limit": limit,
            "is_over": is_over
        })
    
    return {"summary": summary, "alerts": alerts}
# -------------------------------------

@app.post("/expenses", status_code=status.HTTP_201_CREATED)
async def add_expense(
    title: str = Form(...),
    category: str = Form(...),
    amount: float = Form(...),
    user_id: int = Form(...),
    project_id: int = Form(...),
    receipt: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    receipt_path = None
    if receipt:
        file_filename = f"{datetime.utcnow().timestamp()}_{receipt.filename}"
        file_location = os.path.join(UPLOAD_DIR, file_filename)
        with open(file_location, "wb+") as file_object:
            file_object.write(await receipt.read())
        receipt_path = f"/uploads/{file_filename}"

    new_expense = models.Expense(
        title=title,
        category=category,
        amount=amount,
        receipt_path=receipt_path,
        user_id=user_id,
        project_id=project_id
    )
    db.add(new_expense)
    db.commit()
    return {"message": "Expense added successfully"}

@app.get("/expenses")
def get_expenses(
    project_id: Optional[int] = Query(None),
    user_id: Optional[int] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    query = db.query(models.Expense)
    if project_id:
        query = query.filter(models.Expense.project_id == project_id)
    if user_id:
        query = query.filter(models.Expense.user_id == user_id)
    if start_date:
        query = query.filter(models.Expense.date >= datetime.fromisoformat(start_date))
    if end_date:
        query = query.filter(models.Expense.date <= datetime.fromisoformat(end_date + "T23:59:59"))

    expenses = query.order_by(models.Expense.date.desc()).all()
    results = []
    for exp in expenses:
        results.append({
            "id": exp.id,
            "title": exp.title,
            "category": exp.category,
            "amount": exp.amount,
            "receipt_path": exp.receipt_path,
            "date": exp.date,
            "user_id": exp.user_id,
            "username": exp.user.username if exp.user else "Unknown",
            "project_id": exp.project_id,
            "project_name": exp.project.name if exp.project else "Unknown"
        })
    return results

@app.get("/export-csv")
def export_csv(db: Session = Depends(get_db)):
    expenses = db.query(models.Expense).all()
    
    def iter_csv():
        yield "ID,Project,Worker,Category,Title,Amount,Date\n"
        for exp in expenses:
            p_name = exp.project.name if exp.project else "N/A"
            u_name = exp.user.username if exp.user else "N/A"
            yield f"{exp.id},\"{p_name}\",\"{u_name}\",\"{exp.category}\",\"{exp.title}\",{exp.amount},{exp.date}\n"

    return StreamingResponse(iter_csv(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=expense_report.csv"})