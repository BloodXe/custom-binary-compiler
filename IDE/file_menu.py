# menu de archivo nuevo, abrir, guardar, guardar como, salir
from tkinter import END, Menu
from tkinter.filedialog import askopenfile, asksaveasfile
from tkinter.messagebox import askyesno, showerror


class File:
    def __init__(self, text, root, on_content_change=None, clear_errors=None):
        self.filename          = None  # ruta del archivo actual
        self.text              = text
        self.root              = root
        self._on_content_change = on_content_change  # callback para actualizar highlighting y numeros de linea
        self._clear_errors      = clear_errors        # callback para limpiar marcas de error del compilador

    def _after_load(self):
        # borra marcas de error del archivo anterior y dispara highlighting + numeros de linea
        if self._clear_errors:
            self._clear_errors()
        if self._on_content_change:
            self._on_content_change()

    def newFile(self):
        # limpio el editor y olvido el nombre del archivo
        self.filename = None
        self.root.title("TEA-ISA IDE - Untitled")
        self.text.delete("1.0", END)
        self._after_load()

    def saveFile(self):
        # si no hay ruta abro el dialogo de guardar como
        if not self.filename:
            self.saveAs()
            return
        try:
            with open(self.filename, "w", encoding="utf-8") as f:
                f.write(self.text.get("1.0", END).rstrip())
        except Exception:
            showerror(title="Oops!", message="Unable to save file...")

    def saveAs(self):
        # dialogo para elegir donde guardar el archivo
        f = asksaveasfile(
            mode="w",
            defaultextension=".yeison",
            filetypes=[
                ("Yeison source files", "*.yeison"),
                ("All files", "*.*")
            ]
        )
        if f is None:
            return
        try:
            with f:
                f.write(self.text.get("1.0", END).rstrip())
            self.filename = f.name
            self.root.title(f"TEA-ISA IDE - {self.filename}")
        except Exception:
            showerror(title="Oops!", message="Unable to save file...")

    def openFile(self):
        f = askopenfile(
            mode="r",
            filetypes=[
                ("Yeison source files", "*.yeison"),
                ("All files", "*.*")
            ]
        )
        if f is None:
            return
        try:
            with f:
                self.filename = f.name
                content = f.read()
            self.text.delete("1.0", END)
            self.text.insert("1.0", content)
            self.root.title(f"TEA-ISA IDE - {self.filename}")
            # aplicar highlighting y limpiar errores del archivo anterior
            self._after_load()
        except Exception:
            showerror(title="Oops!", message="Unable to open file...")

    def quit(self):
        if askyesno(title="Quit", message="Are you sure you want to quit?"):
            self.root.destroy()


def main(root, text, menubar, on_content_change=None, clear_errors=None):
    filemenu = Menu(
        menubar, tearoff=0,
        bg="#161B22", fg="white",
        activebackground="#000000", activeforeground="white"
    )
    objFile = File(text, root,
                   on_content_change=on_content_change,
                   clear_errors=clear_errors)

    filemenu.add_command(label="New",        command=objFile.newFile)
    filemenu.add_command(label="Open",       command=objFile.openFile)
    filemenu.add_command(label="Save",       command=objFile.saveFile)
    filemenu.add_command(label="Save As...", command=objFile.saveAs)
    filemenu.add_separator()
    filemenu.add_command(label="Quit",       command=objFile.quit)

    menubar.add_cascade(label="File", menu=filemenu)
    root.config(menu=menubar)

    return objFile


if __name__ == "__main__":
    print("Please run 'main.py'")