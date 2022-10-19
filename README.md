# Monster Hunter Soundtrack Compiler
## Workflow
### Rise
1. Extract chunk data (`re_chunk_000.pak`) with `REtool.exe` (see https://github.com/mhvuze/MonsterHunterRiseModding)
2. Get `*.wav` files from `*.pck.*` files inside `re_chunk_000/natives/STM/streaming/Sound\Wwise` with `unpack_pck.py`
3. Get HIRC `*.xml` files from `*_str*.bnk.*` with `wwiser` (see https://github.com/bnnm/wwiser).
4. Configure compiler and compile
### World
1. Extract chunk data (`chunk*.bin`) with `WorldChunkTool.exe`
2. Get `*.wav` files from `*.npck.*` files inside `chunk_combined/sound/wwise/Windows` with `unpack_pck.py`
3. Get HIRC `*.xml` files from `*_cmn.nbnk.*` with `wwiser` (see https://github.com/bnnm/wwiser).
4. Configure compiler and compile

