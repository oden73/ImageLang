import sys
from ImageLangVisitor import ImageLangVisitor
from ImageLangParser import ImageLangParser

class Compiler(ImageLangVisitor):
    def __init__(self):
        self.il_code = []
        self.label_counter = 0
        self.locals_map = {}       
        self.locals_type_map = {}  
        self.next_local_index = 0
        self.in_main = False
        
        self.type_mapping = {
            "int": "int32", "float": "float64", "bool": "bool", "string": "string", "void": "void",
            "image": "class [ImageLangRuntime]ImageLangRuntime.ImageWrapper",
            "pixel": "valuetype [ImageLangRuntime]ImageLangRuntime.LangColor",
            "color": "valuetype [ImageLangRuntime]ImageLangRuntime.LangColor"
        }

    def get_il(self): return "\n".join(self.il_code)
    
    def emit(self, instr): self.il_code.append(f"    {instr}")
    
    def emit_label(self, lbl): self.il_code.append(f"{lbl}:")
    
    def new_label(self):
        self.label_counter += 1
        return f"L_{self.label_counter}"
    
    def map_type(self, t): return self.type_mapping.get(t, "object")

    def reset_scope(self):
        self.locals_map = {}
        self.locals_type_map = {}
        self.next_local_index = 0
    
    def register_local(self, name, lang_type):
        if name not in self.locals_map:
            self.locals_map[name] = self.next_local_index
            self.locals_type_map[name] = self.map_type(lang_type)
            self.next_local_index += 1

    def scan_locals(self, ctx):
        if ctx is None: return
        if isinstance(ctx, ImageLangParser.Var_declContext):
            self.register_local(ctx.ID().getText(), ctx.type_().getText())
        if isinstance(ctx, ImageLangParser.Func_declContext):
            if ctx.param_list():
                for p in ctx.param_list().param():
                    self.register_local(p.ID().getText(), p.type_().getText())
        if isinstance(ctx, ImageLangParser.For_stmtContext):
            self.scan_locals(ctx.for_header())
        if isinstance(ctx, ImageLangParser.Except_clauseContext) and ctx.ID():
            self.register_local(ctx.ID().getText(), "string")
        if hasattr(ctx, "getChildren"):
            for child in ctx.getChildren(): self.scan_locals(child)

    def emit_locals_init(self):
        if not self.locals_map: return
        decls = [f"[{idx}] {self.locals_type_map[name]} {name}" for name, idx in sorted(self.locals_map.items(), key=lambda x: x[1])]
        self.emit(f".locals init ({', '.join(decls)})")

    
    def emit_unbox(self, t):
        if t == "int32": self.emit("unbox.any [mscorlib]System.Int32")
        elif t == "float64": self.emit("unbox.any [mscorlib]System.Double")
        elif t == "bool": self.emit("unbox.any [mscorlib]System.Boolean")
        elif t == "string": self.emit("castclass [mscorlib]System.String")
        elif t.startswith("class"): self.emit(f"castclass {t.split(' ')[1]}")
        elif "valuetype" in t: self.emit(f"unbox.any {t.replace('valuetype ', '')}")

    def emit_box_if_needed(self, t):
        if t == "int32": self.emit("box [mscorlib]System.Int32")
        elif t == "float64": self.emit("box [mscorlib]System.Double")
        elif t == "bool": self.emit("box [mscorlib]System.Boolean")
        elif "valuetype" in t: self.emit(f"box {t.replace('valuetype ', '')}")

    
    def visitProgram(self, ctx):
        self.il_code = [
            ".assembly extern mscorlib {}", ".assembly extern System.Drawing {}",
            ".assembly extern ImageLangRuntime {}", ".assembly ImageLangProgram {}",
            ".module program.exe", ".class public auto ansi Program extends [mscorlib]System.Object {"
        ]
        for td in ctx.top_decl(): self.visit(td)
        self.il_code.append(".method static void Main() cil managed { .entrypoint")
        self.in_main = True
        self.reset_scope()
        self.scan_locals(ctx.main_block())
        self.emit_locals_init()
        self.visit(ctx.main_block())
        self.in_main = False
        self.emit("ret")
        self.il_code.append("} }")

    def visitMain_block(self, ctx): self.visit(ctx.block())

    def visitBlock(self, ctx): 
        for s in ctx.stmt(): self.visit(s)

    def visitFunc_decl(self, ctx):
        name = ctx.ID().getText()
        self.reset_scope()
        self.scan_locals(ctx)
        
        params_info = []
        if ctx.param_list():
            for p in ctx.param_list().param():
                is_ref = p.getToken(ImageLangParser.AMP, 0) is not None
                params_info.append((p.ID().getText(), is_ref))
        
        sig_parts = []
        for _, is_ref in params_info:
            sig_parts.append("object&" if is_ref else "object")
        sig = ", ".join(sig_parts)
        
        self.il_code.append(f".method public static object {name}({sig}) cil managed {{")
        self.emit_locals_init()

        for i, (p_name, is_ref) in enumerate(params_info):
            t = self.locals_type_map[p_name]
            self.emit(f"ldarg {i}")
            if is_ref:
                self.emit("ldind.ref")
            
            self.emit_unbox(t)
            self.emit(f"stloc {self.locals_map[p_name]}")

        self.visit(ctx.block())

        for i, (p_name, is_ref) in enumerate(params_info):
            if is_ref:
                t = self.locals_type_map[p_name]
                self.emit(f"ldarg {i}")
                self.emit(f"ldloc {self.locals_map[p_name]}")
                self.emit_box_if_needed(t)
                self.emit("stind.ref")

        self.emit("ldnull")
        self.emit("ret")
        self.il_code.append("}")
    
    def visitVar_decl(self, ctx):
        if ctx.expression():
            self.visit(ctx.expression())
            name = ctx.ID().getText()
            t = self.locals_type_map[name]
            self.emit_unbox(t)
            self.emit(f"stloc {self.locals_map[name]}")

    def visitAssignment(self, ctx):
        lvalue = ctx.lvalue()
        if lvalue.ID() and not lvalue.DOT():
            name = lvalue.ID().getText()
            self.visit(ctx.expression())
            self.emit_unbox(self.locals_type_map[name])
            self.emit(f"stloc {self.locals_map[name]}")

    def visitReturn_stmt(self, ctx):
        if self.in_main: self.emit("ret")
        else:
            if ctx.expression(): self.visit(ctx.expression())
            else: self.emit("ldnull")
            self.emit("ret")

    def visitExpr_stmt(self, ctx):
        self.visit(ctx.expression())
        txt = ctx.getText()
        if not (txt.startswith("write") or txt.startswith("save")):
            self.emit("pop")

    def visitIf_stmt(self, ctx):
        l1, l2 = self.new_label(), self.new_label()
        self.visit(ctx.expression())
        self.emit_unbox("bool")
        self.emit(f"brfalse {l1}")
        self.visit(ctx.block(0))
        self.emit(f"br {l2}")
        self.emit_label(l1)
        if ctx.ELSE(): self.visit(ctx.block(1))
        self.emit_label(l2)
        
    def visitWhile_stmt(self, ctx):
        s, e = self.new_label(), self.new_label()
        self.emit_label(s)
        self.visit(ctx.expression())
        self.emit_unbox("bool")
        self.emit(f"brfalse {e}")
        self.visit(ctx.block())
        self.emit(f"br {s}")
        self.emit_label(e)

    def visitUntil_stmt(self, ctx):
        s, e = self.new_label(), self.new_label()
        self.emit_label(s)
        self.visit(ctx.expression())
        self.emit_unbox("bool")
        self.emit(f"brtrue {e}")
        self.visit(ctx.block())
        self.emit(f"br {s}")
        self.emit_label(e)
        
    def visitFor_stmt(self, ctx):
        hdr = ctx.for_header()
        start, end = self.new_label(), self.new_label()
        
        if hdr.var_decl(): 
            self.visit(hdr.var_decl())
        
        self.emit_label(start)
                
        if hdr.expression():
            self.visit(hdr.expression())
            self.emit_unbox("bool")
            self.emit(f"brfalse {end}")
            
        self.visit(ctx.block())
        
        if hdr.assignment(): 
            self.visit(hdr.assignment())
             
        self.emit(f"br {start}")
        self.emit_label(end)

    def emit_op(self, ctx, name):
        self.visit(ctx.expression(0))
        self.visit(ctx.expression(1))
        self.emit(f"call object [ImageLangRuntime]ImageLangRuntime.Ops::{name}(object, object)")

    def visitAddExpr(self, ctx): self.emit_op(ctx, "Add")
    def visitSubExpr(self, ctx): self.emit_op(ctx, "Sub")
    def visitMulExpr(self, ctx): self.emit_op(ctx, "Mul")
    def visitDivExpr(self, ctx): self.emit_op(ctx, "Div")
    def visitEqExpr(self, ctx): self.emit_op(ctx, "Eq")
    def visitLtExpr(self, ctx): self.emit_op(ctx, "Lt")
    def visitGtExpr(self, ctx): self.emit_op(ctx, "Gt")    
    
    def visitUnary_expr(self, ctx):
        if ctx.getToken(ImageLangParser.MINUS, 0):
            self.visit(ctx.unary_expr()) 
            self.emit("call object [ImageLangRuntime]ImageLangRuntime.Ops::Neg(object)")
        elif ctx.cast_expr(): 
            self.visit(ctx.cast_expr())
        else: 
            self.visit(ctx.getChild(0))
        
    def visitCast_expr(self, ctx):
        self.visit(ctx.unary_expr())
        t = ctx.type_().getText()
        if t == "string": self.emit("callvirt instance string [mscorlib]System.Object::ToString()")
        elif t == "float": 
             self.emit("call float64 [mscorlib]System.Convert::ToDouble(object)")
             self.emit("box [mscorlib]System.Double")
        elif t == "int":
             self.emit("call int32 [mscorlib]System.Convert::ToInt32(object)")
             self.emit("box [mscorlib]System.Int32")

    def visitPostfix_expr(self, ctx):
        if ctx.primary_base(): self.visit(ctx.primary_base())
        elif ctx.DOT():
            self.visit(ctx.postfix_expr())
            f = ctx.ID().getText()
            self.emit("unbox [ImageLangRuntime]ImageLangRuntime.LangColor")
            self.emit(f"ldfld int32 [ImageLangRuntime]ImageLangRuntime.LangColor::{f}")
            self.emit_box_if_needed("int32")

    def visitPrimary_base(self, ctx):
        if ctx.INT_LITERAL(): 
            self.emit(f"ldc.i4 {ctx.getText()}")
            self.emit("box [mscorlib]System.Int32")
        elif ctx.FLOAT_LITERAL(): 
            self.emit(f"ldc.r8 {ctx.getText()}")
            self.emit("box [mscorlib]System.Double")
        elif ctx.STRING_LITERAL(): self.emit(f"ldstr {ctx.getText()}")
        elif ctx.BOOL_LITERAL(): 
            self.emit(f"ldc.i4 {1 if ctx.getText()=='true' else 0}")
            self.emit("box [mscorlib]System.Boolean")
        elif ctx.NULL_KW(): self.emit("ldnull")
        elif ctx.ID():
            name = ctx.ID().getText()
            if name in self.locals_map:
                self.emit(f"ldloc {self.locals_map[name]}")
                self.emit_box_if_needed(self.locals_type_map[name])
        elif ctx.func_call(): self.visit(ctx.func_call())
        elif ctx.expression(): self.visit(ctx.expression())
        elif ctx.read_type_call():
             self.emit("call string [ImageLangRuntime]ImageLangRuntime.StdLib::read_string()")

    def visitFunc_call(self, ctx):
        name = ctx.ID().getText()
        is_builtin = name in ["load", "save", "write", "pow_channels", "blur", "width", "height", "get_pixel", "avg", "read"]

        if ctx.arg_list():
            for e in ctx.arg_list().expression():
                if not is_builtin and e.getText() in self.locals_map:
                    self.emit(f"ldloca {self.locals_map[e.getText()]}")
                else:
                    self.visit(e)

        rt = "[ImageLangRuntime]ImageLangRuntime.Ops"
        if name == "load": self.emit(f"call object {rt}::Load(object)")
        elif name == "save": self.emit(f"call void {rt}::Save(object, object)")
        elif name == "write": self.emit(f"call void [ImageLangRuntime]ImageLangRuntime.StdLib::write(object)")
        elif name == "pow_channels": self.emit(f"call object {rt}::Pow(object, object)")
        elif name == "blur": self.emit(f"call object {rt}::Blur(object, object)")
        elif name == "width": self.emit(f"call object {rt}::Width(object)")
        elif name == "height": self.emit(f"call object {rt}::Height(object)")
        elif name == "get_pixel": self.emit(f"call object {rt}::GetPixel(object, object, object)")
        elif name == "avg": self.emit(f"call float64 {rt}::Avg(object)"); self.emit("box [mscorlib]System.Double")
        elif name == "read": 
            if ctx.arg_list(): self.emit("pop")
            self.emit(f"call string [ImageLangRuntime]ImageLangRuntime.StdLib::read_string()")
        else:
            cnt = len(ctx.arg_list().expression()) if ctx.arg_list() else 0
            self.emit(f"call object Program::{name}({', '.join(['object']*cnt)})")

    def visitThrow_stmt(self, ctx):
        exc_name = ctx.exception_type().getText()
        cil_type = self.type_mapping.get(exc_name, "[mscorlib]System.Exception")    
        
        self.visit(ctx.expression())
        
        self.emit("castclass [mscorlib]System.String")
        
        self.emit(f"newobj instance void {cil_type}::.ctor(string)")
        self.emit("throw")

    def visitTry_stmt(self, ctx):
        end = self.new_label()
        self.emit(".try {")
        self.visit(ctx.block())
        self.emit(f"leave {end}")
        self.emit("}")
        
        for exc in ctx.except_clause():
            exc_name = exc.exception_type().getText()
            cil_type = self.type_mapping.get(exc_name, "[mscorlib]System.Exception")
            self.emit(f"catch {cil_type} {{")     
            if exc.ID():
                self.emit("callvirt instance string [mscorlib]System.Exception::get_Message()")
                var_name = exc.ID().getText()
                self.emit(f"stloc {self.locals_map[var_name]}")
            else:
                self.emit("pop") 
                
            self.visit(exc.block())
            self.emit(f"leave {end}")
            self.emit("}")
            
        if ctx.default_clause():
            self.emit("catch [mscorlib]System.Object { pop") 
            self.visit(ctx.default_clause().block())
            self.emit(f"leave {end}")
            self.emit("}")
            
        self.emit_label(end)

    def visitNeqExpr(self, ctx):
        self.emit_op(ctx, "Eq")       
        self.emit_unbox("bool")       
        self.emit("ldc.i4.0")         
        self.emit("ceq")              
        self.emit_box_if_needed("bool") 

    def visitLeExpr(self, ctx):
        self.emit_op(ctx, "Gt")
        self.emit_unbox("bool")
        self.emit("ldc.i4.0")
        self.emit("ceq")
        self.emit_box_if_needed("bool")

    def visitGeExpr(self, ctx):
        self.emit_op(ctx, "Lt")
        self.emit_unbox("bool")
        self.emit("ldc.i4.0")
        self.emit("ceq")
        self.emit_box_if_needed("bool")

    def visitAndExpr(self, ctx):
        self.visit(ctx.expression(0))
        self.emit_unbox("bool")
        self.visit(ctx.expression(1))
        self.emit_unbox("bool")
        self.emit("and")
        self.emit_box_if_needed("bool")

    def visitOrExpr(self, ctx):
        self.visit(ctx.expression(0))
        self.emit_unbox("bool")
        self.visit(ctx.expression(1))
        self.emit_unbox("bool")
        self.emit("or")
        self.emit_box_if_needed("bool")
        
    def visitNotExpr(self, ctx):
        self.visit(ctx.expression())
        self.emit_unbox("bool")
        self.emit("ldc.i4.0")
        self.emit("ceq")
        self.emit_box_if_needed("bool")