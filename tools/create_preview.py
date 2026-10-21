# SPDX-License-Identifier: GPL-3.0-or-later
"""Render a redistributable contact preview from the generated hand fixture."""

from pathlib import Path
import runpy

import bpy
from mathutils import Vector

project = Path(__file__).resolve().parents[1]
fixture = runpy.run_path(str(project / "hand_posing/test_hand_posing.py"), run_name="preview_fixture")
addon = fixture["ADDON"]
addon.register()
rig, skin = fixture["create_fixture"]()
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, .09, .055))
surface = bpy.context.object
surface.name = "Contact surface"
surface.scale = (.65, .27, .07)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
bpy.context.view_layer.update()
for side in ("L", "R"):
    addon.HandCalibration(bpy.context, rig, side, skin).capture()
    addon.retrieve_snap_solver(bpy.context, rig, side).snap(surface)


def material(name, color):
    value = bpy.data.materials.new(name)
    value.diffuse_color = (*color, 1)
    value.use_nodes = True
    shader = value.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Roughness"].default_value = .4
    return value


skin.data.materials.append(material("Hand fixture", (.48, .23, .13)))
surface.data.materials.append(material("Contact surface", (.12, .23, .3)))
bevel = skin.modifiers.new("Preview edges", "BEVEL")
bevel.width, bevel.segments = .0015, 3
for polygon in skin.data.polygons:
    polygon.use_smooth = True
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.samples = 32
scene.render.resolution_x, scene.render.resolution_y = 1600, 1000
scene.render.resolution_percentage = 100
scene.world.color = (.2, .2, .2)
for location, energy, size in (((.0, -.4, -.5), 80, .5), ((-.4, .1, -.15), 40, .3)):
    data = bpy.data.lights.new("Preview light", "AREA")
    data.energy, data.shape, data.size = energy, "DISK", size
    light = bpy.data.objects.new(data.name, data)
    scene.collection.objects.link(light)
    light.location = location
    light.rotation_euler = (Vector((0, .09, .02)) - light.location).to_track_quat("-Z", "Y").to_euler()
camera = bpy.data.objects.new("Preview camera", bpy.data.cameras.new("Preview camera"))
scene.collection.objects.link(camera)
camera.location = (.22, -.38, -.55)
camera.rotation_euler = (Vector((0, .08, .02)) - camera.location).to_track_quat("-Z", "Y").to_euler()
camera.data.type, camera.data.ortho_scale = "ORTHO", .8
scene.camera = camera
output = project / "docs/preview.png"
scene.render.filepath = str(output)
bpy.ops.render.render(write_still=True)
print("Preview:", output)
