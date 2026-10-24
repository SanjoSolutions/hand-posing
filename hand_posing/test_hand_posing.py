# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise the public addon against generated, redistributable Blender data."""

import importlib
import importlib.util
import json
import math
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
        bpy.context.scene.tool_settings.use_keyframe_insert_auto = False

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
        hand = self.calibrate("R")
        bpy.ops.hand.add_finger_group()
        hand.hand_posing_finger_groups[0].name = "Together"
        hand.hand_posing_finger_groups[0].fingers = {"f_index", "f_middle"}
        original = hand["Snap Hand Calibration"]
        skin_name = self.skin.name
        with tempfile.TemporaryDirectory() as directory:
            bpy.ops.wm.save_as_mainfile(filepath=str(Path(directory) / "example.blend"))
            bpy.ops.wm.open_mainfile(filepath=str(Path(directory) / "example.blend"))
            rig = bpy.data.objects["Example character"]
            self.assertEqual(rig.pose.bones["hand_ik.R"]["Snap Hand Calibration"], original)
            groups = rig.pose.bones["hand_ik.R"].hand_posing_finger_groups
            self.assertEqual(groups[0].name, "Together")
            self.assertEqual(groups[0].fingers, {"f_index", "f_middle"})
            self.assertEqual(len(rig.pose.bones["hand_ik.L"].hand_posing_finger_groups), 0)
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
        hand = self.select_hand("R")
        bpy.ops.hand.add_finger_group()
        hand.hand_posing_finger_groups[0].fingers = {"thumb", "f_index"}
        ADDON.unregister()
        self.assertFalse(hasattr(bpy.types.PoseBone, "hand_posing_finger_groups"))
        self.assertIsNone(bpy.types.Panel.bl_rna_get_subclass_py("HAND_PT_snap"))
        self.assertFalse(hasattr(bpy.types.PoseBone, "snap_hand_surface"))
        self.assertFalse(hasattr(bpy.types.PoseBone, "hand_on_surface_skin"))
        ADDON.register()
        self.assertTrue(hasattr(bpy.types.PoseBone, "snap_hand_surface"))
        self.assertTrue(bpy.ops.hand.snap.get_rna_type())
        self.assertEqual(hand.hand_posing_finger_groups[0].fingers, {"thumb", "f_index"})

    def test_group_membership_and_removal(self):
        hand = self.select_hand("R")
        self.assertEqual(len(hand.hand_posing_finger_groups), 0)
        for _index in range(7):
            self.assertEqual(bpy.ops.hand.add_finger_group(), {"FINISHED"})
        groups = hand.hand_posing_finger_groups
        self.assertEqual(len({group.name for group in groups}), 7)
        groups[0].fingers = {"thumb", "f_index", "f_middle"}
        groups[1].fingers = {"f_middle", "f_ring", "f_pinky"}
        self.assertEqual(groups[0].fingers, {"thumb", "f_index"})
        groups[2].fingers = {"thumb", "f_ring"}
        self.assertEqual(groups[0].fingers, {"f_index"})
        self.assertEqual(groups[1].fingers, {"f_middle", "f_pinky"})
        self.select_hand("L")
        bpy.ops.hand.add_finger_group()
        self.rig.pose.bones["hand_ik.L"].hand_posing_finger_groups[0].fingers = {"thumb", "f_ring"}
        self.assertEqual(groups[2].fingers, {"thumb", "f_ring"})
        self.select_hand("R")
        self.assertEqual(bpy.ops.hand.remove_finger_group(index=-1), {"CANCELLED"})
        self.assertEqual(bpy.ops.hand.remove_finger_group(index=7), {"CANCELLED"})
        self.assertEqual(bpy.ops.hand.remove_finger_group(index=2), {"FINISHED"})
        groups[0].fingers = {"thumb", "f_ring"}
        self.assertEqual(groups[0].fingers, {"thumb", "f_ring"})
        while groups:
            bpy.ops.hand.remove_finger_group(index=0)
        self.assertEqual(len(groups), 0)

    def retrieve_tip_spacing(self, side, first, second):
        evaluated = self.rig.evaluated_get(bpy.context.evaluated_depsgraph_get())
        return (evaluated.pose.bones[f"{first}.03.{side}"].tail
                - evaluated.pose.bones[f"{second}.03.{side}"].tail).length

    def test_group_membership_applies_immediately_without_setup(self):
        from unittest.mock import patch
        for side in ("L", "R"):
            with self.subTest(side=side):
                hand = self.select_hand(side)
                bpy.ops.hand.add_finger_group()
                group = hand.hand_posing_finger_groups[0]
                before = self.retrieve_tip_spacing(side, "f_index", "f_middle")
                original = {bone.name: bone.matrix_basis.copy() for bone in self.rig.pose.bones}
                self.select_hand("L" if side == "R" else "R")
                with patch.object(ADDON.HandSnap, "snap") as snap:
                    group.fingers = {"f_index", "f_middle"}
                    snap.assert_not_called()
                self.assertEqual(hand.hand_posing_group_error, "")
                self.assertLess(self.retrieve_tip_spacing(side, "f_index", "f_middle"), before * .95)
                self.assertNotIn("Snap Hand Calibration", hand)
                self.assertIsNone(hand.snap_hand_surface)
                for bone in self.rig.pose.bones:
                    if not (bone.name.startswith(("f_index.", "f_middle.")) and bone.name.endswith("." + side)):
                        self.assertEqual(bone.matrix_basis, original[bone.name], bone.name)
                posed = {bone.name: bone.matrix_basis.copy() for bone in self.rig.pose.bones}
                group.fingers = {"f_index"}
                self.select_hand(side)
                bpy.ops.hand.remove_finger_group(index=0)
                for bone in self.rig.pose.bones:
                    self.assertEqual(bone.matrix_basis, posed[bone.name], bone.name)

    def test_adding_group_members_bounds_scene_updates(self):
        from unittest.mock import patch
        for calibrated in (False, True):
            with self.subTest(calibrated=calibrated):
                hand = self.calibrate("R") if calibrated else self.select_hand("L")
                side = hand.name.rsplit(".", 1)[-1]
                bpy.ops.hand.add_finger_group()
                group = hand.hand_posing_finger_groups[0]
                group.fingers = {"f_ring"}
                original = {bone.name: bone.matrix_basis.copy() for bone in self.rig.pose.bones}
                before = self.retrieve_tip_spacing(side, "f_ring", "f_pinky")
                for finger in ("f_pinky", "f_middle", "thumb"):
                    with patch.object(ADDON.HandSnap, "place_finger", autospec=True,
                                      side_effect=ADDON.HandSnap.place_finger) as place:
                        group.fingers = group.fingers | {finger}
                    self.assertEqual(hand.hand_posing_group_error, "")
                    # At most four validated poses; search trials must not
                    # update the scene. This fixture needs one update per joint.
                    self.assertLessEqual(place.call_count, 4 * 3 * len(group.fingers))
                    if finger == "f_pinky":
                        self.assertLess(self.retrieve_tip_spacing(side, "f_ring", "f_pinky"), before * .95)
                for bone in self.rig.pose.bones:
                    if not any(bone.name == f"{finger}.{segment:02}.{side}"
                               for finger in group.fingers for segment in (1, 2, 3)):
                        self.assertEqual(bone.matrix_basis, original[bone.name], bone.name)

    def test_immediate_group_preserves_contact_and_auto_keys_only_members(self):
        hand = self.calibrate("R")
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.mesh.primitive_plane_add(size=2, location=(0, 0, .02))
        target = bpy.context.object
        target.rotation_euler.x = math.pi
        bpy.context.view_layer.update()
        solver = ADDON.retrieve_snap_solver(bpy.context, self.rig, "R")
        solver.snap(target)
        self.select_hand("R")
        hand.snap_hand_surface = target
        bpy.ops.hand.add_finger_group()
        before = self.retrieve_tip_spacing("R", "f_index", "f_middle")
        original = {bone.name: bone.matrix_basis.copy() for bone in self.rig.pose.bones}
        bpy.context.scene.tool_settings.use_keyframe_insert_auto = True
        hand.hand_posing_finger_groups[0].fingers = {"f_index", "f_middle"}
        bpy.context.scene.tool_settings.use_keyframe_insert_auto = False
        self.assertEqual(hand.hand_posing_group_error, "")
        self.assertLess(self.retrieve_tip_spacing("R", "f_index", "f_middle"), before * .95)
        self.assert_group_bounds(solver)
        for bone in self.rig.pose.bones:
            if not (bone.name.startswith(("f_index.", "f_middle.")) and bone.name.endswith(".R")):
                self.assertEqual(bone.matrix_basis, original[bone.name], bone.name)
        surface = ADDON.HandSurface(target, bpy.context.evaluated_depsgraph_get(), self.rig, "R")
        refinement = importlib.import_module(ADDON.__name__ + ".skin_finger_refinement")
        indices = {index for calibration in solver.calibration["fingers"].values()
                   for index in calibration["skin_vertices"]}
        gaps = refinement.retrieve_skin_contacts(bpy.context, self.skin, indices, surface)
        self.assertGreaterEqual(min(gap for gap, _normal, _point in gaps), -.002)
        action = self.rig.animation_data.action
        curves = [curve for layer in action.layers for strip in layer.strips
                  for bag in strip.channelbags for curve in bag.fcurves]
        self.assertEqual(len(curves), 60)
        for curve in curves:
            self.assertTrue(curve.data_path.startswith(('pose.bones["f_index.', 'pose.bones["f_middle.')))
            values = self.rig.path_resolve(curve.data_path)
            self.assertAlmostEqual(curve.evaluate(bpy.context.scene.frame_current), values[curve.array_index], places=5)

    def test_membership_transfer_applies_once_and_failed_update_restores_pose(self):
        from unittest.mock import patch
        hand = self.calibrate("R")
        for _index in range(2):
            bpy.ops.hand.add_finger_group()
        first, second = hand.hand_posing_finger_groups
        first.fingers = {"f_index", "f_middle", "f_ring"}
        grouping = importlib.import_module(ADDON.__name__ + ".finger_groups")
        with patch.object(grouping, "apply_group_edit", wraps=grouping.apply_group_edit) as apply:
            second.fingers = {"f_middle", "f_pinky"}
            self.assertEqual(apply.call_count, 1)
        self.assertEqual(first.fingers, {"f_index", "f_ring"})
        self.assertEqual(hand.hand_posing_group_error, "")
        original = {bone.name: bone.matrix_basis.copy() for bone in self.rig.pose.bones}

        def fail_after_moving(snap, _surface, _memberships, preserve_pose=False):
            snap.rig.pose.bones["f_middle.01.R"].rotation_quaternion.x += .2
            raise ValueError("Could not apply group")

        with patch.object(grouping, "fit_finger_groups", side_effect=fail_after_moving):
            second.fingers = {"f_middle", "f_pinky", "thumb"}
        self.assertEqual(hand.hand_posing_group_error, "Could not apply group")
        for bone in self.rig.pose.bones:
            self.assertLess(max(abs(a - b) for row, other in zip(bone.matrix_basis, original[bone.name])
                                for a, b in zip(row, other)), .000001, bone.name)
        second.fingers = {"f_middle"}
        self.assertEqual(hand.hand_posing_group_error, "")

    def test_grouped_snap_keeps_fingers_close(self):
        for side in ("L", "R"):
            with self.subTest(side=side):
                hand = self.calibrate(side)
                bpy.ops.object.mode_set(mode="OBJECT")
                bpy.ops.mesh.primitive_plane_add(size=2, location=(0, 0, .02))
                target = bpy.context.object
                target.rotation_euler.x = math.pi
                bpy.context.view_layer.update()
                self.select_hand(side)
                hand.snap_hand_surface = target
                bpy.ops.hand.snap()
                pairs = (("f_index", "f_middle"), ("f_ring", "f_pinky"))
                baseline = [self.retrieve_tip_spacing(side, *pair) for pair in pairs]
                thumb = self.rig.pose.bones[f"thumb.03.{side}"].matrix_basis.copy()
                for pair in pairs:
                    bpy.ops.hand.add_finger_group()
                    hand.hand_posing_finger_groups[-1].fingers = set(pair)
                bpy.context.scene.tool_settings.use_keyframe_insert_auto = True
                self.assertEqual(bpy.ops.hand.snap(), {"FINISHED"})
                bpy.context.scene.tool_settings.use_keyframe_insert_auto = False
                for pair, before in zip(pairs, baseline):
                    after = self.retrieve_tip_spacing(side, *pair)
                    self.assertLess(after, before * .95)
                    self.assertGreater(after, .012)
                self.assertLess(max(abs(a - b) for row, other in zip(
                    self.rig.pose.bones[f"thumb.03.{side}"].matrix_basis, thumb)
                    for a, b in zip(row, other)), .0001)
                solver = ADDON.retrieve_snap_solver(bpy.context, self.rig, side)
                surface = ADDON.HandSurface(target, bpy.context.evaluated_depsgraph_get(), self.rig, side)
                refinement = importlib.import_module(ADDON.__name__ + ".skin_finger_refinement")
                indices = {index for calibration in solver.calibration["fingers"].values()
                           for index in calibration["skin_vertices"]}
                gaps = refinement.retrieve_skin_contacts(bpy.context, self.skin, indices, surface)
                self.assertGreaterEqual(min(gap for gap, _normal, _point in gaps), -.002)
                action = self.rig.animation_data.action
                curves = [curve for layer in action.layers for strip in layer.strips
                          for bag in strip.channelbags for curve in bag.fcurves]
                bone = self.rig.pose.bones[f"f_index.01.{side}"]
                path = f'pose.bones["{bone.name}"].rotation_quaternion'
                self.assertEqual(sum(curve.data_path == path for curve in curves), 4)
                for curve in (curve for curve in curves if curve.data_path == path):
                    self.assertAlmostEqual(curve.evaluate(bpy.context.scene.frame_current),
                                           bone.rotation_quaternion[curve.array_index], places=5)

    def test_empty_and_single_finger_groups_leave_pose_unchanged(self):
        hand = self.calibrate("R")
        for members in (set(), {"thumb"}):
            bpy.ops.hand.add_finger_group()
            hand.hand_posing_finger_groups[-1].fingers = members
        original = {bone.name: bone.matrix_basis.copy() for bone in self.rig.pose.bones}
        grouping = importlib.import_module(ADDON.__name__ + ".finger_groups")
        grouping.fit_finger_groups(ADDON.retrieve_snap_solver(bpy.context, self.rig, "R"), None)
        for bone in self.rig.pose.bones:
            self.assertEqual(bone.matrix_basis, original[bone.name])

    def assert_group_bounds(self, solver):
        snap_module = importlib.import_module(ADDON.__name__ + ".snap_hand")
        evaluated = self.rig.evaluated_get(bpy.context.evaluated_depsgraph_get())
        for name, calibration in solver.calibration["fingers"].items():
            rotation = (snap_module.retrieve_matrix(calibration["rest"]).inverted()
                        @ evaluated.pose.bones[calibration["parent"]].matrix.inverted()
                        @ evaluated.pose.bones[name].matrix).to_euler("XYZ")
            for angle, (lower, upper) in zip(rotation, calibration["bounds"]):
                self.assertGreaterEqual(angle, lower - .002, name)
                self.assertLessEqual(angle, upper + .002, name)

    def test_groups_on_curved_surface_with_thumb(self):
        hand = self.calibrate("R")
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=1,
                                            location=(.2, .1, 1.02))
        target = bpy.context.object
        solver = ADDON.retrieve_snap_solver(bpy.context, self.rig, "R")
        solver.snap(target)
        pairs = (("f_index", "f_middle"), ("f_middle", "f_ring"), ("f_pinky", "thumb"))
        before = sum(self.retrieve_tip_spacing("R", *pair) for pair in pairs)
        self.select_hand("R")
        for members in ({"f_index", "f_middle", "f_ring"}, {"f_pinky", "thumb"}):
            bpy.ops.hand.add_finger_group()
            hand.hand_posing_finger_groups[-1].fingers = members
        solver.snap(target)
        after = sum(self.retrieve_tip_spacing("R", *pair) for pair in pairs)
        self.assertLess(after, before * .97)
        self.assert_group_bounds(solver)
        surface = ADDON.HandSurface(target, bpy.context.evaluated_depsgraph_get(), self.rig, "R")
        refinement = importlib.import_module(ADDON.__name__ + ".skin_finger_refinement")
        indices = {index for calibration in solver.calibration["fingers"].values()
                   for index in calibration["skin_vertices"]}
        gaps = refinement.retrieve_skin_contacts(bpy.context, self.skin, indices, surface)
        self.assertGreaterEqual(min(gap for gap, _normal, _point in gaps), -.002)

    def test_legacy_group_fit_and_failure_rollback(self):
        hand = self.calibrate("R")
        calibration = json.loads(hand["Snap Hand Calibration"])
        for joint in calibration["fingers"].values():
            joint.pop("skin_vertices")
        calibration.pop("contact_geometry")
        hand["Snap Hand Calibration"] = json.dumps(calibration)
        bpy.ops.hand.add_finger_group()
        hand.hand_posing_finger_groups[0].fingers = {"f_index", "f_middle"}
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.mesh.primitive_plane_add(size=2, location=(0, 0, .02))
        target = bpy.context.object
        target.rotation_euler.x = math.pi
        bpy.context.view_layer.update()
        solver = ADDON.HandSnap(bpy.context, self.rig, "R")
        solver.snap(target)
        self.assertLess(self.retrieve_tip_spacing("R", "f_index", "f_middle"), .017)
        self.assert_group_bounds(solver)
        original = {bone.name: bone.matrix_basis.copy() for bone in solver.retrieve_controls()}
        grouping = importlib.import_module(ADDON.__name__ + ".finger_groups")
        from unittest.mock import patch
        with patch.object(grouping, "fit_finger_groups", side_effect=ValueError("Group fit failed")):
            with self.assertRaisesRegex(ValueError, "Group fit failed"):
                solver.snap(target, keyframe=True)
        for bone in solver.retrieve_controls():
            self.assertLess(max(abs(a - b) for row, other in zip(bone.matrix_basis, original[bone.name])
                                for a, b in zip(row, other)), .000001)
        self.assertIsNone(self.rig.animation_data)

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
            before = self.retrieve_tip_spacing(side, "f_index", "f_middle")
            self.select_hand(side)
            hand.snap_hand_surface = target
            bpy.ops.hand.add_finger_group()
            hand.hand_posing_finger_groups[0].fingers = {"f_index", "f_middle"}
            self.assertEqual(hand.hand_posing_group_error, "")
            self.assertLess(self.retrieve_tip_spacing(side, "f_index", "f_middle"), before)
            self.assert_group_bounds(solver)
            solver.snap(target)
            self.assertLess(self.retrieve_tip_spacing(side, "f_index", "f_middle"), before)
            self.assert_group_bounds(solver)
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


def create_follow_fixture(name="Follow rig"):
    """An ordinary armature: following needs neither Rigify nor calibration."""
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    rig = bpy.data.objects.new(name, bpy.data.armatures.new(name))
    bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    for name, head, tail in (("A", (0, 0, 0), (0, 1, 0)),
                             ("B", (3, 2, 0), (3, 4, 0)),
                             ("C", (-3, 3, 1), (-3, 4, 1)),
                             ("D", (0, 5, 1), (0, 6, 1)),
                             ("Child", (0, 1, 0), (0, 2, 0))):
        bone = rig.data.edit_bones.new(name)
        bone.head, bone.tail = head, tail
    rig.data.edit_bones["Child"].parent = rig.data.edit_bones["A"]
    rig.data.edit_bones["Child"].use_connect = True
    bpy.ops.object.mode_set(mode="POSE")
    rig.data.bones.active = rig.data.bones["A"]
    bpy.context.view_layer.update()
    return rig


class FollowRelationshipTests(unittest.TestCase):
    def setUp(self):
        if bpy.types.Panel.bl_rna_get_subclass_py("HAND_PT_snap") is None:
            ADDON.register()
        if bpy.context.object and bpy.context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)
        bpy.context.scene.frame_set(1)
        self.rig = create_follow_fixture()

    def add(self, source="A", target="B", offset=0., target_rig=None, original=""):
        if bpy.context.object != self.rig and bpy.context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.context.view_layer.objects.active = self.rig
        self.rig.select_set(True)
        if self.rig.mode != "POSE":
            bpy.ops.object.mode_set(mode="POSE")
        self.assertEqual(bpy.ops.hand.set_follow_relationship(
            source_bone=source, target_armature=(target_rig or self.rig).name,
            target_bone=target, offset=offset, original_source=original), {"FINISHED"})
        return ADDON.retrieve_follow(self.rig.pose.bones[source])

    def assert_aim(self, source="A", target="B", offset=0., target_rig=None):
        bpy.context.view_layer.update()
        graph = bpy.context.evaluated_depsgraph_get()
        evaluated = self.rig.evaluated_get(graph)
        target_object = (target_rig or self.rig).evaluated_get(graph)
        bone, other = evaluated.pose.bones[source], target_object.pose.bones[target]
        head = evaluated.matrix_world @ bone.head
        direction = (evaluated.matrix_world @ bone.tail - head).normalized()
        point = target_object.matrix_world @ other.head.lerp(other.tail, offset)
        self.assertGreater(direction.dot((point - head).normalized()), 1 - 1e-6)
        return head, (evaluated.matrix_world @ bone.tail - head).length

    def test_base_midpoint_tip_and_live_offset(self):
        constraint = self.add()
        for offset in (0., .25, .5, .75, 1.):
            with self.subTest(offset=offset):
                constraint.head_tail = offset
                head, length = self.assert_aim(offset=offset)
                self.assertLess(head.length, 1e-6)
                self.assertAlmostEqual(length, 1., places=6)
                self.assertEqual(self.rig.pose.bones["A"].matrix_basis, Matrix.Identity(4))
        constraint.head_tail = -2
        self.assertEqual(constraint.head_tail, 0.)
        constraint.head_tail = 2
        self.assertEqual(constraint.head_tail, 1.)

    def test_target_motion_rotation_and_animation(self):
        self.add(offset=.5)
        target = self.rig.pose.bones["B"]
        target.rotation_mode = "XYZ"
        target.keyframe_insert("location", frame=1)
        target.keyframe_insert("rotation_euler", frame=1)
        target.location = (1, -2, 3)
        target.rotation_euler = (.4, -.8, 1.2)
        target.keyframe_insert("location", frame=20)
        target.keyframe_insert("rotation_euler", frame=20)
        for frame in (1, 6, 13, 20, 1):
            bpy.context.scene.frame_set(frame)
            self.assert_aim(offset=.5)

    def test_cross_armature_with_world_transforms(self):
        target_rig = create_follow_fixture("Target rig")
        self.rig.location = (-2, 1, 3)
        self.rig.rotation_euler = (.2, -.3, .7)
        self.rig.scale = (1.2, 1.2, 1.2)
        target_rig.location = (5, -3, 1)
        target_rig.rotation_euler = (-.4, .8, -.2)
        target_rig.scale = (.5, 2, 1.5)
        self.add(offset=.75, target_rig=target_rig)
        self.assert_aim(offset=.75, target_rig=target_rig)
        target_rig.location.x += 3
        target_rig.pose.bones["B"].rotation_mode = "XYZ"
        target_rig.pose.bones["B"].rotation_euler.z = 1.
        self.assert_aim(offset=.75, target_rig=target_rig)

    def test_multiple_relationships_and_chain(self):
        self.add(source="B", target="C", offset=1.)
        self.add(offset=1.)
        self.add(source="D", offset=.5)
        self.rig.pose.bones["C"].location = (.5, 1, 2)
        self.assert_aim(source="B", target="C", offset=1.)
        self.assert_aim(offset=1.)
        self.assert_aim(source="D", offset=.5)
        self.assertEqual(len(list(ADDON.retrieve_follows(self.rig))), 3)

    def test_edit_and_remove_preserve_other_constraints_and_pose(self):
        original = self.rig.pose.bones["A"].matrix_basis.copy()
        native = self.rig.pose.bones["A"].constraints.new("LIMIT_ROTATION")
        self.add()
        self.add(target="C", offset=.25, original="A")
        self.assert_aim(target="C", offset=.25)
        self.add(source="D", target="C", offset=1., original="A")
        self.assertIsNone(ADDON.retrieve_follow(self.rig.pose.bones["A"]))
        self.assertEqual(self.rig.pose.bones["A"].constraints[0], native)
        self.assertEqual(self.rig.pose.bones["A"].matrix_basis, original)
        self.assert_aim(source="D", target="C", offset=1.)
        self.assertEqual(bpy.ops.hand.remove_follow_relationship(source_bone="D"), {"FINISHED"})
        self.assertEqual(bpy.ops.hand.remove_follow_relationship(source_bone="D"), {"CANCELLED"})
        bpy.context.view_layer.update()
        self.assertEqual(self.rig.pose.bones["D"].matrix_basis, Matrix.Identity(4))
        self.assertEqual(len(list(ADDON.retrieve_follows(self.rig))), 0)

    def test_invalid_pairs_leave_existing_relationship_unchanged(self):
        original = self.add(offset=.5)
        for source, target, original_source, message in (
                ("A", "A", "A", "itself"), ("A", "Child", "A", "circular"),
                ("A", "Missing", "A", "bone B"), ("Missing", "B", "", "bone A"),
                ("A", "C", "", "already"), ("D", "C", "D", "no longer")):
            with self.subTest(source=source, target=target), self.assertRaisesRegex(RuntimeError, message):
                bpy.ops.hand.set_follow_relationship(source_bone=source,
                    target_armature=self.rig.name, target_bone=target, original_source=original_source)
        self.assertEqual(original.subtarget, "B")
        self.assertEqual(original.head_tail, .5)
        self.assertEqual(len(list(ADDON.retrieve_follows(self.rig))), 1)
        self.assert_aim(offset=.5)

    def test_cycles_through_follows_and_native_constraints_are_rejected(self):
        self.add()
        self.add(source="B", target="C")
        with self.assertRaisesRegex(ValueError, "circular"):
            ADDON.set_follow(self.rig, "C", self.rig, "A")
        native = self.rig.pose.bones["D"].constraints.new("COPY_ROTATION")
        native.target, native.subtarget = self.rig, "A"
        with self.assertRaisesRegex(ValueError, "circular"):
            ADDON.set_follow(self.rig, "A", self.rig, "D", original_source="A")
        target_rig = create_follow_fixture("Other rig")
        ADDON.set_follow(target_rig, "A", self.rig, "A")
        with self.assertRaisesRegex(ValueError, "circular"):
            ADDON.set_follow(self.rig, "C", target_rig, "A")

    def test_save_reopen_rename_and_registration(self):
        import tempfile
        target = create_follow_fixture("Other rig")
        self.add(offset=.5, target_rig=target)
        self.rig.data.bones["A"].name = "Renamed A"
        target.data.bones["B"].name = "Renamed B"
        target.name = "Renamed target rig"
        ADDON.unregister()
        self.assertIsNone(bpy.types.Panel.bl_rna_get_subclass_py("HAND_PT_follow_relationships"))
        self.assert_aim(source="Renamed A", target="Renamed B", offset=.5, target_rig=target)
        ADDON.register()
        self.assertEqual(len(list(ADDON.retrieve_follows(self.rig))), 1)
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "follows.blend")
            bpy.ops.wm.save_as_mainfile(filepath=path)
            bpy.ops.wm.open_mainfile(filepath=path)
        self.rig = bpy.data.objects["Follow rig"]
        target = bpy.data.objects["Renamed target rig"]
        constraint = ADDON.retrieve_follow(self.rig.pose.bones["Renamed A"])
        self.assertEqual(constraint.target, target)
        self.assertEqual(constraint.subtarget, "Renamed B")
        self.assertEqual(constraint.head_tail, .5)
        target.pose.bones["Renamed B"].location = (2, 1, 3)
        self.assert_aim(source="Renamed A", target="Renamed B", offset=.5, target_rig=target)

    def test_deleted_target_can_be_repaired_or_removed(self):
        target = create_follow_fixture("Other rig")
        self.add(target_rig=target)
        bpy.data.objects.remove(target, do_unlink=True)
        bpy.context.view_layer.update()
        self.assertIsNone(ADDON.retrieve_follow(self.rig.pose.bones["A"]).target)
        self.add(original="A")
        self.assert_aim()
        self.assertEqual(bpy.ops.hand.remove_follow_relationship(source_bone="A"), {"FINISHED"})

    def test_undo_redo_creation_edit_and_removal(self):
        bpy.ops.ed.undo_push(message="Before follow")
        self.add(offset=.5)
        bpy.ops.ed.undo_push(message="Added follow")
        self.add(target="C", offset=1., original="A")
        bpy.ops.ed.undo_push(message="Edited follow")
        bpy.ops.hand.remove_follow_relationship(source_bone="A")
        bpy.ops.ed.undo_push(message="Removed follow")
        for target, offset in (("C", 1.), ("B", .5)):
            self.assertEqual(bpy.ops.ed.undo(), {"FINISHED"})
            self.rig = bpy.data.objects["Follow rig"]
            self.assert_aim(target=target, offset=offset)
        self.assertEqual(bpy.ops.ed.undo(), {"FINISHED"})
        self.rig = bpy.data.objects["Follow rig"]
        self.assertIsNone(ADDON.retrieve_follow(self.rig.pose.bones["A"]))
        for target, offset in (("B", .5), ("C", 1.)):
            self.assertEqual(bpy.ops.ed.redo(), {"FINISHED"})
            self.rig = bpy.data.objects["Follow rig"]
            self.assert_aim(target=target, offset=offset)
        self.assertEqual(bpy.ops.ed.redo(), {"FINISHED"})
        self.rig = bpy.data.objects["Follow rig"]
        self.assertIsNone(ADDON.retrieve_follow(self.rig.pose.bones["A"]))


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(HandPosingTests)
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(FollowRelationshipTests))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise RuntimeError("Hand Posing validation failed")
