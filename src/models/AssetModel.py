from .BaseDataModel  import BaseDataModel
from .db_schemes import Asset
from sqlalchemy.future import select
from sqlalchemy import func
import os

class AssetModel(BaseDataModel):

    def __init__(self, db_client: object):
        super().__init__(db_client=db_client)
        

    @classmethod
    async def create_instance(cls, db_client: object):
        instance = cls(db_client)
        return instance
    
    async def create_asset(self, asset: Asset):

        async with self.db_client() as session:
            async with session.begin():
                session.add(asset)
            await session.refresh(asset)
        return asset

    async def get_asset_by_name(self, asset_name: str):

        async with self.db_client() as session:
            query = select(Asset).where(Asset.asset_name == asset_name)
            result = await session.execute(query)
            asset = result.scalars().all()
        return asset
    

    async def get_all_category_assets(self, asset_category_name: str):

        async with self.db_client() as session:
            query = select(Asset).where(Asset.asset_category_name == asset_category_name)
            result = await session.execute(query)
            assets = result.scalars().all()
        return assets

