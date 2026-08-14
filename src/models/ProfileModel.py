from .BaseDataModel import BaseDataModel
from .db_schemes import Profile
from sqlalchemy.future import select


class ProfileModel(BaseDataModel):
    def __init__(self, db_client: object):
        super().__init__(db_client)

    @classmethod
    async def create_instance(cls, db_client: object):
        profile = cls(db_client)
        return profile

    async def get_profile_or_create_one(self, username: str) -> Profile:
        async with self.db_client() as session:
            query = select(Profile).where(Profile.username == username)
            result = await session.execute(query)
            profile = result.scalar_one_or_none()

            if profile is None:
                profile = Profile(username=username)
                async with session.begin():
                    session.add(profile)
                await session.refresh(profile)

            return profile

    async def get_profile_by_username(self, username: str) -> Profile | None:
        async with self.db_client() as session:
            query = select(Profile).where(Profile.username == username)
            result = await session.execute(query)
            return result.scalar_one_or_none()