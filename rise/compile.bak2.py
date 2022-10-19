from pathlib import Path
import subprocess
import shutil
import json
import xml.etree.ElementTree as ET
from datetime import timedelta
from tempfile import TemporaryDirectory

manual_hirc_file = 'manual_hirc.json'
out_file = 'out_malzeno.mp4'
src_tracks_dir = 'src-tracks'
src_track_configs_dir = 'src-track-configs'
target_configs = {
    'staged_dir': 'target-configs/staged',
    'committed_dir': 'target-configs/committed',
}
target_output_dir = 'outputs'
target_image_path = 'MHR-Soundtrack-Background.jpg'


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
    'Afflicted'
]

def get_range(id):
    id = id.split('+')[0]
    # (Begin, Duration, Total duration) in ms
    if id in get_range.hirc_dict:
        best_begin_2 = get_range.hirc_dict[id]['fBeginTrimOffset'] / 1e3
        best_end_1 = get_range.hirc_dict[id]['fEndTrimOffset'] / 1e3
        src_duration = get_range.hirc_dict[id]['fSrcDuration'] / 1e3
        best_duration_1 = src_duration + best_end_1
        best_duration_2 = src_duration - best_begin_2
    else:
        best_duration_1 = 0
        best_begin_2 = None
        best_duration_2 = 0
    current_id = None
    begin_2 = None
    end = None
    for tree in get_range.hirc_xml_trees:
        for node in tree.findall('.//fld'):
            if node.attrib['na'] == 'sourceID':
                current_id = node.attrib['va']
                continue
            if current_id == id:
                if node.attrib['na'] == 'fBeginTrimOffset':
                    begin_2 =  float(node.attrib['va']) / 1e3
                elif node.attrib['na'] == 'fEndTrimOffset':
                    end_1 = float(node.attrib['va']) / 1e3
                elif node.attrib['na'] == 'fSrcDuration':
                    src_duration =  float(node.attrib['va']) / 1e3
                    duration_1 = src_duration + end_1
                    duration_2 = src_duration - begin_2
                    if duration_1 + duration_2 > best_duration_1 + best_duration_2:
                        best_duration_1 = duration_1
                        best_begin_2 = begin_2
                        best_duration_2 = duration_2

    if best_begin_2 is None:
        raise RuntimeError(id)
    return (best_duration_1, best_begin_2, best_duration_2)

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
            compilation = target_config['compilation']
            timestamps = []
            first = True
            follows_instrumental = False
            time = timedelta()
            for id, name in compilation.items():
                timestamp = f'{str(time).split(".")[0]} - {name}'
                print(timestamp)
                timestamps.append(timestamp)
                path = list(Path().rglob(f'{id}.wav'))[0]
                duration_1, begin_2, duration_2 = get_range(id)
                if any((pattern in name for pattern in repetition_blacklist)):
                    subprocess.check_output(['ffmpeg', '-y', '-i', path, '-t', str(duration_1), '-af', f'afade=out:st={duration_1 - 3}:d=3', tmp_dir / 'inp.wav'], stderr=subprocess.DEVNULL)
                    time += timedelta(seconds=duration_1)
                elif 'Instrumental' in name:
                    follows_instrumental = True
                    subprocess.check_output(['ffmpeg', '-y', '-i', path, '-t', str(duration_1), tmp_dir / 'inp.wav'], stderr=subprocess.DEVNULL)
                    time += timedelta(seconds=duration_1)
                elif follows_instrumental:
                    follows_instrumental = False
                    subprocess.check_output(['ffmpeg', '-y', '-i', path, '-ss', str(begin_2), '-t', str(duration_1 - begin_2 ), tmp_dir / 'inp1.wav'], stderr=subprocess.DEVNULL)
                    subprocess.check_output(['ffmpeg', '-y', '-i', path, '-ss', str(begin_2), '-t', str(duration_2), '-af', f'afade=out:st={begin_2 + duration_2 - 3}:d=3', tmp_dir / 'inp2.wav'], stderr=subprocess.DEVNULL)
                    subprocess.check_output(['ffmpeg', '-y', '-i', tmp_dir / 'inp1.wav', '-i', tmp_dir / 'inp2.wav', '-filter_complex', '[0:0][1:0]concat=n=2:v=0:a=1[out]', '-map', '[out]', tmp_dir / 'inp.wav'], stderr=subprocess.DEVNULL)
                    time += timedelta(seconds=duration_1 - begin_2 + duration_2)
                else:
                    subprocess.check_output(['ffmpeg', '-y', '-i', path, '-t', str(duration_1), tmp_dir / 'inp1.wav'], stderr=subprocess.DEVNULL)
                    subprocess.check_output(['ffmpeg', '-y', '-i', path, '-ss', str(begin_2), '-t', str(duration_2), '-af', f'afade=out:st={begin_2 + duration_2 - 3}:d=3', tmp_dir / 'inp2.wav'], stderr=subprocess.DEVNULL)
                    subprocess.check_output(['ffmpeg', '-y', '-i', tmp_dir / 'inp1.wav', '-i', tmp_dir / 'inp2.wav', '-filter_complex', '[0:0][1:0]concat=n=2:v=0:a=1[out]', '-map', '[out]', tmp_dir / 'inp.wav'], stderr=subprocess.DEVNULL)
                    time += timedelta(seconds=duration_1 + duration_2)
                # Normalize RMS volume of track
                subprocess.check_output(['ffmpeg-normalize', '-nt', 'peak', '-t', '-3', tmp_dir / 'inp.wav', '-o', tmp_dir / 'tmp.wav'], stderr=subprocess.DEVNULL)
                Path(tmp_dir / 'tmp.wav').rename(tmp_dir / 'inp.wav')

                if first:
                    Path(tmp_dir / 'inp.wav').rename(tmp_dir / 'out.wav')
                    first = False
                else:
                    subprocess.check_output(['ffmpeg', '-y', '-i', tmp_dir / 'out.wav', '-i', tmp_dir / 'inp.wav', '-filter_complex', '[0:0][1:0]concat=n=2:v=0:a=1[out]', '-map', '[out]', tmp_dir / 'tmp.wav'], stderr=subprocess.DEVNULL)
                    Path(tmp_dir / 'tmp.wav').rename(tmp_dir / 'out.wav')
            # Loudnorm to -14 LUFS
            subprocess.check_output(['ffmpeg-normalize', '-nt', 'ebu', '-t', '-10', tmp_dir / 'out.wav', '-o', tmp_dir / 'tmp.wav'], stderr=subprocess.DEVNULL)
            Path(tmp_dir / 'tmp.wav').rename(tmp_dir / 'out.wav')
            subprocess.check_output(['ffmpeg', '-y', '-loop', '1', '-i', target_image_path, '-i', tmp_dir / 'out.wav', '-c:v', 'libx264', '-tune', 'stillimage', '-c:a', 'aac', '-b:a', '192k', '-pix_fmt', 'yuv420p', '-shortest', tmp_dir / 'out.mp4'])

            # Generate outputs
            target_config['meta_data']['description'] = target_config['meta_data']['description'].format(timestamps='\n'.join(timestamps))
            meta_data_path = tmp_dir / 'meta_data.json'
            with meta_data_path.open('w') as stream:
                stream.write(json.dumps(target_config['meta_data']))
            output_dir = Path(target_output_dir) / config_path.stem
            output_dir.mkdir(exist_ok=True, parents=True)
            shutil.move(tmp_dir / 'out.mp4', output_dir / 'video.mp4')
            with open(output_dir / 'title.txt', 'w', encoding='utf8') as stream:
                stream.write(target_config['meta_data']['title'])
            with open(output_dir / 'tags.txt', 'w', encoding='utf8') as stream:
                stream.write(", ".join(target_config['meta_data']['tags']))
            with open(output_dir / 'description.txt', 'w', encoding='utf8') as stream:
                stream.write(target_config['meta_data']['description'])
            shutil.move(config_path, Path(target_configs['committed_dir']) / config_path.name)
