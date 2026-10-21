# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Sanjo Solutions

"""Identify meshes driven by a control rig or its following deformation rig."""


def uses_rig(mesh, rig):
    for modifier in mesh.modifiers:
        if modifier.type == "ARMATURE" and modifier.object:
            deform = modifier.object
            if deform == rig or any(getattr(constraint, "target", None) == rig
                                    for bone in deform.pose.bones for constraint in bone.constraints):
                return True
    return False
