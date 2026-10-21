# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Sanjo Solutions

"""Refine contact against native Rigify finger deformation."""

from .snap_hand import FingerComfort, JointRotationSearch, retrieve_matrix
from mathutils import Euler


def retrieve_skin_contacts(context, skin, indices, surface):
    evaluated = skin.evaluated_get(context.evaluated_depsgraph_get())
    contacts = []
    for index in indices:
        if index >= len(evaluated.data.vertices):
            raise ValueError("Calibrate the hand after changing the skin topology")
        point = evaluated.matrix_world @ evaluated.data.vertices[index].co
        nearest, normal = surface.retrieve_nearest(point)
        contacts.append(((point - nearest).dot(normal), normal, point))
    return contacts


class SkinFingerRefinement:
    def __init__(self, snap, surface, chain):
        self.snap, self.surface, self.chain = snap, surface, chain
        self.comforts = [FingerComfort(calibration) for _name, calibration in chain]
        self.skin = snap.skin.object
        self.indices = {index for _name, calibration in chain for index in calibration["skin_vertices"]}

    def retrieve_distances(self):
        return [gap for gap, _normal, _point in retrieve_skin_contacts(
            self.snap.context, self.skin, self.indices, self.surface)]

    def retrieve_rotations(self):
        evaluated = self.snap.rig.evaluated_get(self.snap.context.evaluated_depsgraph_get())
        return [(retrieve_matrix(calibration["rest"]).inverted()
                 @ evaluated.pose.bones[calibration["parent"]].matrix.inverted()
                 @ evaluated.pose.bones[name].matrix).to_euler("XYZ")
                for name, calibration in self.chain]

    def apply(self, rotations):
        for (name, calibration), rotation in zip(self.chain, rotations):
            evaluated = self.snap.rig.evaluated_get(self.snap.context.evaluated_depsgraph_get())
            frame = (evaluated.matrix_world @ evaluated.pose.bones[calibration["parent"]].matrix
                     @ retrieve_matrix(calibration["rest"]))
            self.snap.place_finger(name, frame @ rotation.to_matrix().to_4x4())

    def retrieve_cost(self, rotations):
        self.apply(rotations)
        distances = self.retrieve_distances()
        penetration = (sum(max(0.0, .001 - gap) ** 2 for gap in distances) / len(distances)
                       + max(0.0, .001 - min(distances)) ** 2)
        contact = min(abs(gap - .001) for gap in distances)
        comfort = sum(comfort.retrieve_cost(rotation) for comfort, rotation in zip(self.comforts, rotations))
        return 1000 * penetration + contact ** 2 + .000001 * comfort

    def fit(self):
        if min(self.retrieve_distances()) < -.001:
            directions = [[(index, 0, 1) for index in range(len(self.chain))]]
            if self.chain[0][1]["finger"] == "thumb":
                directions.extend([[(0, first, 1), (0, second, sign)]
                                   for first, second in ((0, 1), (0, 2), (1, 2)) for sign in (-1, 1)])
            search = JointRotationSearch(self.comforts, self.retrieve_cost, directions)
            seeds = [self.retrieve_rotations(), [comfort.preferred for comfort in self.comforts]]
            for bound in (0, 1):
                seeds.append([Euler((comfort.bounds[0][bound], comfort.preferred.y, comfort.preferred.z), "XYZ")
                              for comfort in self.comforts])
            rotations = search.refine(min(seeds, key=self.retrieve_cost))
            self.apply(rotations)
        return max(0.0, -min(self.retrieve_distances()))
