# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Sanjo Solutions

"""Persistent bone aiming, evaluated by Blender's native dependency graph."""

import math


CONSTRAINT_NAME = "Hand Posing Follow"


def retrieve_follow(bone):
    constraint = bone.constraints.get(CONSTRAINT_NAME)
    return constraint if constraint and constraint.type == "DAMPED_TRACK" else None


def retrieve_follows(rig):
    for bone in rig.pose.bones:
        constraint = retrieve_follow(bone)
        if constraint:
            yield bone, constraint


def bone_dependencies(rig, bone, ignored):
    """Follow parents and native bone targets, including existing rig controls."""
    if bone.parent:
        yield rig, bone.parent
    for constraint in bone.constraints:
        if constraint == ignored:
            continue
        targets = constraint.targets if constraint.type == "ARMATURE" else (constraint,)
        for item in targets:
            target = getattr(item, "target", None)
            name = getattr(item, "subtarget", "")
            if target and target.type == "ARMATURE" and name in target.pose.bones:
                yield target, target.pose.bones[name]


def set_follow(rig, source_name, target_rig, target_name, offset=0., original_source=""):
    """Validate before changing anything; keep the native constraint as the data."""
    if not rig or rig.type != "ARMATURE" or source_name not in rig.pose.bones:
        raise ValueError("Choose an existing bone A on the selected armature")
    if not target_rig or target_rig.type != "ARMATURE" or target_name not in target_rig.pose.bones:
        raise ValueError("Choose a target armature and an existing bone B")
    if not math.isfinite(offset) or not 0 <= offset <= 1:
        raise ValueError("Offset must be between 0 and 1")
    if rig == target_rig and source_name == target_name:
        raise ValueError("A bone cannot follow itself")

    source = rig.pose.bones[source_name]
    original = rig.pose.bones.get(original_source) if original_source else None
    previous = retrieve_follow(original) if original else None
    if original_source and previous is None:
        raise ValueError("The relationship no longer exists")
    collision = source.constraints.get(CONSTRAINT_NAME)
    if collision and collision != previous:
        raise ValueError("Bone A already has a follow relationship or a constraint with its reserved name")

    pending = [(target_rig, target_rig.pose.bones[target_name])]
    visited = set()
    while pending:
        obj, bone = pending.pop()
        key = (obj.as_pointer(), bone.name)
        if key in visited:
            continue
        visited.add(key)
        if obj == rig and bone == source:
            raise ValueError("This relationship would create a circular bone dependency")
        pending.extend(bone_dependencies(obj, bone, previous))

    constraint = previous if original == source else source.constraints.new("DAMPED_TRACK")
    constraint.name = CONSTRAINT_NAME
    constraint.target = target_rig
    constraint.subtarget = target_name
    constraint.head_tail = offset
    constraint.track_axis = "TRACK_Y"
    constraint.owner_space = constraint.target_space = "WORLD"
    constraint.use_bbone_shape = False
    if previous and original != source:
        original.constraints.remove(previous)
    return constraint


def remove_follow(rig, source_name):
    bone = rig.pose.bones.get(source_name)
    constraint = retrieve_follow(bone) if bone else None
    if constraint is None:
        return False
    bone.constraints.remove(constraint)
    return True
