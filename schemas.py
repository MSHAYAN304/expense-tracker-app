from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class UserCreate(BaseModel):
    username: str
    password: str
    role: str

class UserLogin(BaseModel):
    username: str
    password: str

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    budget: float = 0.0

class CategoryBudgetCreate(BaseModel):
    project_id: int
    category: str
    limit_amount: float