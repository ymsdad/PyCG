from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Set, Optional

import os
import tempfile
import subprocess
from tree_sitter import Parser, Language
import re

from .visitor import TSVisitor


def _node_text(source: bytes, node) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="ignore")


def _render_name(source: bytes, node) -> Optional[str]:
    """Render a readable dotted name from C expressions.

    Supports identifiers and nested field expressions (a->b, a.b).
    """
    if node.type == "identifier":
        return _node_text(source, node)
    if node.type == "field_expression":
        base = node.child_by_field_name("argument") or node.child_by_field_name("object")
        field = node.child_by_field_name("field")
        if base is None or field is None:
            return None
        base_name = _render_name(source, base)
        field_name = _node_text(source, field)
        if base_name is None:
            return None
        return f"{base_name}.{field_name}"
    return None


@dataclass
class CAssignmentVisitor(TSVisitor):
    source: bytes
    # LHS like Func.var.field -> {identifier}
    assignments: Dict[str, Set[str]] = field(default_factory=dict)
    # Direct calls: Func -> {callee}
    direct_calls: Dict[str, Set[str]] = field(default_factory=dict)
    # Attribute calls: Func -> {dotted attribute like var.field}
    attr_calls: Dict[str, Set[str]] = field(default_factory=dict)
    # Discovered function definitions
    functions: Set[str] = field(default_factory=set)
    current_function: Optional[str] = None

    def visit_function_definition(self, node):
        # Extract function name from declarator chain
        name = None
        # Walk to the deepest identifier under the declarator
        declarator = None
        for child in node.children:
            if child.type in {"function_declarator", "pointer_declarator", "declarator"}:
                declarator = child
                break
        cur = declarator
        while cur is not None:
            if cur.type == "identifier":
                name = _node_text(self.source, cur)
                break
            # prefer named children
            nxt = cur.child_by_field_name("declarator") or cur.child_by_field_name("declarator1")
            if nxt is None and cur.children:
                # fallback: descend to the last child
                nxt = cur.children[-1]
            if nxt is cur:
                break
            cur = nxt

        prev = self.current_function
        if name:
            self.current_function = name
            self.functions.add(name)
        # visit body
        for ch in node.children:
            self.visit(ch)
        self.current_function = prev

    def visit_assignment_expression(self, node):
        if not self.current_function:
            return
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        if left is None or right is None:
            return
        # we only care about field_expression on the LHS and identifier on RHS
        if left.type != "field_expression" or right.type != "identifier":
            return
        lhs_name = _render_name(self.source, left)
        rhs_name = _node_text(self.source, right)
        if not lhs_name or not rhs_name:
            return
        key = f"{self.current_function}.{lhs_name}"
        self.assignments.setdefault(key, set()).add(rhs_name)

    # allow expression_statements to be traversed
    def visit_expression_statement(self, node):
        for ch in node.children:
            self.visit(ch)

    def visit_call_expression(self, node):
        if not self.current_function:
            return
        func_node = node.child_by_field_name("function")
        if func_node is None:
            # grammar variance: take first child
            func_node = node.children[0] if node.children else None
        if func_node is None:
            return
        if func_node.type == "identifier":
            callee = _node_text(self.source, func_node)
            if callee:
                self.direct_calls.setdefault(self.current_function, set()).add(callee)
        elif func_node.type == "field_expression":
            dotted = _render_name(self.source, func_node)
            if dotted:
                self.attr_calls.setdefault(self.current_function, set()).add(dotted)


_C_LANG: Optional[Language] = None


def _ensure_c_language() -> Language:
    global _C_LANG
    if _C_LANG is not None:
        return _C_LANG

    # Allow tests/CI to skip building the grammar and use the regex fallback.
    if os.environ.get("TS_C_DISABLE_BUILD") == "1":
        raise RuntimeError("Tree-sitter C build disabled via TS_C_DISABLE_BUILD=1")

    # Try loading a cached compiled language
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
    build_dir = os.path.join(repo_root, ".ts_build")
    os.makedirs(build_dir, exist_ok=True)
    lib_path = os.path.join(build_dir, "c-languages.so")

    if not os.path.exists(lib_path):
        # Fetch the C grammar and build the shared library
        with tempfile.TemporaryDirectory() as tmp:
            gram_dir = os.path.join(tmp, "tree-sitter-c")
            subprocess.run([
                "git", "clone", "--depth", "1",
                "https://github.com/tree-sitter/tree-sitter-c.git", gram_dir,
            ], check=True)
            Language.build_library(lib_path, [gram_dir])

    _C_LANG = Language(lib_path, "c")
    return _C_LANG


@dataclass
class CAnalysisResult:
    assignments: Dict[str, Set[str]]
    direct_calls: Dict[str, Set[str]]
    attr_calls: Dict[str, Set[str]]
    functions: Set[str]


def analyze_c_file_full(path: str) -> CAnalysisResult:
    """Analyze a C source file and return field assignment mapping.

    Returns a dict mapping dotted LHS names within function scope to the set
    of RHS identifiers assigned to them.
    Example key: 'PyImaging_Jpeg2KDecoderNew.decoder.decode'
    """
    with open(path, "rb") as f:
        source = f.read()

    try:
        lang = _ensure_c_language()
        parser = Parser(lang)
        tree = parser.parse(source)

        visitor = CAssignmentVisitor(source)
        visitor.visit(tree.root_node)
        return CAnalysisResult(
            assignments=visitor.assignments,
            direct_calls=visitor.direct_calls,
            attr_calls=visitor.attr_calls,
            functions=visitor.functions,
        )
    except Exception:
        # Fallback: simple regex-based extraction when language build is unavailable.
        text = source.decode("utf-8", errors="ignore")
        assignments: Dict[str, Set[str]] = {}
        direct_calls: Dict[str, Set[str]] = {}
        attr_calls: Dict[str, Set[str]] = {}
        functions: Set[str] = set()
        # Very loose patterns for function starts and assignments with pointer deref
        func_re = re.compile(r"^\s*(?:[\w\*\s]+)?\b(\w+)\s*\([^;]*\)\s*\{", re.M)
        assign_re = re.compile(r"([A-Za-z_][A-Za-z0-9_\-\>\.]*)\s*=\s*([A-Za-z_][A-Za-z0-9_]*)\s*;")
        call_re = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(")
        attr_call_re = re.compile(r"([A-Za-z_][A-Za-z0-9_]*(?:\.|\->)[A-Za-z_][A-Za-z0-9_]*)\s*\(")

        for m in func_re.finditer(text):
            func_name = m.group(1)
            functions.add(func_name)
            # crude block slice
            start = m.end()
            brace = 1
            i = start
            while i < len(text) and brace > 0:
                if text[i] == "{":
                    brace += 1
                elif text[i] == "}":
                    brace -= 1
                i += 1
            body = text[start:i]
            for am in assign_re.finditer(body):
                lhs, rhs = am.groups()
                if "->" not in lhs and "." not in lhs:
                    continue
                dotted_lhs = lhs.replace("->", ".").replace("-", "")
                key = f"{func_name}.{dotted_lhs}"
                assignments.setdefault(key, set()).add(rhs)
            for cm in attr_call_re.finditer(body):
                dotted = cm.group(1).replace("->", ".")
                attr_calls.setdefault(func_name, set()).add(dotted)
            for dm in call_re.finditer(body):
                callee = dm.group(1)
                # Skip if it's the attr_call matched
                if "." in callee:
                    continue
                direct_calls.setdefault(func_name, set()).add(callee)
        return CAnalysisResult(
            assignments=assignments,
            direct_calls=direct_calls,
            attr_calls=attr_calls,
            functions=functions,
        )


def analyze_c_file(path: str) -> Dict[str, Set[str]]:
    """Backwards-compatible helper returning only assignment mapping."""
    return analyze_c_file_full(path).assignments
