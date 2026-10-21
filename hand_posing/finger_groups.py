# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Sanjo Solutions

"""Keep grouped fingers together using evaluated, bounded rig controls."""

from itertools import combinations

from mathutils import Vector

from .snap_hand import FingerComfort, JointRotationSearch, retrieve_matrix
from .skin_finger_refinement import retrieve_skin_contacts


class FingerGroupFit:
    """Refine one group without moving the wrist or unrelated controls."""

    def __init__(self, snap, surface, members):
        self.snap, self.surface = snap, surface
        self.members = members
        self.joints = sorted(snap.calibration["fingers"].items(), key=lambda item: item[1]["segment"])
        self.chain = [(name, calibration) for name, calibration in self.joints
                      if calibration["finger"] in members]
        self.rest = {name: retrieve_matrix(calibration["rest"]) for name, calibration in self.chain}
        self.comforts = [FingerComfort(calibration) for _name, calibration in self.chain]
        self.skin = getattr(getattr(snap, "skin", None), "object", None)
        self.indices = {index for _name, calibration in self.chain
                        for index in calibration.get("skin_vertices", [])} if self.skin else set()
        evaluated = snap.rig.evaluated_get(snap.context.evaluated_depsgraph_get())
        self.rotations = [(self.rest[name].inverted()
                           @ evaluated.pose.bones[calibration["parent"]].matrix.inverted()
                           @ evaluated.pose.bones[name].matrix).to_euler("XYZ")
                          for name, calibration in self.chain]
        self.applied = None
        self.radii = {}
        mesh = self.skin.evaluated_get(snap.context.evaluated_depsgraph_get()) if self.skin else None
        for name, calibration in self.joints:
            matrix = evaluated.matrix_world @ evaluated.pose.bones[name].matrix
            indices = calibration.get("skin_vertices", [])
            if mesh and indices:
                if max(indices) >= len(mesh.data.vertices):
                    raise ValueError("Calibrate the hand after changing the skin topology")
                inverse = matrix.inverted()
                width = max(abs((inverse @ mesh.matrix_world @ mesh.data.vertices[index].co).x)
                            for index in indices)
            else:
                # Legacy calibrations contain pad depths but no skin widths.
                width = max(abs(sample[2]) for sample in calibration["samples"][:4])
            self.radii[name] = max(width * matrix.to_scale().x, .002)
        bases = {calibration["finger"]: evaluated.matrix_world @ evaluated.pose.bones[name].head
                 for name, calibration in self.chain if calibration["segment"] == 1}
        across = (snap.retrieve_hand_pose() @ snap.wrist.inverted()).to_3x3().col[0]
        ordered = sorted(members, key=lambda finger: bases[finger].dot(across))
        self.pairs = list(zip(ordered, ordered[1:]))
        self.minimum_gap = min(self.retrieve_distances())

    def apply(self, rotations):
        changed = set()
        for index, ((name, calibration), rotation) in enumerate(zip(self.chain, rotations)):
            if (self.applied is None or calibration["parent"] in changed
                    or any(abs(a - b) > 1e-7 for a, b in zip(rotation, self.applied[index]))):
                evaluated = self.snap.rig.evaluated_get(self.snap.context.evaluated_depsgraph_get())
                frame = (evaluated.matrix_world @ evaluated.pose.bones[calibration["parent"]].matrix
                         @ self.rest[name])
                self.snap.place_finger(name, frame @ rotation.to_matrix().to_4x4())
                changed.add(name)
        self.applied = [rotation.copy() for rotation in rotations]

    def retrieve_distances(self):
        if self.indices:
            return [gap for gap, _normal, _point in retrieve_skin_contacts(
                self.snap.context, self.skin, self.indices, self.surface)]
        evaluated = self.snap.rig.evaluated_get(self.snap.context.evaluated_depsgraph_get())
        gaps = []
        for name, calibration in self.chain:
            matrix = evaluated.matrix_world @ evaluated.pose.bones[name].matrix
            for sample in calibration["samples"][:4]:
                point = matrix @ Vector(sample)
                nearest, normal = self.surface.retrieve_nearest(point)
                gaps.append((point - nearest).dot(normal))
        return gaps

    def retrieve_spacing_cost(self):
        evaluated = self.snap.rig.evaluated_get(self.snap.context.evaluated_depsgraph_get())
        points = {}
        for name, calibration in self.joints:
            matrix = evaluated.matrix_world @ evaluated.pose.bones[name].matrix
            points.setdefault(calibration["finger"], []).extend(
                (matrix @ Vector((0, sample[1], 0)), self.radii[name])
                for sample in calibration["samples"][:4])
        together = 0.0
        for first, second in self.pairs:
            gaps = [(a - b).length - ra - rb - .001
                    for (a, ra), (b, rb) in zip(points[first], points[second])]
            together += sum(max(0., gap) ** 2 for gap in gaps) / len(gaps)
        overlap = 0.0
        for first, second in combinations(points, 2):
            if first in self.members or second in self.members:
                # Preserve space for other fingers, including between nonadjacent members.
                overlap += max(max(0., ra + rb - (a - b).length) ** 2
                               for (a, ra), (b, rb) in zip(points[first], points[second]))
        return 4 * together + 100 * overlap

    def retrieve_cost(self, rotations):
        self.apply(rotations)
        gaps = self.retrieve_distances()
        penetration = max(0., .001 - min(gaps))
        # Grouping must not undo the surface clearance from the hand fit.
        excess = max(0., min(self.minimum_gap, -.001) - min(gaps))
        contact = sum(max(0., gap - .0015) ** 2 for gap in gaps) / len(gaps)
        comfort = sum(comfort.retrieve_cost(rotation) for comfort, rotation in zip(self.comforts, rotations))
        return (self.retrieve_spacing_cost() + 1000 * penetration ** 2 + contact
                + 100 * excess + .000001 * comfort)

    def fit(self):
        directions = [[(index, 0, 1) for index, (_name, calibration) in enumerate(self.chain)
                       if calibration["finger"] == finger] for finger in sorted(self.members)]
        search = JointRotationSearch(self.comforts, self.retrieve_cost, directions)
        rotations = search.refine(self.rotations)
        self.apply(rotations)


def fit_finger_groups(snap, surface):
    groups = getattr(snap.hand, "hand_posing_finger_groups", ())
    available = {calibration["finger"] for calibration in snap.calibration["fingers"].values()}
    for group in groups:
        members = group.fingers & available
        if len(members) > 1:
            FingerGroupFit(snap, surface, members).fit()
