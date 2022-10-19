from pathlib import Path
import subprocess
import json
import xml.etree.ElementTree as ET
from datetime import timedelta

compilation_file = 'compilation_malzeno.json'
manual_hirc_file = 'manual_hirc.json'
out_file = 'out_malzeno.mp4'

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
    for path in get_range.xml_paths:
        tree = ET.parse(path)
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
get_range.xml_paths = list(Path().rglob('*.xml'))
with open(manual_hirc_file, 'r') as stream:
    get_range.hirc_dict = json.load(stream)

if __name__ == '__main__':
    with open(compilation_file, 'r') as stream:
        compilation = json.load(stream)
    
    first = True
    follows_instrumental = False
    time = timedelta()
    for id, name in compilation.items():
        print(str(time).split('.')[0], '-', name)
        path = list(Path().rglob(f'{id}.wav'))[0]
        duration_1, begin_2, duration_2 = get_range(id)
        if any((pattern in name for pattern in repetition_blacklist)):
            subprocess.check_output(['ffmpeg', '-y', '-i', path, '-t', str(duration_1), '-af', f'afade=out:st={duration_1 - 3}:d=3', 'inp.wav'], stderr=subprocess.DEVNULL)
            time += timedelta(seconds=duration_1)
        elif 'Instrumental' in name:
            follows_instrumental = True
            subprocess.check_output(['ffmpeg', '-y', '-i', path, '-t', str(duration_1), 'inp.wav'], stderr=subprocess.DEVNULL)
            time += timedelta(seconds=duration_1)
        elif follows_instrumental:
            follows_instrumental = False
            subprocess.check_output(['ffmpeg', '-y', '-i', path, '-ss', str(begin_2), '-t', str(duration_1 - begin_2 ), 'inp1.wav'], stderr=subprocess.DEVNULL)
            subprocess.check_output(['ffmpeg', '-y', '-i', path, '-ss', str(begin_2), '-t', str(duration_2), '-af', f'afade=out:st={begin_2 + duration_2 - 3}:d=3', 'inp2.wav'], stderr=subprocess.DEVNULL)
            subprocess.check_output(['ffmpeg', '-y', '-i', 'inp1.wav', '-i', 'inp2.wav', '-filter_complex', '[0:0][1:0]concat=n=2:v=0:a=1[out]', '-map', '[out]', 'inp.wav'], stderr=subprocess.DEVNULL)
            time += timedelta(seconds=duration_1 - begin_2 + duration_2)
        else:
            subprocess.check_output(['ffmpeg', '-y', '-i', path, '-t', str(duration_1), 'inp1.wav'], stderr=subprocess.DEVNULL)
            subprocess.check_output(['ffmpeg', '-y', '-i', path, '-ss', str(begin_2), '-t', str(duration_2), '-af', f'afade=out:st={begin_2 + duration_2 - 3}:d=3', 'inp2.wav'], stderr=subprocess.DEVNULL)
            subprocess.check_output(['ffmpeg', '-y', '-i', 'inp1.wav', '-i', 'inp2.wav', '-filter_complex', '[0:0][1:0]concat=n=2:v=0:a=1[out]', '-map', '[out]', 'inp.wav'], stderr=subprocess.DEVNULL)
            time += timedelta(seconds=duration_1 + duration_2)
        # Normalize RMS volume of track
        subprocess.check_output(['ffmpeg-normalize', '-nt', 'peak', '-t', '-3', 'inp.wav', '-o', 'tmp.wav'], stderr=subprocess.DEVNULL)
        Path('tmp.wav').rename('inp.wav')

        if first:
            Path('inp.wav').rename('out.wav')
            first = False
        else:
            subprocess.check_output(['ffmpeg', '-y', '-i', 'out.wav', '-i', 'inp.wav', '-filter_complex', '[0:0][1:0]concat=n=2:v=0:a=1[out]', '-map', '[out]', 'tmp.wav'], stderr=subprocess.DEVNULL)
            Path('tmp.wav').rename('out.wav')
    # Loudnorm to -14 LUFS
    subprocess.check_output(['ffmpeg-normalize', '-nt', 'ebu', '-t', '-14', 'out.wav', '-o', 'tmp.wav'], stderr=subprocess.DEVNULL)
    Path('tmp.wav').rename('out.wav')
    subprocess.check_output(['ffmpeg', '-y', '-loop', '1', '-i', 'Logo-MHRise_Sunbreak.jpg', '-i', 'out.wav', '-c:v', 'libx264', '-tune', 'stillimage', '-c:a', 'aac', '-b:a', '192k', '-pix_fmt', 'yuv420p', '-shortest', out_file])
