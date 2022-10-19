from pathlib import Path
import struct
import subprocess
from argparse import ArgumentParser

ENDIANNESS = '<' # Little endian
STRUCT_SIGNS = {
	1 : 'c',
	2 : 'H',
	4 : 'I',
	8 : 'Q'
}

def unpack(_bytes):
    return struct.unpack(ENDIANNESS + STRUCT_SIGNS[len(_bytes)], _bytes)[0]

def set_pointer(file):
    if file.read(4) != b'AKPK':
        log("Error, this file does not have a valid AKPK header!", -1)

    file.read(8) # Padding
    file.seek(25 + unpack(file.read(4))) # 25 skips to the sfx header

def extract(wems, file, out_path):
    # Create directory for the extracted files
    out_path.mkdir(exist_ok=True)

    print(f"Log: Extracting {len(wems)} sound files..")

    # Create the .wem files
    for w in wems:
        file.seek(wems[w]['offset'])
        data = file.read(wems[w]['length'])
        Path(out_path.joinpath(str(w) + '.wem')).write_bytes(data)

    # Convert the .wem files to .ogg
    for f in sorted(out_path.glob('*.wem')):
        subprocess.check_output(['./ww2ogg/ww2ogg.exe', f, '--pcb', 'ww2ogg/packed_codebooks_aoTuV_603.bin'], stderr=subprocess.DEVNULL)
        subprocess.check_output(['ffmpeg', '-i', f.with_suffix('.ogg'), f.with_suffix('.wav')], stderr=subprocess.DEVNULL)
        f.unlink()
        f.with_suffix('.ogg').unlink()

def process_pck(pck_path, out_path):
    with pck_path.open('rb') as stream:
        set_pointer(stream)
        stream.read(23) if unpack(stream.read(4)) != 0 else stream.read(3) # Handles for Magic Arena files

        # Get wems
        wems = {}
        for i in range(unpack(stream.read(4))):
            wem_id = unpack(stream.read(4))
            wem_type = unpack(stream.read(4))
            wem_length = unpack(stream.read(4))
            wem_offset = unpack(stream.read(4))

            stream.read(4) # Padding

            wems[wem_id] = {'length' : wem_length, 'offset' : wem_offset}

        extract(wems, stream, out_path)


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('files', nargs='+', type=Path)
    parser.add_argument('-o', '--output', type=Path, required=True)
    args = parser.parse_args()
    for path in args.files:
        process_pck(path, args.output / path.stem)