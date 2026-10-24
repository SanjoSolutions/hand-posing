# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Sanjo Solutions

"""Fit the hand control rectangle, palm, and fingers on a convex surface."""

import math

from mathutils import Euler, Matrix, Vector
from mathutils.bvhtree import BVHTree

from .snap_hand import HandSnap, FingerPlacement, retrieve_matrix
from .resting_hand_rectangle import RestingHandRectangle
from .rig_binding import uses_rig


class PalmSkin:
    """Measure evaluated palm skin while native palm controls change."""

    def __init__(self, context, rig, side):
        self.context = context
        self.object = None
        self.indices = []
        graph = context.evaluated_depsgraph_get()
        import json
        calibration = json.loads(rig.pose.bones[f"hand_ik.{side}"][HandSnap.calibration_property])
        skin_name = calibration.get("skin")
        skin_reference = getattr(rig.pose.bones[f"hand_ik.{side}"], "hand_on_surface_skin", None)
        if skin_reference:
            skin_name = skin_reference.name
        palm_groups = (("DEF-hand", "DEF-palm") if calibration.get("contact_geometry") == "skin"
                       else ("DEF-hand", "DEF-palm", "DEF-thumb.01"))
        for obj in context.scene.objects:
            if obj.type == "MESH" and uses_rig(obj, rig) and (skin_name is None or obj.name == skin_name):
                groups = {group.index for group in obj.vertex_groups if group.name.endswith("." + side)
                          and group.name.startswith(palm_groups)}
                evaluated = obj.evaluated_get(graph)
                indices = [vertex.index for vertex in evaluated.data.vertices
                           if sum(weight.weight for weight in vertex.groups if weight.group in groups) > 0.5]
                if len(indices) > len(self.indices):
                    self.object, self.indices = obj, indices

    def retrieve_penetration(self, surface):
        contacts = self.retrieve_contacts(surface)
        return max((max(0.0, -gap) for gap, _normal, _point in contacts), default=0.0)

    def retrieve_heel_gap(self, surface, palm, anchor):
        inverse = palm.inverted()
        return min((gap for gap, _normal, point in self.retrieve_contacts(surface)
                    if (inverse @ point).y <= anchor.y + 0.012), default=math.inf)

    def retrieve_contacts(self, surface):
        contacts = []
        if self.object:
            evaluated = self.object.evaluated_get(self.context.evaluated_depsgraph_get())
            for index in self.indices:
                point = evaluated.matrix_world @ evaluated.data.vertices[index].co
                nearest, normal = surface.retrieve_nearest(point)
                contacts.append(((point - nearest).dot(normal), normal, point))
        return contacts


class HandControlRectangle:
    """Sample the existing IK widget ahead of the wrist-to-palm contact."""

    def __init__(self, snap, placement):
        self.hand = snap.hand
        self.rig = snap.rig
        self.weights = [1.0] * len(placement.rectangle)
        shape = self.hand.custom_shape
        if (snap.calibration.get("contact_geometry") != "skin"
                and shape and shape.type == "MESH" and shape.data.vertices):
            size = self.hand.length if self.hand.use_custom_shape_bone_size else 1.0
            transform = Matrix.LocRotScale(self.hand.custom_shape_translation,
                                          self.hand.custom_shape_rotation_euler.to_quaternion(),
                                          self.hand.custom_shape_scale_xyz * size)
            if self.hand.custom_shape_transform:
                transform = self.hand.matrix.inverted() @ self.hand.custom_shape_transform.matrix @ transform
            vertices = [vertex.co for vertex in shape.data.vertices]
            lower = Vector(tuple(min(vertex[axis] for vertex in vertices) for axis in range(3)))
            upper = Vector(tuple(max(vertex[axis] for vertex in vertices) for axis in range(3)))
            axes = sorted(range(3), key=lambda axis: upper[axis] - lower[axis], reverse=True)[:2]
            heel = transform.inverted() @ snap.control_rest.inverted() @ placement.anchor
            lower.y = min(max(heel.y, lower.y), upper.y)
            self.samples = []
            for first in range(5):
                for second in range(5):
                    point = (lower + upper) / 2
                    for axis, fraction in zip(axes, (first / 4, second / 4)):
                        point[axis] = lower[axis] + (upper[axis] - lower[axis]) * fraction
                    self.samples.append(transform @ point)
        else:
            self.samples = [snap.control_rest.inverted() @ point for point in placement.rectangle]

    def retrieve_gap(self, surface):
        world = self.rig.matrix_world @ self.hand.matrix
        gaps = []
        clearance = math.inf
        points = [world @ sample for sample in self.samples]
        for point in points:
            nearest, normal = surface.retrieve_nearest(point)
            gaps.append((point - nearest).length)
            clearance = min(clearance, (point - nearest).dot(normal))
        rectangle = BVHTree.FromPolygons([points[index] for index in (0, 20, 24, 4)],
                                         [(0, 1, 2), (0, 2, 3)], all_triangles=True)
        if rectangle.overlap(surface.tree):
            clearance = -math.inf
        return sum(weight * gap for weight, gap in zip(self.weights, gaps)) / sum(self.weights), clearance


class HandControlPlacement:
    """Prefer small control corrections that retain usable evaluated contact."""

    def __init__(self, snap, placement):
        self.snap = snap
        self.placement = placement
        self.rectangle = HandControlRectangle(snap, placement)
        self.bases = [snap.retrieve_hand_pose() @ snap.wrist.inverted(),
                      placement.control @ snap.control_rest.inverted()]
        if (placement.reachable_pose.translation - self.bases[0].translation).length > 0.0001:
            self.bases.append(placement.reachable_pose)
        self.inverse = snap.rig.matrix_world.inverted()
        self.samples = {}

    def evaluate(self, seed, angles):
        key = (seed, *angles)
        if key not in self.samples:
            base = self.bases[seed]
            pose = base @ angles.to_matrix().to_4x4()
            pose.translation = base @ self.placement.anchor - pose.to_3x3() @ self.placement.anchor
            world = pose @ self.snap.control_rest
            for _iteration in range(6):
                self.snap.hand.matrix = self.inverse @ world
                self.snap.rig.update_tag()
                self.snap.context.view_layer.update()
                contacts = self.snap.skin.retrieve_contacts(self.placement.surface)
                gap, normal, _point = min(contacts, key=lambda contact: contact[0])
                aligned = self.snap.retrieve_hand_pose() @ self.snap.wrist.inverted() @ self.snap.control_rest
                difference = world.to_quaternion().rotation_difference(aligned.to_quaternion()).angle
                adjustment = gap - self.placement.clearance
                if abs(adjustment) < 0.00002 and difference < 0.001:
                    break
                world = aligned
                world.translation -= normal * adjustment
            distance, clearance = self.rectangle.retrieve_gap(self.placement.surface)
            cost = distance if gap >= -0.00002 and clearance >= -0.00002 else math.inf
            actual = self.snap.rig.matrix_world @ self.snap.hand.matrix
            movement = self.placement.retrieve_control_movement(actual)
            palm = self.snap.retrieve_hand_pose() @ self.snap.wrist.inverted()
            inverse = palm.inverted()
            heel = min((contact[0] for contact in contacts
                        if (inverse @ contact[2]).y <= self.placement.anchor.y + 0.012), default=math.inf)
            self.samples[key] = (cost, self.snap.hand.matrix_basis.copy(), distance, movement, heel)
        return self.samples[key]

    def fit(self):
        initial = self.evaluate(0, Euler((0, 0, 0)))[2]
        for seed in range(len(self.bases)):
            angles = Euler((0, 0, 0))
            best = self.evaluate(seed, angles)
            for step in (10, 5, 2, 1):
                for axis in range(3):
                    for sign in (-1, 1):
                        trial = angles.copy()
                        trial[axis] = min(max(trial[axis] + math.radians(step) * sign,
                                              -math.radians(30)), math.radians(30))
                        candidate = self.evaluate(seed, trial)
                        if candidate[0] < best[0]:
                            angles, best = trial, candidate
        available = [(key, sample) for key, sample in self.samples.items() if math.isfinite(sample[0])]
        if not available:
            raise ValueError("Adjust the arm pose or surface to reach clear hand contact within the wrist limits")
        reference_key, reference = min(available, key=lambda entry: entry[1][0])
        self.apply(reference_key, reference, initial)
        palm = self.snap.retrieve_hand_pose() @ self.snap.wrist.inverted()
        # Curved surfaces establish the attainable heel contact for this hand.
        self.placement.heel_tolerance = max(0.005, self.snap.skin.retrieve_heel_gap(
            self.placement.surface, palm, self.placement.anchor))
        reference_valid = self.snap.retrieve_contact_gap(
            self.placement.surface, self.placement, require_finger_contact=False) is not None
        retained = {bone.name: bone.matrix_basis.copy() for bone in self.snap.retrieve_controls()}
        reference_diagnostics = self.snap.wrist_diagnostics.copy()
        candidates = sorted(((key, sample) for key, sample in available
                             if sample[4] <= self.placement.heel_tolerance + 0.005
                             and (not reference_valid or sample[3] < reference[3])),
                            key=lambda entry: (entry[1][3], entry[1][0]))
        fitted = False
        tried = []
        for key, best in candidates:
            distinct = all((best[1].translation - basis.translation).length > 0.001
                           or best[1].to_quaternion().rotation_difference(basis.to_quaternion()).angle > 0.02
                           for basis in tried)
            if distinct:
                tried.append(best[1])
                self.apply(key, best, initial)
                if self.snap.retrieve_contact_gap(
                        self.placement.surface, self.placement, require_finger_contact=False) is not None:
                    fitted = True
                    break
                if len(tried) == 8:
                    break
        if not fitted and reference_valid:
            for name, basis in retained.items():
                self.snap.rig.pose.bones[name].matrix_basis = basis
            self.snap.rig.update_tag()
            self.snap.context.view_layer.update()
            self.snap.wrist_diagnostics = reference_diagnostics
        elif not fitted:
            raise ValueError("Adjust the arm pose or surface to reach clear hand contact within the wrist limits")
        self.refine(initial)

    def refine(self, initial):
        """Reduce rotation toward the authored pose while retaining fitted contact."""
        palm = self.snap.retrieve_hand_pose() @ self.snap.wrist.inverted()
        authored = self.placement.control @ self.snap.control_rest.inverted()
        correction = palm.to_quaternion().rotation_difference(authored.to_quaternion())
        seed = len(self.bases)
        self.bases.append(palm)
        retained = {bone.name: bone.matrix_basis.copy() for bone in self.snap.retrieve_controls()}
        diagnostics = self.snap.wrist_diagnostics.copy()
        movement = self.placement.retrieve_control_movement(self.snap.rig.matrix_world @ self.snap.hand.matrix)
        for fraction in (0.25, 0.125, 0.0625):
            angles = Euler((0, 0, 0)).to_quaternion().slerp(correction, fraction).to_euler("XYZ")
            sample = self.evaluate(seed, angles)
            if math.isfinite(sample[0]) and sample[3] < movement:
                self.apply((seed, *angles), sample, initial)
                if self.snap.retrieve_contact_gap(
                        self.placement.surface, self.placement, require_finger_contact=False) is not None:
                    movement = sample[3]
                    retained = {bone.name: bone.matrix_basis.copy() for bone in self.snap.retrieve_controls()}
                    diagnostics = self.snap.wrist_diagnostics.copy()
            for name, basis in retained.items():
                self.snap.rig.pose.bones[name].matrix_basis = basis
            self.snap.rig.update_tag()
            self.snap.context.view_layer.update()
        self.snap.wrist_diagnostics = diagnostics

    def apply(self, key, sample, initial):
        self.snap.hand.matrix_basis = sample[1]
        self.snap.rig.update_tag()
        self.snap.context.view_layer.update()
        self.snap.fit_pose(self.placement.surface, self.snap.retrieve_hand_pose() @ self.snap.wrist.inverted())
        self.snap.wrist_diagnostics.update({"rectangle_gap_before": initial, "rectangle_gap": sample[2],
                                           "rectangle_rotation": list(key[1:]), "control_movement": sample[3],
                                           "placement_heel_gap": sample[4]})


class PalmCupping:
    """Choose a gentle native palm bend before placing the finger chains."""

    def __init__(self, snap, surface, palm):
        self.snap = snap
        self.surface = surface
        self.palm = palm
        self.bone = snap.palm
        self.position, self.rotation, self.scale = self.bone.matrix_basis.decompose()
        self.angles = self.rotation.to_euler("XYZ")
        self.samples = {}

    def apply(self, angle):
        rotation = self.angles.copy()
        rotation.x = angle
        self.bone.matrix_basis = Matrix.LocRotScale(self.position, rotation.to_quaternion(), self.scale)
        self.snap.rig.update_tag()
        self.snap.context.view_layer.update()

    def retrieve_cost(self, angle):
        if angle not in self.samples:
            self.apply(angle)
            evaluated = self.snap.rig.evaluated_get(self.snap.context.evaluated_depsgraph_get())
            cost = 0.001 * angle ** 2
            for calibration in self.snap.calibration["fingers"].values():
                if calibration["segment"] == 1 and calibration["finger"] != "thumb":
                    frame = (evaluated.matrix_world @ evaluated.pose.bones[calibration["parent"]].matrix
                             @ retrieve_matrix(calibration["rest"]))
                    placement = FingerPlacement(self.surface, frame, self.palm,
                                                dict(calibration, samples=calibration["samples"][:4]))
                    pose = placement.retrieve_pose()
                    rotation = (frame.inverted() @ pose).to_euler("XYZ")
                    cost += placement.retrieve_cost(rotation)
            cost += 100.0 * self.snap.skin.retrieve_penetration(self.surface)
            self.samples[angle] = cost
        return self.samples[angle]

    def fit(self):
        angles = [math.radians(angle) for angle in range(-25, 26, 5)]
        angle = min(angles, key=self.retrieve_cost)
        for step in (2, 1):
            candidates = [min(max(angle + math.radians(step) * sign, -math.radians(25)), math.radians(25))
                          for sign in (-1, 0, 1)]
            angle = min(candidates, key=self.retrieve_cost)
        self.apply(angle)
        self.snap.wrist_diagnostics["palm_angle"] = angle

class WristContactSearch:
    """Rank nearby contacts geometrically and confirm them on the native rig."""

    def __init__(self, snap, placement):
        self.snap = snap
        self.placement = placement
        self.origin = placement.contact.copy()
        self.initial = snap.hand.matrix_basis.copy()
        self.best_error = math.inf
        self.reachable = []

    def retrieve_projected_pose(self, candidate):
        wrist = self.snap.rig.pose.bones.get(f"hand_tweak.{self.snap.side}")
        constraint = wrist.constraints.get("Natural Wrist Rotation") if wrist else None
        projected = candidate.copy()
        if (constraint and constraint.influence == 1 and not constraint.mute
                and constraint.owner_space == "CUSTOM" and constraint.space_object):
            graph = self.snap.context.evaluated_depsgraph_get()
            reference = constraint.space_object.evaluated_get(graph).matrix_world
            order = constraint.euler_order if constraint.euler_order != "AUTO" else wrist.rotation_mode
            angles = (reference.inverted() @ candidate @ self.snap.wrist).to_euler(order)
            for index, axis in enumerate("xyz"):
                if getattr(constraint, "use_limit_" + axis):
                    angles[index] = min(max(angles[index], getattr(constraint, "min_" + axis)),
                                        getattr(constraint, "max_" + axis))
            projected = reference @ angles.to_matrix().to_4x4() @ self.snap.wrist.inverted()
            projected.translation = self.placement.contact - projected.to_3x3() @ self.placement.anchor
        return projected

    def retrieve_estimate(self, candidate):
        projected = self.retrieve_projected_pose(candidate)
        contacts = self.placement.retrieve_contacts(projected)
        deficit = max(0.0, self.placement.clearance - min(offset.dot(normal) for offset, normal in contacts))
        rectangle = contacts[:len(self.placement.rectangle)]
        gap = sum(offset.length for offset, _normal in rectangle) / len(rectangle)
        return 10 * deficit + gap + self.placement.retrieve_movement_cost(projected)

    def try_pose(self, candidate, contact):
        self.placement.contact = contact.copy()
        self.snap.place_anchored_wrist(candidate, self.placement)
        actual = self.snap.retrieve_hand_pose() @ self.snap.wrist.inverted()
        error = (actual @ self.placement.anchor - contact).length
        # Rig evaluation adds float rounding to a geometrically valid boundary.
        cost = self.placement.retrieve_cost(actual, clearance_tolerance=0.00002)
        if error < self.best_error:
            self.best_error = error
            difference = candidate.to_quaternion().rotation_difference(actual.to_quaternion()).angle
            self.snap.wrist_diagnostics = {
                "native_heel_error": error,
                "native_rotation_error": math.degrees(min(difference, 2 * math.pi - difference)),
                "native_rectangle_clear": math.isfinite(cost),
            }
        valid = error < 0.0001 and math.isfinite(cost)
        if error < 0.0001:
            contacts = self.placement.retrieve_contacts(actual)
            penetration = max(0.0, -min(offset.dot(normal) for offset, normal in contacts))
            gap = sum(offset.length for offset, _normal in contacts) / len(contacts)
            trial = self.retrieve_fit(actual, contact)
            difference = candidate.to_quaternion().rotation_difference(actual.to_quaternion()).angle
            trial[-1].update({"native_heel_error": error, "native_seed_fallback": True,
                              "native_rectangle_clear": math.isfinite(cost),
                              "native_rotation_error": math.degrees(min(difference, 2 * math.pi - difference))})
            self.reachable.append((10 * penetration + gap + trial[0], trial))
        if valid:
            difference = candidate.to_quaternion().rotation_difference(actual.to_quaternion()).angle
            self.snap.wrist_diagnostics.update({
                "native_heel_error": error, "native_rectangle_clear": True,
                "native_rotation_error": math.degrees(min(difference, 2 * math.pi - difference)),
                "contact_shift": (contact - self.origin).length,
                "contact": list(contact), "rectangle_cost": cost,
            })
        return valid

    def retrieve_nearby_candidates(self):
        # A hand-width neighborhood keeps contact close to the authored pose.
        basis = self.placement.frame.to_3x3() @ self.placement.rest_frame
        width = (self.placement.rectangle[20] - self.placement.rectangle[0]).length
        step = width * 0.3
        candidates = []
        for horizontal in (-2, -1, 0, 1, 2):
            for vertical in (-2, -1, 0, 1, 2):
                point = self.origin + step * (basis.col[0] * horizontal + basis.col[1] * vertical)
                location, normal = self.placement.surface.retrieve_nearest(point)
                contact = location + normal * self.placement.clearance
                self.placement.contact = contact
                for heading in (0, 30, -30, 60, -60):
                    candidate = self.placement.retrieve_frame(point, math.radians(heading))
                    candidates.append((self.retrieve_estimate(candidate), candidate, contact.copy()))
        return sorted(candidates, key=lambda entry: entry[0])

    def fit(self):
        try:
            candidates = self.placement.retrieve_poses()
        except ValueError:
            candidates = []
        # Native limits can collapse several geometric minima to the same pose.
        distinct = []
        for candidate in candidates:
            if all(candidate.to_quaternion().rotation_difference(other.to_quaternion()).angle > 0.01
                   for other in distinct):
                distinct.append(candidate)
        fitted = []
        for candidate in sorted(distinct, key=self.retrieve_estimate)[:3]:
            if self.try_pose(candidate, self.origin):
                fitted.append(self.retrieve_fit(candidate, self.origin))
        if not fitted:
            self.snap.hand.matrix_basis = self.initial
            self.snap.rig.update_tag()
            self.snap.context.view_layer.update()
            for _estimate, candidate, contact in self.retrieve_nearby_candidates()[:10]:
                if self.try_pose(candidate, contact):
                    fitted.append(self.retrieve_fit(candidate, contact))
        if not fitted and self.reachable and self.snap.skin.indices:
            # Skin fitting can resolve collisions of the calibrated flat rectangle.
            fitted.append(min(self.reachable, key=lambda entry: entry[0])[1])
        if fitted:
            best = min(fitted, key=lambda fit: fit[0])
            self.placement.reachable_pose = best[1].copy()
            # Refine the distance back toward the original contact after the coarse search.
            far = best[2].copy()
            near = self.origin.copy()
            for _iteration in range(6):
                point = (near + far) / 2
                location, normal = self.placement.surface.retrieve_nearest(point)
                contact = location + normal * self.placement.clearance
                candidate = best[1].copy()
                candidate.translation = contact - candidate.to_3x3() @ self.placement.anchor
                if self.try_pose(candidate, contact):
                    trial = self.retrieve_fit(candidate, contact)
                    if trial[0] < best[0]:
                        best = trial
                    far = contact
                else:
                    near = contact
                if (far - near).length < 0.0005:
                    break
            _movement, _candidate, contact, basis, diagnostics = best
            self.placement.contact = contact
            self.snap.hand.matrix_basis = basis
            self.snap.rig.update_tag()
            self.snap.context.view_layer.update()
            self.snap.wrist_diagnostics = diagnostics
        else:
            raise ValueError("Adjust the arm pose or surface: the nearby search found no usable contact within the wrist limits")

    def retrieve_fit(self, candidate, contact):
        control = self.snap.rig.matrix_world @ self.snap.hand.matrix
        return (self.placement.retrieve_control_movement(control), candidate.copy(), contact.copy(),
                self.snap.hand.matrix_basis.copy(), self.snap.wrist_diagnostics.copy())


class HandContactReference:
    """Retain the accepted heel distance for the same evaluated hand pose."""

    property_name = "Snap Hand Contact Reference"

    def __init__(self, snap, surface):
        self.snap = snap
        self.surface = surface.target.name_full

    def retrieve_pose(self):
        rig = self.snap.rig.evaluated_get(self.snap.context.evaluated_depsgraph_get())
        matrices = [rig.matrix_world @ rig.pose.bones[bone.name].matrix
                    for bone in self.snap.retrieve_controls()]
        matrices.append(self.snap.retrieve_hand_pose())
        return [value for matrix in matrices for row in matrix for value in row]

    def retrieve_heel_tolerance(self):
        reference = self.snap.hand.get(self.property_name, {})
        previous = reference.get("pose", [])
        current = self.retrieve_pose()
        matches = (reference.get("surface") == self.surface and len(previous) == len(current)
                   and all(abs(first - second) < 0.00001 for first, second in zip(previous, current)))
        return max(0.008, reference["heel_gap"] + 0.00002) if matches else 0.008

    def capture(self, heel_gap):
        self.snap.hand[self.property_name] = {"surface": self.surface, "pose": self.retrieve_pose(),
                                               "heel_gap": heel_gap}


class ConvexHandSnap(HandSnap):
    def __init__(self, context, rig, side):
        super().__init__(context, rig, side)
        self.palm = rig.pose.bones.get(f"palm.{side}")
        self.skin = PalmSkin(context, rig, side)
        rest = rig.data.bones[f"DEF-hand.{side}"].matrix_local.inverted()
        self.control_rest = self.wrist @ rest @ self.hand.bone.matrix_local
        self.footprint = [self.wrist @ rest @ rig.data.bones[name].matrix_local @ Vector(point)
                          for name, calibration in self.calibration["fingers"].items()
                          if calibration["finger"] != "thumb"
                          for point in calibration["samples"][:4]]

    def retrieve_controls(self):
        controls = super().retrieve_controls()
        if self.palm:
            controls.append(self.palm)
        return controls

    def fit_hand(self, surface):
        self.wrist_diagnostics = {}
        previous = self.retrieve_hand_pose() @ self.wrist.inverted()
        control = self.rig.matrix_world @ self.hand.matrix
        placement = RestingHandRectangle(surface, previous, self.calibration["support"], control, self.footprint)
        # A constrained starting pose can contain a large control-to-skin rotation.
        # The native rest relationship keeps the widget aligned with the solved hand.
        placement.control_offset = self.control_rest
        reference = HandContactReference(self, surface)
        placement.heel_tolerance = reference.retrieve_heel_tolerance()
        held = self.retrieve_contact_gap(surface, placement)
        if held is not None:
            self.wrist_diagnostics.update({"rectangle_gap": held, "control_movement": 0.0,
                                           "rectangle_gap_before": held, "retained_contact": True})
        else:
            self.relax_fingers()
            if self.palm:
                position, _rotation, scale = self.palm.matrix_basis.decompose()
                self.palm.matrix_basis = Matrix.LocRotScale(position, Euler((0, 0, 0)).to_quaternion(), scale)
                self.rig.update_tag()
                self.context.view_layer.update()
            WristContactSearch(self, placement).fit()
            if self.skin.indices:
                HandControlPlacement(self, placement).fit()
            else:
                self.fit_pose(surface, self.retrieve_hand_pose() @ self.wrist.inverted())
        actual = self.rig.matrix_world @ self.hand.matrix
        difference = control.to_quaternion().rotation_difference(actual.to_quaternion()).angle
        self.wrist_diagnostics.update({"control_translation": (actual.translation - control.translation).length,
                                       "control_rotation": min(difference, 2 * math.pi - difference)})
        contacts = self.skin.retrieve_contacts(surface)
        inverse = (self.retrieve_hand_pose() @ self.wrist.inverted()).inverted()
        heel = [contact for contact in contacts if (inverse @ contact[2]).y <= placement.anchor.y + 0.012]
        if heel:
            gap, _normal, point = min(heel, key=lambda contact: contact[0])
            self.wrist_diagnostics.update({"heel_gap": gap,
                                           "contact_shift": (point - previous @ placement.anchor).length})
            reference.capture(gap)

    def retrieve_contact_gap(self, surface, placement, *, require_finger_contact=True):
        """Return widget distance for a pose with usable skin contact, in meters."""
        palm = self.retrieve_hand_pose() @ self.wrist.inverted()
        control = self.rig.matrix_world @ self.hand.matrix
        alignment = control.to_quaternion().rotation_difference((palm @ self.control_rest).to_quaternion()).angle
        alignment = min(alignment, 2 * math.pi - alignment)
        rectangle, clearance = HandControlRectangle(self, placement).retrieve_gap(surface)
        contacts = self.skin.retrieve_contacts(surface)
        inverse = palm.inverted()
        heel = min((gap for gap, _normal, point in contacts
                    if (inverse @ point).y <= placement.anchor.y + 0.012), default=math.inf)
        middle = max((offset.length for offset, _normal in self.retrieve_middle_contacts(surface)), default=math.inf)
        evaluated = self.rig.evaluated_get(self.context.evaluated_depsgraph_get())
        fingers_clear = True
        for name, calibration in self.calibration["fingers"].items():
            pose = evaluated.matrix_world @ evaluated.pose.bones[name].matrix
            gaps = []
            for sample in calibration["samples"][:4]:
                point = pose @ Vector(sample)
                nearest, normal = surface.retrieve_nearest(point)
                gaps.append((point - nearest).dot(normal))
            if min(gaps) < -0.002:
                fingers_clear = False
            # Tight pad contact permits skipping the solve for an existing pose.
            # Once fingers have been fitted, curvature and joint limits can leave
            # gaps without making a clear, reachable palm placement invalid.
            if require_finger_contact and calibration["segment"] > 1 and min(gaps) > 0.003:
                fingers_clear = False
            frame = evaluated.matrix_world @ evaluated.pose.bones[calibration["parent"]].matrix @ retrieve_matrix(calibration["rest"])
            angles = (frame.inverted() @ pose).to_euler("XYZ")
            if any(angle < lower - 0.0001 or angle > upper + 0.0001
                   for angle, (lower, upper) in zip(angles, calibration["bounds"])):
                fingers_clear = False
        if (alignment < 0.002 and clearance >= -0.00002 and heel <= getattr(placement, "heel_tolerance", 0.008)
                and min((gap for gap, _normal, _point in contacts), default=-math.inf) >= -0.002
                and (not require_finger_contact or middle <= 0.006) and fingers_clear):
            return rectangle
        return None

    def place_anchored_wrist(self, candidate, placement):
        world = candidate @ placement.control_offset
        for _iteration in range(6):
            self.hand.matrix = self.rig.matrix_world.inverted() @ world
            self.rig.update_tag()
            self.context.view_layer.update()
            actual = self.retrieve_hand_pose() @ self.wrist.inverted()
            offset = placement.contact - actual @ placement.anchor
            if offset.length < 0.00001:
                break
            world.translation += offset

    def relax_fingers(self):
        for name in self.calibration["fingers"]:
            bone = self.rig.pose.bones[name]
            position, _rotation, scale = bone.matrix_basis.decompose()
            bone.matrix_basis = Matrix.LocRotScale(position, Euler((0, 0, 0)).to_quaternion(), scale)
        self.rig.update_tag()
        self.context.view_layer.update()

    def fit_pose(self, surface, palm):
        self.relax_fingers()
        if self.palm:
            PalmCupping(self, surface, palm).fit()
        self.fit_fingers(surface, palm)
        return palm
