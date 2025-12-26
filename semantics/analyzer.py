from antlr4 import CommonTokenStream, ParserRuleContext
from ImageLangParser import ImageLangParser
from ImageLangVisitor import ImageLangVisitor

from semantics.symbols import Scope, VarSymbol, FuncSymbol
from semantics.types import *
from semantics.errors import make_error


# -----------------------------
# Built-in functions registry
# -----------------------------
def seed_builtins(scope: Scope):
    # IO
    scope.define_func(FuncSymbol("write", NULL, [VarSymbol("msg", STRING)]))
    # read(type) по грамматике как read_type_call: фактический тип берём из конструкции, не из сигнатуры
    scope.define_func(FuncSymbol("read", STRING, [VarSymbol("dummy", STRING)]))

    # Files/images
    scope.define_func(FuncSymbol("load", IMAGE, [VarSymbol("path", STRING)]))
    scope.define_func(FuncSymbol("save", NULL, [VarSymbol("img", IMAGE), VarSymbol("path", STRING)]))

    # Image processing
    scope.define_func(FuncSymbol("pow_channels", IMAGE, [VarSymbol("img", IMAGE), VarSymbol("gamma", FLOAT)]))
    scope.define_func(FuncSymbol("width", INT, [VarSymbol("img", IMAGE)]))
    scope.define_func(FuncSymbol("height", INT, [VarSymbol("img", IMAGE)]))
    scope.define_func(FuncSymbol("get_pixel", COLOR, [
        VarSymbol("img", IMAGE), VarSymbol("x", INT), VarSymbol("y", INT)
    ]))
    scope.define_func(FuncSymbol("blur", IMAGE, [VarSymbol("img", IMAGE), VarSymbol("radius", FLOAT)]))
    scope.define_func(FuncSymbol("avg", FLOAT, [VarSymbol("img", IMAGE)]))


class SemanticAnalyzer(ImageLangVisitor):
    def __init__(self, token_stream: CommonTokenStream):
        super().__init__()
        self.tokens = token_stream
        self.errors = []
        self.global_scope = Scope()
        self.current_scope = self.global_scope
        self.current_func: FuncSymbol | None = None

    def analyze(self, tree):
        seed_builtins(self.global_scope)
        self.current_scope = self.global_scope
        self.visit(tree)
        return self.errors

    def push_scope(self): self.current_scope = Scope(self.current_scope)
    def pop_scope(self): self.current_scope = self.current_scope.parent

    def type_from_ctx(self, ctx: ImageLangParser.TypeContext) -> Type:
        if ctx.getToken(ImageLangParser.IMAGE_KW, 0): return IMAGE
        if ctx.getToken(ImageLangParser.PIXEL_KW, 0): return PIXEL
        if ctx.getToken(ImageLangParser.COLOR_KW, 0): return COLOR
        if ctx.getToken(ImageLangParser.INT_KW, 0): return INT
        if ctx.getToken(ImageLangParser.FLOAT_KW, 0): return FLOAT
        if ctx.getToken(ImageLangParser.BOOL_KW, 0): return BOOL
        if ctx.getToken(ImageLangParser.STRING_KW, 0): return STRING
        if ctx.getToken(ImageLangParser.NULL_KW, 0): return NULL
        if ctx.getToken(ImageLangParser.VECTOR_KW, 0):
            inner_ctx = ctx.type_()
            if inner_ctx:
                inner = self.type_from_ctx(inner_ctx)
                return Type("vector", param=inner)
            else:
                return Type("vector", param=None)
        return Type("unknown")

    def visitProgram(self, ctx: ImageLangParser.ProgramContext):
        for td in ctx.top_decl():
            self.visit(td)
        self.visit(ctx.main_block())
        return None

    def visitMain_block(self, ctx: ImageLangParser.Main_blockContext):
        self.visit(ctx.block())
        return None

    def visitBlock(self, ctx: ImageLangParser.BlockContext):
        self.push_scope()
        for s in ctx.stmt():
            self.visit(s)
        self.pop_scope()
        return None
    
    def visitFunc_decl(self, ctx: ImageLangParser.Func_declContext):
        ret_t = self.type_from_ctx(ctx.type_())
        name = ctx.ID().getText()
        tok = ctx.ID().getSymbol()

        params = []
        if ctx.param_list():
            for p in ctx.param_list().param():
                t = self.type_from_ctx(p.type_())
                by_ref = p.getToken(ImageLangParser.AMP, 0) is not None
                pname = p.ID().getText()
                params.append(VarSymbol(pname, t, by_ref))

        fn = FuncSymbol(name, ret_t, params)
        if not self.global_scope.define_func(fn):
            self.errors.append(make_error(tok, f"Function '{name}' already defined"))

        self.current_func = fn
        self.push_scope()
        for p in params:
            self.current_scope.define_var(p)

        self.visit(ctx.block())
        self.pop_scope()
        self.current_func = None
        return None

    def visitStmt(self, ctx: ImageLangParser.StmtContext):
        for child in ctx.getChildren():
            self.visit(child)
        return None

    def visitVar_decl(self, ctx: ImageLangParser.Var_declContext):
        t = self.type_from_ctx(ctx.type_())
        name_tok = ctx.ID().getSymbol()
        name = ctx.ID().getText()

        sym = VarSymbol(name, t)
        if not self.current_scope.define_var(sym):
            self.errors.append(make_error(name_tok, f"Variable '{name}' already declared"))

        if ctx.expression():
            rhs_t = self.visit(ctx.expression())
            if rhs_t and not can_assign(t, rhs_t):
                self.errors.append(make_error(name_tok, f"Incompatible assignment: {rhs_t} → {t}"))
        return t

    def visitAssignment(self, ctx: ImageLangParser.AssignmentContext):
        lhs_t, lhs_tok, lhs_is_lvalue = self.resolve_lvalue(ctx.lvalue())
        if lhs_t is None:
            return None
        rhs_t = self.visit(ctx.expression())
        if rhs_t is None:
            return None
        if not can_assign(lhs_t, rhs_t):
            tok_node = ctx.getToken(ImageLangParser.ASSIGN, 0)
            tok = tok_node.symbol if tok_node else lhs_tok
            self.errors.append(make_error(tok, f"Incompatible assignment: {rhs_t} → {lhs_t}"))
        return lhs_t

    def visitExpr_stmt(self, ctx: ImageLangParser.Expr_stmtContext):
        self.visit(ctx.expression())
        return None

    def resolve_lvalue(self, ctx: ImageLangParser.LvalueContext):
        if ctx.ID() and ctx.getToken(ImageLangParser.DOT, 0) is None and ctx.getToken(ImageLangParser.LBRACK, 0) is None:
            name = ctx.ID().getText()
            tok = ctx.ID().getSymbol()
            sym = self.current_scope.resolve_var(name)
            if not sym:
                self.errors.append(make_error(tok, f"Undeclared variable '{name}'"))
                return None, tok, False
            return sym.type, tok, True

        base_t, tok, _ = self.resolve_lvalue(ctx.lvalue())
        if base_t is None:
            return None, tok, False

        if ctx.getToken(ImageLangParser.DOT, 0):
            field = ctx.ID().getText()
            dot_tok = ctx.getToken(ImageLangParser.DOT, 0).symbol
            if base_t.equals(COLOR) or base_t.equals(PIXEL):
                if field in ("r", "g", "b"):
                    return FLOAT, dot_tok, True
                self.errors.append(make_error(dot_tok, f"Unknown field '{field}' on type {base_t}"))
                return None, tok, False
            self.errors.append(make_error(dot_tok, f"Field access '{field}' not supported on type {base_t}"))
            return None, tok, False

        if ctx.getToken(ImageLangParser.LBRACK, 0):
            lbr_tok = ctx.getToken(ImageLangParser.LBRACK, 0).symbol
            exprs = ctx.expression()
            idx_ctx = exprs[0] if isinstance(exprs, list) else exprs
            idx_t = self.visit(idx_ctx) if idx_ctx is not None else None
            if idx_t is None:
                return None, tok, False
            if not idx_t.equals(INT):
                self.errors.append(make_error(lbr_tok, f"Index must be int, got {idx_t}"))
                return None, tok, False
            if base_t.name == "vector" and base_t.param:
                return base_t.param, tok, True
            self.errors.append(make_error(lbr_tok, f"Type {base_t} is not indexable"))
            return None, tok, False

        return None, tok, False


    def visitIf_stmt(self, ctx: ImageLangParser.If_stmtContext):
        t = self.visit(ctx.expression())
        if t and not t.is_bool():
            tok_node = ctx.getToken(ImageLangParser.IF, 0)
            tok = tok_node.symbol if tok_node else ctx.start
            self.errors.append(make_error(tok, f"Condition must be bool, got {t}"))
        self.visit(ctx.block(0))
        if ctx.getToken(ImageLangParser.ELSE, 0):
            self.visit(ctx.block(1))
        return None

    def visitWhile_stmt(self, ctx: ImageLangParser.While_stmtContext):
        t = self.visit(ctx.expression())
        if t and not t.is_bool():
            tok_node = ctx.getToken(ImageLangParser.WHILE, 0)
            tok = tok_node.symbol if tok_node else ctx.start
            self.errors.append(make_error(tok, f"Condition must be bool, got {t}"))
        self.visit(ctx.block())
        return None

    def visitUntil_stmt(self, ctx: ImageLangParser.Until_stmtContext):
        t = self.visit(ctx.expression())
        if t and not t.is_bool():
            tok_node = ctx.getToken(ImageLangParser.UNTIL, 0)
            tok = tok_node.symbol if tok_node else ctx.start
            self.errors.append(make_error(tok, f"Condition must be bool, got {t}"))
        self.visit(ctx.block())
        return None

    def visitFor_stmt(self, ctx: ImageLangParser.For_stmtContext):
        hdr = ctx.for_header()
        self.push_scope()
        self.visit(hdr.var_decl())
        t = self.visit(hdr.expression())
        if t and not t.is_bool():
            semi_tok_node = hdr.getToken(ImageLangParser.SEMI, 0)
            semi_tok = semi_tok_node.symbol if semi_tok_node else hdr.start
            self.errors.append(make_error(semi_tok, f"For condition must be bool, got {t}"))
        self.visit(hdr.assignment())
        self.visit(ctx.block())
        self.pop_scope()
        return None

    def visitReturn_stmt(self, ctx: ImageLangParser.Return_stmtContext):
        tok_node = ctx.getToken(ImageLangParser.RETURN, 0)
        tok = tok_node.symbol if tok_node else ctx.start
        if self.current_func is None:
            self.errors.append(make_error(tok, "Return statement outside of function"))
            return None

        ret_expected = self.current_func.ret_type
        if ctx.expression():
            ret_actual = self.visit(ctx.expression())
            if ret_actual and not can_assign(ret_expected, ret_actual):
                self.errors.append(make_error(tok, f"Return type mismatch: {ret_actual} → {ret_expected}"))
        else:
            if not ret_expected.is_null():
                self.errors.append(make_error(tok, f"Missing return value for function returning {ret_expected}"))
        return None

    def visitIo_stmt(self, ctx: ImageLangParser.Io_stmtContext):
        name = ctx.ID().getText()
        tok = ctx.ID().getSymbol()
        fn = self.current_scope.resolve_func(name)
        arg_types = []
        arg_lvals = []

        if ctx.type_():
            t = self.type_from_ctx(ctx.type_())
            arg_types.append(t)
            arg_lvals.append(False)
        else:
            t = self.visit(ctx.expression())
            arg_types.append(t)
            arg_lvals.append(False)

        if fn is None:
            if name != "read":
                self.errors.append(make_error(tok, f"Unknown IO operation or function '{name}'"))
        else:
            self.check_call(tok, fn, arg_types, arg_lvals)
        return None
    
    def visitTry_stmt(self, ctx: ImageLangParser.Try_stmtContext):
        self.visit(ctx.block())

        if not ctx.except_clause() and not ctx.default_clause():
            tok = ctx.getToken(ImageLangParser.TRY, 0).symbol
            self.errors.append(make_error(tok, "Try block must have at least one except"))

        for exc in ctx.except_clause():
            self.visit(exc)

        if ctx.default_clause():
            self.visit(ctx.default_clause())

        return None


    def visitExcept_clause(self, ctx: ImageLangParser.Except_clauseContext):
        exc_type_str = ctx.exception_type().getText()
        
        allowed = {"Exception", "ValueError", "IOError", "TypeError", "IndexError"}
        if exc_type_str not in allowed:
            tok = ctx.exception_type().start
            self.errors.append(make_error(tok, f"Unknown exception type '{exc_type_str}'"))

        self.push_scope()

        if ctx.ID():
            var_name = ctx.ID().getText()
            var_tok = ctx.ID().getSymbol()
            
            sym = VarSymbol(var_name, STRING)
            
            if not self.current_scope.define_var(sym):
                self.errors.append(make_error(var_tok, f"Variable '{var_name}' already declared in this scope"))

        self.visit(ctx.block())

        self.pop_scope()
        
        return None


    def visitDefault_clause(self, ctx: ImageLangParser.Default_clauseContext):
        self.visit(ctx.block())
        return None


    def visitThrow_stmt(self, ctx: ImageLangParser.Throw_stmtContext):
        tok = ctx.getToken(ImageLangParser.THROW, 0).symbol
        exc_type = ctx.exception_type().getText()
        
        allowed = {"Exception", "ValueError", "IOError", "TypeError", "IndexError"}
        if exc_type not in allowed:
            self.errors.append(make_error(tok, f"Unknown exception type '{exc_type}'"))
        
        if ctx.expression():
            msg_type = self.visit(ctx.expression())
            
            if msg_type is None:
                return None
                
            if not msg_type.equals(STRING):
                expr_start = ctx.expression().start
                self.errors.append(make_error(expr_start, f"Exception message must be string, got {msg_type}"))
        
        return None


    def visitException_type(self, ctx: ImageLangParser.Exception_typeContext):
        exc_type = ctx.getText()
        allowed = {"Exception", "ValueError", "IOError", "TypeError", "IndexError"}
        if exc_type not in allowed:
            tok = ctx.start
            self.errors.append(make_error(tok, f"Unknown exception type '{exc_type}'"))
        return None


    def _is_lvalue_expr(self, e) -> bool:
        try:
            start = e.start
            stop = e.stop
            if start == stop and start.type == ImageLangParser.ID:
                return True
        except Exception:
            pass
        return False


    def visitFunc_call(self, ctx: ImageLangParser.Func_callContext):
        name = ctx.ID().getText()
        tok = ctx.ID().getSymbol()
        fn = self.current_scope.resolve_func(name)
        arg_types = []
        arg_lvals = []

        if ctx.arg_list():
            for e in ctx.arg_list().expression():
                t = self.visit(e)
                is_lv = self._is_lvalue_expr(e)
                if is_lv:
                    var_name = e.start.text
                    if self.current_scope.resolve_var(var_name) is None:
                        is_lv = False
                arg_types.append(t)
                arg_lvals.append(is_lv)

        if fn is None:
            self.errors.append(make_error(tok, f"Call to undeclared function '{name}'"))
            return None

        self.check_call(tok, fn, arg_types, arg_lvals)
        return fn.ret_type

    def check_call(self, tok, fn: FuncSymbol, arg_types, arg_lvalue_flags):
        if len(arg_types) != len(fn.params):
            self.errors.append(make_error(tok, f"Argument count mismatch: expected {len(fn.params)}, got {len(arg_types)}"))
            return
        for i, (arg_t, param) in enumerate(zip(arg_types, fn.params)):
            if arg_t is None: continue
            if not can_assign(param.type, arg_t):
                self.errors.append(make_error(tok, f"Argument {i+1} type mismatch: {arg_t} → {param.type}"))
            if param.by_ref and not arg_lvalue_flags[i]:
                self.errors.append(make_error(tok, f"Argument {i+1} must be an lvalue for by-ref parameter '{param.name}'"))

    def visitUnaryExpr(self, ctx: ImageLangParser.UnaryExprContext):
        minus_tok_node = ctx.getToken(ImageLangParser.MINUS, 0)
        if minus_tok_node:
            minus_tok = minus_tok_node.symbol
            children = [c for c in ctx.getChildren() if isinstance(c, ParserRuleContext)]
            t = self.visit(children[0]) if children else None
            if t is None:
                return None
            if not t.is_numeric():
                self.errors.append(make_error(minus_tok, f"Unary minus requires numeric, got {t}"))
                return None
            return t

        children = [c for c in ctx.getChildren() if isinstance(c, ParserRuleContext)]
        if children:
            return self.visit(children[0])

        return None

    def visitCast_expr(self, ctx: ImageLangParser.Cast_exprContext):
        target_t = self.type_from_ctx(ctx.type_())
        _ = self.visit(ctx.unary_expr())
        return target_t

    def visitPostfix_expr(self, ctx: ImageLangParser.Postfix_exprContext):
        if ctx.primary_base():
            return self.visit(ctx.primary_base())

        base_t = self.visit(ctx.postfix_expr())
        if base_t is None:
            return None

        if ctx.getToken(ImageLangParser.DOT, 0) and ctx.ID():
            field = ctx.ID().getText()
            dot_tok = ctx.getToken(ImageLangParser.DOT, 0).symbol
            if base_t.equals(COLOR) or base_t.equals(PIXEL):
                if field in ("r", "g", "b"):
                    return FLOAT
                self.errors.append(make_error(dot_tok, f"Unknown field '{field}' on type {base_t}"))
                return None
            self.errors.append(make_error(dot_tok, f"Unknown field '{field}' on type {base_t}"))
            return None

        if ctx.getToken(ImageLangParser.LBRACK, 0):
            lbr_tok = ctx.getToken(ImageLangParser.LBRACK, 0).symbol
            idx_t = self.visit(ctx.expression(0))
            if idx_t is None:
                return None
            if not idx_t.equals(INT):
                self.errors.append(make_error(lbr_tok, f"Index must be int, got {idx_t}"))
                return None
            if base_t.name == "vector" and base_t.param:
                return base_t.param
            self.errors.append(make_error(lbr_tok, f"Type {base_t} is not indexable"))
            return None

        if ctx.getToken(ImageLangParser.DOT, 0) and ctx.getToken(ImageLangParser.PIXEL_KW, 0):
            dot_tok = ctx.getToken(ImageLangParser.DOT, 0).symbol
            px_tok = ctx.getToken(ImageLangParser.PIXEL_KW, 0).symbol
            x_t = self.visit(ctx.expression(0))
            y_t = self.visit(ctx.expression(1))
            if not base_t.equals(IMAGE):
                self.errors.append(make_error(dot_tok, f"'pixel' can be called on image, got {base_t}"))
                return None
            if not (x_t and x_t.equals(INT)) or not (y_t and y_t.equals(INT)):
                self.errors.append(make_error(px_tok, "pixel(x,y) expects int, int"))
                return None
            return PIXEL

        return None

    def visitPrimary_base(self, ctx: ImageLangParser.Primary_baseContext):
        if ctx.getToken(ImageLangParser.INT_LITERAL, 0): return INT
        if ctx.getToken(ImageLangParser.FLOAT_LITERAL, 0): return FLOAT
        if ctx.getToken(ImageLangParser.STRING_LITERAL, 0): return STRING
        if ctx.getToken(ImageLangParser.NULL_KW, 0): return NULL
        if ctx.getToken(ImageLangParser.BOOL_LITERAL, 0): return BOOL
        if ctx.ID():
            name = ctx.ID().getText()
            tok = ctx.ID().getSymbol()
            sym = self.current_scope.resolve_var(name)
            if sym is None:
                self.errors.append(make_error(tok, f"Undeclared identifier '{name}'"))
                return None
            return sym.type
        if ctx.getToken(ImageLangParser.LPAREN, 0):
            return self.visit(ctx.expression())
        if ctx.func_call():
            return self.visit(ctx.func_call())
        if ctx.read_type_call():
            t = self.type_from_ctx(ctx.read_type_call().type_())
            return t
        return None

    def visitAddExpr(self, ctx):
        t1 = self.visit(ctx.expression(0))
        t2 = self.visit(ctx.expression(1))
        if not t1 or not t2: return None
        if t1.equals(STRING) and t2.equals(STRING):
            return STRING
        res = binary_numeric_result(t1, t2)
        if res: return res
        tok_node = ctx.getToken(ImageLangParser.PLUS, 0)
        if tok_node:
            self.errors.append(make_error(tok_node.symbol, f"Operator '+' not defined for {t1}, {t2}"))
        return None

    def visitSubExpr(self, ctx):
        t1 = self.visit(ctx.expression(0))
        t2 = self.visit(ctx.expression(1))
        if not t1 or not t2: return None
        if t1.equals(IMAGE) and t2.equals(IMAGE):
            return IMAGE
        res = binary_numeric_result(t1, t2)
        if res: return res
        tok_node = ctx.getToken(ImageLangParser.MINUS, 0)
        if tok_node:
            self.errors.append(make_error(tok_node.symbol, f"Operator '-' not defined for {t1}, {t2}"))
        return None

    def visitMulExpr(self, ctx):
        t1 = self.visit(ctx.expression(0))
        t2 = self.visit(ctx.expression(1))
        if not t1 or not t2: return None
        if (t1.equals(IMAGE) and t2.equals(FLOAT)) or (t1.equals(FLOAT) and t2.equals(IMAGE)):
            return IMAGE
        res = binary_numeric_result(t1, t2)
        if res: return res
        tok_node = ctx.getToken(ImageLangParser.MULT, 0)
        if tok_node:
            self.errors.append(make_error(tok_node.symbol, f"Operator '*' not defined for {t1}, {t2}"))
        return None

    def visitDivExpr(self, ctx):
        t1 = self.visit(ctx.expression(0))
        t2 = self.visit(ctx.expression(1))
        if not t1 or not t2: return None
        res = binary_numeric_result(t1, t2)
        if res: return res
        tok_node = ctx.getToken(ImageLangParser.DIV, 0)
        if tok_node:
            self.errors.append(make_error(tok_node.symbol, f"Operator '/' not defined for {t1}, {t2}"))
        return None

    def visitModExpr(self, ctx):
        t1 = self.visit(ctx.expression(0))
        t2 = self.visit(ctx.expression(1))
        if not t1 or not t2: return None
        if t1.is_numeric() and t2.is_numeric():
            return FLOAT if FLOAT in (t1, t2) else INT
        tok_node = ctx.getToken(ImageLangParser.MOD, 0)
        if tok_node:
            self.errors.append(make_error(tok_node.symbol, f"Operator '%' requires numeric operands, got {t1}, {t2}"))
        return None

    def visitAndExpr(self, ctx):
        t1 = self.visit(ctx.expression(0))
        t2 = self.visit(ctx.expression(1))
        if not t1 or not t2: return None
        if not (t1.is_bool() and t2.is_bool()):
            tok_node = ctx.getToken(ImageLangParser.AND, 0)
            if tok_node:
                self.errors.append(make_error(tok_node.symbol, f"'and' requires bool operands, got {t1}, {t2}"))
            return None
        return BOOL

    def visitOrExpr(self, ctx):
        t1 = self.visit(ctx.expression(0))
        t2 = self.visit(ctx.expression(1))
        if not t1 or not t2: return None
        if not (t1.is_bool() and t2.is_bool()):
            tok_node = ctx.getToken(ImageLangParser.OR, 0)
            if tok_node:
                self.errors.append(make_error(tok_node.symbol, f"'or' requires bool operands, got {t1}, {t2}"))
            return None
        return BOOL

    def visitNotExpr(self, ctx):
        t = self.visit(ctx.expression())
        if not t or not t.is_bool():
            tok_node = ctx.getToken(ImageLangParser.NOT, 0)
            if tok_node:
                self.errors.append(make_error(tok_node.symbol, f"'not' requires bool operand, got {t}"))
            return None
        return BOOL

    def visitEqExpr(self, ctx):
        return self._eqneq(ctx, ImageLangParser.EQ, "==")

    def visitNeqExpr(self, ctx):
        return self._eqneq(ctx, ImageLangParser.NEQ, "!=")

    def _eqneq(self, ctx, token_type, op):
        t1 = self.visit(ctx.expression(0))
        t2 = self.visit(ctx.expression(1))
        if not t1 or not t2: return None
        if t1.equals(t2) or t1.is_null() or t2.is_null():
            return BOOL
        tok_node = ctx.getToken(token_type, 0)
        if tok_node:
            self.errors.append(make_error(tok_node.symbol, f"Equality '{op}' requires compatible types, got {t1}, {t2}"))
        return None

    def visitLtExpr(self, ctx): return self._order(ctx, ImageLangParser.LT_SYM, "<")
    def visitGtExpr(self, ctx): return self._order(ctx, ImageLangParser.GT_SYM, ">")
    def visitLeExpr(self, ctx): return self._order(ctx, ImageLangParser.LE_SYM, "<=")
    def visitGeExpr(self, ctx): return self._order(ctx, ImageLangParser.GE_SYM, ">=")

    def _order(self, ctx, token_type, op):
        t1 = self.visit(ctx.expression(0))
        t2 = self.visit(ctx.expression(1))
        if not t1 or not t2: return None
        if t1.is_numeric() and t2.is_numeric():
            return BOOL
        tok_node = ctx.getToken(token_type, 0)
        if tok_node:
            self.errors.append(make_error(tok_node.symbol, f"Comparison '{op}' requires numeric operands, got {t1}, {t2}"))
        return None
