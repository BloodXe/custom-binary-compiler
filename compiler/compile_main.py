import os
import sys
from types import SimpleNamespace

from compiler.lexer       import Lexer
from compiler.parser      import Parser, ParseError
from compiler.ast_nodes   import AstNode
from compiler.semantic    import SemanticAnalyzer
from compiler.asmgen      import AsmGen
from compiler.asmgen2     import AsmGen2
from compiler.resolver    import Resolver
from compiler.binary_gen  import BinaryGen
from compiler.IRGen       import IRGen
from compiler.basic_blocks import build_basic_blocks, format_blocks
from compiler.cfg         import build_cfg
from compiler.optimizer   import optimize


# ── Impresión del AST ────────────────────────────────────────────────────────

def print_ast(node: AstNode, last: bool = True, prefix: str = '') -> None:
    """Imprime el AST con formato de árbol usando ramas."""
    connector    = '└── ' if last else '├── '
    child_prefix = prefix + ('    ' if last else '│   ')
    print(prefix + connector + repr(node))
    children = [c for c in node.children if isinstance(c, AstNode)]
    for i, child in enumerate(children):
        print_ast(child, last=(i == len(children) - 1), prefix=child_prefix)


# ── Carga de archivos con resolución de imports ───────────────────────────────

def load_with_imports(file: str) -> str:
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
            if ls.startswith("importar"):
                parts = ls.split()
                if len(parts) < 2:
                    result.append(line)
                    continue
                module = parts[1].replace("'", "").strip()
                module_path = os.path.join(base_dir, module + ".yeison")
                result.append(_load(module_path, prefix=module))
            else:
                if prefix:
                    import re
                    for sym in sorted(symbols, key=len, reverse=True):
                        pattern = r'(?<!' + re.escape(prefix) + r'\.)\\b' + re.escape(sym) + r'\\b'
                        line = re.sub(pattern, f'{prefix}.{sym}', line)
                result.append(line)
        return "\n".join(result)

    return _load(file)


# ── Pipeline fases 1-3 ────────────────────────────────────────────────────────

def run_phases_1_to_3(source: str, args):
    # Fase 1: léxico
    lexer  = Lexer(source)
    tokens = lexer.tokenize()

    if args.lexer:
        print('\n=== TOKENS ===\n')
        lexer.print_tokens(tokens)

    if lexer.errors:
        print(f'\nErrores léxicos ({len(lexer.errors)}):')
        for ln, col, msg in lexer.errors:
            print(f'  Línea {ln}, col {col}: {msg}')
        sys.exit(1)

    # Fase 2: sintáctico
    try:
        ast = Parser(tokens).parse()
    except ParseError as e:
        print(f'Error sintáctico: {e}')
        sys.exit(1)

    if args.verbose:
        print('\n=== ÁRBOL SINTÁCTICO (AST) ===\n')
        print_ast(ast)

    # Fase 3: semántico
    sem = SemanticAnalyzer()
    sem.visit(ast)

    if args.semantico:
        print('\n=== TABLA DE SÍMBOLOS ===')
        sem.symbol_table.print_table()
    if args.etiquetas:
        print('\n=== ETIQUETAS DE SALTO ===')
        sem.print_labels()
    if args.memoria:
        print('\n=== MAPA DE MEMORIA ===')
        sem.print_memory()

    if sem.errors:
        print(f'\nErrores semánticos ({len(sem.errors)}):')
        for e in sem.errors:
            print(f'  {e}')
        sys.exit(1)

    return ast, sem


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    import argparse

    ap = argparse.ArgumentParser(
        description='Compilador Yeison → TEA-ISA binario',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python main.py programa.yeison -S              # mostrar ASM
  python main.py programa.yeison -b              # compilar a .bin
  python main.py programa.yeison -a              # todo (tokens, AST, IR, CFG, ASM, binario)
  python main.py programa.yeison -O2 -S          # optimizar y mostrar ASM
  python main.py programa.yeison -O2 --cfg       # IR + CFG + optimizaciones
  python main.py programa.yeison -O2 -b -o salida # optimizar y guardar binario
        """
    )

    # Archivo fuente
    ap.add_argument('archivo',              help='Archivo fuente .yeison o .asm')

    # Reportes de análisis
    ap.add_argument('-v', '--verbose',      action='store_true', help='Mostrar AST')
    ap.add_argument('-l', '--lexer',        action='store_true', help='Mostrar tokens')
    ap.add_argument('-s', '--semantico',    action='store_true', help='Mostrar tabla de símbolos')
    ap.add_argument('-m', '--memoria',      action='store_true', help='Mostrar mapa de memoria')
    ap.add_argument('-e', '--etiquetas',    action='store_true', help='Mostrar etiquetas de salto')

    # IR y CFG
    ap.add_argument('--ir',                 action='store_true', help='Mostrar IR de tres direcciones')
    ap.add_argument('--bloques',            action='store_true', help='Mostrar bloques básicos')
    ap.add_argument('--cfg',                action='store_true', help='Mostrar CFG y exportar JSON')
    ap.add_argument('--cfg-json',           metavar='ARCHIVO',   help='Guardar CFG original en JSON')
    ap.add_argument('--cfg-opt-json',       metavar='ARCHIVO',   help='Guardar CFG optimizado en JSON')

    # Optimizaciones
    ap.add_argument('-O0',                  action='store_true', help='Sin optimizaciones')
    ap.add_argument('-O1',                  action='store_true', help='DCE + renombramiento')
    ap.add_argument('-O2',                  action='store_true', help='Todo: unroll + rename + DCE + reorder')
    ap.add_argument('--unroll',             action='store_true', help='Activar loop unrolling')
    ap.add_argument('--no-unroll',          action='store_true', help='Desactivar loop unrolling')
    ap.add_argument('--factor',             type=int, default=4, help='Factor de unrolling (default: 4)')
    ap.add_argument('--dce',                action='store_true', help='Activar DCE')
    ap.add_argument('--rename',             action='store_true', help='Activar renombramiento')
    ap.add_argument('--reorder',            action='store_true', help='Activar reordenamiento')
    ap.add_argument('--stats',              action='store_true', help='Mostrar estadísticas de optimización')

    # Salida
    ap.add_argument('-S', '--asm',          action='store_true', help='Mostrar ASM generado y resuelto')
    ap.add_argument('-b', '--binario',      action='store_true', help='Generar archivo .bin')
    ap.add_argument('-x', '--hex',          action='store_true', help='Generar hex dump .mem')
    ap.add_argument('-o', '--output',       help='Nombre base del archivo de salida')
    ap.add_argument('-a', '--all',          action='store_true', help='Activar todos los reportes y generar binario')
    ap.add_argument('-A', '--from-asm',     action='store_true', help='Compilar desde .asm directo')

    args = ap.parse_args()

    # -a activa todo
    if args.all:
        args.verbose   = True
        args.lexer     = True
        args.semantico = True
        args.memoria   = True
        args.etiquetas = True
        args.ir        = True
        args.bloques   = True
        args.cfg       = True
        args.stats     = True
        args.asm       = True
        args.binario   = True
        args.hex       = True
        setattr(args, 'O2', True)

    # Determinar configuración de optimizaciones
    enable_unroll  = True
    enable_rename  = True
    enable_dce     = True
    enable_reorder = False
    unroll_factor  = args.factor

    if getattr(args, 'O0', False):
        enable_unroll = enable_rename = enable_dce = enable_reorder = False
    elif getattr(args, 'O1', False):
        enable_unroll  = False
        enable_reorder = False
        enable_dce     = True
        enable_rename  = True
    elif getattr(args, 'O2', False):
        enable_unroll  = True
        enable_rename  = True
        enable_dce     = True
        enable_reorder = True

    # Flags individuales tienen prioridad
    if args.unroll:    enable_unroll  = True
    if args.no_unroll: enable_unroll  = False
    if args.dce:       enable_dce     = True
    if args.rename:    enable_rename  = True
    if args.reorder:   enable_reorder = True

    # Nombre base de salida
    base_name = args.output or os.path.splitext(args.archivo)[0]

    # ── Rama .asm directo ────────────────────────────────────────────────────
    if args.from_asm:
        try:
            with open(args.archivo, encoding='utf-8') as f:
                asm_code = f.read()
        except FileNotFoundError:
            print(f'Error: archivo no encontrado: {args.archivo}')
            return 1
        if args.asm:
            print('\n=== ASM ===\n')
            print(asm_code)
        resolver     = Resolver(asm_code)
        resolved_asm = resolver.resolve()
        if args.asm:
            print('\n=== ASM RESUELTO ===\n')
            print(resolved_asm)
        if args.binario:
            bg = BinaryGen(resolved_asm)
            bg.generate(base_name + '.bin',
                        (base_name + '.mem') if args.hex else None)
        return 0

    # ── Pipeline normal ──────────────────────────────────────────────────────
    try:
        source = load_with_imports(args.archivo)
    except FileNotFoundError as e:
        print(f'Error: {e}')
        return 1

    # Fases 1-3
    ast, sem = run_phases_1_to_3(source, args)

    # Fase IR + bloques + CFG
    ir_code = IRGen().generate(ast)

    if args.ir:
        print('\n=== REPRESENTACIÓN INTERMEDIA (IR) ===\n')
        print(ir_code)

    blocks = build_basic_blocks(ir_code)
    if args.bloques:
        print('\n=== BLOQUES BÁSICOS ===\n')
        print(format_blocks(blocks))

    cfg_orig = build_cfg(ir_code)
    if args.cfg:
        print('\n=== CFG ORIGINAL ===\n')
        print(cfg_orig.summary())

    if args.cfg_json:
        with open(args.cfg_json, 'w', encoding='utf-8') as f:
            f.write(cfg_orig.to_json())
        print(f'CFG original guardado en: {args.cfg_json}')

    # Optimizaciones
    any_opt = enable_unroll or enable_rename or enable_dce or enable_reorder
    opt_ir, opt_stats = optimize(
        ir_code,
        enable_unroll  = enable_unroll,
        unroll_factor  = unroll_factor,
        enable_rename  = enable_rename,
        enable_dce     = enable_dce,
        enable_reorder = enable_reorder,
    )

    if args.stats:
        print('\n=== ESTADÍSTICAS DE OPTIMIZACIÓN ===\n')
        print(opt_stats)

    cfg_opt = build_cfg(opt_ir)
    if args.cfg:
        print('\n=== CFG OPTIMIZADO ===\n')
        print(cfg_opt.summary())

    if args.cfg_opt_json:
        with open(args.cfg_opt_json, 'w', encoding='utf-8') as f:
            f.write(cfg_opt.to_json())
        print(f'CFG optimizado guardado en: {args.cfg_opt_json}')

    # Generación de ASM
    if any_opt and opt_ir:
        asm_code = AsmGen2().generate(opt_ir)
    else:
        asm_code = AsmGen(sem).generate(ast)

    if args.asm:
        print('\n=== ASM GENERADO ===\n')
        print(asm_code)

    resolver     = Resolver(asm_code)
    resolved_asm = resolver.resolve()

    if args.asm:
        print('\n=== ASM RESUELTO ===\n')
        print(resolved_asm)
        if args.etiquetas:
            print('\n=== TABLA DE ETIQUETAS (Resolver) ===')
            for label, addr in resolver.get_label_table().items():
                print(f'  {label:<30} 0x{addr:04X}')

    if args.output and args.asm:
        with open(base_name + '.asm', 'w', encoding='utf-8') as f:
            f.write(asm_code)
        print(f'\nASM guardado en: {base_name}.asm')

    if args.binario:
        bg = BinaryGen(resolved_asm)
        ok = bg.generate(base_name + '.bin',
                         (base_name + '.mem') if args.hex else None)
        if not ok:
            print('\nFalló la generación del binario.')
            return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
