from enum import Enum


class AssetTypeEnums(Enum):
    CSV = ".csv"
    EXCEL = ".xlsx"
    JSON = ".json"
    PARQUET = ".parquet"
    ARROW = ".arrow"