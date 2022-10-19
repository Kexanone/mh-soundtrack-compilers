from asyncio.subprocess import DEVNULL
from pathlib import Path
import subprocess
import shutil
from io import StringIO
import json
import xml.etree.ElementTree as ET
from datetime import timedelta
from tempfile import NamedTemporaryFile, TemporaryDirectory
import numpy as np


SRC_TRACKS_DIR = 'src-tracks'
SRC_TRACK_CONFIGS_DIR = 'src-track-configs'
TARGET_CONFIGS = {
    'staged_dir': 'target-configs/staged',
    'committed_dir': 'target-configs/committed',
}
TARGET_OUTPUT_DIR = 'outputs'
IMAGES_DIR = 'images'


def get_hirc_obj_attrib(obj_node, attrib, dtype=str):
    try:
        return dtype(obj_node.findall(f'.//fld[@na="{attrib}"]')[0].attrib['va'])
    except IndexError:
        return None


def get_range(hirc_id):
    hirc_id = hirc_id.split('+')[0]
    # json dict overrides hirc xml
    if hirc_id in get_range.hirc_dict:
        begin = get_range.hirc_dict[hirc_id]['fBeginTrimOffset'] / 1e3
        end = get_range.hirc_dict[hirc_id]['fEndTrimOffset'] / 1e3
        if end <= 0:
            end += get_range.hirc_dict[hirc_id]['fSrcDuration'] / 1e3
        # Returns duration_1, begin_2, duration_2 in ms
        return (end, begin, end-begin)
    # Extract loop points from HIRC for given soundtrack hirc_id
    loop_points = set()
    for tree in get_range.hirc_xml_trees:
        for obj_node in tree.findall('.//obj'):
            if hirc_id != get_hirc_obj_attrib(obj_node, "sourceID"):
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
        raise RuntimeError(hirc_id)
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
    #def fmt(s):
    #    return str(timedelta(seconds=s))
    #print([(fmt(b), fmt(e)) for b,e in loop_points])
    #print((fmt(best_begin), fmt(best_end)))
    #print([(b, e) for b,e in loop_points])
    #print(((best_begin), (best_end)))
    # Returns duration_1, begin_2, duration_2 in ms
    return (best_end, best_begin, best_end-best_begin)

      
# Load HIRC configs for soundtrack range getter
get_range.hirc_xml_trees = []
for path in Path(SRC_TRACK_CONFIGS_DIR).glob('*.xml'):
    get_range.hirc_xml_trees.append(ET.parse(path))
get_range.hirc_dict = {}
for path in Path(SRC_TRACK_CONFIGS_DIR).glob('*.json'):
    with path.open('r') as stream:
        get_range.hirc_dict.update(json.load(stream))


def ffmpeg(*inputs, output_file=None, pre_options=(), options=(), stderr=None):
    cml = ['ffmpeg', '-y']
    cml.extend(pre_options)
    for input_file in inputs:
        cml.extend(['-i', input_file])
    cml.extend(options)
    if output_file is None:
        cml.extend(['-f', 'null', '-'])
        response = subprocess.check_output(cml, stderr=stderr)
    else:
        with TemporaryDirectory() as tmp_dir:
            tmp_out = Path(tmp_dir) / output_file.name
            cml.append(tmp_out)
            response = subprocess.check_output(cml, stderr=stderr)
            shutil.move(tmp_out, output_file)
    return StringIO(response.decode('utf8'))


def normalize_audio(input_file, output_file=None, target_lufs=-14.0):
    '''
    Loudnorm to -14 LUFS by default (Recommended by YouTube)
    '''
    subprocess.check_output(['ffmpeg-normalize', '-f', '-nt', 'ebu', '-t', str(target_lufs), '--keep-loudness-range-target', input_file, '-o', output_file])


def set_mean_volume(input_file, output_file=None, target=-14.0):
    response = ffmpeg(input_file, options=['-af', 'volumedetect'], stderr=subprocess.STDOUT)
    for line in response:
        if 'mean_volume' in line:
            break
    volume_offset = target - float(line.split()[-2])
    ffmpeg(input_file, output_file=input_file, options=['-af', f'volume={volume_offset}dB'], stderr=subprocess.DEVNULL)



def join_audio(*inputs, output_file=None, crossfade=None):
    if crossfade is None:
        ffmpeg(*inputs, output_file=output_file, options=['-filter_complex', '[0:0][1:0]concat=n=2:v=0:a=1[out]', '-map', '[out]'], stderr=subprocess.DEVNULL)
    else:
        ffmpeg(*inputs, output_file=output_file, options=['-filter_complex', f'acrossfade=d={crossfade}'], stderr=subprocess.DEVNULL)


def cut_audio(input_file, output_file=None, begin=0.0, duration=0.0):
    ffmpeg(input_file, output_file=output_file, options=['-ss', str(begin), '-t', str(duration)], stderr=subprocess.DEVNULL)


def fadeout_audio(input_file, output_file=None, begin=0.0, duration=0.0):
    ffmpeg(input_file, output_file=output_file, options=['-af', f'afade=out:st={begin}:d={duration}'], stderr=subprocess.DEVNULL)


def load_and_process_entry(entry, output_file=None):
    try:
        path = list(Path(SRC_TRACKS_DIR).rglob(f'{entry["id"]}.wav'))[0]
    except IndexError:
        print(f'{entry["id"]}.wav')
        raise
    duration_1, begin_2, duration_2 = get_range(entry["id"])
    if entry.get('intro', True):
        begin = 0.0
        duration = duration_1
    else:
        begin = begin_2
        duration = duration_2
    if 'crossfade' in entry:
        begin -= entry['crossfade']
        duration += entry["crossfade"]
    
    # Trim initial block
    cut_audio(path, output_file=output_file, begin=begin, duration=duration)

    # Loop entry
    with NamedTemporaryFile(suffix='.wav') as tmp_file:
        tmp_file = Path(tmp_file.name)
        for _ in range(entry.get('nloop', 0)):
            cut_audio(path, output_file=tmp_file, begin=begin_2, duration=duration_2)
            #print(time+timedelta(seconds=duration))
            join_audio(output_file, tmp_file, output_file=output_file)
            duration += duration_2

    # Add fadeout to end
    if 'fadeout' in entry:
        fadeout_audio(output_file, output_file=output_file, begin=duration-entry['fadeout'], duration=entry['fadeout'])
    
    set_mean_volume(output_file, output_file=output_file)

    return duration

def postprocess_and_save_compilation(input_file, duration=0.0, config_path=None, meta_data={}, timestamps=[]):
    description = meta_data['description'].format(timestamps='\n'.join(timestamps))
    output_dir = Path(TARGET_OUTPUT_DIR) / config_path.stem
    output_dir.mkdir(exist_ok=True, parents=True)
    set_mean_volume(input_file, output_file=input_file)
    #shutil.copyfile(input_file, output_dir / 'video.wav')
    ffmpeg(Path(IMAGES_DIR) / meta_data['image'], input_file, output_file=output_dir / 'video.mp4', pre_options=['-loop', '1', '-framerate', '1'], options=['-t', str(duration), '-c:v', 'libx264', '-preset', 'medium', '-tune', 'stillimage', '-crf', '18', '-c:a', 'aac', '-pix_fmt', 'yuv420p'])
    with open(output_dir / 'title.txt', 'w', encoding='utf8') as stream:
        stream.write(meta_data['title'])
    with open(output_dir / 'tags.txt', 'w', encoding='utf8') as stream:
        stream.write(", ".join(meta_data['tags']))
    with open(output_dir / 'description.txt', 'w', encoding='utf8') as stream:
        stream.write(description)
    shutil.move(config_path, Path(TARGET_CONFIGS['committed_dir']) / config_path.name)

if __name__ == '__main__':
    with TemporaryDirectory() as tmp_dir:
        input_file = Path(tmp_dir) / 'inp.wav'
        output_file = Path(tmp_dir) / 'out.wav'
        Path(TARGET_CONFIGS['committed_dir']).mkdir(exist_ok=True)
        for config_path in list(Path(TARGET_CONFIGS['staged_dir']).glob('*.json')):
            with config_path.open('r') as stream:
                target_config = json.load(stream)
            timestamps = []
            first = True
            time = timedelta()
            for entry in target_config['compilation']:
                timestamp = f'{str(time).split(".")[0]} - {entry["name"]}'
                print(timestamp)
                timestamps.append(timestamp)
                duration = load_and_process_entry(entry, output_file=input_file)

                if 'crossfade' in entry:
                    time += timedelta(seconds=duration-entry['crossfade'])
                else:
                    time += timedelta(seconds=duration)

                # Append entry to stream
                if first:
                    shutil.move(input_file, output_file)
                    first = False
                else:
                    join_audio(output_file, input_file, output_file=output_file)

            postprocess_and_save_compilation(output_file, duration=time.total_seconds(), config_path=config_path, meta_data=target_config['meta_data'], timestamps=timestamps)
