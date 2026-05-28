# menu de edicion: copiar, cortar, pegar, deshacer, buscar, etc.
from tkinter import END, INSERT, SEL, SEL_FIRST, SEL_LAST, Menu, TclError
from tkinter.simpledialog import askstring


class Edit:
    def __init__(self, text, root):
        self.text       = text
        self.root       = root
        self.rightClick = Menu(root, tearoff=0)  # menu contextual al hacer click derecho

    def popup(self, event):
        # muestro el menu contextual en la posicion del click
        self.rightClick.tk_popup(event.x_root, event.y_root)

    def copy(self, *args):
        try:
            self.text.event_generate("<<Copy>>")
        except TclError:
            pass

    def cut(self, *args):
        try:
            self.text.event_generate("<<Cut>>")
        except TclError:
            pass

    def paste(self, *args):
        try:
            self.text.event_generate("<<Paste>>")
        except TclError:
            pass

    def selectAll(self, *args):
        self.text.tag_add(SEL, "1.0", END)
        self.text.mark_set(INSERT, "1.0")
        self.text.see(INSERT)
        return "break"

    def undo(self, *args):
        try:
            self.text.edit_undo()
        except TclError:
            pass
        return "break"

    def redo(self, *args):
        try:
            self.text.edit_redo()
        except TclError:
            pass
        return "break"

    def find(self, *args):
        # busco texto en el editor y resalto todas las coincidencias
        self.text.tag_remove("found", "1.0", END)
        target = askstring("Find", "Search String:")
        if target:
            idx = "1.0"
            while True:
                idx = self.text.search(target, idx, nocase=True, stopindex=END)
                if not idx:
                    break
                lastidx = f"{idx}+{len(target)}c"
                self.text.tag_add("found", idx, lastidx)
                idx = lastidx
            self.text.tag_config("found", foreground="white", background="blue")


def main(root, text, menubar):
    objEdit  = Edit(text, root)
    editmenu = Menu(menubar, tearoff=0,
                    bg="#161B22", fg="white",
                    activebackground="#000000", activeforeground="white")

    editmenu.add_command(label="Copy",       command=objEdit.copy,      accelerator="Ctrl+C")
    editmenu.add_command(label="Cut",        command=objEdit.cut,       accelerator="Ctrl+X")
    editmenu.add_command(label="Paste",      command=objEdit.paste,     accelerator="Ctrl+V")
    editmenu.add_command(label="Undo",       command=objEdit.undo,      accelerator="Ctrl+Z")
    editmenu.add_command(label="Redo",       command=objEdit.redo,      accelerator="Ctrl+Y")
    editmenu.add_command(label="Find",       command=objEdit.find,      accelerator="Ctrl+F")
    editmenu.add_separator()
    editmenu.add_command(label="Select All", command=objEdit.selectAll, accelerator="Ctrl+A")
    menubar.add_cascade(label="Edit", menu=editmenu)

    # atajos de teclado globales
    root.bind_all("<Control-z>", objEdit.undo)
    root.bind_all("<Control-y>", objEdit.redo)
    root.bind_all("<Control-f>", objEdit.find)
    root.bind_all("<Control-a>", objEdit.selectAll)

    # opciones del menu contextual (click derecho)
    objEdit.rightClick.add_command(label="Copy",       command=objEdit.copy)
    objEdit.rightClick.add_command(label="Cut",        command=objEdit.cut)
    objEdit.rightClick.add_command(label="Paste",      command=objEdit.paste)
    objEdit.rightClick.add_separator()
    objEdit.rightClick.add_command(label="Select All", command=objEdit.selectAll)

    text.bind("<Button-3>", objEdit.popup)
    root.config(menu=menubar)


if __name__ == "__main__":
    print("Please run 'main.py'")
