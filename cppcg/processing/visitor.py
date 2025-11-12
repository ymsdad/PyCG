from tree_sitter import Node as TSNode
from typing import Any


class TSVisitor:
    def visit(self, node: TSNode) -> Any:
        method = "visit_" + node.type
        visitor = getattr(self, method, self.generic_visit)
        return visitor(node)

    def generic_visit(self, node: TSNode) -> None:
        for child in node.children:
            self.visit(child)
