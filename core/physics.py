import numpy as np
import pymunk

# 物理定数
GRAVITY = 900.0        # 重力加速度 (pixel/s^2)
BALL_RADIUS = 14.0     # ボール半径 (pixel)
KEYBOARD_THICKNESS = 8.0 # 鍵盤の厚み (pixel)
KEYBOARD_LENGTH = 70.0  # 鍵盤の長さ (pixel)
FPS = 60
SUBSTEPS = 4

# 音名から周波数へのマッピング
NOTES_FREQ = {
    'C4': 261.63, 'D4': 293.66, 'E4': 329.63, 'F4': 349.23,
    'G4': 392.00, 'A4': 440.00, 'B4': 493.88, 'C5': 523.25,
    'D5': 587.33, 'E5': 659.25, 'F5': 698.46, 'G5': 783.99,
    'A5': 880.00, 'B5': 987.77, 'C6': 1046.50
}

def calculate_required_velocity(p_start, p_end, dt, g):
    """
    衝突直後の必要な速度ベクトル (vx, vy) を算出する。
    """
    dx = p_end[0] - p_start[0]
    dy = p_end[1] - p_start[1]
    
    vx = dx / dt
    # 垂直方向: dy = vy_out * dt - 0.5 * g * dt^2
    vy = (dy + 0.5 * g * (dt ** 2)) / dt
    return np.array([vx, vy])

def calculate_keyboard_geometry(v_in, v_out):
    """
    衝突直前速度 v_in と 衝突直後速度 v_out から
    鍵盤の法線ベクトル n と傾き角度 theta (ラジアン) を決定する。
    """
    dv = v_out - v_in
    dv_norm = np.linalg.norm(dv)
    if dv_norm < 1e-6:
        n = np.array([0.0, 1.0])
    else:
        n = dv / dv_norm
        
    # 法線は上向きにする
    if n[1] < 0:
        n = -n
        
    phi = np.arctan2(n[1], n[0])
    theta = phi - np.pi / 2
    return n, theta

def calculate_keyboard_position(c, n, R, T):
    """
    ボール衝突時の中心座標 c, 法線 n, ボール半径 R, 鍵盤厚み T から
    鍵盤の配置中心座標 P を逆算する（幾何補正）。
    """
    return c - (R + T / 2) * n

def generate_rail_points(p_start, v_out, dt, g, steps=30):
    """
    放物線軌道に沿って、ボールの底面に配置される美しいガイドレールの点群を算出する。
    物理演算には影響を与えない、視覚的装飾としてのレール。
    """
    points = []
    t_vals = np.linspace(0, dt, steps)
    
    for t in t_vals:
        # 放物線上のボール中心座標
        bx = p_start[0] + v_out[0] * t
        by = p_start[1] + v_out[1] * t - 0.5 * g * (t ** 2)
        
        # ボールの現在速度ベクトル
        vx = v_out[0]
        vy = v_out[1] - g * t
        v_len = np.hypot(vx, vy)
        
        if v_len > 1e-3:
            # 軌道に直交する下向き法線ベクトル
            # 進行方向 (vx, vy) -> 直交下向き (-vy, vx) または (vy, -vx)
            # ここではボールの下側にレールを配置するため、進行方向の右側（時計回り90度）を求める
            # 右側ベクトル: (vy, -vx) -> 単位化して下向きになるよう符号調整
            # Pymunk上向き正なので、速度が右方向(vx > 0)のときは下向き法線はyがマイナス
            nx_down = vy / v_len
            ny_down = -vx / v_len
        else:
            nx_down = 0.0
            ny_down = -1.0
            
        # ボール半径 R ＋ レールとの隙間（6px）分だけ下側にオフセット
        offset_dist = BALL_RADIUS + 5.0
        rx = bx + nx_down * offset_dist
        ry = by + ny_down * offset_dist
        
        points.append((rx, ry))
        
    return points

def build_simulation_plan(melody_data):
    """
    音符・タイミングの配列から、全鍵盤の配置・角度・および軌道ガイドレールの点群を完全予見して計画を作成する。
    """
    plan = []
    
    # 開始位置からの最初の落下を t=1.2秒とするため、時間をシフトする
    times = [item[1] + 1.2 for item in melody_data]
    notes = [item[0] for item in melody_data]
    
    # ジグザグな座標設計
    xs = []
    ys = []
    current_y = 350.0  # 開始y座標
    
    for i in range(len(melody_data)):
        # 左右にバウンドさせる (左右の幅 160px)
        x = 160.0 if i % 2 == 1 else -160.0
        xs.append(x)
        current_y -= 140.0  # 各ステップで140pxずつ自然に落下
        ys.append(current_y)
        
    # 最後の鍵盤から脱出させるための終点を追加
    times.append(times[-1] + 1.2)
    xs.append(-xs[-1])  # 反対側に跳ねる
    ys.append(current_y - 140.0)
    notes.append('C4')  # ダミー音

    # 初期位置（自由落下開始）
    t_start = times[0] - 1.0
    x_start = xs[0]
    y_start = ys[0] + 0.5 * GRAVITY * (1.0 ** 2)
    
    v_in_prev = np.array([0.0, -GRAVITY * 1.0])  # 最初の衝突直前の落下速度
    
    # 各衝突セグメントの計算
    for i in range(len(times) - 1):
        p_curr = np.array([xs[i], ys[i]])
        p_next = np.array([xs[i+1], ys[i+1]])
        dt = times[i+1] - times[i]
        
        # 衝突直後に必要な速度
        v_out = calculate_required_velocity(p_curr, p_next, dt, GRAVITY)
        
        # 衝突直前の速度
        if i == 0:
            v_in = v_in_prev
        else:
            dt_prev = times[i] - times[i-1]
            v_in = np.array([plan[i-1]['v_out'][0], plan[i-1]['v_out'][1] - GRAVITY * dt_prev])
            
        # 鍵盤の法線と角度
        n, theta = calculate_keyboard_geometry(v_in, v_out)
        
        # 幾何補正された鍵盤の配置中心
        pos = calculate_keyboard_position(p_curr, n, BALL_RADIUS, KEYBOARD_THICKNESS)
        
        # 視覚的ガイドレールの点群を生成
        rail_points = generate_rail_points(p_curr, v_out, dt, GRAVITY, steps=30)
        
        plan.append({
            'index': i,
            'time': times[i],
            'note': notes[i],
            'freq': NOTES_FREQ.get(notes[i], 261.63),
            'c_pos': p_curr,      # ボール中心衝突予定座標
            'key_pos': pos,       # 鍵盤配置中心座標
            'n': n,               # 法線ベクトル
            'theta': theta,       # 鍵盤角度 (ラジアン)
            'v_in': v_in,
            'v_out': v_out,
            'rail_points': rail_points # 美しいガイドレールの点群
        })
        
    return plan, (x_start, y_start, t_start)

def run_simulation(plan, start_info, duration):
    """
    Pymunkを用いて物理シミュレーションを回し、各フレームのボール位置と衝突イベントを取得する。
    """
    x_start, y_start, t_start = start_info
    
    space = pymunk.Space()
    space.gravity = (0, -GRAVITY)
    
    # ボールの物理オブジェクト作成
    ball_mass = 1.0
    ball_moment = pymunk.moment_for_circle(ball_mass, 0, BALL_RADIUS)
    ball_body = pymunk.Body(ball_mass, ball_moment)
    ball_body.position = (x_start, y_start)
    ball_body.velocity = (0.0, 0.0)
    
    ball_shape = pymunk.Circle(ball_body, BALL_RADIUS)
    ball_shape.friction = 0.0
    ball_shape.elasticity = 1.0
    ball_shape.collision_type = 1
    
    space.add(ball_body, ball_shape)
    
    # 静的な鍵盤オブジェクトを配置
    for item in plan:
        theta = item['theta']
        pos = item['key_pos']
        
        # 線分の端点を算出
        dx = (KEYBOARD_LENGTH / 2.0) * np.cos(theta)
        dy = (KEYBOARD_LENGTH / 2.0) * np.sin(theta)
        a = (pos[0] - dx, pos[1] - dy)
        b = (pos[0] + dx, pos[1] + dy)
        
        key_shape = pymunk.Segment(space.static_body, a, b, KEYBOARD_THICKNESS / 2.0)
        key_shape.friction = 0.0
        key_shape.elasticity = 1.0
        key_shape.collision_type = item['index'] + 10
        
        space.add(key_shape)
        
    collision_events = []
    has_collided = [False] * len(plan)
    
    # Pymunk 7.2.0 の on_collision API による精密同期補正
    for item in plan:
        idx = item['index']
        
        def make_pre_solve(i):
            def pre_solve_callback(arbiter, space_obj, data):
                if not has_collided[i]:
                    # 離散化誤差を排除するため、衝突時に位置と速度を精密に理論値へリセット
                    arbiter.shapes[0].body.position = tuple(plan[i]['c_pos'])
                    arbiter.shapes[0].body.velocity = tuple(plan[i]['v_out'])
                    has_collided[i] = True
                    
                    actual_pos = arbiter.shapes[0].body.position
                    collision_events.append({
                        'index': i,
                        'time': space_obj.seconds_passed,
                        'pos': actual_pos,
                        'note': plan[i]['note'],
                        'freq': plan[i]['freq']
                    })
            return pre_solve_callback
            
        space.on_collision(1, idx + 10, pre_solve=make_pre_solve(idx))

    # シミュレーションループの実行
    frames_count = int(duration * FPS)
    ball_positions = []
    
    dt_frame = 1.0 / FPS
    dt_step = dt_frame / SUBSTEPS
    space.seconds_passed = t_start
    
    for f in range(frames_count):
        t_frame = f * dt_frame
        
        if t_frame < t_start:
            ball_positions.append((x_start, y_start))
        else:
            for _ in range(SUBSTEPS):
                space.step(dt_step)
                space.seconds_passed += dt_step
            ball_positions.append(tuple(ball_body.position))
            
    return ball_positions, collision_events
