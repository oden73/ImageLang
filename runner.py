import sys, argparse, json
from antlr4 import *
from antlr4.error.ErrorListener import ErrorListener
from antlr4.tree.Trees import Trees

from ImageLangLexer import ImageLangLexer
from ImageLangParser import ImageLangParser

from semantics.analyzer import SemanticAnalyzer
from compiler import Compiler  # <-- Импортируем наш компилятор

class CollectingErrorListener(ErrorListener):
    def __init__(self):
        super().__init__()
        self.errors = []

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        token_text = getattr(offendingSymbol, "text", None)
        self.errors.append({
            "line": line,
            "column": column,
            "token": token_text,
            "message": msg
        })

def parse_text(text: str):
    input_stream = InputStream(text)
    lexer = ImageLangLexer(input_stream)
    lexer_errors = CollectingErrorListener()
    lexer.removeErrorListeners()
    lexer.addErrorListener(lexer_errors)
    token_stream = CommonTokenStream(lexer)

    parser = ImageLangParser(token_stream)
    parser_errors = CollectingErrorListener()
    parser.removeErrorListeners()
    parser.addErrorListener(parser_errors)

    tree = parser.program()
    return tree, parser, lexer_errors.errors, parser_errors.errors, token_stream

def format_error(err, source_lines):
    line = source_lines[err["line"] - 1]
    pointer = " " * err["column"] + "^"
    return (
        f"[line {err['line']}, col {err['column']}] "
        f"Unexpected token '{err['token']}' → {err['message']}\n"
        f"    {line.rstrip()}\n"
        f"    {pointer}"
    )

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", help="Source file (.img)")
    ap.add_argument("--output", help="Output IL file", default="program.il")
    args = ap.parse_args()

    try:
        source_lines = open(args.file, encoding="utf-8").read().splitlines()
    except FileNotFoundError:
        print(f"File not found: {args.file}")
        return

    # 1. Parsing
    tree, parser, lex_errs, parse_errs, tokens = parse_text("\n".join(source_lines))
    all_errs = lex_errs + parse_errs

    if all_errs:
        print("Syntax Errors:")
        for e in all_errs:
            print(format_error(e, source_lines))
        return

    # 2. Semantic Analysis
    analyzer = SemanticAnalyzer(tokens)
    sem_errors = analyzer.analyze(tree)
    
    if analyzer.errors:
        print("Semantic Errors:")
        for e in analyzer.errors:
            print(format_error(e, source_lines))
        return

    print("Verification OK. Compiling...")

    # 3. Compilation
    compiler = Compiler()
    compiler.visit(tree)
    
    with open(args.output, "w") as f:
        f.write(compiler.get_il())
    
    print(f"Compilation successful! Output written to {args.output}")
    print("Next step: Run 'ilasm program.il' to generate executable.")

if __name__ == "__main__":
    main()