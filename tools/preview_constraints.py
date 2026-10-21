# SPDX-License-Identifier: GPL-3.0-or-later
"""Copy the reference scene's anatomical limit policy to an MPFB preview rig."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
from mathutils import Matrix

FIELDS = ('owner_space', 'euler_order', 'use_transform_limit', 'influence', 'mute',
          'use_limit_x', 'use_limit_y', 'use_limit_z',
          'min_x', 'max_x', 'min_y', 'max_y', 'min_z', 'max_z')
WRIST_PROPERTIES = ('Wrist Flexion', 'Wrist Extension', 'Wrist Radial Deviation',
                    'Wrist Ulnar Deviation', 'Forearm Roll')


def rest_bend(rig, owner, parent):
    return (rig.data.bones[parent].matrix_local.inverted()
            @ rig.data.bones[owner].matrix_local).to_euler('XYZ').x


def export_reference(source, output):
    bpy.ops.wm.open_mainfile(filepath=str(source.resolve()))
    rig = bpy.data.objects['Woman.rigify']
    records = []
    for bone in rig.pose.bones:
        for constraint in bone.constraints:
            if constraint.name not in {'Natural Finger Rotation', 'Natural Wrist Rotation'}:
                continue
            assert constraint.type == 'LIMIT_ROTATION' and constraint.space_object
            frame = constraint.space_object
            assert frame.parent == rig and frame.parent_type == 'BONE'
            is_wrist = constraint.name == 'Natural Wrist Rotation'
            rest = 'ORG-hand.' + bone.name[-1] if is_wrist else bone.name
            record = {'bone': bone.name, 'name': constraint.name,
                      'parent': frame.parent_bone, 'rest_bone': rest,
                      'settings': {field: getattr(constraint, field) for field in FIELDS}}
            if not is_wrist and int(bone.name.split('.')[1]) > 1:
                record['rest_bend'] = rest_bend(rig, rest, frame.parent_bone)
            records.append(record)
    assert len(records) == 32, f'Expected 30 finger and two wrist limits, got {len(records)}'
    result = {'reference': source.name, 'reference_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'rig': rig.name, 'constraints': records,
              'wrist_properties': {side: {key: rig.pose.bones[f'hand_ik.{side}'][key]
                                        for key in WRIST_PROPERTIES} for side in ('L', 'R')}}
    output.write_text(json.dumps(result, indent=2) + '\n')
    print('Exported reference constraints:', len(records))


def apply_reference(rig, path):
    reference = json.loads(Path(path).read_text())
    checks = []
    for record in reference['constraints']:
        bone = rig.pose.bones[record['bone']]
        parent = rig.data.bones[record['parent']]
        rest = parent.matrix_local.inverted() @ rig.data.bones[record['rest_bone']].matrix_local
        frame = bpy.data.objects.new(f'Preview Joint Frame {bone.name}', None)
        bpy.context.scene.collection.objects.link(frame)
        frame.parent, frame.parent_type, frame.parent_bone = rig, 'BONE', parent.name
        frame.matrix_parent_inverse = Matrix.Identity(4)
        frame.matrix_basis = Matrix.Translation((0, -parent.length, 0)) @ rest
        frame.hide_render = True
        frame.hide_set(True)
        previous = bone.constraints.get(record['name'])
        if previous:
            bone.constraints.remove(previous)
        constraint = bone.constraints.new('LIMIT_ROTATION')
        constraint.name = record['name']
        constraint.space_object = frame
        settings = dict(record['settings'])
        # Preserve anatomical extension/flexion, compensating for rest-bend
        # differences between the reference woman and the newly generated model.
        adjustment = 0.0
        if 'rest_bend' in record:
            adjustment = record['rest_bend'] - rest.to_euler('XYZ').x
            for field in ('min_x', 'max_x'):
                settings[field] += adjustment
        for field, value in settings.items():
            setattr(constraint, field, value)
        for field, value in settings.items():
            actual = getattr(constraint, field)
            assert abs(actual - value) < 1e-6 if isinstance(value, (float, int)) else actual == value
        checks.append({'bone': bone.name, 'constraint': constraint.name, 'settings_match': True,
                       'rest_bend_adjustment': adjustment})
    for side, properties in reference['wrist_properties'].items():
        control = rig.pose.bones[f'hand_ik.{side}']
        for key, value in properties.items():
            control[key] = value
        wrist = rig.pose.bones[f'hand_tweak.{side}'].constraints['Natural Wrist Rotation']
        bounds = {'min_x': ('Wrist Ulnar Deviation', -1), 'max_x': ('Wrist Radial Deviation', 1),
                  'min_y': ('Forearm Roll', -1), 'max_y': ('Forearm Roll', 1),
                  'min_z': ('Wrist Flexion' if side == 'L' else 'Wrist Extension', -1),
                  'max_z': ('Wrist Extension' if side == 'L' else 'Wrist Flexion', 1)}
        for field, (key, direction) in bounds.items():
            curve = wrist.driver_add(field)
            driver = curve.driver
            driver.type = 'SCRIPTED'
            variable = driver.variables.new()
            variable.name, variable.type = 'angle', 'SINGLE_PROP'
            variable.targets[0].id = rig
            variable.targets[0].data_path = control.path_from_id() + '[' + json.dumps(key) + ']'
            driver.expression = f'angle * {direction * 3.141592653589793 / 180}'
    rig.update_tag()
    bpy.context.view_layer.update()
    assert len(checks) == 32
    return {'reference': reference['reference'], 'reference_sha256': reference['reference_sha256'],
            'native_limit_constraints': len(checks), 'wrist_limit_drivers': 12,
            'constraints': checks}


def verify_evaluated_limits(rig):
    """Check the posed bones in their actual evaluated custom constraint spaces."""
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = rig.evaluated_get(depsgraph)
    violations, maximum = [], 0.0
    for bone in evaluated.pose.bones:
        for constraint in bone.constraints:
            if constraint.name not in {'Natural Finger Rotation', 'Natural Wrist Rotation'}:
                continue
            assert not constraint.mute and constraint.influence == 1.0
            frame = constraint.space_object.evaluated_get(depsgraph).matrix_world
            angles = (frame.inverted() @ evaluated.matrix_world @ bone.matrix).to_euler(constraint.euler_order)
            for axis, angle in zip('xyz', angles):
                error = max(getattr(constraint, f'min_{axis}') - angle,
                            angle - getattr(constraint, f'max_{axis}'), 0.0)
                maximum = max(maximum, error)
                if error > 1e-4:
                    violations.append({'bone': bone.name, 'axis': axis, 'error_radians': error})
    assert not violations, f'Evaluated native limits exceeded: {violations}'
    return {'maximum_limit_error_radians': maximum, 'evaluated_limits_passed': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    export_reference(args.source, args.output)
