# SPDX-License-Identifier: GPL-3.0-or-later
"""Capture the native follow sidebar and evaluated base/midpoint/tip examples.

Run in an isolated, windowed Blender: blender --factory-startup --python PATH.
The generated scene and screenshot are saved under .cache/follow-relationships.
"""

from pathlib import Path
import runpy

import bpy
from mathutils import Quaternion, Vector


bpy.context.preferences.view.show_splash = False
project = Path(__file__).resolve().parents[1]
fixture = runpy.run_path(str(project / "hand_posing/test_hand_posing.py"), run_name="preview_fixture")
addon = fixture["ADDON"]
addon.register()
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
armature = bpy.data.armatures.new("Follow examples")
rig = bpy.data.objects.new("Follow examples", armature)
bpy.context.scene.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig
rig.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
for index, offset in enumerate((0., .5, 1.)):
    x = index * 5
    suffix = f"{offset:g}"
    for name, head, tail in ((f"A ({suffix})", (x, 0, 0), (x, 2, 0)),
                             (f"B ({suffix})", (x + 3, 2, 0), (x + 3, 5, 0))):
        bone = armature.edit_bones.new(name)
        bone.head, bone.tail = head, tail
bpy.ops.object.mode_set(mode="POSE")
for offset in (0., .5, 1.):
    bpy.ops.hand.set_follow_relationship(source_bone=f"A ({offset:g})",
        target_armature=rig.name, target_bone=f"B ({offset:g})", offset=offset)
armature.show_names = True
for bone in rig.pose.bones:
    bone.select = bone.name.startswith("A")
    bone.color.palette = "THEME04" if bone.name.startswith("A") else "THEME03"
armature.bones.active = armature.bones["A (0.5)"]
bpy.context.view_layer.update()

# The guide lines use the evaluated result, so incorrect aiming fails the preview.
graph = bpy.context.evaluated_depsgraph_get()
evaluated = rig.evaluated_get(graph)
for offset in (0., .5, 1.):
    a, b = (evaluated.pose.bones[f"{name} ({offset:g})"] for name in ("A", "B"))
    point = b.head.lerp(b.tail, offset)
    assert (a.tail - a.head).normalized().dot((point - a.head).normalized()) > 1 - 1e-6
    curve = bpy.data.curves.new("Aim guide", "CURVE")
    curve.dimensions = "3D"
    line = curve.splines.new("POLY")
    line.points.add(1)
    line.points[0].co, line.points[1].co = (*a.tail, 1), (*point, 1)
    obj = bpy.data.objects.new(curve.name, curve)
    bpy.context.scene.collection.objects.link(obj)

output = project / ".cache/follow-relationships"
output.mkdir(parents=True, exist_ok=True)
for area in bpy.context.screen.areas:
    if area.type == "VIEW_3D":
        space = area.spaces.active
        space.show_region_ui = True
        space.show_region_toolbar = False
        space.overlay.show_floor = False
        space.overlay.show_axis_x = space.overlay.show_axis_y = False
        space.region_3d.view_rotation = Quaternion((1, 0, 0, 0))
        space.region_3d.view_perspective = "ORTHO"
        space.region_3d.view_location = Vector((7.5, 2.5, 0))
        space.region_3d.view_distance = 19


def capture():
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "follow-examples.blend"))
    bpy.ops.screen.screenshot(filepath=str(output / "follow-sidebar.png"))
    area = next(area for area in bpy.context.screen.areas if area.type == "VIEW_3D")
    region = next(region for region in area.regions if region.type == "WINDOW")
    with bpy.context.temp_override(area=area, region=region):
        bpy.ops.hand.set_follow_relationship("INVOKE_DEFAULT", original_source="A (0.5)")
    bpy.app.timers.register(capture_dialog, first_interval=1.)


def capture_dialog():
    bpy.ops.screen.screenshot(filepath=str(output / "follow-dialog.png"))
    bpy.ops.wm.quit_blender()


if not bpy.app.background:
    bpy.app.timers.register(capture, first_interval=3.)
