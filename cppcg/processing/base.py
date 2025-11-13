"""
Minimal C-focused processing base.

This project was migrated from Python AST analysis to C analysis via
assignment-graph tracking. The base class now provides only lightweight
utilities shared by the processors and contains no Python-AST visitor methods.
"""

import logging
import tree_sitter_cpp as ts_cpp

from tree_sitter import Language, Parser, Node as TSNode
from typing import Set, Tuple
from machinery.definitions import Definition, DefinitionManager
from machinery.files import FileManager
from machinery.funcs import FuncManager
from machinery.scopes import ScopeManager,ScopeItem

import utils
from utils.constants import GLOBAL_NAME, RETURN_NAME, INVALID_NAME, DefType

from .visitor import TSVisitor


logger = logging.getLogger(__name__)
CPP_LANG = Language(ts_cpp.language())
PARSER = Parser(CPP_LANG)

class ProcessingBase(TSVisitor):
    def __init__(
        self, fill_rel: str,
        def_manager: DefinitionManager,
        file_manager: FileManager,
        func_manager: FuncManager,
        scope_manager: ScopeManager
    ):
        self.file_rel = fill_rel

        self.def_manager = def_manager
        self.file_manager = file_manager
        self.func_manager = func_manager
        self.scope_manager = scope_manager
        self.name_stack = []

    def analyze(self):
        file_abs = self.file_manager.file_abs_path(self.file_rel)
        try:
            with open(file_abs, "r") as fr:
                code = fr.read()
        except Exception as e:
            print(f"Failed to read file {file_abs}: {e}")
            return
        self.analyze_code(code)
    
    def analyze_code(self, code: str):
        tree = PARSER.parse(bytes(code, "utf-8"))
        self.visit(tree.root_node)

    def visit_translation_unit(self, node: TSNode):
        self.name_stack.append(GLOBAL_NAME)
        self.generic_visit(node)
        self.name_stack.pop()

    def visit_function_definition(self, node: TSNode):
        func_name, _ = self._visit_decl_decl(node.child_by_field_name("declarator"))
        if not func_name:
            func_name = "<anon>"
        self.name_stack.append(func_name)
        self.generic_visit(node.child_by_field_name("body"))
        self.name_stack.pop()

    def _visit_decl_decl(self, node: TSNode) -> Tuple[str, bool]:
        if node.type == "identifier":
            return node.text.decode("utf-8").strip(), False
        elif node.type == "field_identifier":
            return node.text.decode("utf-8").strip(), False
        elif node.type == "type_identifier":
            return node.text.decode("utf-8").strip(), False
        elif node.type == "pointer_declarator":
            return self._visit_decl_decl(node.child_by_field_name("declarator"))
        elif node.type == "init_declarator":
            return self._visit_decl_decl(node.child_by_field_name("declarator"))
        elif node.type == "function_declarator":
            return self._visit_decl_decl(node.child_by_field_name("declarator"))[0], True
        elif node.type == "parenthesized_declarator":
            declarator_node = node.children[-2]
            return self._visit_decl_decl(declarator_node)

    def visit_struct_specifier(self, node: TSNode) -> str:
        name_node = node.child_by_field_name("name")
        if name_node:
            struct_name = name_node.text.decode("utf-8").strip()
        else: 
            struct_counter = self.scope_manager.get_scope(self.current_ns).inc_struct_counter()
            struct_name = utils.get_struct_name(struct_counter)
        body_node = node.child_by_field_name("body")
        if body_node:
            self.name_stack.append(struct_name)
            self.visit(body_node)
            self.name_stack.pop()

        return struct_name

    def visit_union_specifier(self, node: TSNode) -> str:
        return self.visit_struct_specifier(node)

    def visit_lambda_expression(self, node: TSNode, lambda_name = None):
        if lambda_name is None:
            lambda_counter = self.scope_manager.get_scope(self.current_ns).inc_lambda_counter()
            lambda_name = utils.get_lambda_name(lambda_counter)

        self.name_stack.append(lambda_name)
        self.generic_visit(node.child_by_field_name("body"))
        self.name_stack.pop()

    def _create_def_and_scope(self, target_name: str, def_type: DefType) -> Tuple[Definition, ScopeItem]:
        parent_sc = self.scope_manager.get_scope(self.current_ns)
        target_ns = utils.join_ns(self.current_ns, target_name)
        sc = self.scope_manager.create_scope(target_ns, parent_sc)
        defi = self.def_manager.get(target_ns)
        if not defi:
            defi = self.def_manager.create(target_ns, def_type)
        parent_sc.add_def(target_name, defi)
        return defi, sc

    def _create_global_def_and_scope(self, target_name: str, def_type: DefType) -> Tuple[Definition, ScopeItem]:
        parent_sc = self.scope_manager.get_scope(GLOBAL_NAME)
        target_ns = utils.join_ns(GLOBAL_NAME, target_name)
        sc = self.scope_manager.create_scope(target_ns, parent_sc)
        defi = self.def_manager.get(target_ns)
        if not defi:
            defi = self.def_manager.create(target_ns, def_type)
        parent_sc.add_def(target_name, defi)
        return defi, sc

    @property
    def current_ns(self):
        return ".".join([n for n in self.name_stack if n])


    def _decode_node(self, node: TSNode) -> str | Definition:
        if node.type == "identifier":
            id_name = node.text.decode("utf-8")
            return [self.scope_manager.get_def(self.current_ns, id_name)]
        elif node.type == "pointer_expression":
            return self._decode_node(node.child_by_field_name("argument"))
        elif node.type == "filed_expression":
            names = self._retrieve_attribute_names(node)
            defis = []
            for name in names:
                defi = self.def_manager.get(name)
                if defi:
                    defis.append(defi)
            return defis
        elif node.type == "number_literal":
            return [node.text.decode("utf-8")]
        elif node.type == "string_literal":
            return [node.text.decode("utf-8").strip('"')]
        elif node.type == "char_literal":
            return [node.text.decode("utf-8").strip("'")]
        elif node.type == "binary_expression":
            left = self._decode_node(node.child_by_field_name("left"))
            if left and isinstance(left[0], str | Definition):
                return left
            right = self._decode_node(node.child_by_field_name("right"))
            if right and isinstance(right[0], str | Definition):
                return right
        elif node.type == "lambda_expression":
            lambda_counter = self.scope_manager.get_scope(self.current_ns).inc_lambda_counter()
            lambda_name = utils.get_lambda_name(lambda_counter)
            ret_ns = utils.join_ns(self.current_ns, lambda_name, RETURN_NAME)
            return [self.def_manager.get(self.current_ns, ret_ns)]
        elif node.type == "call_expression":
            decoded = self._decode_node(node.child_by_field_name("function"))
            return_defs = []
            for called_def in decoded:
                if not isinstance(called_def, Definition):
                    continue
                return_ns = INVALID_NAME
                if called_def.get_type() & DefType.FUNC_DEF:
                    return_ns = utils.join_ns(called_def.get_ns(), RETURN_NAME)
                defi = self.def_manager.get(return_ns)
                if defi:
                    return_defs.append(defi)
            return return_defs

    def _retrieve_parent_names(self, node: TSNode):
        decoded = self._decode_node(nodev)
        if not decoded:
            return set()

        names = set()
        for parent in decoded:
            if not parent or not isinstance(parent, Definition):
                continue
            if getattr(self, "closured", None) and self.closured.get(
                parent.get_ns(), None
            ):
                names = names.union(self.closured.get(parent.get_ns()))
            else:
                names.add(parent.get_ns())
        return names

    def _retrieve_attribute_names(self, node: TSNode) -> Set[str]:
        if not getattr(self, "closured", None):
            return set()
        pass
