# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Sanjo Solutions

"""Capture Rigify hand contact geometry from an evaluated skinned mesh."""

import json
import math

from mathutils import Matrix

from .rig_binding import uses_rig

FINGERS = ("f_index", "f_middle", "f_ring", "f_pinky", "thumb")
CALIBRATION_PROPERTY = "Snap Hand Calibration"


def serialize_matrix(matrix):
    return [value for row in matrix for value in row]


def retrieve_selected_rig(context):
    rig, bone = context.object, context.active_pose_bone
    if rig and rig.type == "ARMATURE" and context.mode == "POSE" and bone:
        side = bone.name.rsplit(".", 1)[-1]
        if side in {"L", "R"} and f"hand_ik.{side}" in rig.pose.bones:
            if bone.name.startswith(("hand_", "f_index", "f_middle", "f_ring", "f_pinky", "thumb", "palm")):
                return rig, side
    return None


class HandCalibration:
    """Own the measurements for one hand; commit them after a complete capture."""

    def __init__(self, context, rig, side, skin):
        self.context, self.rig, self.side, self.skin = context, rig, side, skin

    def capture(self):
        armatures = {self.rig, *[modifier.object for modifier in self.skin.modifiers
                                if modifier.type == "ARMATURE" and modifier.object]} if self.skin else {self.rig}
        positions = {rig: rig.data.pose_position for rig in armatures}
        try:
            for rig in positions:
                rig.data.pose_position = "REST"
            self.context.view_layer.update()
            calibration = self.capture_geometry()
        finally:
            for rig, position in positions.items():
                rig.data.pose_position = position
            self.context.view_layer.update()
        return calibration

    def capture_geometry(self):
        rig, side, skin = self.rig, self.side, self.skin
        if skin and skin.type == "MESH" and uses_rig(skin, rig):
            required = [f"hand_ik.{side}", f"DEF-hand.{side}", f"upper_arm_parent.{side}",
                        *[f"{finger}.{segment:02}.{side}" for finger in FINGERS for segment in (1, 2, 3)]]
            missing = [name for name in required if name not in rig.pose.bones]
            if missing:
                raise ValueError("Use a standard Rigify hand with controls: " + ", ".join(missing))
            if "IK_FK" not in rig.pose.bones[f"upper_arm_parent.{side}"]:
                raise ValueError("Use a Rigify arm with an IK_FK property")
            mesh = skin.evaluated_get(self.context.evaluated_depsgraph_get())
            self.vertices = [(mesh.matrix_world @ vertex.co,
                              {weight.group: weight.weight for weight in vertex.groups})
                             for vertex in mesh.data.vertices]
            palm_groups = [group.name for group in skin.vertex_groups
                           if group.name.endswith("." + side) and group.name.startswith(("DEF-hand", "DEF-palm"))]
            points = self.retrieve_points(palm_groups)
            if len(points) < 4:
                raise ValueError("Choose a skin with weighted palm vertices")
            hand = rig.matrix_world @ rig.data.bones[f"DEF-hand.{side}"].matrix_local
            middle = rig.matrix_world @ rig.data.bones[f"f_middle.01.{side}"].matrix_local
            index = rig.matrix_world @ rig.data.bones[f"f_index.01.{side}"].matrix_local
            pinky = rig.matrix_world @ rig.data.bones[f"f_pinky.01.{side}"].matrix_local
            heading = middle.translation - hand.translation
            normal = (index.translation - pinky.translation).cross(heading)
            if normal.length < 1e-6:
                raise ValueError("Pose the hand with distinct wrist and knuckle positions")
            normal.normalize()
            if normal.dot(middle.to_3x3().col[2]) > 0:
                normal.negate()
            heading -= normal * heading.dot(normal)
            if heading.length < 1e-6:
                raise ValueError("Pose the hand with a clear wrist-to-finger direction")
            heading.normalize()
            palm = Matrix((heading.cross(normal), heading, normal)).transposed().to_4x4()
            palm.translation = hand.translation
            inverse = palm.inverted()
            cells = {}
            spacing = max(rig.data.bones[f"DEF-hand.{side}"].length / 6, 0.001)
            for point in points:
                local = inverse @ point
                cell = tuple(round(local[axis] / spacing) for axis in (0, 1))
                if cell not in cells or local.z < cells[cell].z:
                    cells[cell] = local
            support = [list(point) for point in cells.values()]
            fingers = {f"{finger}.{segment:02}.{side}": self.retrieve_finger(finger, segment)
                       for finger in FINGERS for segment in (1, 2, 3)}
            calibration = {"wrist": serialize_matrix(inverse @ hand), "support": support,
                           "fingers": fingers, "skin": skin.name, "schema_version": 1,
                           "contact_geometry": "skin"}
            rig.pose.bones[f"hand_ik.{side}"][CALIBRATION_PROPERTY] = json.dumps(calibration)
            rig.pose.bones[f"hand_ik.{side}"].hand_on_surface_skin = skin
            return calibration
        else:
            raise ValueError("Choose a mesh driven by the selected Rigify rig")

    def retrieve_points(self, names):
        groups = {self.skin.vertex_groups[name].index for name in names if name in self.skin.vertex_groups}
        return [point for point, weights in self.vertices
                if sum(weights.get(group, 0) for group in groups) > 0.25]

    def retrieve_finger(self, finger, segment):
        name = f"{finger}.{segment:02}.{self.side}"
        bone = self.rig.data.bones[name]
        if segment > 1:
            parent = self.rig.data.bones[f"{finger}.{segment - 1:02}.{self.side}"]
        else:
            parent = bone.parent.parent if bone.parent and bone.parent.parent else bone.parent
            if parent is None:
                raise ValueError("Use a finger control with a Rigify parent: " + name)
        rest = parent.matrix_local.inverted() @ bone.matrix_local
        points = self.retrieve_points(["DEF-" + name])
        if len(points) < 4:
            raise ValueError("Choose a skin with weighted vertices for " + name)
        inverse = (self.rig.matrix_world @ bone.matrix_local).inverted()
        local = [inverse @ point for point in points]
        depths = []
        for fraction in (0.25, 0.5, 0.75, 1.0):
            nearby = sorted(local, key=lambda point: abs(point.y / bone.length - fraction))[:max(4, len(local) // 4)]
            depths.append(max(point.z for point in nearby))
        if segment == 1:
            opposition = (-85, 85)
            ranges = ((-60, 60), opposition, (-45, 45)) if finger == "thumb" else ((-25, 90), (0, 0), (-20, 20))
        else:
            bend = math.degrees(rest.to_euler("XYZ").x)
            extension, flexion = ((-10, 70) if segment == 2 else (-20, 90)) if finger == "thumb" else ((0, 110) if segment == 2 else (-5, 90))
            ranges = ((extension - bend, flexion - bend), (0, 0), (0, 0))
        return {"finger": finger, "segment": segment, "parent": parent.name,
                "rest": serialize_matrix(rest),
                "bounds": [[math.radians(value) for value in bounds] for bounds in ranges],
                "samples": [[0, bone.length * fraction, depth]
                            for fraction, depth in zip((0.25, 0.5, 0.75, 1.0), depths)], "depths": depths,
                "skin_vertices": [index for index, (_point, weights) in enumerate(self.vertices)
                                  if weights.get(self.skin.vertex_groups["DEF-" + name].index, 0) > .25]}
