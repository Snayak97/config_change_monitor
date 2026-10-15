"""
Flattens and un-flattens nested dictionary hierarchies using dot notation.
"""

from typing import Any, Dict


def flatten_dict(d: Dict[str, Any], parent_key: str = "", sep: str = ".") -> Dict[str, Any]:
    """
    Recursively flattens a nested dictionary.
    Example:
        {"db": {"host": "localhost", "port": 5432}}
        -> {"db.host": "localhost", "db.port": 5432}
    """
    items: Dict[str, Any] = {}
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else str(k)
        if isinstance(v, dict) and v:
            items.update(flatten_dict(v, new_key, sep=sep))
        else:
            items[new_key] = v
    return items


def get_type_name(val: Any) -> str:
    """
    Map Python primitive types to standard JSON / schema type names.
    Order is important: bool before int because bool subclasses int in Python.
    """
    if val is None:
        return "null"
    if isinstance(val, bool):
        return "boolean"
    if isinstance(val, int):
        return "integer"
    if isinstance(val, float):
        return "float"
    if isinstance(val, str):
        return "string"
    if isinstance(val, dict):
        return "object"
    if isinstance(val, (list, tuple, set)):
        return "array"
    return type(val).__name__
