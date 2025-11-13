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
# This file has been modified from the original.
# Modifications Copyright (c) 2025 [Your Name/Company]
#
# Changes:
# - The `to_mod_name` function was improved to correctly convert file paths 
#   into module names, especially for compiled shared object (`.so`) files.
import os
from typing import Optional
from tree_sitter import Node

def get_lambda_name(counter):
    return "<lambda{}>".format(counter)

def get_struct_name(counter):
    return "<struct{}>".format(counter)

def get_field_name(counter):
    return "<field{}>".format(counter)


def get_int_name(counter):
    return "<int{}>".format(counter)


def join_ns(*args):
    return ".".join([arg for arg in args])


def to_mod_name(name, package=None):
    name_parts = name.split(os.path.sep)
    # This is for shared objects
    if len(name_parts) > 0:
        name_parts[-1] = name_parts[-1].split(".")[0]

    return ".".join(name_parts)

def fetch_first_node_by_type(node: Node, types: list[str]) -> Optional[Node]:
    cursor = node.walk()
    visited_children = False
    while True:
        if not visited_children:
            node = cursor.node
            if node.type in types:
                return node
        if not visited_children and cursor.goto_first_child():
            visited_children = False
            continue
        if cursor.goto_next_sibling():
            visited_children = False
            continue
        if not cursor.goto_parent():
            break
        else:
            visited_children = True
    