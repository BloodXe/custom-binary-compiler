#Punto de entrada del compilador
import sys
from lexer import Lexer
from parser import Parser, ParseError
from ast_nodes import AstNode


def print_ast(node: AstNode, last: bool = True, prefix: str = '') -> None:
    """Imprime el AST con formato de árbol usando ramas.
    `last` - indica si este nodo es el último hijo de su padre
    `prefix` - prefijo acumulado de ramas del nivel anterior
    """
    connector    = '└── ' if last else '├── '
    child_prefix = prefix + ('    ' if last else '│   ')

    print(prefix + connector + repr(node))

    children = [c for c in node.children if isinstance(c, AstNode)]
    for i, child in enumerate(children):
        print_ast(child, last=(i == len(children) - 1), prefix=child_prefix)


def main():
    import argparse
    ap = argparse.ArgumentParser(description='Compilador Yeison')
    ap.add_argument('archivo', help='Archivo fuente .yeison')
    ap.add_argument('-v', '--verbose', action='store_true',
                    help='Mostrar el AST completo')
    ap.add_argument('-l', '--lexer', action='store_true',
                    help='Mostrar tokens')
    args = ap.parse_args()

    try:
        with open(args.archivo, encoding='utf-8') as f:
            source = f.read()
    except FileNotFoundError:
        print(f"Error: no se encontró '{args.archivo}'")
        return 1

    # Análisis léxico
    lexer = Lexer(source)
    tokens = lexer.tokenize()

    if args.lexer:
        lexer.print_tokens(tokens)

    if lexer.errors:
        print(f'\nErrores léxicos ({len(lexer.errors)}):')
        for ln, col, msg in lexer.errors:
            print(f'  Línea {ln}, col {col}: {msg}')
        return 1

    # Análisis sintáctico
    try:
        ast = Parser(tokens).parse()
    except ParseError as e:
        print(f'Error sintáctico: {e}')
        return 1

    if args.verbose:
        print_ast(ast)
    else:
        nodos = sum(1 for _ in ast.walk())
        print(f'ok| {nodos} nodos| {args.archivo}')

    return 0


if __name__ == '__main__':
    sys.exit(main())