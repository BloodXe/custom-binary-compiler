import sys
import os

from lexer      import Lexer
from parser     import Parser, ParseError
from ast_nodes  import AstNode
from semantic   import SemanticAnalyzer
from asmgen     import AsmGen
from resolver   import Resolver
from binary_gen import BinaryGen
from lexer     import Lexer
from parser    import Parser, ParseError
from ast_nodes import AstNode, FunctionDeclaration
from semantic  import SemanticAnalyzer
from asmgen import AsmGen
from resolver import Resolver


# Impresión del AST

def print_ast(node: AstNode, last: bool = True, prefix: str = '') -> None:
    """Imprime el AST con formato de árbol usando ramas."""
    connector    = '└── ' if last else '├── '
    child_prefix = prefix + ('    ' if last else '│   ')
    print(prefix + connector + repr(node))
    children = [c for c in node.children if isinstance(c, AstNode)]
    for i, child in enumerate(children):
        print_ast(child, last=(i == len(children) - 1), prefix=child_prefix)


# Carga de archivos con resolución de imports

def load_with_imports(file: str) -> str:
    """
    Carga el archivo principal y todos sus imports recursivamente.

    Para cada módulo importado, renombra sus símbolos globales con
    el prefijo del módulo:
        func suma   →   func modulo.suma
        var x       →   var modulo.x
        const C     →   const modulo.C

    Esto permite que en el archivo que importa se use:
        modulo.suma(...)   o   modulo.x

    El lexer reconoce "modulo.suma" como un solo token IDENTIFIER
    porque soporta puntos en identificadores (ver lexer.py).
    El semántico los registra con el nombre completo, sin cambios.
    """
    visited = set()

    def _load(f: str, prefix: str = None) -> str:
        f = os.path.abspath(f)

        if f in visited:
            return ""
        visited.add(f)

        if not os.path.exists(f):
            raise FileNotFoundError(f"Módulo no encontrado: '{f}'")

        base_dir = os.path.dirname(f)

        with open(f, encoding='utf-8') as fh:
            code = fh.read()

        # Primera pasada: recolectar todos los símbolos declarados en este módulo
        symbols = set()
        if prefix:
            for l in code.splitlines():
                ls2 = l.strip()
                if ls2.startswith("func "):
                    sym = ls2.split()[1].split("(")[0]
                    symbols.add(sym)
                elif ls2.startswith("var "):
                    sym = ls2.split()[1]
                    symbols.add(sym)
                elif ls2.startswith("const "):
                    sym = ls2.split()[1]
                    symbols.add(sym)

        result = []
        for line in code.splitlines():
            ls = line.strip()

            # Detectar 'importar nombre'
            if ls.startswith("importar"):
                parts = ls.split()
                if len(parts) < 2:
                    result.append(line)
                    continue
                module = parts[1].replace("'", "").strip()
                module_path = os.path.join(base_dir, module + ".yeison")
                result.append(_load(module_path, prefix=module))
            else:
                # Renombrar referencias internas con el prefijo del módulo
                if prefix:
                    import re
                    for sym in sorted(symbols, key=len, reverse=True):
                        pattern = r'(?<!' + re.escape(prefix) + r'\.)\b' + re.escape(sym) + r'\b'
                        line = re.sub(pattern, f'{prefix}.{sym}', line)
                result.append(line)

        return "\n".join(result)

    return _load(file)  # ← llamada al final, dentro de load_with_imports


# Pipeline de compilación: fases 1 a 3 (léxico, sintáctico, semántico)

def run_phases_1_to_3(source: str, args):
    """
    Ejecuta léxico, sintáctico y semántico.
    Retorna (ast, sem) o llama sys.exit() si hay errores.
    """
    # Fase 1: Análisis léxico
    lexer  = Lexer(source)
    tokens = lexer.tokenize()

    if args.lexer:
        lexer.print_tokens(tokens)

    if lexer.errors:
        print(f'\nErrores léxicos ({len(lexer.errors)}):')
        for ln, col, msg in lexer.errors:
            print(f'  Línea {ln}, col {col}: {msg}')
        sys.exit(1)

    # Fase 2: Análisis sintáctico
    try:
        ast = Parser(tokens).parse()
    except ParseError as e:
        print(f'Error sintáctico: {e}')
        sys.exit(1)

    if args.verbose:
        print('\n=== ÁRBOL SINTÁCTICO ===\n')
        print_ast(ast)

    # Fase 3: Análisis semántico
    sem = SemanticAnalyzer()
    sem.visit(ast)

    if args.semantico:
        sem.symbol_table.print_table()
    if args.etiquetas:
        sem.print_labels()
    if args.memoria:
        sem.print_memory()

    if sem.errors:
        print(f'\nErrores semánticos ({len(sem.errors)}):')
        for e in sem.errors:
            print(f'  {e}')
        sys.exit(1)

    return ast, sem


# Main
def main():
    import argparse

    ap = argparse.ArgumentParser(
        description='Compilador Yeison → TEA-ISA binario',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python main.py programa.yeison -S          # mostrar ASM generado
  python main.py programa.yeison -b          # compilar a .bin
  python main.py programa.yeison -b -x       # compilar a .bin y .hex
  python main.py programa.yeison -a          # todo (AST, tokens, ASM, binario)
  python main.py programa.yeison -b -o salida  # binario en salida.bin
  python main.py programa.asm -A -b          # compilar desde .asm directo
        """
    )

    ap.add_argument('archivo',            help='Archivo fuente .yeison o .asm')
    ap.add_argument('-v', '--verbose',    action='store_true', help='Mostrar AST')
    ap.add_argument('-l', '--lexer',      action='store_true', help='Mostrar tokens')
    ap.add_argument('-s', '--semantico',  action='store_true', help='Mostrar tabla de símbolos')
    ap.add_argument('-m', '--memoria',    action='store_true', help='Mostrar mapa de memoria')
    ap.add_argument('-e', '--etiquetas',  action='store_true', help='Mostrar etiquetas de salto')
    ap.add_argument('-S', '--asm',        action='store_true', help='Mostrar ASM generado y resuelto')
    ap.add_argument('-b', '--binario',    action='store_true', help='Generar archivo .bin')
    ap.add_argument('-x', '--hex',        action='store_true', help='Generar hex dump .hex (requiere -b)')
    ap.add_argument('-o', '--output',     help='Nombre base del archivo de salida (sin extensión)')
    ap.add_argument('-a', '--all',        action='store_true', help='Activar todos los reportes y generar binario')
    ap.add_argument('-A', '--from-asm',   action='store_true', help='Compilar desde .asm (saltar fases 1-3)')

    args = ap.parse_args()

    # -a activa todo
    if args.all:
        args.verbose   = True
        args.lexer     = True
        args.semantico = True
        args.memoria   = True
        args.etiquetas = True
        args.asm       = True
        args.binario   = True
        args.hex       = True

    # Determinar nombre base de salida
    if args.output:
        base_name = args.output
    else:
        base_name = os.path.splitext(args.archivo)[0]

    # ── Obtener asm_code: desde .asm directo o desde pipeline normal ──
    if args.from_asm:
        try:
            with open(args.archivo, encoding='utf-8') as f:
                asm_code = f.read()
        except FileNotFoundError:
            print(f'Error: archivo no encontrado: {args.archivo}')
            return 1
    else:
        # Cargar fuente resolviendo imports
        try:
            source = load_with_imports(args.archivo)
        except FileNotFoundError as e:
            print(f'Error: {e}')
            return 1

        # Fases 1-3: léxico, sintáctico, semántico
        ast, sem = run_phases_1_to_3(source, args)

        # Fase 4: Generación de ensamblador
        gen      = AsmGen(sem)
        asm_code = gen.generate(ast)

    # ── Desde aquí igual para ambas ramas ──

    if args.asm:
        print('\n=== ASM GENERADO ===\n')
        print(asm_code)

    # Fase 5: Resolución de referencias (etiquetas → offsets numéricos)
    resolver     = Resolver(asm_code)
    resolved_asm = resolver.resolve()

    if args.asm:
        print('\n=== ASM RESUELTO ===\n')
        print(resolved_asm)

        # Mostrar tabla de etiquetas si se pidió debug
        if args.etiquetas:
            print('\n=== TABLA DE ETIQUETAS (Resolver) ===')
            for label, addr in resolver.get_label_table().items():
                print(f'  {label:<30} 0x{addr:04X}')

    # Guardar ASM si se pidió output y se generó ASM
    if args.output and args.asm:
        asm_path = base_name + '.asm'
        with open(asm_path, 'w', encoding='utf-8') as f:
            f.write(asm_code)
        print(f'\nASM guardado en: {asm_path}')

    # Fase 6: Generación de binario
    if args.binario:
        hex_path = (base_name + '.mem') if args.hex else None
        bin_path = base_name + '.bin'

        bg = BinaryGen(resolved_asm)
        ok = bg.generate(bin_path, hex_path)

        if not ok:
            print('\nFalló la generación del binario.')
            return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())