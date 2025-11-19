#
# Copyright (c) 2020 Vitalis Salis.
#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#
# MODIFIED:
# Adapted from PyCG to analyze C code using tree-sitter.
# Modifications Copyright (c) 2025
#
import os

from .machinery.callgraph import CallGraph
from .machinery.definitions import DefinitionManager
from .machinery.scopes import ScopeManager
from .machinery.files import FileManager
from .machinery.funcs import FuncManager
from .processing.cgprocessor import CallGraphProcessor
from .processing.postprocessor import PostProcessor
from .processing.preprocessor import PreProcessor


class CallGraphGenerator(object):
    """Generate call graphs for C code.
    
    Performs multi-pass analysis:
    1. PreProcessor: discover definitions and build scope tree
    2. PostProcessor: perform assignment analysis (fixed-point iteration)
    3. CallGraphProcessor: construct call graph from assignment graph
    """
    
    def __init__(self, entry_points, package, max_iter):
        self.entry_points = [os.path.abspath(x) for x in entry_points]
        self.package = os.path.abspath(package) if package else None
        self.state = None
        self.max_iter = max_iter
        self.files_whitelist = []
        
        # Collect C files
        if package:
            for root, _, files in os.walk(package):
                for file in files:
                    if file.endswith((".c", ".h")):
                        self.files_whitelist.append(os.path.abspath(os.path.join(root, file)))
        
        self.setUp()

    def setUp(self):
        self.scope_manager = ScopeManager()
        self.def_manager = DefinitionManager()
        self.file_manager = FileManager()
        self.func_manager = FuncManager()
        self.cg = CallGraph()

    def extract_state(self):
        state = {}
        state["defs"] = {}
        for key, defi in self.def_manager.get_defs().items():
            state["defs"][key] = {
                "names": defi.get_name_pointer().get().copy(),
                "lit": defi.get_lit_pointer().get().copy(),
            }

        state["scopes"] = {}
        for key, scope in self.scope_manager.get_scopes().items():
            state["scopes"][key] = set([
                x.get_ns() for (_, x) in scope.get_defs().items()
            ])

        return state

    def reset_counters(self):
        for key, scope in self.scope_manager.get_scopes().items():
            scope.reset_counters()

    def has_converged(self):
        if not self.state:
            return False

        curr_state = self.extract_state()

        # check defs
        for key, defi in curr_state["defs"].items():
            if key not in self.state["defs"]:
                return False
            if defi["names"] != self.state["defs"][key]["names"]:
                return False
            if defi["lit"] != self.state["defs"][key]["lit"]:
                return False

        # check scopes
        for key, scope in curr_state["scopes"].items():
            if key not in self.state["scopes"]:
                return False
            if scope != self.state["scopes"][key]:
                return False

        return True

    def tearDown(self):
        pass

    def do_pass(self, cls, *args, **kwargs):
        """Run a processor pass on all entry points."""
        for entry_point in self.entry_points:
            input_file = os.path.abspath(entry_point)
            
            if not os.path.exists(input_file):
                print(f"Warning: {input_file} does not exist")
                continue
            
            # Read the C file
            try:
                with open(input_file, "r") as f:
                    code = f.read()
            except Exception as e:
                print(f"Error reading {input_file}: {e}")
                continue
            
            processor = cls(*args, **kwargs)
            processor.analyze_code(code)

    def analyze(self):
        """Run the full analysis pipeline."""
        # Pass 1: PreProcessor - discover definitions
        self.do_pass(
            PreProcessor,
            self.def_manager,
            self.file_manager,
            self.func_manager,
            self.scope_manager,
        )
        self.def_manager.complete_definitions()

        # Pass 2: PostProcessor - assignment analysis (fixed-point iteration)
        iter_cnt = 0
        while (self.max_iter < 0 or iter_cnt < self.max_iter) and (
            not self.has_converged()
        ):
            self.state = self.extract_state()
            self.reset_counters()
            self.do_pass(
                PostProcessor,
                self.def_manager,
                self.file_manager,
                self.func_manager,
                self.scope_manager,
            )

            self.def_manager.complete_definitions()
            iter_cnt += 1

        # Pass 3: CallGraphProcessor - construct call graph
        self.reset_counters()
        self.do_pass(
            CallGraphProcessor,
            self.def_manager,
            self.file_manager,
            self.func_manager,
            self.scope_manager,
            call_graph=self.cg,
        )

    def output(self):
        """Return the call graph as a dictionary."""
        return self.cg.get()

    def output_edges(self):
        """Return the call graph edges as a list of [src, dst] pairs."""
        return self.cg.get_edges()

    def output_functions(self):
        """Return all function definitions."""
        functions = []
        for ns, defi in self.def_manager.get_defs().items():
            if defi.is_function_def():
                functions.append(ns)
        return functions

    def get_as_graph(self):
        """Return the assignment graph (definitions)."""
        return self.def_manager.get_defs().items()
