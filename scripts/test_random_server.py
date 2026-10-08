"""Optional official BDS auxiliary test; no Windows client/player verification.
Run after creating both fixtures with make_server_test_world.py.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import time
import pexpect

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('server_root', type=Path)
args = parser.parse_args()
layout = json.loads((ROOT / 'dist/layout.json').read_text())
server = args.server_root.resolve()
serial = 0
results = {}


def start(name, logname):
    props = server / 'server.properties'
    text = props.read_text()
    props.write_text(re.sub(r'^level-name=.*$', 'level-name=' + name, text, flags=re.M))
    proc = pexpect.spawn(str(server / 'bedrock_server'), cwd=str(server), env={**os.environ, 'LD_LIBRARY_PATH': '.'}, encoding='utf-8', echo=False, timeout=30)
    proc.delaybeforesend = 0.005
    proc.logfile_read = (ROOT / 'docs' / logname).open('w')
    proc.expect('Server started')
    proc.sendline('scoreboard objectives add qa_marker dummy')
    return proc


def cmd(proc, command):
    global serial
    serial += 1
    marker = 'QA_END_' + str(serial)
    proc.sendline(command)
    proc.sendline(f'scoreboard players set {marker} qa_marker {serial}')
    proc.expect(marker)
    return proc.before


def load_area(proc):
    cmd(proc, 'tickingarea add -16 0 -16 143 90 95 qa_north true')
    cmd(proc, 'tickingarea add -16 0 96 143 90 207 qa_south true')
    time.sleep(2)


def stop(proc):
    proc.sendline('stop')
    proc.expect(pexpect.EOF)
    proc.logfile_read.close()


p = start('math_maze_v5_original', 'server_probe_v5_console.txt')
load_area(p)
for room_index in range(22):
    x, z = room_index % 4 * 32 + 16, room_index // 4 * 32 + 3
    for y, material in ((64, 'planks ["wood_type"="birch"]'), (65, 'air'), (66, 'air')):
        out = cmd(p, f'testforblock {x} {y} {z} {material}')
        assert 'Successfully found' in out, out
for record in layout['commands']:
    out = cmd(p, record['command'])
    assert not re.search(r'Syntax error|Unknown command|Unexpected', out, re.I), out
results['original_world_load'] = 'PASS'
results['original_arrival_block_tests'] = 66
results['original_commands_syntax_checked'] = len(layout['commands'])
stop(p)

p = start('math_maze_v5_surrogate', 'server_surrogate_v5_console.txt')
load_area(p)
probe = '@e[type=pig,name=maze_probe]'
cmd(p, f'kill {probe}')
cmd(p, 'summon pig maze_probe 16.5 65.1 3.5')
cmd(p, f'effect {probe} slowness 999999 255 true')
cmd(p, f'tag {probe} add maze_started')
cmd(p, f'scoreboard players set {probe} maze_count -1')
cmd(p, f'tag {probe} remove maze_draw')


def at(proc, point):
    x, y, z = point
    out = cmd(proc, f'testfor @e[type=pig,name=maze_probe,x={x-1},y={y},z={z-1},dx=2,dy=3,dz=2]')
    return 'Found maze_probe' in out


# Freeze count at -1 while checking each individual original plate route.
for room in layout['rooms']:
    for route in room['routes']:
        x, y, z = route['plate']
        cmd(p, f'tp {probe} {x+0.5} {y+0.1} {z+0.5}')
        time.sleep(0.65)
        assert at(p, route['destination']), (room['pool_index'], route, p.before)
        cmd(p, f'tag {probe} remove maze_draw')
results['surrogate_plate_routes'] = {'result': 'PASS', 'routes': 60, 'correct': 20, 'retry': 40}


def room_now(proc):
    out = cmd(proc, f'querytarget {probe}')
    match = re.search(r'\[\s*\{.*?\}\s*\]', out, re.S)
    assert match, out
    # querytarget may return JSON with a nested position object.
    data = json.loads(match.group(0))[0]['position']
    return int(data['x'] // 32) + int(data['z'] // 32) * 4


def score(proc, n):
    out = cmd(proc, f'scoreboard players test {probe} maze_count {n} {n}')
    assert f'Score {n} is in range {n} to {n}' in out, out


# Start fresh; then physically press replay for the second full random run.
for i in range(20):
    cmd(p, f'tag {probe} remove maze_seen_{i}')
cmd(p, f'scoreboard players set {probe} maze_count 0')
cmd(p, f'tag {probe} add maze_draw')
cmd(p, f'tp {probe} 16.5 65 3.5')
sequences = []
for run in range(3):
    sequence = []
    for n in range(10):
        time.sleep(0.7)
        physical_room = room_now(p)
        assert 1 <= physical_room <= 20, (n, physical_room)
        pool = physical_room - 1
        assert pool not in sequence, sequence
        assert (pool < 10) == (n % 2 == 0), sequence
        sequence.append(pool)
        score(p, n + 1)
        room = layout['rooms'][pool]
        # Wrong answer must stay on same question and preserve the count.
        wrong = next(r for r in room['routes'] if not r['correct'])
        x, y, z = wrong['plate']
        cmd(p, f'tp {probe} {x+0.5} {y+0.1} {z+0.5}')
        time.sleep(0.65)
        assert at(p, room['entry']), (run, n, 'wrong')
        score(p, n + 1)
        right = next(r for r in room['routes'] if r['correct'])
        x, y, z = right['plate']
        cmd(p, f'tp {probe} {x+0.5} {y+0.1} {z+0.5}')
    time.sleep(0.8)
    assert at(p, layout['randomization']['goal']), 'goal not reached'
    assert 'Found maze_probe' in cmd(p, 'testfor @e[type=pig,name=maze_probe,tag=maze_goal]')
    sequences.append(sequence)
    if run < 2:
        x, y, z = layout['restart_plate']
        cmd(p, f'tp {probe} {x+0.5} {y+0.1} {z+0.5}')
        time.sleep(0.8)
        score(p, 1)
        assert 'Found maze_probe' in cmd(p, 'testfor @e[type=pig,name=maze_probe,tag=!maze_goal]')
assert len(set(map(tuple, sequences))) == 3
results['surrogate_random_runs'] = {'result': 'PASS', 'runs': 3, 'pool_index_sequences': sequences, 'unique_questions_per_run': 10, 'addition_per_run': 5, 'subtraction_per_run': 5, 'wrong_answers_preserve_question_and_count': True, 'physical_replays': 2}
stop(p)
results.update({'artifact': layout['artifact'], 'artifact_sha256': hashlib.sha256((ROOT/'dist'/layout['artifact']).read_bytes()).hexdigest(), 'server': 'Official Bedrock Dedicated Server Linux 1.26.52.3', 'test_date': '2026-10-08', 'minecraft_windows_import': 'NOT_TESTED', 'minecraft_windows_gameplay': 'NOT_TESTED', 'limitations': ['The auxiliary copy replaces @a[...] selectors with named pig entity selectors. No real player connects.', 'Japanese rendering, screen score display, sound, celebration visuals and child usability are not verified.', 'The distribution archive remains the unmodified original, not the server upgraded test copy.']})
(ROOT/'dist/server_validation.json').write_text(json.dumps(results, ensure_ascii=False, indent=2)+'\n')
print(json.dumps(results, ensure_ascii=False, indent=2))
