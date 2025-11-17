from tree_sitter import Node as TSNode
from typing import Any, Iterable


class TSVisitor:
    def visit(self, node: TSNode) -> Any:
        method = "visit_" + node.type
        visitor = getattr(self, method, self.generic_visit)
        return visitor(node)

    def generic_visit(self, node: TSNode) -> Any:
        results = []
        for child in node.children:
            res = self.visit(child)
            if res:
                if isinstance(res, Iterable):
                    results.extend(res)
                else:
                    results.append(res)

        return results