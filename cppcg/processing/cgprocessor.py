from tree_sitter import Node as TSNode
from typing import Set

import utils
from utils.constants import DefType, GLOBAL_NAME

from .base import ProcessingBase


class CallGraphProcessor(ProcessingBase):
    """Third pass: construct the call graph from the assignment graph.
    
    This processor walks the AST and for each call_expression, it:
    1. Resolves the callee using the assignment graph (via transitive closure)
    2. Adds edges from the current function to all possible callees
    3. Marks external calls (e.g., malloc, printf) as external functions
    """
    
    def __init__(
        self, def_manager, file_manager, func_manager, scope_manager, call_graph
    ):
        super().__init__(def_manager, file_manager, func_manager, scope_manager)
        self.call_graph = call_graph
        self.closured = None
        self.external_funcs = {"malloc", "calloc", "realloc", "free", "printf", "scanf", "sizeof"}
    
    def analyze_code(self, code: str):
        # Compute transitive closure once before traversing
        self.closured = self.def_manager.transitive_closure()
        super().analyze_code(code)
    
    def visit_call_expression(self, node: TSNode):
        """Process a call expression and add call graph edges."""
        func_node = node.child_by_field_name("function")
        if not func_node and node.children:
            func_node = node.children[0]
        if not func_node:
            return
        
        # Resolve the callee(s) using the assignment graph
        callee_vals = self._resolve_callees(func_node)
        
        # Add edges from current function to all possible callees
        caller_ns = self.current_ns
        for callee_ns in callee_vals:
            self._add_call_edge(caller_ns, callee_ns)
        
        # Continue visiting children
        self.generic_visit(node)
    
    def _resolve_callees(self, func_node: TSNode) -> Set[str]:
        """Resolve possible callee namespaces from a function expression.
        
        This uses the precomputed transitive closure to find all possible
        function definitions that the func_node could refer to.
        """
        callees = set()
        
        if func_node.type == "identifier":
            func_name = func_node.text.decode("utf-8").strip()
            
            # Check if it's an external function
            if func_name in self.external_funcs:
                callees.add(f"{GLOBAL_NAME}.{func_name}")
                # Mark it as external
                ext_def = self.def_manager.get(f"{GLOBAL_NAME}.{func_name}")
                if not ext_def:
                    ext_def = self.def_manager.create(f"{GLOBAL_NAME}.{func_name}", DefType.EXT_DEF | DefType.FUNC_DEF)
                return callees
            
            # Resolve through scope manager
            func_def = self.scope_manager.get_def(self.current_ns, func_name)
            if func_def:
                func_ns = func_def.get_ns()
                # Use closure to find all possible targets
                if self.closured and func_ns in self.closured:
                    for target_ns in self.closured[func_ns]:
                        target_def = self.def_manager.get(target_ns)
                        if target_def and target_def.is_function_def():
                            callees.add(target_ns)
                # Also add the direct definition if it's a function
                if func_def.is_function_def():
                    callees.add(func_ns)
        
        elif func_node.type == "field_expression":
            # Handle p->func(...) or obj.method(...)
            field_name = func_node.child_by_field_name("field")
            if not field_name:
                return callees
            
            field_str = field_name.text.decode("utf-8").strip()
            
            # Try to resolve the parent and find the field
            arg_node = func_node.child_by_field_name("argument")
            if arg_node:
                parent_names = self._resolve_parent_names(arg_node)
                for parent_ns in parent_names:
                    field_ns = utils.join_ns(parent_ns, field_str)
                    field_def = self.def_manager.get(field_ns)
                    if field_def:
                        # Use closure to find function targets
                        if self.closured and field_ns in self.closured:
                            for target_ns in self.closured[field_ns]:
                                target_def = self.def_manager.get(target_ns)
                                if target_def and target_def.is_function_def():
                                    callees.add(target_ns)
        
        return callees
    
    def _resolve_parent_names(self, node: TSNode) -> Set[str]:
        """Resolve possible namespaces for a parent expression."""
        names = set()
        
        if node.type == "identifier":
            var_name = node.text.decode("utf-8").strip()
            var_def = self.scope_manager.get_def(self.current_ns, var_name)
            if var_def:
                var_ns = var_def.get_ns()
                names.add(var_ns)
                # Use closure to find all possible targets
                if self.closured and var_ns in self.closured:
                    names.update(self.closured[var_ns])
        
        elif node.type == "field_expression":
            # Recursive field access
            arg_node = node.child_by_field_name("argument")
            field_node = node.child_by_field_name("field")
            if arg_node and field_node:
                field_name = field_node.text.decode("utf-8").strip()
                parent_names = self._resolve_parent_names(arg_node)
                for parent_ns in parent_names:
                    field_ns = utils.join_ns(parent_ns, field_name)
                    names.add(field_ns)
                    if self.closured and field_ns in self.closured:
                        names.update(self.closured[field_ns])
        
        return names
    
    def _add_call_edge(self, caller_ns: str, callee_ns: str):
        """Add an edge to the call graph."""
        if not self.call_graph:
            return
        
        # Don't add self-loops or edges to non-function entities
        if caller_ns == callee_ns:
            return
        
        callee_def = self.def_manager.get(callee_ns)
        if not callee_def:
            # Might be an external function
            if any(ext in callee_ns for ext in self.external_funcs):
                self.call_graph.add_node(callee_ns)
                self.call_graph.add_edge(caller_ns, callee_ns)
            return
        
        if not callee_def.is_function_def():
            return
        
        self.call_graph.add_node(caller_ns)
        self.call_graph.add_node(callee_ns)
        self.call_graph.add_edge(caller_ns, callee_ns)
