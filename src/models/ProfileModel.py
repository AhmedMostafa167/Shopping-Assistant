from sqlalchemy import select

from .BaseDataModel import BaseDataModel
from .db_schemes import Profile


class ProfileModel(BaseDataModel):
    def __init__(self, db_client: object):
        super().__init__(db_client)

    @classmethod
    async def create_instance(cls, db_client: object):
        return cls(db_client)

    async def get_profile_or_create_one(self, username: str) -> Profile:
        async with self.db_client() as session:
            result = await session.execute(
                select(Profile).where(Profile.username == username)
            )
            profile = result.scalar_one_or_none()
            if profile is not None:
                return profile

            profile = Profile(username=username)
            session.add(profile)
            try:
                await session.commit()
            except Exception:
                await session.rollback()
                # A concurrent request may have created the same unique user.
                result = await session.execute(
                    select(Profile).where(Profile.username == username)
                )
                profile = result.scalar_one_or_none()
                if profile is None:
                    raise
                return profile

            await session.refresh(profile)
            return profile

    async def get_profile_by_username(self, username: str) -> Profile | None:
        async with self.db_client() as session:
            result = await session.execute(
                select(Profile).where(Profile.username == username)
            )
            return result.scalar_one_or_none()
