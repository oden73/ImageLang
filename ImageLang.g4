grammar ImageLang;

// -----------------------------
// Parser rules
// -----------------------------
program
    : top_decl* main_block EOF
    ;

top_decl
    : func_decl
    ;

func_decl
    : type ID LPAREN param_list? RPAREN block
    ;

param_list
    : param (COMMA param)*
    ;

param
    : type AMP? ID
    ;

main_block
    : block
    ;

block
    : LBRACE stmt* RBRACE
    ;

stmt
    : var_decl SEMI
    | assignment SEMI
    | expr_stmt SEMI
    | if_stmt
    | while_stmt
    | until_stmt
    | for_stmt
    | return_stmt SEMI
    | io_stmt SEMI
    | throw_stmt SEMI
    | try_stmt
    | block
    ;

var_decl
    : type ID (ASSIGN expression)?
    ;

assignment
    : lvalue ASSIGN expression
    ;

lvalue
    : ID
    | lvalue DOT ID
    | lvalue LBRACK expression RBRACK
    ;

expr_stmt
    : expression
    ;

if_stmt
    : IF expression THEN block (ELSE block)?
    ;

while_stmt
    : WHILE expression DO block
    ;

until_stmt
    : UNTIL expression DO block
    ;

for_stmt
    : FOR for_header DO block
    ;

for_header
    : var_decl SEMI expression SEMI assignment
    ;

return_stmt
    : RETURN expression?
    ;

io_stmt
    : ID LPAREN type RPAREN
    | ID LPAREN expression RPAREN
    ;
// -----------------------------
// Exception handling
// -----------------------------
try_stmt
    : TRY block except_clause+ (default_clause)?
    ;

except_clause
    : EXCEPT exception_type ID? block 
    ;

default_clause
    : EXCEPT block   
    ;

throw_stmt
    : THROW exception_type LPAREN expression RPAREN
    ;

exception_type
    : EXCEPTION_KW
    | VALUE_ERROR_KW
    | IO_ERROR_KW
    | TYPE_ERROR_KW
    | INDEX_ERROR_KW
    ;

type
    : IMAGE_KW
    | PIXEL_KW
    | COLOR_KW
    | INT_KW
    | FLOAT_KW
    | BOOL_KW
    | STRING_KW
    | NULL_KW
    | VECTOR_KW LT_SYM type GT_SYM
    ;

// -----------------------------
// Expressions with precedence
// -----------------------------
expression
    : expression OR expression          # orExpr
    | expression AND expression         # andExpr
    | NOT expression                    # notExpr
    | expression EQ expression          # eqExpr
    | expression NEQ expression         # neqExpr
    | expression LE_SYM expression      # leExpr
    | expression GE_SYM expression      # geExpr
    | expression LT_SYM expression      # ltExpr
    | expression GT_SYM expression      # gtExpr
    | expression PLUS expression        # addExpr
    | expression MINUS expression       # subExpr
    | expression MULT expression        # mulExpr
    | expression DIV expression         # divExpr
    | expression MOD expression         # modExpr
    | unary_expr                        # unaryExpr
    ;

unary_expr
    : MINUS unary_expr
    | cast_expr
    | postfix_expr
    ;

cast_expr
    : LPAREN type RPAREN unary_expr
    ;

postfix_expr
    : primary_base
    | postfix_expr DOT ID
    | postfix_expr LBRACK expression RBRACK
    | postfix_expr DOT PIXEL_KW LPAREN expression COMMA expression RPAREN
    ;

primary_base
    : INT_LITERAL
    | FLOAT_LITERAL
    | STRING_LITERAL
    | BOOL_LITERAL
    | NULL_KW
    | ID
    | LPAREN expression RPAREN
    | func_call
    | read_type_call
    | type LPAREN arg_list? RPAREN
    ;

func_call
    : ID LPAREN arg_list? RPAREN
    ;

read_type_call
    : ID LPAREN type RPAREN
    ;

arg_list
    : expression (COMMA expression)*
    ;

// -----------------------------
// Lexer rules (tokens)
// -----------------------------
IF      : 'if';
THEN    : 'then';
ELSE    : 'else';
FOR     : 'for';
DO      : 'do';
WHILE   : 'while';
UNTIL   : 'until';
RETURN  : 'return';
TRY     : 'try';
EXCEPT  : 'except';
THROW   : 'throw';

IMAGE_KW : 'image';
PIXEL_KW : 'pixel';
COLOR_KW : 'color';
INT_KW   : 'int';
FLOAT_KW : 'float';
BOOL_KW  : 'bool';
STRING_KW: 'string';
NULL_KW  : 'null';
VECTOR_KW: 'vector';

// Exception keywords
EXCEPTION_KW   : 'Exception';
VALUE_ERROR_KW : 'ValueError';
IO_ERROR_KW    : 'IOError';
TYPE_ERROR_KW  : 'TypeError';
INDEX_ERROR_KW : 'IndexError';

PLUS    : '+';
MINUS   : '-';
MULT    : '*';
DIV     : '/';
MOD     : '%';
ASSIGN  : '=';       
EQ      : '==';      
NEQ     : '!=';      

LE_SYM  : '<=';
GE_SYM  : '>=';
LT_SYM  : '<';
GT_SYM  : '>';

AND     : 'and';
OR      : 'or';
NOT     : 'not';

AMP     : '&';
DOT     : '.';
LPAREN  : '(';
RPAREN  : ')';
LBRACE  : '{';
RBRACE  : '}';
LBRACK  : '[';
RBRACK  : ']';
SEMI    : ';';
COMMA   : ',';
COLON   : ':';
ARROW   : '->';

BOOL_LITERAL : 'true' | 'false';

ID
    :   [a-zA-Z_] [a-zA-Z_0-9]*
    ;

STRING_LITERAL
    :   '"' (~["\\] | '\\' .)* '"'
    ;

FLOAT_LITERAL
    :   [0-9]+ '.' [0-9]+ ([eE] [+-]? [0-9]+)?
    ;

INT_LITERAL
    :   [0-9]+
    ;

WS
    :   [ \t\r\n]+ -> skip
    ;

LINE_COMMENT
    :   '//' ~[\r\n]* -> skip
    ;

BLOCK_COMMENT
    :   '/*' .*? '*/' -> skip
    ;

