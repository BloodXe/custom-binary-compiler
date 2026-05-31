# menu del compilador con deteccion de errores en tiempo real


import sys
import os
from tkinter import Menu, END
from tkinter.filedialog import asksaveasfilename
from tkinter.messagebox import showerror

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from IDE.compiler_logic import compile_source, run_live_check
from IDE.autofix import autofix


_STYLES = {
    "lex":      {"background": "#4D2600", "foreground": "#FFA657", "underline": True},
    "parse":    {"background": "#5A1E1E", "foreground": "#FF6B6B", "underline": True},
    "semantic": {"background": "#3D3800", "foreground": "#E3B341", "underline": True},
    "codegen":  {"background": "#5A1E1E", "foreground": "#FF6B6B", "underline": True},
    "error":    {"background": "#5A1E1E", "foreground": "#FF6B6B", "underline": True},
    "autofix":  {"background": "#1F2D3D", "foreground": "#79C0FF", "underline": True},
}

_ERR_PREFIX    = "cmperr_"
_DEBOUNCE_MS   = 300   # ms de espera antes de correr el pipeline en live_check
_PHASE_LABELS  = {
    "lex":      "Léxico",
    "parse":    "Sintáctico",
    "semantic": "Semántico",
    "codegen":  "Generación de código",
}


class CompilerMenu:

    def __init__(self, text, console):
        self.text       = text
        self.console    = console
        self._err_tags  = []      # tags de error activos en el editor
        self._mode      = "ready" # ready | live | compile | autofix
        self._debounce  = None    # id del after() pendiente para live_check



    def _write(self, msg: str):
        # reemplaza todo el contenido de la consola con el mensaje nuevo
        self.console.delete("1.0", END)
        self.console.insert("1.0", msg)

    def _clear_console(self):
        # deja la consola en blanco
        self.console.delete("1.0", END)



    # "Compilar" o F5
    def compile_code(self):
        self._cancel_debounce()
        source = self.text.get("1.0", END)
        self.clear_errors()
        result = compile_source(source)
        self._mode = "compile"

        if result["success"]:
            out = "Compilación exitosa.\n\n"
            if result.get("asm"):
                out += "=== ASM GENERADO ===\n\n" + result["asm"] + "\n\n"
            if result.get("resolved_asm"):
                out += "=== ASM RESUELTO ===\n\n" + result["resolved_asm"]
            self._write(out)
        else:
            errors = result.get("errors", [])
            phase  = result.get("phase", "error")
            self._mark_errors(errors)
            label  = _PHASE_LABELS.get(phase, "compilación")
            header = f"Error {label}  —  {len(errors)} error(es) detectado(s)\n{'─'*50}\n\n"
            self._write(header + result.get("message", ""))



    # compila el codigo y genera un archivo .mem
    def compile_to_mem(self):
        self._cancel_debounce()
        source = self.text.get("1.0", END)
        self.clear_errors()
        result = compile_source(source)
        self._mode = "compile"

        if not result["success"]:
            errors = result.get("errors", [])
            phase  = result.get("phase", "error")
            self._mark_errors(errors)
            label  = _PHASE_LABELS.get(phase, "compilación")
            header = f"Error {label}  —  {len(errors)} error(es) detectado(s)\n{'─'*50}\n\n"
            self._write(header + result.get("message", ""))
            return

        # si la compilacion fue exitosa, pedimos donde guardar el .mem
        mem_path = asksaveasfilename(
            title="Guardar archivo .mem",
            defaultextension=".mem",
            filetypes=[("MEM files", "*.mem"), ("All files", "*.*")],
        )
        if not mem_path:
            # el usuario canceló el dialogo; volvemos a modo listo
            self._mode = "ready"
            return

        try:
            from compiler.binary_gen import BinaryGen

            bin_path = os.path.splitext(mem_path)[0] + ".bin"
            resolved = result.get("resolved_asm", "")

            bg = BinaryGen(resolved)
            ok = bg.generate(bin_path, mem_path)

            if ok:
                self._write(
                    f"Compilación a .mem exitosa.\n\n"
                    f"Binario : {bin_path}\n"
                    f"Mem     : {mem_path}\n\n"
                    f"=== ASM RESUELTO ===\n\n{resolved}"
                )
            else:
                errs = "\n".join(f"  • {e}" for e in bg.errors)
                self._write(f"Error en generación binaria:\n{'─'*50}\n\n{errs}")
        except Exception as exc:
            showerror("Error generando .mem", str(exc))

 

    # aplica autofix al codigo del editor usando autofix.py y reporta los cambios
    def autofix_code(self):
        self._cancel_debounce()
        source = self.text.get("1.0", END)
        self.clear_errors()
        self._mode = "autofix"

        fix = autofix(source)

        if not fix["changed"]:
            self._write("No se encontraron errores que corregir automáticamente.")
            return

        # reemplaza el contenido del editor con el codigo corregido
        self.text.delete("1.0", END)
        self.text.insert("1.0", fix["fixed_source"])

        # resalta visualmente las lineas que recibieron alguna correccion
        fixed_lines = set(fix["term_lines"]) | set(fix["paren_lines"])
        entries = [{"line": ln, "col": 1, "phase": "autofix"} for ln in fixed_lines]
        self._mark_errors(entries)

        self._write("Corrección automática aplicada:\n\n" + fix["summary"])

  

    def schedule_live_check(self, event=None):
        self._mode = "live"
        self._cancel_debounce()
        self._debounce = self.text.after(_DEBOUNCE_MS, self._run_live_check)

    def _cancel_debounce(self):

        if self._debounce is not None:
            try:
                self.text.after_cancel(self._debounce)
            except Exception:
                pass
            self._debounce = None

    def _run_live_check(self):

        self._debounce = None

        if self._mode != "live":
            return

        self.clear_errors()
        try:
            source = self.text.get("1.0", END)
            errors = run_live_check(source)

            if errors:
                self._mark_errors(errors)
                self._write(self._format_live_errors(errors))
            else:
       
                self._write("Sin errores")
                self._mode = "ready"
        except Exception:
            pass  

    def _format_live_errors(self, errors: list) -> str:

        lines = [f"{len(errors)} error(es) detectado(s)\n{'─'*50}\n"]
        for err in errors:
            phase = _PHASE_LABELS.get(err.get("phase", ""), "Error")
            ln    = err.get("line", "?")
            col   = err.get("col",  "?")
            msg   = err.get("msg",  "")
            lines.append(f"[{phase}] Línea {ln}, col {col}: {msg}")
        return "\n".join(lines)



    def _mark_errors(self, errors: list):

        for err in errors:
            ln    = err.get("line", 1)
            col   = err.get("col",  1)
            phase = err.get("phase", "error")
            style = _STYLES.get(phase, _STYLES["error"])

            tag = f"{_ERR_PREFIX}{ln}_{col}_{phase}"
            self.text.tag_configure(tag, **style)

            start     = f"{ln}.{max(0, col - 1)}"
            end       = f"{ln}.end"
            line_text = self.text.get(f"{ln}.0", end)
            if not line_text.strip() or col <= 1:
                start = f"{ln}.0"

            self.text.tag_add(tag, start, end)
            self.text.tag_raise(tag)
            self._err_tags.append(tag)

        # muevo la vista al primer error
        if errors:
            self.text.see(f"{errors[0]['line']}.0")

    def clear_errors(self):
        # borro solo los tags de error, los de highlighting no los toco
        for tag in self._err_tags:
            try:
                self.text.tag_remove(tag, "1.0", END)
                self.text.tag_delete(tag)
            except Exception:
                pass
        self._err_tags = []


def main(root, text, console, menubar, on_content_change=None, file_obj=None):
    obj = CompilerMenu(text, console)


    m = Menu(menubar, tearoff=0, bg="#161B22", fg="white",
             activebackground="#000000", activeforeground="white")
    m.add_command(label="Compilar",         command=obj.compile_code,   accelerator="F5")
    m.add_command(label="Compilar a .mem",  command=obj.compile_to_mem, accelerator="F7")
    m.add_separator()
    m.add_command(label="Auto-corregir",    command=obj.autofix_code,   accelerator="F6")
    m.add_command(label="Limpiar marcas",   command=obj.clear_errors)
    menubar.add_cascade(label="Compilador", menu=m)

    # atajos de teclado
    root.bind("<F5>", lambda e: obj.compile_code())
    root.bind("<F6>", lambda e: obj.autofix_code())
    root.bind("<F7>", lambda e: obj.compile_to_mem())
    root.config(menu=menubar)

    text.bind("<KeyRelease>", lambda e: obj.schedule_live_check(), add="+")

    return obj