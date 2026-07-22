from .base import SQLAlchemyBase  
from sqlalchemy import Column, DateTime, func, String
from sqlalchemy.dialects.postgresql import UUID
import uuid
from sqlalchemy.orm import relationship


class Category(SQLAlchemyBase):
    
    __tablename__ = "categories"
    category_name = Column(String, primary_key=True, autoincrement=True)
    category_uuid = Column(UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    
    product = relationship("Product", back_populates="category")
    asset = relationship("Asset", back_populates="category")