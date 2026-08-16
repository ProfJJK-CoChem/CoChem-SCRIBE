import warnings

class CircularASTWarning(Warning):
    raise NotImplementedError("Implementation pending")
class ASTNode:
    def __init__(self, name, children=None):
        self.name = name
        self.children = children if children is not None else []

def find_cycles_tarjan(root):
    index = 0
    stack = []
    indices = {}
    lowlinks = {}
    on_stack = set()
    cycles = []
    parent_map = {}

    def strongconnect(node):
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)

        for child in node.children:
            parent_map[child] = node
            if child not in indices:
                strongconnect(child)
                lowlinks[node] = min(lowlinks[node], lowlinks[child])
            elif child in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[child])

        if lowlinks[node] == indices[node]:
            cycle = []
            while True:
                w = stack.pop()
                on_stack.remove(w)
                cycle.append(w)
                if w == node:
                    break
            if len(cycle) > 1 or (node in node.children):
                cycles.append(cycle)

    strongconnect(root)
    return cycles, parent_map

def process_and_render_ast(root):
    cycles, parent_map = find_cycles_tarjan(root)
    
    broken_edges = set()
    if cycles:
        warnings.warn("Circular dependency detected in AST.", CircularASTWarning)
        for cycle in cycles:
            # We break the edge from the last visited node in the cycle
            # To do this simply, we will just take the last element in the cycle 
            # and break the edge to the first element that is also in the cycle.
            for node in cycle:
                for child in node.children:
                    if child in cycle:
                        broken_edges.add((id(node), id(child)))
                        # Only break one edge per cycle to prevent all edges from breaking
                        break
                else:
                    continue
                break
    
    def render_ast(node, visited=None):
        if visited is None:
            visited = set()

        html = f"<div class='ast-node' id='{id(node)}'><span>{node.name}</span>"
        html += "<ul>"
        
        for child in node.children:
            if (id(node), id(child)) in broken_edges:
                html += "<li>"
                html += f"<div class='ast-node ast-cycle-broken' id='{id(child)}'><span style='color: red; border: 1px dotted red;'>[Cycle Broken] {child.name}</span></div>"
                html += "</li>"
            else:
                html += "<li>"
                html += render_ast(child, visited)
                html += "</li>"
            
        html += "</ul></div>"
        return html

    return render_ast(root)
