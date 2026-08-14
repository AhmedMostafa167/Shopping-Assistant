from .BaseDataModel  import BaseDataModel
from .db_schemes import Product, RetreivedProduct
from sqlalchemy.future import select
from sqlalchemy import func, delete, desc

class ProductModel(BaseDataModel):
    def __init__(self, db_client: object):
        super().__init__(db_client)
        
    @classmethod
    async def create_instance(cls, db_client: object):
        product = cls(db_client)
        return product
    
    async def insert_product(self, product: Product):
        async with self.db_client() as session:
            async with session.begin():
                session.add(product)
                await session.refresh(product)
                
        return product
    
    async def get_products_by_ids(self, product_ids: list[int]):
        async with self.db_client() as session:
            query = select(Product).where(Product.product_id.in_(product_ids))
            result = await session.execute(query)
            products = result.scalars().all()
        return [RetreivedProduct.model_validate(p) for p in products]

    async def insert_many_products(self, products: list[Product], batch_size: int=100):
        async with self.db_client() as session:
            async with session.begin():
                for i in range(0, len(products), batch_size):
                    session.add_all(products[i:i+batch_size])
                    
        return len(products)
    
    
    async def delete_products_by_category(self, category_name: int):
        async with self.db_client() as session:
            query = delete(Product).where(Product.category_name == category_name)  
            result = await session.execute(query)
            await session.commit()
            
            return result.rowcount
                    
    async def get_products_by_category(self, category_name: str, page_no: int=1, page_size: int=50):
        async with self.db_client() as session:
            query = select(Product).where(Product.category_name == category_name).offset(( page_no-1 ) * page_size ).limit(page_size)
            result = await session.execute(query)
            products = result.scalars().all()
            
            return products
        
    async def keyword_search(self, query: str, top_k: int = 10):
        async with self.db_client() as session:
            ts_query = func.plainto_tsquery("english", query)

            stmt = (
                select(
                    Product.product_id,
                    func.ts_rank(Product.search_vector, ts_query).label("score")
                )
                .where(Product.search_vector.op("@@")(ts_query))
                .order_by(desc("score"))
                .limit(top_k)
            )
            result = await session.execute(stmt)
            return result.all()
