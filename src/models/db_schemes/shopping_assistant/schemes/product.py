from .base import SQLAlchemyBase  
from sqlalchemy import Column, Integer, String, Index, Float, DateTime, func, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from pydantic import BaseModel
import uuid

class Product(SQLAlchemyBase):
    
    __tablename__ = "products"
    
    product_id = Column(Integer, primary_key=True, autoincrement=True)
    product_uuid = Column(UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4)
    project_id = Column(Integer, ForeignKey("projects.project_id"), nullable=False)
    asset_id = Column(Integer, ForeignKey("assets.asset_id"), nullable=False)
    
    title = Column(String, nullable=False)
    description = Column(String, nullable=False)
    main_category = Column(String, nullable=False)
    store = Column(String, nullable=False)
    average_rating = Column(Float, nullable=False)
    rating_number = Column(Integer, nullable=False)
    price = Column(Integer, nullable=False)
    image = Column(String, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    
    project = relationship("Project", "products")
    asset = relationship("Asset", "products")
    
    __table_args__ = (
        Index("ix_product_project_id", project_id),
        Index("ix_product_asset_id", asset_id)
    )
    
class RetreivedProduct(BaseModel):
    title: str
    description: str
    main_category: str
    store: str
    average_rating: float
    rating_number: int
    price: int
    image: str
    