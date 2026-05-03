import sys

from lexer     import Lexer
from parser    import Parser, ParseError
from ast_nodes import AstNode, FunctionDeclaration
from semantic  import SemanticAnalyzer
from asmgen import AsmGen
from resolver import Resolver


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
    ap.add_argument('archivo',            help='Archivo fuente .yeison')
    ap.add_argument('-v', '--verbose',    action='store_true', help='Mostrar el AST completo')
    ap.add_argument('-l', '--lexer',      action='store_true', help='Mostrar tokens')
    ap.add_argument('-s', '--semantico',  action='store_true', help='Mostrar tabla de simbolos')
    ap.add_argument('-m', '--memoria',    action='store_true', help='Mostrar mapa de memoria')
    ap.add_argument('-e', '--etiquetas',  action='store_true', help='Mostrar etiquetas de salto')
    ap.add_argument('-S', '--asm',        action='store_true', help='Generar código ASM')
    ap.add_argument('-n', '--resolver',   action='store_true', help='Mostrar el código ASM con los saltos resueltos')
    ap.add_argument('-o', '--output', help='Archivo de salida')
    ap.add_argument('-a', '--all',        action='store_true', help='Mostrar todo')
    
    args = ap.parse_args()

    # -a activa todos los reportes
    if args.all:
        args.verbose = True
        args.lexer = True
        args.semantico = True
        args.memoria = True
        args.etiquetas = True
        args.asm = True
        args.resolver = True

    #se lee el archivo
    try:
        with open(args.archivo, encoding='utf-8') as f:
            source = f.read()
    except FileNotFoundError:
        print(f"Error: no se encontro '{args.archivo}'")
        return 1

    #Lexer
    lexer = Lexer(source)
    tokens = lexer.tokenize()

    if args.lexer:
        lexer.print_tokens(tokens)

    if lexer.errors:
        print(f'\nErrores lexicos ({len(lexer.errors)}):')
        for ln, col, msg in lexer.errors:
            print(f'  Linea {ln}, col {col}: {msg}')
        return 1

    # Parser
    try:
        ast = Parser(tokens).parse()
    except ParseError as e:
        print(f'Error sintactico: {e}')
        return 1

    if args.verbose:
        print_ast(ast)


    #Semantico
    sem = SemanticAnalyzer()
    sem.visit(ast)

   
    if args.semantico:
        sem.symbol_table.print_table()

    if args.etiquetas:
        sem.print_labels()

    if args.memoria:
        sem.print_memory()

    #errores
    if sem.errors:
        print(f'\nErrores semanticos ({len(sem.errors)}):')
        for e in sem.errors:
            print(f'  {e}')
        return 1

    # Code Generation
    if args.asm:
        gen = AsmGen(sem)
        asm_code = gen.generate(ast)

        print("\n=== ASM GENERADO ===\n")
        print(asm_code)

        # Guardar archivo si se pidió
        if args.output:
            with open(args.output, 'w') as f:
                f.write(asm_code)
            print(f"\nASM guardado en: {args.output}")
    
    # Code Generation
    if args.resolver:
        new = Resolver(asm_code)
        resolved_code = new.resolve()

        print("\n=== NUEVO ASM GENERADO ===\n")
        print(resolved_code)

        # Guardar archivo si se pidió
        if args.output:
            with open(args.output, 'w') as f:
                f.write(resolved_code)
            print(f"\nASM guardado en: {args.output}")

    return 0


if __name__ == '__main__':
    sys.exit(main())