from tkinter import Menu, END
import re

# Función principal del backend del compilador.
# Se encarga de ejecutar las fases del compilador y devolver
# el resultado al IDE.
from IDE.compiler_logic import compile_source
from IDE.autofix import autofix


class CompilerMenu:
    def __init__(self, text, console):
        self.text = text
        self.console = console
    
    # Escribe texto en la consola del IDE.
    def write_console(self, message):
        self.console.delete("1.0", END)
        self.console.insert("1.0", message)

    # Autofix
    def fix_code(self):
        """Aplica autofix al código en el editor y reporta los cambios."""
        code = self.text.get("1.0", END)

        fix = autofix(code)

        if not fix["changed"]:
            self.write_console("✔ No se encontraron errores que corregir automáticamente.")
            return

        # Reemplazar el contenido del editor con el código corregido
        self.text.delete("1.0", END)
        self.text.insert("1.0", fix["fixed_source"])

        # Marcar visualmente las líneas que recibieron un terminador
        self.clear_errors()
        for ln in fix["term_lines"]:
            self._mark_fixed_line(ln)
        for ln in fix["paren_lines"]:
            self._mark_fixed_line(ln)

        self.write_console(
            "✔ Corrección automática aplicada:\n\n" + fix["summary"]
        )

    def _mark_fixed_line(self, line: int):
        """Resalta en verde la línea que fue corregida automáticamente."""
        start = f"{line}.0"
        end   = f"{line}.end"
        self.text.tag_add("fixed", start, end)
        self.text.tag_configure(
            "fixed",
            background="#1A3A1A",
            foreground="#7EE787",
        )
        self.text.tag_raise("fixed")

    def clear_fixed(self):
        self.text.tag_remove("fixed", "1.0", END)

    # Compilacion

    # Se ejecuta cuando se presiona el botón "Compile" o F5.
    def compile_code(self):
        
        # Obtiene todo el texto escrito en el editor.
        code = self.text.get("1.0", END)
        
        # Ejecuta el compilador usando el código fuente obtenido del editor.
        result = compile_source(code)

        # Limpia cualquier error visual anterior antes de recompilar.
        self.clear_errors()

        # Cuando la compilación es exitosa
        if result["success"]:
            output = "Compilación exitosa.\n\n"

            if result.get("asm"):
                output += "=== ASM GENERADO ===\n\n"
                output += result["asm"] + "\n\n"

            if result.get("resolved_asm"):
                output += "=== ASM RESUELTO ===\n\n"
                output += result["resolved_asm"]

            # Escribe el resultado en la consola
            self.write_console(output)

            # Cuando se generan errores de compilación

        else:
            # Limpia cualquier error visual anterior antes de recompilar.
            message = result.get("message", "")

            # Mostrar el error en la consola del IDE.
            self.write_console(
                f"Error de compilación\n"
                f"Fase: {result.get('phase', 'desconocida')}\n\n"
                f"{message}"
            )

            # Buscar automáticamente el número de línea dentro del mensaje.
            match = re.search(r"[Ll][íi]nea\s*(\d+)", message)

            # Si se encontró una línea válida, la marca visualmente.
            if match:
                line = int(match.group(1))
                self.mark_error_line(line, message)

            # Si no se pudo detectar la línea, marcar la primera línea por defecto.
            else:
                self.mark_error_line(1, message)

    # Marca visualmente una línea con error dentro del editor.
    def mark_error_line(self, line, message=""):
        self.clear_errors()

        # Índices de inicio y fin de la línea en el widget Text.
        start = f"{line}.0"
        end = f"{line}.end"

        self.text.tag_add("error", start, end)

        self.text.tag_configure(
            "error",
            background="#5A1E1E",
            foreground="#FF6B6B",
            underline=True
        )

        self.text.tag_raise("error")
        self.text.see(start)

    def clear_errors(self):
        self.text.tag_remove("error", "1.0", END)


def main(root, text, console, menubar):
    obj = CompilerMenu(text, console)

    compiler_menu = Menu(
        menubar,
        tearoff=0,
        bg="#161B22",
        fg="white",
        activebackground="#000000",
        activeforeground="white"
    )

    compiler_menu.add_command(label="Compile", command=obj.compile_code, accelerator="F5")
    compiler_menu.add_command(label="Fix Code", command=obj.fix_code, accelerator ="Ctrl+F4")
    compiler_menu.add_command(label="Fix & Compile", command=lambda: (obj.fix_code(), obj.compile_code()), accelerator="F6")        
    compiler_menu.add_separator()                                                                                                    
    compiler_menu.add_command(label="Clear Errors", command=obj.clear_errors)

    menubar.add_cascade(label="Compiler", menu=compiler_menu)
    root.bind("<F5>", lambda event: obj.compile_code())
    root.bind("<F4>", lambda event: obj.fix_code())                                    
    root.bind("<F6>", lambda event: (obj.fix_code(), obj.compile_code()))              
    root.config(menu=menubar)