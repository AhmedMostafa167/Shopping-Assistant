from .base import SQLAlchemyBase  
from sqlalchemy.dialects.postgresql import UUID, TSVECTOR
from sqlalchemy import Column, Integer, String, Index, Float, DateTime, func, ForeignKey, Computed
from sqlalchemy.orm import relationship
from pydantic import BaseModel
import uuid

class Product(SQLAlchemyBase):
    __tablename__ = "products"
    
    product_id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(String, nullable=True)
    product_uuid = Column(UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4)
    category_name = Column(String, ForeignKey("categories.category_name"), nullable=False)
    asset_id = Column(Integer, ForeignKey("assets.asset_id"), nullable=False)
    
    title = Column(String, nullable=False)
    description = Column(String, nullable=False)
    store = Column(String, nullable=True)
    average_rating = Column(Float, nullable=True)
    rating_number = Column(Integer, nullable=True)
    price = Column(Float, nullable=True)
    image = Column(String, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    search_vector = Column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', coalesce(title,'') || ' ' || coalesce(description,'') || ' ' || coalesce(store,''))",
            persisted=True
        )
    )

    category = relationship("Category", back_populates="products")
    asset = relationship("Asset", back_populates="products")     

    __table_args__ = (
        Index("ix_product_category_name", category_name),
        Index("ix_product_asset_id", asset_id),
        Index("ix_products_search_vector", "search_vector", postgresql_using="gin")
    )
    
    
class RetreivedProduct(BaseModel):
    title: str
    description: str
    category_name: str
    store: str | None
    average_rating: float | None
    rating_number: int | None
    price: float | None
    image: str | None

    class Config:
        from_attributes = True