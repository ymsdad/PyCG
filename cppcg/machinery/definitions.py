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
import utils
from utils.constants import DefType, RETURN_NAME, UNKNOWN_RET_TYPE
from machinery.pointers import LiteralPointer, NamePointer, Pointer
from typing import Dict, Optional


class Definition(object):
    def __init__(self, fullns: str, def_type: DefType):
        self.fullns = fullns
        self.points_to: Dict[str, Pointer] = {"lit": LiteralPointer(), "name": NamePointer()}
        self.def_type = def_type

    def get_type(self):
        return self.def_type

    def is_function_def(self):
        return self.def_type & DefType.FUNC_DEF

    def is_ext_def(self):
        return self.def_type & DefType.EXT_DEF

    def is_callable(self):
        return not (self.def_type & (DefType.NAME_DEF | DefType.TYPE_DEF))

    def is_struct_def(self):
        return self.def_type & DefType.TYPE_DEF

    def get_lit_pointer(self):
        return self.points_to["lit"]

    def get_name_pointer(self) -> NamePointer:
        return self.points_to["name"]

    def get_name(self):
        return self.fullns.split(".")[-1]

    def get_ns(self):
        return self.fullns

    def merge(self, to_merge):
        for name, pointer in to_merge.points_to.items():
            self.points_to[name].merge(pointer)


class DefinitionError(Exception):
    pass


class DefinitionManager(object):
    def __init__(self):
        self.defs: Dict[str, Definition] = {}

    def create(self, ns: str, def_type: DefType) -> Definition:
        if self.get(ns):
            raise DefinitionError("Definition already exists")
        self.defs[ns] = Definition(ns, def_type)
        return self.defs[ns]

    def assign(self, ns: str, defi: Definition) -> Definition:
        self.defs[ns] = Definition(ns, defi.get_type())
        self.defs[ns].merge(defi)

        # if it is a function def, we need to create a return pointer
        if defi.is_function_def():
            return_ns = utils.join_ns(ns, RETURN_NAME)
            self.defs[return_ns] = Definition(return_ns, DefType.NAME_DEF)
            self.defs[return_ns].get_name_pointer().add(
                utils.join_ns(defi.get_ns(), RETURN_NAME)
            )

        return self.defs[ns]

    def get(self, ns) -> Optional[Definition]:
        if ns in self.defs:
            return self.defs[ns]

    def get_defs(self) -> Dict[str, Definition]:
        return self.defs

    def transitive_closure(self):
        closured = {}

        def dfs(defi: Definition):
            name_pointer = defi.get_name_pointer()
            new_set = set()
            # bottom
            if closured.get(defi.get_ns(), None) is not None:
                return closured[defi.get_ns()]

            if not name_pointer.get():
                new_set.add(defi.get_ns())

            closured[defi.get_ns()] = new_set

            for name in name_pointer.get():
                if not self.defs.get(name, None):
                    continue
                items = dfs(self.defs[name])
                if not items:
                    items = set([name])
                new_set.update(items)

            closured[defi.get_ns()] = new_set
            return closured[defi.get_ns()]

        for ns, current_def in self.defs.items():
            if closured.get(ns, None) is None:
                dfs(current_def)

        return closured

    def complete_definitions(self):
        # THE MOST expensive part of this tool's process
        # TODO: IMPROVE COMPLEXITY
        def update_pointsto_args(pointsto_args: set[str], args: set[str], name: str):
            changed_something = False
            if update_pointsto_args == pointsto_args:
                return False
            for pointsto_arg in pointsto_args:
                if not self.defs.get(pointsto_arg, None):
                    continue
                if pointsto_arg == name:
                    continue
                pointsto_arg_def = self.defs[pointsto_arg].get_name_pointer()
                if pointsto_arg_def == pointsto_args:
                    continue

                # sometimes we may end up with a cycle
                if pointsto_arg in args:
                    args.remove(pointsto_arg)

                for item in args:
                    if item not in pointsto_arg_def.get():
                        if self.defs.get(item, None) is not None:
                            changed_something = True
                    # HACK: this check shouldn't be needed
                    # if we remove this the following breaks:
                    # x = lambda x: x + 1
                    # x(1)
                    # since on line 184 we don't discriminate between
                    # literal values and name values
                    if not self.defs.get(item, None):
                        continue
                    pointsto_arg_def.add(item)
            return changed_something

        for _ in range(len(self.defs)):
            changed_something = False
            for ns, current_def in self.defs.items():
                # the name pointer of the definition we're currently iterating
                current_name_pointer: NamePointer = current_def.get_name_pointer()
                # iterate the names the current definition points to items
                # for name in current_name_pointer.get():
                for name in current_name_pointer.get().copy():
                    # get the name pointer of the points to name
                    if not self.defs.get(name, None):
                        continue
                    if name == ns:
                        continue

                    pointsto_name_pointer: NamePointer = self.defs[name].get_name_pointer()
                    # iterate the arguments of the definition
                    # we're currently iterating
                    for arg_name, arg in current_name_pointer.get_args().items():
                        pos = current_name_pointer.get_pos_of_name(arg_name)
                        if pos is not None:
                            pointsto_args = pointsto_name_pointer.get_pos_arg(pos)
                            if not pointsto_args:
                                pointsto_name_pointer.add_pos_arg(pos, None, arg)
                                continue
                        else:
                            pointsto_args = pointsto_name_pointer.get_arg(arg_name)
                            if not pointsto_args:
                                pointsto_name_pointer.add_arg(arg_name, arg)
                                continue
                        changed_something = changed_something or update_pointsto_args(
                            pointsto_args, arg, current_def.get_ns()
                        )

            if not changed_something:
                break
