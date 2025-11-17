from tree_sitter import Node as TSNode
from typing import Optional, List, Tuple, Union

import utils
from machinery.definitions import Definition
from utils.constants import DefType, RETURN_NAME

from .base import ProcessingBase

IDefinition = Union[str, Definition]

class PostProcessor(ProcessingBase):
    def __init__(
        self, *args, **kwargs
    ):
        super().__init__(*args, **kwargs)

    def visit_call_expression(self, node: TSNode) -> Definition:
        pass

    def visit_assignment_expression(self, node: TSNode):
        leftns = self.__resolve_asignee_ns(node.child_by_field_name("left"))
        

    def visit_return_statement(self, node: TSNode):
        leftns = utils.join_ns(self.current_ns, RETURN_NAME)
        

    def visit_init_declarator(self, node: TSNode):
        decl_node = node.child_by_field_name("declarator")
        if decl_node:
            decl_name, _= self._visit_decl_decl(decl_node)
        else:
            field_counter = self.scope_manager.get_scope(self.current_ns).inc_field_counter()
            decl_name = utils.get_field_name(field_counter)
        leftns = utils.join_ns(self.current_ns, decl_name)
        


    def visit_field_expression(self, node: TSNode) -> Definition:
        pass

    def visit_pointer_expression(self, node: TSNode) -> IDefinition:
        return self.visit(node.child_by_field_name("argument"))

    def visit_binary_expression(self, node: TSNode) -> IDefinition:
        left = self.visit(node.child_by_field_name("left"))
        right = self.visit(node.child_by_field_name("right"))
        if isinstance(left, Definition):
            return left
        elif isinstance(right, Definition):
            return right
        return left


    def __resolve_asignee_ns(self, node: TSNode) -> str:
        if node.type == "identifier":
            id_name = node.text.decode("utf-8").strip()
            defi = self.scope_manager.get_def(self.current_ns, id_name)
            if not defi:
                defi, _ = self._create_def_and_scope(id_name, DefType.NAME_DEF)
            return defi.get_ns()
        elif node.type == "field_expression":
            parent_ns = self.__resolve_asignee_ns(node.child_by_field_name("argument"))
            field_name = node.child_by_field_name("field").text.decode("utf-8").strip()
            _, field_defi = self._create_def_and_scope(
                field_name, DefType.NAME_DEF, parent_ns=parent_ns)
            return field_defi.get_ns()
        elif node.type == "pointer_expression":
            return self.__resolve_asignee_ns(node.child_by_field_name("argument"))
        elif node.type == "subscript_expression":
            return self.__resolve_asignee_ns(node.child_by_field_name("argument"))
        elif node.type == "parenthesized_expression":
            return self.__resolve_asignee_ns(node.children[1])
        elif node.type == "call_expression":
            return self.visit_call_expression(node).get_ns()
        return f"{self.current_ns}.<anon>"
            

    def __handle_assign(self, leftns: str, right: IDefinition):
        defi = self.def_manager.get(leftns)
        if not defi:
            defi, _ = self._create_def_and_scope(leftns, DefType.NAME_DEF)
        if isinstance(right, str):
            defi.get_lit_pointer().add(right)
        elif isinstance(right, Definition):
            defi.get_name_pointer().add(right.get_ns())