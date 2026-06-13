# menu del compilador con deteccion de errores en tiempo real


import sys
import os
import tkinter as tk
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

# ── Configuración de optimizaciones por defecto ──────────────────────────────
_DEFAULT_OPT = {
    "unroll":  True,
    "factor":  4,
    "total":   False,
    "rename":  True,
    "dce":     True,
    "reorder": False,
}


def _show_opt_dialog(root, current: dict) -> dict | None:
    """Muestra un diálogo modal para configurar las optimizaciones.
    Retorna el dict actualizado, o None si el usuario canceló.
    """
    dlg = tk.Toplevel(root)
    dlg.title("Configurar optimizaciones")
    dlg.resizable(False, False)
    dlg.configure(bg="#161B22")
    dlg.grab_set()   # modal

    pad = {"padx": 12, "pady": 4}

    # Variables de control
    var_unroll  = tk.BooleanVar(value=current["unroll"])
    var_factor  = tk.IntVar(value=current["factor"])
    var_total   = tk.BooleanVar(value=current["total"])
    var_rename  = tk.BooleanVar(value=current["rename"])
    var_dce     = tk.BooleanVar(value=current["dce"])
    var_reorder = tk.BooleanVar(value=current["reorder"])
    result      = {"ok": False}

    def label(text, row, col=0):
        tk.Label(dlg, text=text, bg="#161B22", fg="#C9D1D9",
                 font=("Consolas", 10)).grid(row=row, column=col,
                 sticky="w", **pad)

    def check(var, text, row):
        tk.Checkbutton(dlg, text=text, variable=var,
                       bg="#161B22", fg="#C9D1D9", selectcolor="#0D1117",
                       activebackground="#161B22", activeforeground="white",
                       font=("Consolas", 10)).grid(row=row, column=0,
                       columnspan=2, sticky="w", **pad)

    # ── Título ────────────────────────────────────────────────────────────────
    tk.Label(dlg, text="Optimizaciones del compilador",
             bg="#161B22", fg="#58A6FF",
             font=("Consolas", 11, "bold")).grid(
             row=0, column=0, columnspan=2, pady=(12, 6), padx=12)

    tk.Frame(dlg, bg="#30363D", height=1).grid(
        row=1, column=0, columnspan=2, sticky="ew", padx=12)

    # ── Loop Unrolling ────────────────────────────────────────────────────────
    check(var_unroll, "Loop unrolling", 2)

    label("  Factor de unrolling:", 3)
    spin = tk.Spinbox(dlg, from_=2, to=16, textvariable=var_factor, width=5,
                      bg="#0D1117", fg="#C9D1D9", insertbackground="white",
                      font=("Consolas", 10), buttonbackground="#21262D")
    spin.grid(row=3, column=1, sticky="w", **pad)

    check(var_total, "  Unrolling total (ignorar factor)", 4)

    def _toggle_unroll_opts(*_):
        state = "normal" if var_unroll.get() else "disabled"
        spin.config(state=state)
    var_unroll.trace_add("write", _toggle_unroll_opts)
    _toggle_unroll_opts()

    tk.Frame(dlg, bg="#30363D", height=1).grid(
        row=5, column=0, columnspan=2, sticky="ew", padx=12, pady=4)

    # ── Otras optimizaciones ─────────────────────────────────────────────────
    check(var_rename,  "Renombramiento de registros", 6)
    check(var_dce,     "Eliminación de código muerto (DCE)", 7)
    check(var_reorder, "Reordenamiento de instrucciones", 8)

    tk.Frame(dlg, bg="#30363D", height=1).grid(
        row=9, column=0, columnspan=2, sticky="ew", padx=12, pady=4)

    # ── Botones ───────────────────────────────────────────────────────────────
    btn_frame = tk.Frame(dlg, bg="#161B22")
    btn_frame.grid(row=10, column=0, columnspan=2, pady=(4, 12), padx=12)

    def on_ok():
        result["ok"]     = True
        result["unroll"] = var_unroll.get()
        result["factor"] = var_factor.get()
        result["total"]  = var_total.get()
        result["rename"] = var_rename.get()
        result["dce"]    = var_dce.get()
        result["reorder"]= var_reorder.get()
        dlg.destroy()

    def on_cancel():
        dlg.destroy()

    tk.Button(btn_frame, text="Aplicar", command=on_ok, width=10,
              bg="#238636", fg="white", activebackground="#2EA043",
              font=("Consolas", 10), relief="flat").pack(side="left", padx=4)

    tk.Button(btn_frame, text="Cancelar", command=on_cancel, width=10,
              bg="#21262D", fg="#C9D1D9", activebackground="#30363D",
              font=("Consolas", 10), relief="flat").pack(side="left", padx=4)

    dlg.wait_window()
    return {k: v for k, v in result.items() if k != "ok"} if result["ok"] else None


class CompilerMenu:

    def __init__(self, text, console):
        self.text       = text
        self.console    = console
        self._err_tags  = []      # tags de error activos en el editor
        self._mode      = "ready" # ready | live | compile | autofix
        self._debounce  = None    # id del after() pendiente para live_check
        self._opt_config = dict(_DEFAULT_OPT)  # configuración de optimizaciones activa
        self._last_cfg_json = None              # JSON del CFG del último compile exitoso

    def open_opt_dialog(self):
        """Abre el diálogo de configuración de optimizaciones."""
        new_cfg = _show_opt_dialog(self.text.winfo_toplevel(), self._opt_config)
        if new_cfg is not None:
            self._opt_config = new_cfg
            # Confirmación breve en consola
            activas = [k for k, v in new_cfg.items() if v and k != "factor"]
            self._write(
                "Configuración de optimizaciones actualizada:\n\n" +
                "\n".join(f"  • {k}" for k in activas) +
                (f"\n  • factor de unrolling: {new_cfg['factor']}" if new_cfg.get("unroll") else "")
            )

    def export_cfg_json(self):
        """Exporta el JSON del CFG al disco para visualización web."""
        from tkinter.filedialog import asksaveasfilename

        if not self._last_cfg_json:
            self._write("No hay CFG disponible. Compilá primero (F5).")
            return

        path = asksaveasfilename(
            title="Exportar CFG como JSON",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("Todos", "*.*")],
            initialfile="cfg.json",
        )
        if not path:
            return

        with open(path, "w", encoding="utf-8") as f:
            f.write(self._last_cfg_json)

        self._write(f"CFG exportado a:\n{path}\n\nAbrilo en el visualizador web para ver el grafo.")



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
        result = compile_source(source, opt_config=self._opt_config)
        self._mode = "compile"

        if result["success"]:
            # Guardar el JSON del CFG para poder exportarlo después
            self._last_cfg_json = result.get("cfg_json")

            out = "Compilación exitosa.\n\n"
            if result.get("ir"):
                out += "=== REPRESENTACIÓN INTERMEDIA ===\n\n" + result["ir"] + "\n\n"
            if result.get("blocks"):
                out += "=== BLOQUES BÁSICOS ===\n\n" + result["blocks"] + "\n\n"
            if result.get("cfg_summary"):
                out += "=== CFG (Control Flow Graph) ===\n\n" + result["cfg_summary"] + "\n\n"
            if result.get("optimization"):
                out += "=== OPTIMIZACIÓN ===\n\n" + result["optimization"] + "\n\n"
            if result.get("stats"):
                out += "=== ESTADÍSTICAS DE OPTIMIZACIÓN ===\n\n" + result["stats"] + "\n\n"
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
        result = compile_source(source, opt_config=self._opt_config)
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
    m.add_command(label="Compilar",                 command=obj.compile_code,     accelerator="F5")
    m.add_command(label="Compilar a .mem",          command=obj.compile_to_mem,   accelerator="F7")
    m.add_separator()
    m.add_command(label="Configurar optimizaciones...", command=obj.open_opt_dialog, accelerator="F8")
    m.add_command(label="Exportar CFG (JSON)...",   command=obj.export_cfg_json,  accelerator="F9")
    m.add_separator()
    m.add_command(label="Auto-corregir",            command=obj.autofix_code,     accelerator="F6")
    m.add_command(label="Limpiar marcas",           command=obj.clear_errors)
    menubar.add_cascade(label="Compilador", menu=m)

    # atajos de teclado
    root.bind("<F5>", lambda e: obj.compile_code())
    root.bind("<F6>", lambda e: obj.autofix_code())
    root.bind("<F7>", lambda e: obj.compile_to_mem())
    root.bind("<F8>", lambda e: obj.open_opt_dialog())
    root.bind("<F9>", lambda e: obj.export_cfg_json())
    root.config(menu=menubar)

    text.bind("<KeyRelease>", lambda e: obj.schedule_live_check(), add="+")

    return obj