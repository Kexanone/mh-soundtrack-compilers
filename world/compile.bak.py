from pathlib import Path
import subprocess
import shutil
import json
import xml.etree.ElementTree as ET
from datetime import timedelta
from tempfile import TemporaryDirectory
import numpy as np

manual_hirc_file = 'manual_hirc.json'
out_file = 'out_malzeno.mp4'
src_tracks_dir = 'src-tracks'
src_track_configs_dir = 'src-track-configs'
target_configs = {
    'staged_dir': 'target-configs/staged',
    'committed_dir': 'target-configs/committed',
}
target_output_dir = 'outputs'
target_image_path = 'MHWI-Soundtrack-Background.jpg'


repetition_blacklist = [
    'Intro',
    'Proof of a Hero (Sunbreak Ed.)',
    'Character',
    'Title',
    'Ending',
    'Kamura',
    'Elgado',
    'Hub',
    'Quest',
    'Camp',
    'Ending',
    'Afflicted'
]

def get_hirc_obj_attrib(obj_node, attrib, dtype=str):
    try:
        return dtype(obj_node.findall(f'.//fld[@na="{attrib}"]')[0].attrib['va'])
    except IndexError:
        return None

def get_range(id):
    id = id.split('+')[0]
    # json dict overrides hirc xml
    if id in get_range.hirc_dict:
        begin = get_range.hirc_dict[id]['fBeginTrimOffset'] / 1e3
        end = get_range.hirc_dict[id]['fEndTrimOffset'] / 1e3
        if end <= 0:
            end += get_range.hirc_dict[id]['fSrcDuration'] / 1e3
        # Returns duration_1, begin_2, duration_2 in ms
        return (end, begin, end-begin)
    # Extract loop points from HIRC for given soundtrack ID
    loop_points = set()
    for tree in get_range.hirc_xml_trees:
        for obj_node in tree.findall('.//obj'):
            if id != get_hirc_obj_attrib(obj_node, "sourceID"):
                continue
            begin = get_hirc_obj_attrib(obj_node, "fBeginTrimOffset", dtype=float)
            if begin is None:
                continue
            begin /= 1e3
            end = get_hirc_obj_attrib(obj_node, "fEndTrimOffset", dtype=float)
            end /= 1e3
            src_duration = get_hirc_obj_attrib(obj_node, "fSrcDuration", dtype=float)
            src_duration /= 1e3
            # Handle negative values
            if begin < 0:
                begin += src_duration
            if end <= 0:
                end += src_duration
            loop_points.add((begin, end))
    if not loop_points:
        raise RuntimeError(id)
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
    # Returns duration_1, begin_2, duration_2 in ms
    return (best_end, best_begin, best_end-best_begin)
        
# Load HIRC configs for soundtrack range getter
get_range.hirc_xml_trees = []
for path in Path(src_track_configs_dir).glob('*.xml'):
    get_range.hirc_xml_trees.append(ET.parse(path))
get_range.hirc_dict = {}
for path in Path(src_track_configs_dir).glob('*.json'):
    with path.open('r') as stream:
        get_range.hirc_dict.update(json.load(stream))

if __name__ == '__main__':
    with TemporaryDirectory() as tmp_dir:
        tmp_dir = Path(tmp_dir)
        Path(target_configs['committed_dir']).mkdir(exist_ok=True)
        for config_path in list(Path(target_configs['staged_dir']).glob('*.json')):
            with config_path.open('r') as stream:
                target_config = json.load(stream)
            timestamps = []
            first = True
            time = timedelta()
            for entry in target_config['compilation']:
                timestamp = f'{str(time).split(".")[0]} - {entry["name"]}'
                print(timestamp)
                timestamps.append(timestamp)
                path = list(Path().rglob(f'{entry["id"]}.wav'))[0]
                duration_1, begin_2, duration_2 = get_range(entry["id"])
                filter_complex = []
                
                if entry.get('intro', True):
                    begin = 0.0
                    duration = duration_1
                else:
                    begin = begin_2
                    duration = duration_2
                if 'crossfade' in entry:
                    filter_complex.append(f'acrossfade=d={entry["crossfade"]}')
                    begin -= entry['crossfade']
                    duration += entry["crossfade"]
                else:
                    filter_complex.append('acrossfade=d=0')
                
                # Trim initial block
                subprocess.check_output([
                        'ffmpeg', '-y',
                        '-ss', str(begin), '-t', str(duration), 
                        '-i', path, tmp_dir / 'tmp1.wav'
                    ], stderr=subprocess.DEVNULL
                )

                # Loop entry
                for _ in range(entry.get('nloop', 0)):
                    subprocess.check_output([
                            'ffmpeg', '-y',
                            '-ss', str(begin_2), '-t', str(duration_2), 
                            '-i', path, tmp_dir / 'tmp2.wav'
                        ], stderr=subprocess.DEVNULL
                    )
                    subprocess.check_output([
                            'ffmpeg', '-y',
                            '-filter_complex', 'acrossfade=d=0',
                            '-i', tmp_dir / 'tmp1.wav', '-i', tmp_dir / 'tmp2.wav', tmp_dir / 'tmp3.wav'
                        ], stderr=subprocess.DEVNULL
                    )
                    Path(tmp_dir / 'tmp3.wav').rename(tmp_dir / 'tmp1.wav')
                    duration += duration_2
                
                if 'fadeout' in entry:
                    print(entry['name'], 11)
                    subprocess.check_output([
                            'ffmpeg', '-y',
                            '-i', tmp_dir / 'tmp1.wav',
                            '-af', f'afade=out:st={duration-entry["fadeout"]}:d={entry["fadeout"]}',
                            tmp_dir / 'tmp2.wav'
                        ], stderr=subprocess.DEVNULL
                    )
                    Path(tmp_dir / 'tmp2.wav').rename(tmp_dir / 'tmp1.wav')

                # Normalize maximum amplitude
                subprocess.check_output(['ffmpeg-normalize', '-f', '-nt', 'peak', '-t', '-3', tmp_dir / 'tmp1.wav', '-o', tmp_dir / 'tmp2.wav'], stderr=subprocess.DEVNULL)
                Path(tmp_dir / 'tmp2.wav').rename(tmp_dir / 'tmp1.wav')

                # Append entry to stream
                if first:
                    Path(tmp_dir / 'tmp1.wav').rename(tmp_dir / 'out.wav')
                    first = False
                else:
                    subprocess.check_output([
                            'ffmpeg', '-y',
                            '-filter_complex', ';'.join(filter_complex), 
                            '-i', tmp_dir / 'out.wav', '-i', tmp_dir / 'tmp1.wav', tmp_dir / 'tmp2.wav'
                         ], stderr=subprocess.DEVNULL
                    )
                    Path(tmp_dir / 'tmp2.wav').rename(tmp_dir / 'out.wav')
                
                if 'crossfade' in entry:
                    time += timedelta(seconds=duration-entry['crossfade'])
                else:
                    time += timedelta(seconds=duration)
                print(11, time)

            # Loudnorm to -14 LUFS
            #subprocess.check_output(['ffmpeg-normalize', '-nt', 'ebu', '-t', '-14', tmp_dir / 'out.wav', '-o', tmp_dir / 'tmp1.wav'], stderr=subprocess.DEVNULL)
            #subprocess.check_output(['ffmpeg', '-y', '-loop', '1', '-i', target_image_path, '-i', tmp_dir / 'out.wav', '-c:v', 'libx264', '-tune', 'stillimage', '-c:a', 'aac', '-b:a', '192k', '-pix_fmt', 'yuv420p', '-shortest', tmp_dir / 'out.mp4'])

            # Generate outputs
            target_config['meta_data']['description'] = target_config['meta_data']['description'].format(timestamps='\n'.join(timestamps))
            meta_data_path = tmp_dir / 'meta_data.json'
            with meta_data_path.open('w') as stream:
                stream.write(json.dumps(target_config['meta_data']))
            output_dir = Path(target_output_dir) / config_path.stem
            output_dir.mkdir(exist_ok=True, parents=True)
            #shutil.move(tmp_dir / 'out.mp4', output_dir / 'video.mp4')
            shutil.move(tmp_dir / 'out.wav', output_dir / 'video.wav')
            with open(output_dir / 'title.txt', 'w', encoding='utf8') as stream:
                stream.write(target_config['meta_data']['title'])
            with open(output_dir / 'tags.txt', 'w', encoding='utf8') as stream:
                stream.write(", ".join(target_config['meta_data']['tags']))
            with open(output_dir / 'description.txt', 'w', encoding='utf8') as stream:
                stream.write(target_config['meta_data']['description'])
            shutil.move(config_path, Path(target_configs['committed_dir']) / config_path.name)
