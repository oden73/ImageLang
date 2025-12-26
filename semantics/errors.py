def make_error(token, message: str):
    text = getattr(token, "text", None)
    return {
        "line": token.line,
        "column": token.column,
        "token": text,
        "message": message
    }
