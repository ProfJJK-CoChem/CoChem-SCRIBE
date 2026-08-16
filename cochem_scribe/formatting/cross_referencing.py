import warnings
import re

class CircularReferenceWarning(Warning):
    raise NotImplementedError("Implementation pending")
class ReferenceNode:
    def __init__(self, ref_id, text):
        self.ref_id = ref_id
        self.text = text

class RecursiveExpander:
    def __init__(self):
        self.nodes = {}

    def add_node(self, node: ReferenceNode):
        self.nodes[node.ref_id] = node

    def expand(self, ref_id: str) -> str:
        return self._expand(ref_id, set(), [])

    def _expand(self, current_id: str, visited: set, path: list) -> str:
        if current_id not in self.nodes:
            return f"\\ref{{{current_id}}}"

        if current_id in visited:
            warnings.warn(f"Circular reference detected in path: {' -> '.join(path + [current_id])}", CircularReferenceWarning)
            # Break cycle by returning raw string instead of expanding
            return f"\\ref{{{current_id}}}"

        visited.add(current_id)
        path.append(current_id)

        content = self.nodes[current_id].text

        def replacer(match):
            ref_id = match.group(1)
            # Use a copy of visited and path for different branches
            return self._expand(ref_id, visited.copy(), path.copy())

        expanded_content = re.sub(r'\\ref\{([^}]+)\}', replacer, content)
        
        return expanded_content
