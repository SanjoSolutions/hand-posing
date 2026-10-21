# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Sanjo Solutions

"""Experimental convex-surface rectangle fitting, separate from native rig posing."""

import math

from mathutils import Euler, Matrix, Vector
from mathutils.bvhtree import BVHTree


class RestingHandRectangle:
    """Prototype a fixed-contact rest rectangle on a convex target surface."""

    # In meters.
    clearance = 0.001

    def __init__(self, surface, previous, samples, control=None, footprint=None):
        self.surface = surface
        self.samples = [Vector(sample) for sample in samples]
        minimum = Vector(tuple(min(sample[axis] for sample in self.samples) for axis in range(3)))
        boundary = [*self.samples, *[Vector(point) for point in (footprint or [])]]
        heel = [sample for sample in self.samples if sample.y <= minimum.y + 0.012]
        self.anchor = Vector((sum(sample.x for sample in heel) / len(heel), minimum.y, minimum.z))
        offsets = [point - self.anchor for point in boundary]
        horizontal = sum(point.x ** 2 for point in offsets)
        vertical = sum(point.y ** 2 for point in offsets)
        mixed = sum(point.x * point.y for point in offsets)
        determinant = horizontal * vertical - mixed ** 2
        slope_x = slope_y = 0.0
        if determinant > 1e-12:
            first = sum(point.x * point.z for point in offsets)
            second = sum(point.y * point.z for point in offsets)
            slope_x = (vertical * first - mixed * second) / determinant
            slope_y = (horizontal * second - mixed * first) / determinant
        normal = Vector((-slope_x, -slope_y, 1)).normalized()
        heading = Vector((0, 1, slope_y)).normalized()
        self.rest_frame = Matrix((heading.cross(normal), heading, normal)).transposed()
        projected = [self.rest_frame.transposed() @ point for point in offsets]
        left, right = min(point.x for point in projected), max(point.x for point in projected)
        length = max(point.y for point in projected)
        self.rectangle = [self.anchor + self.rest_frame @ Vector((left + (right - left) * x / 4, length * y / 4, 0))
                          for x in range(5) for y in range(5)]
        self.weights = [(0.5 if x in (0, 4) else 1.0) * (0.5 if y in (0, 4) else 1.0)
                        for x in range(5) for y in range(5)]
        self.previous = previous.copy()
        self.control = control.copy() if control is not None else previous.copy()
        self.control_offset = previous.inverted() @ self.control
        self.rotation_radius = max((sample - self.control_offset.translation).length for sample in self.samples)
        location, self.normal = self.surface.retrieve_nearest(previous @ self.anchor)
        self.contact = location + self.normal * self.clearance
        self.frame = self.retrieve_frame(previous @ self.anchor)

    def retrieve_frame(self, point, heading=0.0):
        location, normal = self.surface.retrieve_nearest(point)
        direction = self.previous.to_3x3() @ self.rest_frame.col[1]
        tangent = direction - normal * direction.dot(normal)
        if tangent.length < 1e-6:
            tangent = normal.orthogonal()
        tangent.normalize()
        tangent = Matrix.Rotation(heading, 3, normal) @ tangent
        palm = (Matrix((tangent.cross(normal), tangent, normal)).transposed()
                @ self.rest_frame.transposed()).to_4x4()
        palm.translation = location + normal * self.clearance - palm.to_3x3() @ self.anchor
        return palm

    def retrieve_contacts(self, palm):
        contacts = []
        for sample in [*self.rectangle, *self.samples]:
            point = palm @ sample
            nearest, normal = self.surface.retrieve_nearest(point)
            contacts.append((point - nearest, normal))
        return contacts

    def retrieve_candidate(self, rotation):
        change = self.rest_frame @ rotation.to_matrix() @ self.rest_frame.transposed()
        palm = self.frame @ change.to_4x4()
        palm.translation = self.contact - palm.to_3x3() @ self.anchor
        return palm

    def retrieve_intersection(self, palm):
        corners = [palm @ self.rectangle[index] for index in (0, 20, 24, 4)]
        rectangle = BVHTree.FromPolygons(corners, [(0, 1, 2), (0, 2, 3)], all_triangles=True)
        return bool(rectangle.overlap(self.surface.tree))

    def retrieve_movement_cost(self, palm):
        return self.retrieve_control_movement(palm @ self.control_offset)

    def retrieve_control_movement(self, control):
        """Return translation plus hand-radius angular travel, in meters."""
        translation = (control.translation - self.control.translation).length
        difference = self.control.to_quaternion().rotation_difference(control.to_quaternion()).angle
        angle = min(difference, 2 * math.pi - difference)
        return translation + self.rotation_radius * angle

    def retrieve_cost(self, palm, clearance_tolerance=0.00001):
        """Score contact with a clearance tolerance expressed in meters."""
        intersects = self.retrieve_intersection(palm)
        contacts = self.retrieve_contacts(palm) if not intersects else []
        clearance = min((offset.dot(normal) for offset, normal in contacts), default=-math.inf)
        if clearance < self.clearance - clearance_tolerance:
            cost = math.inf
        else:
            gaps = [max(0.0, offset.length - self.clearance)
                    for offset, _normal in contacts[:len(self.rectangle)]]
            gap = sum(weight * distance for weight, distance in zip(self.weights, gaps)) / sum(self.weights)
            cost = gap + 0.001 * self.retrieve_movement_cost(palm)
        return cost

    def retrieve_axis_pose(self, palm, axis):
        basis = palm.to_3x3() @ self.rest_frame
        trials = {}

        def evaluate(angle):
            if angle not in trials:
                change = Matrix.Rotation(angle, 3, axis)
                candidate = (basis @ change @ self.rest_frame.transposed()).to_4x4()
                candidate.translation = self.contact - candidate.to_3x3() @ self.anchor
                trials[angle] = (self.retrieve_cost(candidate), candidate)
            return trials[angle][0]

        extent = 24 if axis == "Z" else 12
        angles = [math.radians(7.5 * index) for index in range(-extent, extent + 1)]
        for angle in angles:
            evaluate(angle)
        selected = min(angles, key=evaluate)
        index = angles.index(selected)
        lower, upper = angles[max(0, index - 1)], angles[min(len(angles) - 1, index + 1)]
        for _iteration in range(16):
            if upper - lower < math.radians(0.05):
                break
            bracket = sorted({lower, (lower + selected) / 2, selected, (selected + upper) / 2, upper})
            selected = min(bracket, key=evaluate)
            index = bracket.index(selected)
            lower, upper = bracket[max(0, index - 1)], bracket[min(len(bracket) - 1, index + 1)]
        return trials[selected][1]

    def refine(self, palm):
        cost = self.retrieve_cost(palm)
        for _sweep in range(8):
            previous_cost = cost
            for axis in ("X", "Y", "Z"):
                candidate = self.retrieve_axis_pose(palm, axis)
                candidate_cost = self.retrieve_cost(candidate)
                if candidate_cost < cost - 1e-8:
                    palm, cost = candidate, candidate_cost
            if previous_cost - cost < 1e-8:
                break
        return palm

    def retrieve_poses(self):
        retained = self.previous.copy()
        retained.translation = self.contact - retained.to_3x3() @ self.anchor
        palm = self.frame.copy()
        cost = self.retrieve_cost(palm)
        retained_cost = self.retrieve_cost(retained)
        seeds = [(cost, palm), (retained_cost, retained)]
        if retained_cost <= cost:
            palm, cost = retained, retained_cost
        for tilt, lean, heading in ((0, 0, -180), (0, 0, -90), (0, 0, 90),
                                    (-15, 0, 0), (15, 0, 0), (0, -15, 0), (0, 15, 0),
                                    (-30, 0, 0), (30, 0, 0)):
            candidate_rotation = Euler(tuple(math.radians(angle) for angle in (tilt, lean, heading)), "XYZ")
            candidate = self.retrieve_candidate(candidate_rotation)
            candidate_cost = self.retrieve_cost(candidate)
            seeds.append((candidate_cost, candidate))
            if candidate_cost < cost - 1e-8:
                palm, cost = candidate, candidate_cost
        seeds = sorted((seed for seed in seeds if math.isfinite(seed[0])), key=lambda seed: seed[0])[:4]
        poses = [pose for _cost, pose in seeds]
        for _seed_cost, seed in seeds:
            candidate = self.refine(seed)
            candidate_cost = self.retrieve_cost(candidate)
            poses.append(candidate)
            if candidate_cost < cost:
                palm, cost = candidate, candidate_cost
        if math.isfinite(cost) is False:
            raise ValueError("The wrist contact needs a clearer surface patch for the resting hand rectangle")
        return sorted(poses, key=self.retrieve_cost)

    def retrieve_pose(self):
        return self.retrieve_poses()[0]


