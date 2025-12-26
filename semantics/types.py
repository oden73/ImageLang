from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class Type:
    name: str
    param: Optional['Type'] = None  # for vector<T>

    def __str__(self):
        return f"vector<{self.param}>" if self.name == "vector" and self.param else self.name

    def is_numeric(self): return self.name in ("int", "float")
    def is_bool(self): return self.name == "bool"
    def is_string(self): return self.name == "string"
    def is_null(self): return self.name == "null"
    def equals(self, other: 'Type') -> bool: return self.name == other.name and self.param == other.param

# Predefined types
INT = Type("int")
FLOAT = Type("float")
BOOL = Type("bool")
STRING = Type("string")
NULL = Type("null")
IMAGE = Type("image")
PIXEL = Type("pixel")
COLOR = Type("color")

def VECTOR(elem: Type) -> Type:
    return Type("vector", elem)

def can_assign(lhs: Type, rhs: Type) -> bool:
    # Exact match
    if lhs.equals(rhs): return True
    # Numeric widening
    if lhs.equals(FLOAT) and rhs.equals(INT): return True
    # Allow null to reference-like/composite types (customize as needed)
    if rhs.is_null() and lhs.name in ("image", "color", "pixel", "vector"):
        return True
    return False

def binary_numeric_result(t1: Type, t2: Type) -> Optional[Type]:
    if t1.is_numeric() and t2.is_numeric():
        return FLOAT if FLOAT in (t1, t2) else INT
    return None
