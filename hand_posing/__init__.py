# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Sanjo Solutions

"""Fit editable Rigify hand controls to mesh surfaces."""

import bpy
from bpy.app.handlers import persistent

from .calibration import HandCalibration, retrieve_selected_rig
from .snap_hand import HandSnap, HandSurface, retrieve_selected_hand, retrieve_snap_solver

__version__ = "0.1.0"


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
                 "convex_hand_snap", "hand_surface_clearance", "skin_finger_refinement"):
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
            setup = self.layout.box()
            setup.label(text="Calibration")
            setup.prop(hand, "hand_on_surface_skin", text="Hand skin")
            setup.operator("hand.calibrate_surface")
            setup.label(text="Captures the hand's rest geometry")
        else:
            self.layout.label(text="Select a Rigify hand IK or finger control")


CLASSES = (HAND_OT_calibrate_surface, HAND_OT_snap, HAND_PT_snap)


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
            if previous:
                bpy.utils.unregister_class(previous)
            bpy.utils.register_class(cls)
    if restore_interface not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(restore_interface)


def unregister():
    if restore_interface in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(restore_interface)
    for cls in reversed(CLASSES):
        previous = cls.__bases__[0].bl_rna_get_subclass_py(cls.__name__)
        if previous == cls:
            bpy.utils.unregister_class(cls)
    for name in ("snap_hand_surface", "hand_on_surface_skin"):
        if hasattr(bpy.types.PoseBone, name):
            delattr(bpy.types.PoseBone, name)
