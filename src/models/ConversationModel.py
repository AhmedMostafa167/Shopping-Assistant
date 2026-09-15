import uuid

from sqlalchemy import select

from .BaseDataModel import BaseDataModel
from .db_schemes import Conversation


class ConversationModel(BaseDataModel):
    def __init__(self, db_client):
        super().__init__(db_client)

    @classmethod
    async def create_instance(cls, db_client):
        return cls(db_client)

    async def create_conversation(
        self,
        profile_id: int,
        title: str | None = None,
    ) -> Conversation:
        conversation = Conversation(
            profile_id=profile_id,
            thread_id=str(uuid.uuid4()),
            title=title,
        )

        async with self.db_client() as session:
            async with session.begin():
                session.add(conversation)
            await session.refresh(conversation)

            return conversation
    async def get_by_uuid(
        self,
        conversation_uuid: uuid.UUID,
    ) -> Conversation | None:
        async with self.db_client() as session:
            result = await session.execute(
                select(Conversation).where(
                    Conversation.conversation_uuid == conversation_uuid
                )
            )
            return result.scalar_one_or_none()

    async def get_by_uuid_for_profile(
            self,
            conversation_uuid: uuid.UUID,
            profile_id: int,
        ) -> Conversation | None:
            # Ownership is checked in the database query itself.
            async with self.db_client() as session:
                result = await session.execute(
                    select(Conversation).where(
                        Conversation.conversation_uuid == conversation_uuid,
                        Conversation.profile_id == profile_id,
                    )
                )

                return result.scalar_one_or_none()