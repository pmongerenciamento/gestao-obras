# Regras de negócio de versionamento: criação de snapshots e imutabilidade do baseline
from .snapshots import ImportResult, ImportType, process_import

__all__ = ["ImportType", "ImportResult", "process_import"]
