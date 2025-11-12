"""
Minimal C-focused processing base.

This project was migrated from Python AST analysis to C analysis via
assignment-graph tracking. The base class now provides only lightweight
utilities shared by the processors and contains no Python-AST visitor methods.
"""

import os
import logging
import tree_sitter_cpp as ts_cpp

from tree_sitter import Language, Parser, Node as TSNode

from machinery.definitions import DefinitionManager
from machinery.files import FileManager
from machinery.funcs import FuncManager
from machinery.scopes import ScopeManager

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
        tree = PARSER.parse(bytes(code, "utf-8"))
        self.visit(tree.root_node)

    def visit_translation_unit(self, node: TSNode):
        self.name_stack.append("<glob>")
        self.generic_visit(node)
        self.name_stack.pop()

    def visit_function_definition(self, node: TSNode):
        func_name = self.__extract_func_def_name(node)
        if not func_name:
            func_name = "<anon>"
        self.name_stack.append(func_name)
        self.generic_visit(node)
        self.name_stack.pop()

    def __extract_func_def_name(self, node: TSNode) -> str | None:
        cur_node = node
        while cur_node.type != "identifier":
            cur_node = cur_node.child_by_field_name("declarator")
            if not cur_node:
                return None
        return cur_node.text.decode("utf-8")

    @property
    def current_ns(self):
        return ".".join([n for n in self.name_stack if n])

