from pathlib import Path
import xml.etree.ElementTree as ET

if __name__ == '__main__':
    best_range = (0, 0)
    current_id = None
    current_begin = None
    current_end = None
    current_src_duration = None
    for path in Path().glob('*.xml'):
        tree = ET.parse(path)
        for node in tree.findall('.//fld'):
            if node.attrib['na'] == 'sourceID':
                current_id = node.attrib['va']
                continue
            if current_id == '217525265':
                if node.attrib['na'] == 'fBeginTrimOffset':
                    current_begin =  float(node.attrib['va'])
                elif node.attrib['na'] == 'fEndTrimOffset':
                    current_end =  float(node.attrib['va'])
                elif node.attrib['na'] == 'fSrcDuration':
                    current_src_duration =  float(node.attrib['va'])
                    current_end = current_src_duration + current_end
                    current_duration = current_end - current_begin
                    if current_duration > best_range[1]:
                        best_range = (current_begin, current_duration)
    print(best_range)