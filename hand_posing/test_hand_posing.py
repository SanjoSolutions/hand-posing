# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise the public addon against generated, redistributable Blender data."""

import importlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

import bpy
from mathutils import Matrix, Vector


def retrieve_addon():
    installed = next((name for name in bpy.context.preferences.addons.keys()
                      if name.endswith(".hand_posing")), None)
    if installed:
        return importlib.import_module(installed)
    if "hand_posing" in sys.modules:
        return sys.modules["hand_posing"]
    directory = Path(__file__).resolve().parent
    specification = importlib.util.spec_from_file_location("hand_posing", directory / "__init__.py",
                                                          submodule_search_locations=[str(directory)])
    addon = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = addon
    specification.loader.exec_module(addon)
    return addon


ADDON = retrieve_addon()


def create_fixture():
    """Create a Rigify-shaped hand fixture with native evaluated skin deformation."""
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    armature = bpy.data.armatures.new("Example armature")
    rig = bpy.data.objects.new("Example character", armature)
    bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    for side, offset in (("L", -0.2), ("R", 0.2)):
        def add(name, head, tail, parent=None):
            bone = armature.edit_bones.new(name + "." + side)
            bone.head, bone.tail = head, tail
            if parent:
                bone.parent = armature.edit_bones[parent + "." + side]
            return bone
        add("upper_arm_parent", (offset, -0.2, 0), (offset, -0.1, 0))
        add("hand_ik", (offset, 0, 0), (offset, .09, 0))
        add("DEF-hand", (offset, 0, 0), (offset, .09, 0))
        for index, finger in enumerate(("f_index", "f_middle", "f_ring", "f_pinky", "thumb")):
            x = offset + (index - 1.5) * .018
            for segment in (1, 2, 3):
                name = f"{finger}.{segment:02}"
                parent = "DEF-hand" if segment == 1 else f"{finger}.{segment - 1:02}"
                head = (x, .09 + (segment - 1) * .025, 0)
                tail = (x, .09 + segment * .025, 0)
                add(name, head, tail, parent)
                add("DEF-" + name, head, tail)
    bpy.ops.object.mode_set(mode="OBJECT")
    for bone in armature.bones:
        if bone.name.startswith("DEF-"):
            pose = rig.pose.bones[bone.name]
            constraint = pose.constraints.new("COPY_TRANSFORMS")
            constraint.target = rig
            constraint.subtarget = bone.name.replace("DEF-hand", "hand_ik") if bone.name.startswith("DEF-hand") else bone.name[4:]
    skin = create_skin(rig)
    for side in ("L", "R"):
        rig.pose.bones[f"upper_arm_parent.{side}"]["IK_FK"] = 1.0
    bpy.context.view_layer.update()
    return rig, skin


def create_skin(rig):
    vertices, faces, groups = [], [], {}
    for bone in rig.data.bones:
        if bone.name.startswith(("DEF-hand.", "DEF-f_", "DEF-thumb.")):
            indices = []
            width = .035 if bone.name.startswith("DEF-hand") else .007
            frame = bone.matrix_local.copy()
            length = bone.length
            if bone.name.startswith("DEF-hand"):
                side = bone.name.rsplit(".", 1)[1]
                middle = rig.data.bones[f"f_middle.01.{side}"].head_local
                across = (rig.data.bones[f"f_index.01.{side}"].head_local
                          - rig.data.bones[f"f_pinky.01.{side}"].head_local)
                heading = (middle - bone.head_local).normalized()
                normal = across.cross(heading).normalized()
                if normal.dot(rig.data.bones[f"f_middle.01.{side}"].matrix_local.to_3x3().col[2]) < 0:
                    normal.negate()
                frame = Matrix((heading.cross(normal), heading, normal)).transposed().to_4x4()
                frame.translation = bone.head_local
                length = (middle - bone.head_local).length
                width = across.length * .6
            for y in (0, .25, .5, .75, 1):
                base = len(vertices)
                for x, z in ((-width, -.006), (width, -.006), (width, .006), (-width, .006)):
                    indices.append(len(vertices))
                    vertices.append(frame @ Vector((x, length * y, z)))
                if y:
                    for index in range(4):
                        faces.append((base - 4 + index, base - 4 + (index + 1) % 4,
                                      base + (index + 1) % 4, base + index))
            groups[bone.name] = indices
    mesh = bpy.data.meshes.new("Example skin")
    mesh.from_pydata(vertices, [], faces)
    skin = bpy.data.objects.new("Example skin", mesh)
    bpy.context.scene.collection.objects.link(skin)
    for name, indices in groups.items():
        skin.vertex_groups.new(name=name).add(indices, 1, "REPLACE")
    modifier = skin.modifiers.new("Rig deformation", "ARMATURE")
    modifier.object = rig
    bpy.context.view_layer.update()
    return skin


class HandPosingTests(unittest.TestCase):
    def setUp(self):
        if bpy.types.Panel.bl_rna_get_subclass_py("HAND_PT_snap") is None:
            ADDON.register()
        self.rig, self.skin = create_fixture()

    def select_hand(self, side):
        bpy.context.view_layer.objects.active = self.rig
        if self.rig.mode == "OBJECT":
            bpy.ops.object.mode_set(mode="POSE")
        self.rig.data.bones.active = self.rig.data.bones[f"hand_ik.{side}"]
        return self.rig.pose.bones[f"hand_ik.{side}"]

    def calibrate(self, side):
        hand = self.select_hand(side)
        hand.hand_on_surface_skin = self.skin
        original_position = self.rig.data.pose_position
        original_pose = {bone.name: bone.matrix_basis.copy() for bone in self.rig.pose.bones}
        self.assertEqual(bpy.ops.hand.calibrate_surface(), {"FINISHED"})
        self.assertEqual(self.rig.data.pose_position, original_position)
        self.assertLess(max(abs(first - second) for bone in self.rig.pose.bones
                            for row, other in zip(bone.matrix_basis, original_pose[bone.name])
                            for first, second in zip(row, other)), .000001)
        return hand

    def test_calibration_and_selection_for_both_hands(self):
        for side in ("L", "R"):
            with self.subTest(side=side):
                hand = self.calibrate(side)
                calibration = json.loads(hand["Snap Hand Calibration"])
                self.assertEqual(len(calibration["fingers"]), 15)
                self.assertGreaterEqual(len(calibration["support"]), 4)
                self.assertEqual(calibration["skin"], self.skin.name)
                self.assertEqual(ADDON.retrieve_selected_hand(bpy.context), (self.rig, side))

    def test_snap_operator_and_auto_keying(self):
        for side in ("L", "R"):
            with self.subTest(side=side):
                hand = self.calibrate(side)
                self.skin.name = "Renamed example skin"
                bpy.ops.object.mode_set(mode="OBJECT")
                bpy.ops.mesh.primitive_plane_add(size=2, location=(0, 0, .02))
                target = bpy.context.object
                target.rotation_euler.x = 3.141592653589793
                bpy.context.view_layer.update()
                self.select_hand(side)
                hand.snap_hand_surface = target
                bpy.context.scene.tool_settings.use_keyframe_insert_auto = True
                self.assertEqual(bpy.ops.hand.snap(), {"FINISHED"})
                evaluated = self.rig.evaluated_get(bpy.context.evaluated_depsgraph_get())
                position = evaluated.pose.bones[f"DEF-hand.{side}"].matrix.translation
                self.assertGreater(position.z, .005)
                self.assertLess(position.z, .025)
                self.assertEqual(self.rig.pose.bones[f"upper_arm_parent.{side}"]["IK_FK"], 0.0)
                action = self.rig.animation_data.action
                paths = {curve.data_path for layer in action.layers for strip in layer.strips
                         for bag in strip.channelbags for curve in bag.fcurves}
                self.assertIn(f'pose.bones["hand_ik.{side}"].location', paths)
                self.assertIn(f'pose.bones["f_index.03.{side}"].rotation_quaternion', paths)
                bpy.context.scene.tool_settings.use_keyframe_insert_auto = False
                bpy.ops.object.mode_set(mode="OBJECT")

    def test_existing_calibration_and_saved_file_playback(self):
        import tempfile
        from unittest.mock import patch
        hand = self.calibrate("R")
        original = hand["Snap Hand Calibration"]
        skin_name = self.skin.name
        with tempfile.TemporaryDirectory() as directory:
            bpy.ops.wm.save_as_mainfile(filepath=str(Path(directory) / "example.blend"))
            with patch.object(ADDON, "register") as registration:
                bpy.ops.wm.open_mainfile(filepath=str(Path(directory) / "example.blend"))
            registration.assert_not_called()
            rig = bpy.data.objects["Example character"]
            self.assertEqual(rig.pose.bones["hand_ik.R"]["Snap Hand Calibration"], original)
            self.assertIs(bpy.types.Panel.bl_rna_get_subclass_py("HAND_PT_snap"), ADDON.HAND_PT_snap)
            self.assertTrue(bpy.ops.hand.snap.get_rna_type())
            self.assertEqual(rig.pose.bones["hand_ik.R"].hand_on_surface_skin, bpy.data.objects[skin_name])
            solver = ADDON.retrieve_snap_solver(bpy.context, rig, "R")
            self.assertEqual(len(solver.calibration["fingers"]), 15)

    def test_reach_failure_restores_authored_controls(self):
        hand = self.calibrate("R")
        original_pose = hand.matrix_basis.copy()
        parent = self.rig.pose.bones["upper_arm_parent.R"]
        original_blend = parent["IK_FK"]
        limit = self.rig.pose.bones["DEF-hand.R"].constraints.new("LIMIT_LOCATION")
        limit.use_min_z = limit.use_max_z = True
        limit.min_z = limit.max_z = 0
        limit.owner_space = "WORLD"
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.mesh.primitive_plane_add(size=2, location=(0, 0, .04))
        target = bpy.context.object
        target.rotation_euler.x = 3.141592653589793
        bpy.context.view_layer.update()
        solver = ADDON.retrieve_snap_solver(bpy.context, self.rig, "R")
        with self.assertRaises(ValueError):
            solver.snap(target)
        self.assertEqual(parent["IK_FK"], original_blend)
        self.assertLess(max(abs(first - second) for row, other in zip(hand.matrix_basis, original_pose)
                            for first, second in zip(row, other)), .000001)

    def test_registration_cycle(self):
        ADDON.unregister()
        self.assertIsNone(bpy.types.Panel.bl_rna_get_subclass_py("HAND_PT_snap"))
        self.assertFalse(hasattr(bpy.types.PoseBone, "snap_hand_surface"))
        self.assertFalse(hasattr(bpy.types.PoseBone, "hand_on_surface_skin"))
        ADDON.register()
        self.assertTrue(hasattr(bpy.types.PoseBone, "snap_hand_surface"))
        self.assertTrue(bpy.ops.hand.snap.get_rna_type())

    def test_generated_rigify_hand_calibration(self):
        import addon_utils
        if self.rig.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        self.assertIsNotNone(addon_utils.enable("rigify", default_set=True))
        bpy.ops.object.armature_human_metarig_add()
        bpy.ops.pose.rigify_generate()
        self.rig = bpy.context.object
        self.skin = create_skin(self.rig)
        for side in ("L", "R"):
            control = self.rig.pose.bones[f"hand_ik.{side}"]
            shoulder = self.rig.pose.bones[f"ORG-upper_arm.{side}"].head
            pose = control.matrix.copy()
            pose.translation += (shoulder - pose.translation).normalized() * .1
            control.matrix = pose
            self.rig.pose.bones[f"upper_arm_parent.{side}"]["IK_FK"] = 0.0
            self.rig.update_tag()
            bpy.context.view_layer.update()
            hand = self.calibrate(side)
            solver = ADDON.retrieve_snap_solver(bpy.context, self.rig, side)
            self.assertEqual(solver.skin.object, self.skin)
            self.assertEqual(len(json.loads(hand["Snap Hand Calibration"])["fingers"]), 15)
            palm = solver.retrieve_hand_pose() @ solver.wrist.inverted()
            normal = palm.to_3x3().col[2].normalized()
            bpy.ops.object.mode_set(mode="OBJECT")
            bpy.ops.mesh.primitive_plane_add(size=2, location=palm.translation - normal * .015)
            target = bpy.context.object
            target.rotation_mode = "QUATERNION"
            target.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(normal)
            bpy.context.view_layer.update()
            solver.snap(target)
            surface = ADDON.HandSurface(target, bpy.context.evaluated_depsgraph_get(), self.rig, side)
            self.assertLess(solver.skin.retrieve_penetration(surface), .002)
            evaluated = self.skin.evaluated_get(bpy.context.evaluated_depsgraph_get())
            indices = {index for calibration in solver.calibration["fingers"].values()
                       for index in calibration["skin_vertices"]}
            gaps = []
            for index in indices:
                point = evaluated.matrix_world @ evaluated.data.vertices[index].co
                nearest, normal = surface.retrieve_nearest(point)
                gaps.append((point - nearest).dot(normal))
            self.assertGreaterEqual(min(gaps), -.002)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(HandPosingTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise RuntimeError("Hand Posing validation failed")
