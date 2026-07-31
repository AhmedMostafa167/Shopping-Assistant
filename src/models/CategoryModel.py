from .BaseDataModel  import BaseDataModel
from .db_schemes import Category
from sqlalchemy.future import select
from sqlalchemy import func

class CategoryModel(BaseDataModel):
    
    def __init__(self, db_client: object):
        super().__init__(db_client)
        
    @classmethod
    async def create_instance(cls, db_client: object):
        category = cls(db_client)
        return category
    
    async def create_category(self, category: Category):
        async with self.db_client() as session:
            async with session.begin():
                session.add(category)
            await session.refresh(category)
                
        return category
    
    async def get_category_or_create_one(self, category_name: str):
        async with self.db_client() as session:
            async with session.begin():
                query = select(Category).where(Category.category_name == category_name)
                result = await session.execute(query)
                category = result.scalar_one_or_none()
                if category is None:
                    category = Category(category_name=category_name)
                    category = await self.create_category(category)
                    
                    return category
                else: 
                    return category
                
    async def get_all_categories(self, page: int=1, page_size: int=10):
        async with self.db_client() as session:
            with session.begin():
                total_categories = await session.execute(select(func.count(Category.category_name)))
                total_categories = total_categories.scalar_one()    
                
                total_pages = total_categories // page_size
                if total_categories % page_size != 0:
                    total_pages += 1
                
                query = select(Category).offset(( page-1 ) * page_size ).limit(page_size)
                categories = await session.execute(query).scalars().all()
                
                return categories, total_pages