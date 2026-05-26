from tkinter import END
from tkinter import Menu
from tkinter.filedialog import askopenfile, asksaveasfile
from tkinter.messagebox import askyesno, showerror


class File:
    def __init__(self, text, root):
        self.filename = None
        self.text = text
        self.root = root

    def newFile(self):
        self.filename = None
        self.root.title("TextEditor - Untitled")
        self.text.delete("1.0", END)

    def saveFile(self):
        if not self.filename:
            self.saveAs()
            return

        try:
            with open(self.filename, "w", encoding="utf-8") as f:
                f.write(self.text.get("1.0", END))
        except Exception:
            showerror(title="Oops!", message="Unable to save file...")

    def saveAs(self):
        f = asksaveasfile(mode="w", defaultextension=".txt", filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if f is None:
            return

        try:
            with f:
                f.write(self.text.get("1.0", END).rstrip())
            self.filename = f.name
            self.root.title(f"TextEditor - {self.filename}")
        except Exception:
            showerror(title="Oops!", message="Unable to save file...")

    def openFile(self):
        f = askopenfile(mode="r", filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if f is None:
            return

        try:
            with f:
                self.filename = f.name
                content = f.read()
            self.text.delete("1.0", END)
            self.text.insert("1.0", content)
            self.root.title(f"TextEditor - {self.filename}")
        except Exception:
            showerror(title="Oops!", message="Unable to open file...")

    def quit(self):
        if askyesno(title="Quit", message="Are you sure you want to quit?"):
            self.root.destroy()


def main(root, text, menubar):
    filemenu = Menu(
        menubar,
        tearoff=0,
        bg="#161B22",
        fg="white",
        activebackground="#000000",
        activeforeground="white"
    )
    
    objFile = File(text, root)

    filemenu.add_command(label="New", command=objFile.newFile)
    filemenu.add_command(label="Open", command=objFile.openFile)
    filemenu.add_command(label="Save", command=objFile.saveFile)
    filemenu.add_command(label="Save As...", command=objFile.saveAs)
    filemenu.add_separator()
    filemenu.add_command(label="Quit", command=objFile.quit)

    menubar.add_cascade(label="File", menu=filemenu)
    root.config(menu=menubar)


if __name__ == "__main__":
    print("Please run 'main.py'")
