# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Sanjo Solutions

"""Fit editable Rigify hand controls to mesh surfaces."""

import bpy
from bpy.app.handlers import persistent

from .calibration import HandCalibration, retrieve_selected_rig
from .snap_hand import HandSnap, HandSurface, retrieve_selected_hand, retrieve_snap_solver

__version__ = "0.1.0"

FINGER_ITEMS = tuple((identifier, label, "Move this finger into this group", 1 << index)
                     for index, (identifier, label) in enumerate((
                         ("thumb", "Thumb"), ("f_index", "Index"), ("f_middle", "Middle"),
                         ("f_ring", "Ring"), ("f_pinky", "Pinky"))))


def update_group_members(group, _context):
    """Enforce exclusive membership for UI edits and direct RNA assignments."""
    rig = group.id_data
    if not rig or rig.type != "ARMATURE":
        return
    for bone in rig.pose.bones:
        groups = bone.hand_posing_finger_groups
        if any(other.as_pointer() == group.as_pointer() for other in groups):
            for other in groups:
                if other.as_pointer() != group.as_pointer() and other.fingers & group.fingers:
                    other.fingers = other.fingers - group.fingers
            break


class HAND_PG_finger_group(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Group name", default="Group", options=set())
    fingers: bpy.props.EnumProperty(name="Fingers", items=FINGER_ITEMS,
                                    options={"ENUM_FLAG"}, update=update_group_members)


class HAND_OT_add_finger_group(bpy.types.Operator):
    bl_idname = "hand.add_finger_group"
    bl_label = "Add Group"
    bl_description = "Create a finger group for the selected hand"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return retrieve_selected_rig(context) is not None

    def execute(self, context):
        rig, side = retrieve_selected_rig(context)
        groups = rig.pose.bones[f"hand_ik.{side}"].hand_posing_finger_groups
        names = {group.name for group in groups}
        number = 1
        while f"Group {number}" in names:
            number += 1
        groups.add().name = f"Group {number}"
        return {"FINISHED"}


class HAND_OT_remove_finger_group(bpy.types.Operator):
    bl_idname = "hand.remove_finger_group"
    bl_label = "Remove Group"
    bl_description = "Remove this group and release its fingers"
    bl_options = {"REGISTER", "UNDO"}

    index: bpy.props.IntProperty(default=-1, options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return retrieve_selected_rig(context) is not None

    def execute(self, context):
        rig, side = retrieve_selected_rig(context)
        groups = rig.pose.bones[f"hand_ik.{side}"].hand_posing_finger_groups
        if not 0 <= self.index < len(groups):
            return {"CANCELLED"}
        groups.remove(self.index)
        return {"FINISHED"}


def retrieve_source_revision():
    """Return the SHA-256 of the current package's Python sources."""
    import hashlib
    from pathlib import Path
    digest = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        if not path.name.startswith("test_"):
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def reload_for_development():
    """Load edited solver files for the next interactive refinement."""
    import importlib
    import sys
    for name in ("rig_binding", "calibration", "snap_hand", "resting_hand_rectangle",
                 "convex_hand_snap", "hand_surface_clearance", "skin_finger_refinement", "finger_groups"):
        qualified = __name__ + "." + name
        if qualified in sys.modules:
            importlib.reload(sys.modules[qualified])
    solver = sys.modules[__name__ + ".snap_hand"]
    for name in ("HandSnap", "HandSurface", "retrieve_selected_hand", "retrieve_snap_solver"):
        globals()[name] = getattr(solver, name)
    globals()["HandCalibration"] = sys.modules[__name__ + ".calibration"].HandCalibration
    register()


class HAND_OT_calibrate_surface(bpy.types.Operator):
    bl_idname = "hand.calibrate_surface"
    bl_label = "Calibrate Hand"
    bl_description = "Measure the selected hand's palm and finger pads from its skin"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return retrieve_selected_rig(context) is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event, message="Capture this hand's contact calibration from its rest skin?")

    def execute(self, context):
        rig, side = retrieve_selected_rig(context)
        hand = rig.pose.bones[f"hand_ik.{side}"]
        try:
            HandCalibration(context, rig, side, hand.hand_on_surface_skin).capture()
        except (ValueError, KeyError, RuntimeError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        self.report({"INFO"}, "Hand calibration saved")
        return {"FINISHED"}


class HAND_OT_snap(bpy.types.Operator):
    bl_idname = "hand.snap"
    bl_label = "Snap Hand"
    bl_description = "Fit the selected palm and fingers to the surface with editable IK controls"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return retrieve_selected_hand(context) is not None

    def execute(self, context):
        rig, side = retrieve_selected_hand(context)
        try:
            solver = retrieve_snap_solver(context, rig, side)
            solver.snap(solver.hand.snap_hand_surface, context.scene.tool_settings.use_keyframe_insert_auto)
        except (ValueError, KeyError, RuntimeError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Snapped {rig.name} hand {side}")
        return {"FINISHED"}


class HAND_PT_snap(bpy.types.Panel):
    bl_label = "Hand Posing"
    bl_idname = "HAND_PT_snap"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Item"

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == "ARMATURE" and context.mode == "POSE"

    def draw(self, context):
        selected = retrieve_selected_rig(context)
        if selected:
            rig, side = selected
            hand = rig.pose.bones[f"hand_ik.{side}"]
            self.layout.prop(hand, "snap_hand_surface", text="Surface")
            self.layout.operator("hand.snap")
            grouping = self.layout.column()
            grouping.label(text="Finger groups")
            for index, group in enumerate(hand.hand_posing_finger_groups):
                box = grouping.box()
                row = box.row(align=True)
                row.prop(group, "name", text="")
                row.operator("hand.remove_finger_group", text="", icon="X").index = index
                members = box.column_flow(columns=2, align=True)
                for identifier, label, _description, _value in FINGER_ITEMS:
                    members.prop_enum(group, "fingers", identifier, text=label)
            grouping.operator("hand.add_finger_group", icon="ADD")
            if hand.hand_posing_finger_groups:
                grouping.label(text="Select fingers, then Snap Hand")
            setup = self.layout.box()
            setup.label(text="Calibration")
            setup.prop(hand, "hand_on_surface_skin", text="Hand skin")
            setup.operator("hand.calibrate_surface")
            setup.label(text="Captures the hand's rest geometry")
        else:
            self.layout.label(text="Select a Rigify hand IK or finger control")


CLASSES = (HAND_PG_finger_group, HAND_OT_add_finger_group, HAND_OT_remove_finger_group,
           HAND_OT_calibrate_surface, HAND_OT_snap, HAND_PT_snap)


@persistent
def restore_interface(_document):
    """Use the enabled extension's operators after loading a saved helper scene."""
    register()


def register():
    for name in ("snap_hand_surface", "hand_on_surface_skin"):
        if not hasattr(bpy.types.PoseBone, name):
            setattr(bpy.types.PoseBone, name, bpy.props.PointerProperty(
                name="Surface" if name == "snap_hand_surface" else "Hand skin", type=bpy.types.Object,
                poll=lambda _bone, obj: obj.type == "MESH"))
    for cls in CLASSES:
        previous = cls.__bases__[0].bl_rna_get_subclass_py(cls.__name__)
        if previous != cls:
            if cls == HAND_PG_finger_group and hasattr(bpy.types.PoseBone, "hand_posing_finger_groups"):
                del bpy.types.PoseBone.hand_posing_finger_groups
            if previous:
                bpy.utils.unregister_class(previous)
            bpy.utils.register_class(cls)
    if not hasattr(bpy.types.PoseBone, "hand_posing_finger_groups"):
        bpy.types.PoseBone.hand_posing_finger_groups = bpy.props.CollectionProperty(
            name="Finger groups", type=HAND_PG_finger_group)
    if restore_interface not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(restore_interface)


def unregister():
    if restore_interface in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(restore_interface)
    if hasattr(bpy.types.PoseBone, "hand_posing_finger_groups"):
        del bpy.types.PoseBone.hand_posing_finger_groups
    for cls in reversed(CLASSES):
        previous = cls.__bases__[0].bl_rna_get_subclass_py(cls.__name__)
        if previous == cls:
            bpy.utils.unregister_class(cls)
    for name in ("snap_hand_surface", "hand_on_surface_skin"):
        if hasattr(bpy.types.PoseBone, name):
            delattr(bpy.types.PoseBone, name)
