from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np


src_track_configs_dir = 'src-track-configs'
id = '119860714'

def get_obj_attrib(obj_node, attrib, dtype=str):
    try:
        return dtype(obj_node.findall(f'.//fld[@na="{attrib}"]')[0].attrib['va'])
    except IndexError:
        return None

# Extract loop points from HIRC for given soundtrack ID
loop_points = set()
for path in Path(src_track_configs_dir).glob('*.xml'):
    tree = ET.parse(path)
    for obj_node in tree.findall('.//obj'):
        if id != get_obj_attrib(obj_node, "sourceID"):
            continue
        begin = get_obj_attrib(obj_node, "fBeginTrimOffset", dtype=float)
        if begin is None:
            continue
        end = get_obj_attrib(obj_node, "fEndTrimOffset", dtype=float)
        src_duration = get_obj_attrib(obj_node, "fSrcDuration", dtype=float)
        # Handle negative values
        if begin < 0:
            begin += src_duration
        if end < 0:
            end += src_duration
        loop_points.add((begin, end))
# Get best loop point, i.e. longest interval
best_begin, best_end = max(loop_points, key=lambda point: point[1]-point[0])
# Locate possible points that fill a gap at the beginning
extension_points = []
for loop_point in loop_points:
    if np.isclose(loop_point[1], best_begin):
        extension_points.append(loop_point)
# First extension point will be for start of music
# If a second extension is present, it will fill a gap
if len(extension_points) > 1:
    best_begin, _ = min(extension_points, key=lambda point: point[1]-point[0])
print(loop_points)
print(extension_points)
# Returns duration_1, begin_2, duration_2
print(best_end, best_begin, best_end-best_begin)
