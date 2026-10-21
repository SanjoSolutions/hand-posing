# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Sanjo Solutions

"""Calibrated palm and finger pad clearance against evaluated skin."""

from mathutils import Matrix, Quaternion, Vector


def spread_fingers(snap, palm, angle):
    """Fan finger roots within their native limits; angle uses radians."""
    evaluated = snap.rig.evaluated_get(snap.context.evaluated_depsgraph_get())
    frames = {name: evaluated.matrix_world @ evaluated.pose.bones[name].matrix
              for name, calibration in snap.calibration['fingers'].items()
              if calibration['segment'] == 1 and calibration['finger'] != 'thumb'}
    names = sorted(frames, key=lambda name: (palm.inverted() @ frames[name]).translation.x)
    for index, name in enumerate(names):
        frame = frames[name]
        rotation = Quaternion(palm.to_3x3().col[2], angle * (1 - 2 * index / max(1, len(names) - 1)))
        world = Matrix.LocRotScale(frame.translation, rotation @ frame.to_quaternion(), frame.to_scale())
        snap.rig.pose.bones[name].matrix = snap.rig.matrix_world.inverted() @ world
    snap.rig.update_tag()
    snap.context.view_layer.update()


class ContactSurface:
    def __init__(self, surface, margin=.0015):
        self.surface, self.margin = surface, margin

    def retrieve_nearest(self, point):
        nearest, normal = self.surface.retrieve_nearest(point)
        return nearest + normal * self.margin, normal


class HandSurfaceClearance:
    def __init__(self, snap):
        self.snap = snap

    def validate(self, surface):
        snap = self.snap
        palm = snap.retrieve_hand_pose() @ snap.wrist.inverted()
        points = [('palm', palm @ Vector(sample)) for sample in snap.calibration['support']]
        evaluated = snap.rig.evaluated_get(snap.context.evaluated_depsgraph_get())
        for name, calibration in snap.calibration['fingers'].items():
            frame = evaluated.matrix_world @ evaluated.pose.bones[name].matrix
            points.extend((name, frame @ Vector(sample)) for sample in calibration['samples'])
        gaps = []
        for name, point in points:
            nearest, normal = surface.retrieve_nearest(point)
            gaps.append(((point - nearest).dot(normal), name))
        minimum, name = min(gaps)
        if minimum < -.002:
            raise ValueError(f'Fit {name} to the evaluated skin: penetration {-minimum:.5f}')
        return max(0., -minimum)
