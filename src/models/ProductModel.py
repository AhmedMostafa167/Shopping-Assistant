from .BaseDataModel  import BaseDataModel
from .db_schemes import Product
from sqlalchemy.future import select
from sqlalchemy import column, func, delete, desc, exists, table

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
        return products

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
        
    @staticmethod
    def _without_embedding(category_name: str, vector_table_name: str):
        """Filter: products of a category with no row in the given vector table."""
        vectors = table(vector_table_name, column("product_id"))
        return (
            Product.category_name == category_name,
            ~exists().where(vectors.c.product_id == Product.product_id),
        )

    async def get_products_without_embedding(self, category_name: str,
                                             vector_table_name: str, limit: int):
        async with self.db_client() as session:
            # Ordered, so every run walks the catalogue in the same sequence.
            query = (
                select(Product)
                .where(*self._without_embedding(category_name, vector_table_name))
                .order_by(Product.product_id)
                .limit(limit)
            )
            result = await session.execute(query)
            return result.scalars().all()

    async def count_products_without_embedding(self, category_name: str,
                                               vector_table_name: str) -> int:
        async with self.db_client() as session:
            query = (
                select(func.count())
                .select_from(Product)
                .where(*self._without_embedding(category_name, vector_table_name))
            )
            result = await session.execute(query)
            return result.scalar_one()

    async def filter_products(self, category_name: str, min_price: float = None, max_price: float = None,
                               min_rating: float = None, top_k: int = 10):
        async with self.db_client() as session:
            query = select(Product).where(Product.category_name == category_name)
            if min_price is not None:
                query = query.where(Product.price >= min_price)
            if max_price is not None:
                query = query.where(Product.price <= max_price)
            if min_rating is not None:
                query = query.where(Product.average_rating >= min_rating)
            query = query.limit(top_k)
            result = await session.execute(query)
            return result.scalars().all()

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
            products = result.all()
            
            return products