from tkinter import Menu, END
from IDE.compiler_logic import compile_source


class CompilerMenu:
    def __init__(self, text, console):
        self.text = text
        self.console = console

    def write_console(self, message):
        self.console.delete("1.0", END)
        self.console.insert("1.0", message)

    def compile_code(self):
        code = self.text.get("1.0", END)

        result = compile_source(code)

        self.clear_errors()

        if result["success"]:
            output = "Compilación exitosa.\n\n"

            if result.get("asm"):
                output += "=== ASM GENERADO ===\n\n"
                output += result["asm"] + "\n\n"

            if result.get("resolved_asm"):
                output += "=== ASM RESUELTO ===\n\n"
                output += result["resolved_asm"]

            self.write_console(output)

        else:
            self.write_console(
                f"Error de compilación\n"
                f"Fase: {result.get('phase', 'desconocida')}\n\n"
                f"{result.get('message', '')}"
            )

            self.mark_error_line(1, result.get("message", ""))


    def mark_error_line(self, line, message):
        start = f"{line}.0"
        end = f"{line}.end"
        self.text.tag_add("error", start, end)
        self.text.tag_config("error", background="#5A1E1E", underline=True)

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
    compiler_menu.add_command(label="Clear Errors", command=obj.clear_errors)

    menubar.add_cascade(label="Compiler", menu=compiler_menu)
    root.bind("<F5>", lambda event: obj.compile_code())
    root.config(menu=menubar)