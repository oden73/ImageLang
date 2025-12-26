from dataclasses import dataclass
from typing import Dict, List, Optional
from semantics.types import Type

@dataclass
class VarSymbol:
    name: str
    type: Type
    by_ref: bool = False

@dataclass
class FuncSymbol:
    name: str
    ret_type: Type
    params: List[VarSymbol]

class Scope:
    def __init__(self, parent: Optional['Scope'] = None):
        self.parent = parent
        self.vars: Dict[str, VarSymbol] = {}
        self.funcs: Dict[str, FuncSymbol] = {}

    def define_var(self, sym: VarSymbol) -> bool:
        if sym.name in self.vars:
            return False
        self.vars[sym.name] = sym
        return True

    def define_func(self, fn: FuncSymbol) -> bool:
        if fn.name in self.funcs:
            return False
        self.funcs[fn.name] = fn
        return True

    def resolve_var(self, name: str) -> Optional[VarSymbol]:
        s = self
        while s:
            if name in s.vars:
                return s.vars[name]
            s = s.parent
        return None

    def resolve_func(self, name: str) -> Optional[FuncSymbol]:
        s = self
        while s:
            if name in s.funcs:
                return s.funcs[name]
            s = s.parent
        return None
