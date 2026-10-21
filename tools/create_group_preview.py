# SPDX-License-Identifier: GPL-3.0-or-later
"""Render grouping applied by membership edits without snapping again."""

import math
from pathlib import Path
import runpy

import bpy
from mathutils import Vector

project = Path(__file__).resolve().parents[1]
fixture = runpy.run_path(str(project / "hand_posing/test_hand_posing.py"), run_name="preview_fixture")
addon = fixture["ADDON"]
addon.register()
rig, skin = fixture["create_fixture"]()
bpy.ops.mesh.primitive_plane_add(size=2, location=(0, 0, .02))
surface = bpy.context.object
surface.name = "Contact surface"
surface.rotation_euler.x = math.pi
bpy.context.view_layer.update()
for side in ("L", "R"):
    addon.HandCalibration(bpy.context, rig, side, skin).capture()
    rig.pose.bones[f"hand_ik.{side}"].snap_hand_surface = surface
    addon.retrieve_snap_solver(bpy.context, rig, side).snap(surface)
hand = rig.pose.bones["hand_ik.R"]
for name, members in (("Index + middle", {"f_index", "f_middle"}), ("Ring + pinky", {"f_ring", "f_pinky"})):
    group = hand.hand_posing_finger_groups.add()
    group.name, group.fingers = name, members
    if hand.hand_posing_group_error:
        raise RuntimeError(hand.hand_posing_group_error)


def material(name, color):
    value = bpy.data.materials.new(name)
    value.diffuse_color = (*color, 1)
    value.use_nodes = True
    shader = value.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Roughness"].default_value = .5
    return value


for name, color in (("Ungrouped", (.45, .5, .56)), ("Index and middle", (.1, .55, .9)),
                    ("Ring and pinky", (1, .45, .12))):
    skin.data.materials.append(material(name, color))
for polygon in skin.data.polygons:
    groups = {skin.vertex_groups[weight.group].name for index in polygon.vertices
              for weight in skin.data.vertices[index].groups}
    if any(name.endswith(".R") and name.startswith(("DEF-f_index", "DEF-f_middle")) for name in groups):
        polygon.material_index = 1
    elif any(name.endswith(".R") and name.startswith(("DEF-f_ring", "DEF-f_pinky")) for name in groups):
        polygon.material_index = 2
surface.data.materials.append(material("Surface", (.035, .05, .08)))
bevel = skin.modifiers.new("Preview edges", "BEVEL")
bevel.width, bevel.segments = .0007, 3
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.samples = 32
scene.render.resolution_x, scene.render.resolution_y = 1400, 700
scene.render.resolution_percentage = 100
scene.world.color = (.25, .25, .25)
white = material("Labels", (.8, .87, .95))
for x, title in ((-.2, "Independent"), (.2, "Immediate groups")):
    curve = bpy.data.curves.new(title, "FONT")
    curve.body, curve.align_x, curve.size = title, "CENTER", .013
    label = bpy.data.objects.new(title, curve)
    scene.collection.objects.link(label)
    label.location = (x, -.034, -.02)
    label.rotation_euler.y = math.pi
    label.data.materials.append(white)
light_data = bpy.data.lights.new("Preview light", "AREA")
light_data.energy, light_data.size = 8, .7
light = bpy.data.objects.new(light_data.name, light_data)
scene.collection.objects.link(light)
light.location = (0, .1, -.5)
light.rotation_euler = (Vector((0, .1, 0)) - light.location).to_track_quat("-Z", "Y").to_euler()
camera = bpy.data.objects.new("Preview camera", bpy.data.cameras.new("Preview camera"))
scene.collection.objects.link(camera)
camera.location = (0, .065, -.7)
camera.rotation_euler.y = math.pi
camera.data.type, camera.data.ortho_scale = "ORTHO", .62
scene.camera = camera
bpy.context.view_layer.objects.active = rig
rig.select_set(True)
surface.select_set(False)
bpy.ops.object.mode_set(mode="POSE")
rig.data.bones.active = rig.data.bones["hand_ik.R"]
output = project / ".cache/finger-groups"
output.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(output / "comparison.blend"))
scene.render.filepath = str(output / "comparison.png")
bpy.ops.render.render(write_still=True)
print("Finger grouping preview:", scene.render.filepath)
