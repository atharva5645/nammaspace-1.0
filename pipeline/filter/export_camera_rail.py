import numpy as np
import json
from scipy.spatial.transform import Rotation as R

sparse_dir = 'data/experiments/supermarket001_chunk50_rectified/sparse/0'
with open(f'{sparse_dir}/images.txt', 'r') as f:
    lines = [l.strip() for l in f if l.strip() and not l.startswith('#')]

cams_raw = []
for i in range(0, len(lines), 2):
    p = lines[i].split()
    qw, qx, qy, qz = float(p[1]), float(p[2]), float(p[3]), float(p[4])
    tx, ty, tz = float(p[5]), float(p[6]), float(p[7])
    img = p[9]
    rot = R.from_quat([qx, qy, qz, qw]).as_matrix()
    c = -rot.T @ np.array([tx, ty, tz])
    fwd = rot.T @ np.array([0, 0, 1])
    up = -rot.T @ np.array([0, 1, 0])
    cams_raw.append({'img': img, 'pos': c, 'fwd': fwd, 'up': up})

# Exact same R_align as align_and_clean_supermarket.py
cam_pos = np.array([c['pos'] for c in cams_raw])
cam_fwd = np.array([c['fwd'] for c in cams_raw])
cam_up  = np.array([c['up']  for c in cams_raw])

mid_idx = len(cams_raw) // 2
c0 = cam_pos[mid_idx]

up_vec = cam_up.mean(axis=0)
up_vec /= np.linalg.norm(up_vec)
fwd_vec = cam_fwd.mean(axis=0)
fwd_vec -= np.dot(fwd_vec, up_vec) * up_vec
fwd_vec /= np.linalg.norm(fwd_vec)
right_vec = np.cross(fwd_vec, up_vec)

R_align = np.column_stack([right_vec, up_vec, -fwd_vec]).T
floor_y = -0.90

print('c0:', c0.round(4))
print('R_align det:', round(float(np.linalg.det(R_align)), 6))
print('floor_y offset:', floor_y)

cams_raw.sort(key=lambda c: c['img'])

waypoints = []
for cam in cams_raw:
    pos_raw = cam['pos']
    tgt_raw = pos_raw + cam['fwd'] * 1.5

    pos_a = (pos_raw - c0) @ R_align.T
    tgt_a = (tgt_raw - c0) @ R_align.T

    pos_a[1] -= floor_y
    tgt_a[1] -= floor_y

    waypoints.append({
        'img': cam['img'],
        'pos': [round(float(v), 4) for v in pos_a.tolist()],
        'target': [round(float(v), 4) for v in tgt_a.tolist()],
    })

print('Sample waypoints:')
for wp in waypoints[:3]:
    print(f"  {wp['img']}: pos={wp['pos']}  target={wp['target']}")
print(f'Total: {len(waypoints)}')

with open('frontend/namma-space/public/supermarket_rail.json', 'w') as f:
    json.dump({'waypoints': waypoints}, f, indent=2)
print('Written supermarket_rail.json')
