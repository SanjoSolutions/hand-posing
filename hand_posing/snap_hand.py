# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Sanjo Solutions

"""Pose a selected Rigify hand against a mesh surface on request."""

import json
import math

import bpy
from mathutils import Euler, Matrix, Vector
from mathutils.bvhtree import BVHTree

from .rig_binding import uses_rig

SNAP_HAND_IMPLEMENTATION = "minimal_movement_v4"


def retrieve_matrix(values):
    return Matrix([values[index:index + 4] for index in range(0, 16, 4)])


class HandSurface:
    """Snapshot the evaluated target so a snap has a stable surface."""

    def __init__(self, target, graph, rig, side):
        self.target = target
        evaluated = target.evaluated_get(graph)
        mesh = evaluated.data
        omitted = set()
        own_body = uses_rig(target, rig)
        if own_body:
            # The IK solve moves this entire arm. Its starting skin belongs to
            # the moving limb, while the remaining body supplies the target.
            groups = {group.index for group in target.vertex_groups
                      if side in group.name.split(".")[1:]
                      and group.name.startswith(("DEF-hand", "DEF-palm", "DEF-f_", "DEF-thumb",
                                                 "DEF-forearm", "DEF-upper_arm"))}
            omitted = {vertex.index for vertex in mesh.vertices
                       if sum(weight.weight for weight in vertex.groups if weight.group in groups) > 0.25}
        polygons = [tuple(polygon.vertices) for polygon in mesh.polygons
                    if all(index not in omitted for index in polygon.vertices)]
        if not polygons:
            raise ValueError("Choose a mesh with a surface outside the selected hand")
        self.tree = BVHTree.FromPolygons(
            [evaluated.matrix_world @ vertex.co for vertex in mesh.vertices], polygons,
        )

    def retrieve_nearest(self, point):
        location, normal, _index, _distance = self.tree.find_nearest(point)
        if location is None:
            raise ValueError("Choose a mesh with polygon geometry")
        return location, normal


class PalmPlacement:
    """Fit nearby palm support while favoring the current wrist control pose."""

    # In meters.
    clearance = 0.001

    def __init__(self, surface, previous, samples, control=None):
        self.surface = surface
        self.samples = [Vector(sample) for sample in samples]
        self.previous = previous.copy()
        self.control = control.copy() if control is not None else previous.copy()
        self.control_offset = previous.inverted() @ self.control
        self.rotation_radius = max((sample - self.control_offset.translation).length for sample in self.samples)
        location, normal = surface.retrieve_nearest(previous.translation)
        heading = previous.to_3x3().col[1]
        tangent = heading - normal * heading.dot(normal)
        if tangent.length < 1e-6:
            tangent = normal.orthogonal()
        tangent.normalize()
        self.frame = Matrix((tangent.cross(normal), tangent, normal)).transposed().to_4x4()
        self.frame.translation = location + normal * self.clearance

    def retrieve_contacts(self, palm):
        contacts = []
        for sample in self.samples:
            point = palm @ sample
            nearest, normal = self.surface.retrieve_nearest(point)
            contacts.append((point - nearest, normal))
        return contacts

    def retrieve_candidate(self, rotation):
        palm = self.frame @ rotation.to_matrix().to_4x4()
        for _iteration in range(24):
            contacts = self.retrieve_contacts(palm)
            offset, normal = min(contacts, key=lambda contact: contact[0].dot(contact[1]))
            correction = offset.dot(normal) - self.clearance
            palm.translation -= normal * correction
            if abs(correction) < 0.000001:
                break
        return palm

    def retrieve_movement_cost(self, palm):
        control = palm @ self.control_offset
        translation = (control.translation - self.control.translation).length
        difference = self.control.to_quaternion().rotation_difference(control.to_quaternion()).angle
        angle = min(difference, 2 * math.pi - difference)
        return translation + self.rotation_radius * angle

    def retrieve_cost(self, palm):
        contacts = self.retrieve_contacts(palm)
        penetration = max(0.0, self.clearance - min(offset.dot(normal) for offset, normal in contacts))
        gaps = [max(0.0, offset.length - self.clearance - 0.0015) for offset, _normal in contacts]
        # Every support region contributes, including the heel and both palm edges.
        return (30.0 * penetration + sum(gaps) / len(gaps) + 0.25 * max(gaps)
                + 0.1 * self.retrieve_movement_cost(palm))

    def retrieve_pose(self):
        aligned = self.frame.copy()
        self.frame = self.previous.copy()
        retained = self.retrieve_candidate(Euler((0, 0, 0), "XYZ"))
        self.frame = aligned
        rotation = Euler((0.0, 0.0, 0.0), "XYZ")
        palm = self.retrieve_candidate(rotation)
        cost = self.retrieve_cost(palm)
        retained_cost = self.retrieve_cost(retained)
        if retained_cost <= cost:
            self.frame = self.previous.copy()
            palm, cost = retained, retained_cost
        for step in (15, 8, 4, 2, 1, 0.5, 0.25):
            for _iteration in range(8):
                improved = False
                for axis in (0, 1):
                    for sign in (-1, 1):
                        candidate_rotation = rotation.copy()
                        candidate_rotation[axis] = min(max(
                            rotation[axis] + sign * math.radians(step), -math.pi / 3), math.pi / 3)
                        candidate = self.retrieve_candidate(candidate_rotation)
                        candidate_cost = self.retrieve_cost(candidate)
                        if candidate_cost < cost - 1e-8:
                            rotation, palm, cost = candidate_rotation, candidate, candidate_cost
                            improved = True
                if not improved:
                    break
        return palm


class FingerComfort:
    """Favor calibrated resting rotations, close spread, and coordinated flexion."""

    def __init__(self, calibration, parent_flexion=None, heading=None):
        self.bounds = [tuple(bounds) for bounds in calibration["bounds"]]
        self.weights = (1.0, 20.0, 40.0) if calibration["finger"] == "thumb" else (1.0, 2.0, 80.0)
        segment = calibration["segment"]
        self.rest_flexion = retrieve_matrix(calibration["rest"]).to_euler("XYZ").x
        self.follow_flexion = (0.65 * max(0.0, parent_flexion)
                               if segment == 3 and parent_flexion is not None else None)
        spread = (math.atan2(-heading.x, heading.y)
                  if segment == 1 and calibration["finger"] != "thumb" and heading is not None else 0.0)
        if segment == 1 and calibration["finger"] != "thumb" and heading is not None:
            lower, upper = self.bounds[2]
            self.bounds[2] = (max(lower, spread - math.radians(20)), min(upper, spread + math.radians(20)))
        self.preferred = self.clamp((0.0, 0.0, spread))

    def clamp(self, angles):
        return Euler(tuple(min(max(angle, lower), upper)
                           for angle, (lower, upper) in zip(angles, self.bounds)), "XYZ")

    def retrieve_cost(self, angles):
        cost = 0.0
        for angle, preferred, (lower, upper), weight in zip(
                angles, self.preferred, self.bounds, self.weights):
            if upper > lower:
                cost += weight * (angle - preferred) ** 2
                extent = upper - preferred if angle >= preferred else preferred - lower
                # Euler channels use single precision; a preferred angle at a
                # bound has zero available motion despite representation noise.
                if extent > 1e-6:
                    effort = abs(angle - preferred) / extent
                    cost += 20.0 * max(0.0, effort - 0.75) ** 2
        if self.follow_flexion is not None:
            cost += 0.25 * (angles.x + self.rest_flexion - self.follow_flexion) ** 2
        return cost


class JointRotationSearch:
    """Refine bounded rotations with individual and coordinated joint steps."""

    def __init__(self, comforts, retrieve_cost, directions=None):
        self.comforts = comforts
        self.retrieve_cost = retrieve_cost
        self.directions = [[(joint, axis, 1)] for joint, comfort in enumerate(comforts)
                           for axis, (lower, upper) in enumerate(comfort.bounds) if upper > lower]
        self.directions.extend(directions or [])

    def refine(self, rotations):
        rotations = [comfort.clamp(rotation) for comfort, rotation in zip(self.comforts, rotations)]
        cost = self.retrieve_cost(rotations)
        for step in (10, 5, 2, 1, 0.5, 0.25):
            for _iteration in range(8):
                improved = False
                for direction in self.directions:
                    for sign in (-1, 1):
                        candidate = [rotation.copy() for rotation in rotations]
                        for joint, axis, factor in direction:
                            candidate[joint][axis] += sign * factor * math.radians(step)
                            candidate[joint] = self.comforts[joint].clamp(candidate[joint])
                        candidate_cost = self.retrieve_cost(candidate)
                        if candidate_cost < cost - 1e-10:
                            rotations, cost = candidate, candidate_cost
                            improved = True
                if not improved:
                    break
        return rotations


class FingerCurlContact:
    """Find bounded surface tangencies along a finger's flexion arc."""

    def __init__(self, placement):
        self.placement = placement
        self.samples = {}

    def retrieve_sample(self, flexion):
        if flexion not in self.samples:
            rotation = self.placement.comfort.preferred.copy()
            rotation.x = flexion
            distances = self.placement.retrieve_distances(rotation)
            self.samples[flexion] = (rotation, min(distances), self.placement.retrieve_cost(rotation, distances))
        return self.samples[flexion]

    def retrieve_rotation(self):
        lower, upper = self.placement.comfort.bounds[0]
        angles = sorted({lower + (upper - lower) * index / 12 for index in range(13)}
                        | {self.placement.comfort.preferred.x})
        for first, second in zip(angles, angles[1:]):
            first_gap = self.retrieve_sample(first)[1]
            second_gap = self.retrieve_sample(second)[1]
            if first_gap * second_gap < 0:
                for _iteration in range(18):
                    middle = (first + second) / 2
                    middle_gap = self.retrieve_sample(middle)[1]
                    if first_gap * middle_gap > 0:
                        first, first_gap = middle, middle_gap
                    else:
                        second, second_gap = middle, middle_gap
                    if abs(middle_gap) < 0.000001:
                        break
        for angle in angles:
            self.retrieve_sample(angle)
        # A tangent can remain clear at both sampled ends. Refine the best
        # interval as well as crossings so these contacts receive equal precision.
        ordered = sorted(self.samples)
        selected = min(ordered, key=lambda angle: self.samples[angle][2])
        index = ordered.index(selected)
        self.refine_interval(ordered[max(0, index - 1)], selected,
                             ordered[min(len(ordered) - 1, index + 1)],
                             lambda angle: self.retrieve_sample(angle)[2])
        return min(self.samples.values(), key=lambda sample: sample[2])[0]

    def refine_interval(self, lower, selected, upper, score):
        for _iteration in range(16):
            if upper - lower < math.radians(0.05):
                break
            bracket = sorted({lower, (lower + selected) / 2, selected,
                              (selected + upper) / 2, upper})
            selected = min(bracket, key=score)
            index = bracket.index(selected)
            lower = bracket[max(0, index - 1)]
            upper = bracket[min(len(bracket) - 1, index + 1)]


class FingerPlacement:
    """Balance surface support and comfortable rotation within joint limits."""

    def __init__(self, surface, frame, palm, calibration, parent_flexion=None):
        self.surface = surface
        self.frame = frame
        self.input = frame.copy()
        self.samples = [Vector(sample) for sample in calibration["samples"]]
        pads = self.samples[:4]
        self.pads = [first.lerp(second, fraction / 4)
                     for first, second in zip(pads, pads[1:]) for fraction in range(4)] + pads[-1:]
        self.hinge_contact = calibration["segment"] == 1 and calibration["finger"] != "thumb"
        self.opposition = calibration["segment"] == 1 and calibration["finger"] == "thumb"
        self.directions = ([[(0, first, 1), (0, second, sign)]
                            for first, second in ((0, 1), (0, 2), (1, 2)) for sign in (-1, 1)]
                           if self.opposition else [])
        self.bounds = calibration["bounds"]
        self.comfort = FingerComfort(calibration, parent_flexion,
                                     frame.to_3x3().inverted() @ palm.to_3x3().col[1])
        self.clearance = 0.001
        if calibration["segment"] == 1:
            nearest, _normal = surface.retrieve_nearest(frame @ self.samples[0])
            relative = frame.inverted() @ nearest
            spread = min(max(math.atan2(-relative.x, relative.y), -math.pi / 4), math.pi / 4)
            self.input = frame @ Matrix.Rotation(spread, 4, "Z")
            if calibration["finger"] == "thumb":
                normal = self.input.to_3x3().inverted() @ -palm.to_3x3().col[2]
                self.input = self.input @ Matrix.Rotation(math.atan2(normal.x, normal.z), 4, "Y")
        self.inverse = self.input.inverted()

    def retrieve_projection(self, sample):
        point = sample.copy()
        for _iteration in range(16):
            nearest, normal = self.surface.retrieve_nearest(self.input @ point)
            projected = self.inverse @ (nearest + normal * self.clearance)
            projected.x = sample.x
            if projected.length > 1e-10:
                projected *= sample.length / projected.length
            change = (projected - point).length
            point = projected
            if change < 0.000001:
                break
        return point

    def retrieve_candidate(self, sample):
        point = self.retrieve_projection(sample)
        angle = math.atan2(point.z, point.y) - math.atan2(sample.z, sample.y)
        rotation = (self.frame.inverted() @ self.input @ Matrix.Rotation(angle, 4, "X")).to_euler("XYZ")
        return self.comfort.clamp(rotation)

    def retrieve_distances(self, rotation):
        candidate = self.frame @ rotation.to_matrix().to_4x4()
        distances = []
        for pad in [*self.pads, *self.samples[4:]]:
            point = candidate @ pad
            nearest, normal = self.surface.retrieve_nearest(point)
            distances.append((point - nearest).dot(normal) - self.clearance)
        return distances

    def retrieve_cost(self, rotation, distances=None):
        if distances is None:
            distances = self.retrieve_distances(rotation)
        penetration = max(0.0, -min(distances))
        gaps = [max(0.0, distance - 0.0005) for distance in distances[:len(self.pads)]]
        gap = sum(gaps) / len(gaps) + 0.25 * max(gaps)
        following = distances[len(self.pads):]
        if self.opposition and following:
            # The thumb base positions its phalanges for the following curl fits.
            gap += 0.5 * sum(max(0.0, distance - 0.0005) for distance in following) / len(following)
        support = (6.0 * max(0.0, distances[len(self.pads) - 1] - 0.0005)
                   if self.hinge_contact else 0.0)
        # Contact inside this small tolerance allows the joints to relax.
        return 30.0 * penetration + gap + support + 0.0005 * self.comfort.retrieve_cost(rotation)

    def retrieve_pose(self):
        if self.opposition:
            candidates = [self.retrieve_candidate(sample) for sample in self.samples]
            candidates.append(self.comfort.preferred)
            seeds = sorted(candidates, key=self.retrieve_cost)[:3]
            search = JointRotationSearch([self.comfort], lambda rotations: self.retrieve_cost(rotations[0]), self.directions)
            rotations = [search.refine([seed])[0] for seed in seeds]
            rotation = min(rotations, key=self.retrieve_cost)
        else:
            rotation = FingerCurlContact(self).retrieve_rotation()
        return self.frame @ rotation.to_matrix().to_4x4()


class HandSnap:
    calibration_property = "Snap Hand Calibration"

    def __init__(self, context, rig, side, calibration=None):
        self.context = context
        self.rig = rig
        self.side = side
        self.hand = rig.pose.bones[f"hand_ik.{side}"]
        self.calibration = calibration if calibration is not None else json.loads(self.hand[self.calibration_property])
        self.wrist = retrieve_matrix(self.calibration["wrist"])

    def retrieve_hand_pose(self):
        graph = self.context.evaluated_depsgraph_get()
        evaluated = self.rig.evaluated_get(graph)
        return evaluated.matrix_world @ evaluated.pose.bones[f"DEF-hand.{self.side}"].matrix

    def retrieve_palm_placement(self, surface):
        previous = self.retrieve_hand_pose() @ self.wrist.inverted()
        evaluated = self.rig.evaluated_get(self.context.evaluated_depsgraph_get())
        control = evaluated.matrix_world @ evaluated.pose.bones[self.hand.name].matrix
        return PalmPlacement(surface, previous, self.calibration["support"], control)

    def retrieve_palm_pose(self, surface):
        return self.retrieve_palm_placement(surface).retrieve_pose()

    def place_wrist(self, desired):
        for _iteration in range(16):
            current = self.retrieve_hand_pose()
            if ((current.translation - desired.translation).length < 0.00001
                    and current.to_quaternion().rotation_difference(desired.to_quaternion()).angle < 0.0001):
                break
            graph = self.context.evaluated_depsgraph_get()
            control = self.rig.evaluated_get(graph).pose.bones[self.hand.name]
            world = desired @ current.inverted() @ self.rig.matrix_world @ control.matrix
            self.hand.matrix = self.rig.matrix_world.inverted() @ world
            self.rig.update_tag()
            self.context.view_layer.update()

    def fit_fingers(self, surface, palm):
        fingers = sorted(self.calibration["fingers"].items(), key=lambda item: item[1]["segment"])
        for finger in dict.fromkeys(calibration["finger"] for _name, calibration in fingers):
            chain = [(name, calibration) for name, calibration in fingers if calibration["finger"] == finger]
            self.fit_finger(surface, palm, chain)

    def fit_finger(self, surface, palm, chain):
        flexion = None
        for index, (name, calibration) in enumerate(chain):
            graph = self.context.evaluated_depsgraph_get()
            evaluated = self.rig.evaluated_get(graph)
            frame = (evaluated.matrix_world @ evaluated.pose.bones[calibration["parent"]].matrix
                     @ retrieve_matrix(calibration["rest"]))
            samples = list(calibration["samples"][:4])
            continuation = Matrix.Identity(4)
            for _child_name, child in chain[index + 1:]:
                continuation = (continuation @ retrieve_matrix(child["rest"])
                                @ Matrix.Rotation(child["bounds"][0][0], 4, "X"))
                samples.extend(list(continuation @ Vector(sample)) for sample in child["samples"][:4])
            pose = FingerPlacement(surface, frame, palm, dict(calibration, samples=samples), flexion).retrieve_pose()
            self.place_finger(name, pose)
            evaluated = self.rig.evaluated_get(self.context.evaluated_depsgraph_get())
            joint = evaluated.pose.bones[calibration["parent"]].matrix.inverted() @ evaluated.pose.bones[name].matrix
            flexion = joint.to_euler("XYZ").x

    def place_finger(self, name, pose):
        self.rig.pose.bones[name].matrix = self.rig.matrix_world.inverted() @ pose
        self.rig.update_tag()
        self.context.view_layer.update()

    def fit_pose(self, surface, palm):
        self.place_wrist(palm @ self.wrist)
        fitted = self.retrieve_hand_pose() @ self.wrist.inverted()
        for _iteration in range(3):
            settlement = PalmPlacement(surface, fitted, self.calibration["support"])
            settlement.frame = fitted.copy()
            settled = settlement.retrieve_candidate(Euler((0, 0, 0), "XYZ"))
            if (settled.translation - fitted.translation).length < 0.00001:
                break
            self.place_wrist(settled @ self.wrist)
            fitted = self.retrieve_hand_pose() @ self.wrist.inverted()
        self.fit_fingers(surface, fitted)
        return fitted

    def retrieve_middle_contacts(self, surface):
        evaluated = self.rig.evaluated_get(self.context.evaluated_depsgraph_get())
        contacts = []
        for name, calibration in self.calibration["fingers"].items():
            if calibration["segment"] == 1 and calibration["finger"] != "thumb":
                point = (evaluated.matrix_world @ evaluated.pose.bones[name].matrix
                         @ Vector(calibration["samples"][3]))
                nearest, normal = surface.retrieve_nearest(point)
                contacts.append((point - nearest, normal))
        return contacts

    def fit_hand(self, surface):
        placement = self.retrieve_palm_placement(surface)
        palm = self.fit_pose(surface, placement.retrieve_pose())
        contacts = self.retrieve_middle_contacts(surface)
        supports = placement.retrieve_contacts(palm)
        if (max(offset.length for offset, _normal in contacts) > 0.003
                and sum(offset.length for offset, _normal in supports) / len(supports) > 0.006):
            # A curved grip can need a forward palm tilt to support its middle hinges.
            placement.frame = palm.copy()
            names = [self.hand.name, *self.calibration["fingers"]]
            poses = {name: self.rig.pose.bones[name].matrix_basis.copy() for name in names}
            cost = self.retrieve_fit_cost(placement, palm, contacts)
            for tilt in (-10, -20, -30, -40, -45):
                candidate = placement.retrieve_candidate(Euler((math.radians(tilt), 0, 0), "XYZ"))
                candidate = self.fit_pose(surface, candidate)
                contacts = self.retrieve_middle_contacts(surface)
                candidate_cost = self.retrieve_fit_cost(placement, candidate, contacts)
                if candidate_cost < cost:
                    cost = candidate_cost
                    poses = {name: self.rig.pose.bones[name].matrix_basis.copy() for name in names}
            for name, pose in poses.items():
                self.rig.pose.bones[name].matrix_basis = pose
            self.rig.update_tag()
            self.context.view_layer.update()

    def retrieve_fit_cost(self, placement, palm, contacts):
        return (placement.retrieve_cost(palm)
                + 6.0 * sum(max(0.0, offset.length - 0.0015) for offset, _normal in contacts)
                + 30.0 * sum(max(0.0, 0.001 - offset.dot(normal)) for offset, normal in contacts)
                + self.retrieve_finger_support_cost(placement.surface)
                + 0.0005 * self.retrieve_rest_cost(palm))

    def retrieve_finger_support_cost(self, surface):
        evaluated = self.rig.evaluated_get(self.context.evaluated_depsgraph_get())
        cost = 0.0
        for name, calibration in self.calibration["fingers"].items():
            pose = evaluated.matrix_world @ evaluated.pose.bones[name].matrix
            gaps = []
            for sample in calibration["samples"][:4]:
                point = pose @ Vector(sample)
                nearest, normal = surface.retrieve_nearest(point)
                gaps.append((point - nearest).dot(normal))
            # The thumb base is a metacarpal; its phalanges carry the grip contact.
            weight = (0.25 if calibration["segment"] == 1 else 2.0) if calibration["finger"] == "thumb" else 3.0
            cost += (30.0 * max(0.0, 0.001 - min(gaps))
                     + weight * sum(max(0.0, gap - 0.0015) for gap in gaps) / len(gaps))
            if calibration["finger"] != "thumb":
                cost += 6.0 * max(0.0, sum(gaps) / len(gaps) - 0.004)
        return cost

    def retrieve_rest_cost(self, palm):
        evaluated = self.rig.evaluated_get(self.context.evaluated_depsgraph_get())
        hand = evaluated.pose.bones[f"DEF-hand.{self.side}"]
        rest = (hand.parent.matrix @ hand.parent.bone.matrix_local.inverted() @ hand.bone.matrix_local
                if hand.parent else hand.bone.matrix_local)
        difference = rest.to_quaternion().rotation_difference(hand.matrix.to_quaternion()).angle
        wrist_cost = min(difference, 2 * math.pi - difference) ** 2
        finger_cost = 0.0
        for name, calibration in self.calibration["fingers"].items():
            frame = evaluated.matrix_world @ evaluated.pose.bones[calibration["parent"]].matrix @ retrieve_matrix(calibration["rest"])
            rotation = (frame.inverted() @ evaluated.matrix_world @ evaluated.pose.bones[name].matrix).to_euler("XYZ")
            comfort = FingerComfort(calibration, heading=frame.to_3x3().inverted() @ palm.to_3x3().col[1])
            finger_cost += comfort.retrieve_cost(rotation)
        return wrist_cost + finger_cost / len(self.calibration["fingers"])

    def retrieve_controls(self):
        return [self.hand, *[self.rig.pose.bones[name] for name in self.calibration["fingers"]]]

    def snap(self, target, keyframe=False):
        if target is None or target.type != "MESH":
            raise ValueError("Choose the hand's target mesh in the Hand Posing panel")
        surface = HandSurface(target, self.context.evaluated_depsgraph_get(), self.rig, self.side)
        poses = {bone.name: bone.matrix_basis.copy() for bone in self.retrieve_controls()}
        parent = self.rig.pose.bones[f"upper_arm_parent.{self.side}"]
        previous_blend = parent["IK_FK"]
        try:
            parent["IK_FK"] = 0.0
            self.rig.update_tag()
            self.context.view_layer.update()
            self.fit_hand(surface)
            from .finger_groups import fit_finger_groups
            fit_finger_groups(self, surface)
            if keyframe:
                parent.keyframe_insert('["IK_FK"]', group=parent.name)
                for name in poses:
                    bone = self.rig.pose.bones[name]
                    rotation = "rotation_quaternion" if bone.rotation_mode == "QUATERNION" else "rotation_axis_angle" if bone.rotation_mode == "AXIS_ANGLE" else "rotation_euler"
                    for path in ("location", rotation, "scale"):
                        bone.keyframe_insert(path, group=name)
        except Exception:
            for name, pose in poses.items():
                self.rig.pose.bones[name].matrix_basis = pose
            parent["IK_FK"] = previous_blend
            self.rig.update_tag()
            self.context.view_layer.update()
            raise
        return self.hand


class SkinHandSnap(HandSnap):
    """Fit measured Rigify skin independently of its control widget design."""

    def __init__(self, context, rig, side):
        super().__init__(context, rig, side)
        from .convex_hand_snap import PalmSkin
        self.skin = PalmSkin(context, rig, side)
        if self.skin.object is None:
            raise ValueError("Choose the calibrated hand skin or calibrate the hand")

    def retrieve_palm_placement(self, surface):
        previous = self.retrieve_hand_pose() @ self.wrist.inverted()
        inverse = previous.inverted()
        mesh = self.skin.object.evaluated_get(self.context.evaluated_depsgraph_get())
        indices = {index for calibration in self.calibration["fingers"].values()
                   if calibration["finger"] != "thumb" for index in calibration["skin_vertices"]}
        points = [*map(Vector, self.calibration["support"]),
                  *[inverse @ mesh.matrix_world @ mesh.data.vertices[index].co for index in indices]]
        cells = {}
        for point in points:
            cell = (round(point.x / .012), round(point.y / .012))
            if cell not in cells or point.z < cells[cell].z:
                cells[cell] = point
        control = self.rig.matrix_world @ self.hand.matrix
        return PalmPlacement(surface, previous, list(cells.values()), control)

    def place_finger(self, name, pose):
        candidate = pose.copy()
        for _iteration in range(8):
            super().place_finger(name, candidate)
            evaluated = self.rig.evaluated_get(self.context.evaluated_depsgraph_get())
            current = evaluated.matrix_world @ evaluated.pose.bones[name].matrix
            distance = (current.translation - pose.translation).length
            angle = current.to_quaternion().rotation_difference(pose.to_quaternion()).angle
            if distance < 0.00001 and min(angle, 2 * math.pi - angle) < 0.0001:
                break
            candidate = pose @ current.inverted() @ candidate

    def fit_hand(self, surface):
        placement = self.retrieve_palm_placement(surface)
        self.fit_pose(surface, placement.retrieve_pose())
        from .skin_finger_refinement import SkinFingerRefinement, retrieve_skin_contacts
        fingers = sorted(self.calibration["fingers"].items(), key=lambda item: item[1]["segment"])
        refinements = {}
        for finger in dict.fromkeys(calibration["finger"] for _name, calibration in fingers):
            chain = [(name, calibration) for name, calibration in fingers if calibration["finger"] == finger]
            refinement = SkinFingerRefinement(self, surface, chain)
            refinement.fit()
            refinements[finger] = refinement
        indices = {*self.skin.indices, *[index for refinement in refinements.values() for index in refinement.indices]}
        for _iteration in range(4):
            contacts = retrieve_skin_contacts(self.context, self.skin.object, indices, surface)
            distance, normal, _point = min(contacts, key=lambda contact: contact[0])
            if distance >= -.001:
                break
            desired = self.retrieve_hand_pose()
            desired.translation += normal * (.001 - distance)
            self.place_wrist(desired)
        finger_measurements = {finger: max(0., -min(refinement.retrieve_distances()))
                               for finger, refinement in refinements.items()}
        finger_penetration = max(finger_measurements.values())
        contacts = self.skin.retrieve_contacts(surface)
        penetration = self.skin.retrieve_penetration(surface)
        gap = min((abs(distance) for distance, _normal, _point in contacts), default=math.inf)
        if max(penetration, finger_penetration) > 0.002 or gap > 0.008:
            raise ValueError(f"Adjust the arm pose or surface: palm penetration {penetration:.4f}, "
                             f"finger penetration {finger_penetration:.4f} "
                             f"({max(finger_measurements, key=finger_measurements.get)}), palm gap {gap:.4f}")


def retrieve_snap_solver(context, rig, side):
    calibration = json.loads(rig.pose.bones[f"hand_ik.{side}"][HandSnap.calibration_property])
    if calibration.get("contact_geometry") == "skin":
        solver = SkinHandSnap(context, rig, side)
    else:
        from .convex_hand_snap import ConvexHandSnap
        solver = ConvexHandSnap(context, rig, side)
    return solver


def retrieve_selected_hand(context):
    rig = context.object
    bone = context.active_pose_bone
    if rig and rig.type == "ARMATURE" and context.mode == "POSE" and bone:
        side = bone.name.rsplit(".", 1)[-1]
        hand = rig.pose.bones.get(f"hand_ik.{side}")
        if bone.name.startswith(("hand_", "f_index", "f_middle", "f_ring", "f_pinky", "thumb", "palm")) and hand and HandSnap.calibration_property in hand:
            return rig, side
    return None


def register():
    from . import register as register_addon
    register_addon()
