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
from typing import Dict, Optional

import utils
from .definitions import Definition

class ScopeItem(object):
    def __init__(self, fullns, parent):
        if parent and not isinstance(parent, ScopeItem):
            raise ScopeError("Parent must be a ScopeItem instance")

        if not isinstance(fullns, str):
            raise ScopeError("Namespace should be a string")

        self.parent = parent
        self.defs: Dict[str, Definition] = {}
        self.lambda_counter = 0
        self.struct_counter = 0
        self.field_counter = 0
        self.fullns = fullns

    def get_ns(self) -> str:
        return self.fullns

    def get_defs(self) -> Dict[str, Definition]:
        return self.defs

    def get_def(self, name) -> Optional[Definition]:
        defs = self.get_defs()
        if name in defs:
            return defs[name]

    def get_lambda_counter(self) -> int:
        return self.lambda_counter

    def get_struct_counter(self) -> int:
        return self.struct_counter

    def get_field_counter(self) -> int:
        return self.field_counter

    def inc_lambda_counter(self, val=1) -> int:
        self.lambda_counter += val
        return self.lambda_counter

    def inc_struct_counter(self, val=1) -> int:
        self.struct_counter += val
        return self.struct_counter

    def inc_field_counter(self, val=1) -> int:
        self.field_counter += val
        return self.field_counter

    def reset_counters(self):
        self.lambda_counter = 0
        self.struct_counter = 0
        self.field_counter = 0

    def add_def(self, name: str, defi: Definition):
        self.defs[name] = defi

    def merge_def(self, name: str, to_merge: Definition):
        if name not in self.defs:
            self.defs[name] = to_merge
            return

        self.defs[name].merge(to_merge)


class ScopeError(Exception):
    pass


class ScopeManager(object):
    """Manages the scope entries"""

    def __init__(self):
        self.scopes: Dict[str, ScopeItem] = {}

    # called when init funciton or struct or var
    def handle_assign(self, ns: str, target: str, defi: Definition):
        scope = self.get_scope(ns)
        if scope:
            scope.add_def(target, defi)

    def get_def(self, current_ns: str, var_name: str) -> Optional[Definition]:
        current_scope = self.get_scope(current_ns)
        while current_scope:
            defi = current_scope.get_def(var_name)
            if defi:
                return defi
            current_scope = current_scope.parent

    def get_scope(self, namespace) -> Optional[ScopeItem]:
        if namespace in self.get_scopes():
            return self.get_scopes()[namespace]

    def create_scope(self, namespace: str, parent) -> ScopeItem:
        if namespace not in self.scopes:
            sc = ScopeItem(namespace, parent)
            self.scopes[namespace] = sc
        return self.scopes[namespace]

    def get_scopes(self) -> Dict[str, ScopeItem]:
        return self.scopes


