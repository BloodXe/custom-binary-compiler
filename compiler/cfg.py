"""
CFG — Control Flow Graph
Construye el grafo de flujo de control a partir de los bloques básicos
y lo exporta a JSON para visualización web.

Estructura del JSON:
{
  "nodes": [
    { "id": "B1", "label": "B1", "instructions": ["x = 5", ...], "func": "global" }
  ],
  "edges": [
    { "from": "B1", "to": "B2", "type": "fall" }
  ]
}

Tipos de arista:
  "fall"   — caída natural al siguiente bloque (sin salto)
  "jump"   — goto incondicional
  "true"   — rama verdadera de if
  "false"  — rama falsa de if (caída al siguiente bloque)
  "call"   — llamada a función
  "return" — retorno de función
"""

import re
import json
from compiler.basic_blocks import BasicBlock, build_basic_blocks


# ─────────────────────────────────────────────────────────────────────────────
#  Nodo y arista del CFG
# ─────────────────────────────────────────────────────────────────────────────

class CFGNode:
    def __init__(self, block: BasicBlock, func: str = "global"):
        self.id           = block.name          # "B1", "B2", ...
        self.instructions = list(block.lineas)  # copia de las instrucciones
        self.func         = func                # función a la que pertenece
        self.succs        = []                  # lista de CFGEdge salientes
        self.preds        = []                  # lista de CFGEdge entrantes

    def __repr__(self):
        return f"CFGNode({self.id}, func={self.func}, instrs={len(self.instructions)})"


class CFGEdge:
    def __init__(self, src: str, dst: str, kind: str):
        self.src  = src   # id del nodo origen
        self.dst  = dst   # id del nodo destino
        self.kind = kind  # "fall", "jump", "true", "false", "call", "return"

    def __repr__(self):
        return f"CFGEdge({self.src} --{self.kind}--> {self.dst})"


# ─────────────────────────────────────────────────────────────────────────────
#  Constructor del CFG
# ─────────────────────────────────────────────────────────────────────────────

class CFG:
    def __init__(self):
        self.nodes: dict[str, CFGNode] = {}  # id → CFGNode
        self.edges: list[CFGEdge]      = []

    # ── construcción ─────────────────────────────────────────────────────────

    def _add_edge(self, src: str, dst: str, kind: str):
        if src not in self.nodes or dst not in self.nodes:
            return
        edge = CFGEdge(src, dst, kind)
        self.edges.append(edge)
        self.nodes[src].succs.append(edge)
        self.nodes[dst].preds.append(edge)

    def build(self, blocks: list[BasicBlock]) -> "CFG":
        """
        Construye el CFG a partir de la lista de bloques básicos.

        Algoritmo:
          1. Crear un nodo por cada bloque.
          2. Construir un mapa etiqueta → nodo para resolver saltos.
          3. Para cada bloque, analizar su última instrucción:
             - goto L          → arista jump a L
             - if t goto L     → arista true a L + arista false al siguiente
             - iffalse t goto L→ arista false a L + arista true al siguiente
             - return          → arista return al end_func de la función
             - call f, N       → arista call a begin_func de f
             - sin salto       → arista fall al siguiente bloque
        """
        if not blocks:
            return self

        # Paso 1: crear nodos y detectar función de cada bloque
        current_func = "global"
        for block in blocks:
            node = CFGNode(block, func=current_func)
            self.nodes[block.name] = node
            # Actualizar función activa según instrucciones del bloque
            for instr in block.lineas:
                s = instr.strip()
                m = re.match(r'^begin_func\s+(\w+)', s)
                if m:
                    current_func = m.group(1)
                elif s.startswith('end_func'):
                    current_func = "global"
            node.func = current_func if not any(
                re.match(r'^begin_func', i.strip()) for i in block.lineas
            ) else re.search(r'^begin_func\s+(\w+)', 
                             next(i for i in block.lineas 
                                  if re.match(r'^begin_func', i.strip()))
                             ).group(1)

        # Paso 2: mapa etiqueta → id de bloque
        # Una etiqueta es la primera instrucción de un bloque que termina en ':'
        label_to_block: dict[str, str] = {}
        for bid, node in self.nodes.items():
            for instr in node.instructions:
                s = instr.strip()
                if s.endswith(':') and not s.startswith('#') and not s.startswith('LOOP_'):
                    lbl = s[:-1]  # quitar el ':'
                    label_to_block[lbl] = bid
                m = re.match(r'^begin_func\s+(\w+)', s)
                if m:
                    label_to_block[m.group(1)] = bid

        # Paso 3: conectar nodos
        block_list = list(self.nodes.keys())

        for idx, bid in enumerate(block_list):
            node  = self.nodes[bid]
            next_bid = block_list[idx + 1] if idx + 1 < len(block_list) else None

            # Última instrucción ejecutable del bloque
            last = None
            for instr in reversed(node.instructions):
                s = instr.strip()
                if s and not s.startswith('#') and not s.startswith('LOOP_'):
                    last = s
                    break

            if last is None:
                # Bloque vacío → caída natural
                if next_bid:
                    self._add_edge(bid, next_bid, "fall")
                continue

            # goto L
            m = re.match(r'^goto\s+(\w+)$', last)
            if m:
                dst = label_to_block.get(m.group(1))
                if dst:
                    self._add_edge(bid, dst, "jump")
                continue

            # if t goto L  (rama verdadera)
            m = re.match(r'^if\s+\S+\s+goto\s+(\w+)$', last)
            if m:
                dst_true = label_to_block.get(m.group(1))
                if dst_true:
                    self._add_edge(bid, dst_true, "true")
                if next_bid:
                    self._add_edge(bid, next_bid, "false")
                continue

            # iffalse t goto L  (rama falsa)
            m = re.match(r'^iffalse\s+\S+\s+goto\s+(\w+)$', last)
            if m:
                dst_false = label_to_block.get(m.group(1))
                if dst_false:
                    self._add_edge(bid, dst_false, "false")
                if next_bid:
                    self._add_edge(bid, next_bid, "true")
                continue

            # return
            if last.startswith('return'):
                # Conectar al end_func de la función actual
                for other_bid, other_node in self.nodes.items():
                    if any(re.match(r'^end_func\s+' + re.escape(node.func),
                                    i.strip())
                           for i in other_node.instructions):
                        self._add_edge(bid, other_bid, "return")
                        break
                continue

            # call dentro de una asignación: t = call f, N
            m = re.match(r'^\w[\w.]*\s*=\s*call\s+(\w[\w.]*)', last)
            if m:
                func_name = m.group(1)
                dst = label_to_block.get(func_name)
                if dst:
                    self._add_edge(bid, dst, "call")
                # También caída natural al siguiente (para el retorno)
                if next_bid:
                    self._add_edge(bid, next_bid, "fall")
                continue

            # Sin salto → caída natural
            if next_bid:
                self._add_edge(bid, next_bid, "fall")

        return self

    # ── exportación ──────────────────────────────────────────────────────────

    def to_json(self) -> str:
        """Exporta el CFG a JSON para visualización web."""
        nodes = []
        for bid, node in self.nodes.items():
            nodes.append({
                "id":           bid,
                "label":        bid,
                "func":         node.func,
                "instructions": node.instructions,
            })

        edges = []
        for edge in self.edges:
            edges.append({
                "from": edge.src,
                "to":   edge.dst,
                "type": edge.kind,
            })

        return json.dumps({"nodes": nodes, "edges": edges}, indent=2, ensure_ascii=False)

    def to_dot(self) -> str:
        """Exporta el CFG en formato DOT (Graphviz) — útil para debug."""
        lines = ["digraph CFG {", '  node [shape=box fontname="Consolas" fontsize=10]']

        colors = {
            "fall":   "black",
            "jump":   "blue",
            "true":   "green",
            "false":  "red",
            "call":   "purple",
            "return": "orange",
        }

        for bid, node in self.nodes.items():
            label = bid + "\\n" + "\\n".join(
                i.replace('"', '\\"') for i in node.instructions[:6]
            )
            if len(node.instructions) > 6:
                label += f"\\n... (+{len(node.instructions)-6})"
            lines.append(f'  {bid} [label="{label}"]')

        for edge in self.edges:
            color = colors.get(edge.kind, "black")
            lines.append(
                f'  {edge.src} -> {edge.dst} '
                f'[label="{edge.kind}" color="{color}"]'
            )

        lines.append("}")
        return "\n".join(lines)

    def summary(self) -> str:
        """Resumen legible del CFG."""
        lines = [f"CFG: {len(self.nodes)} nodos, {len(self.edges)} aristas"]
        for bid, node in self.nodes.items():
            succs = ", ".join(f"{e.dst}({e.kind})" for e in node.succs)
            preds = ", ".join(e.src for e in node.preds)
            lines.append(
                f"  {bid:4s} [{node.func}]  "
                f"succs=[{succs}]  preds=[{preds}]"
            )
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
#  Función de conveniencia
# ─────────────────────────────────────────────────────────────────────────────

def build_cfg(ir_code: str) -> CFG:
    """Construye el CFG directamente desde el IR como string."""
    blocks = build_basic_blocks(ir_code)
    return CFG().build(blocks)
