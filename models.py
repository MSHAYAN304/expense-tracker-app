from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False)
    
    expenses = relationship("Expense", back_populates="user")

class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(String, nullable=True)
    budget = Column(Float, default=0.0, nullable=False)

    expenses = relationship("Expense", back_populates="project", cascade="all, delete-orphan")
    category_budgets = relationship("CategoryBudget", back_populates="project", cascade="all, delete-orphan")

class CategoryBudget(Base):
    __tablename__ = "category_budgets"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    category = Column(String, nullable=False)
    limit_amount = Column(Float, nullable=False)

    project = relationship("Project", back_populates="category_budgets")

class Expense(Base):
    __tablename__ = "expenses"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    category = Column(String, nullable=False, default="Miscellaneous")
    amount = Column(Float, nullable=False)
    receipt_path = Column(String, nullable=True)
    date = Column(DateTime, default=datetime.utcnow)
    
    user_id = Column(Integer, ForeignKey("users.id"))
    project_id = Column(Integer, ForeignKey("projects.id"))

    user = relationship("User", back_populates="expenses")
    project = relationship("Project", back_populates="expenses")  # <-- Fixed here