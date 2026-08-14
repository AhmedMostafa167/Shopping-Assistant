from pydantic import BaseModel
from typing import Optional

class ProcessRequest(BaseModel):
    batch_size: int = 100
