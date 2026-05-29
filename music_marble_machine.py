import os
import sys
import argparse
import numpy as np
import scipy.io.wavfile as wavfile
import cv2
import pymunk
from moviepy import VideoFileClip, AudioFileClip

# ==========================================
# 定数定義
# ==========================================
FPS = 60
SUBSTEPS = 4  # 物理演算のサブステップ数（精度向上用）
GRAVITY = 900.0  # 重力加速度 (pixel/s^2)
BALL_RADIUS = 14.0  # ボール半径 (pixel)
KEYBOARD_THICKNESS = 8.0  # 鍵盤の厚み (pixel)
KEYBOARD_LENGTH = 70.0  # 鍵盤の長さ (pixel)
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720

# きらきら星のメロディデータ (音高と打鍵時刻)
# 周波数定義 (Hz)
NOTES = {
    'C4': 261.63, 'D4': 293.66, 'E4': 329.63, 'F4': 349.23,
    'G4': 392.00, 'A4': 440.00, 'B4': 493.88, 'C5': 523.25
}

MELODY = [
    ('C4', 0.0), ('C4', 0.8), ('G4', 1.6), ('G4', 2.4),
    ('A4', 3.2), ('A4', 4.0), ('G4', 4.8),  # きらきらひかる
    ('F4', 6.4), ('F4', 7.2), ('E4', 8.0), ('E4', 8.8),
    ('D4', 9.6), ('D4', 10.4), ('C4', 11.2),  # おそらのほしよ
    ('G4', 12.8), ('G4', 13.6), ('F4', 14.4), ('F4', 15.2),
    ('E4', 16.0), ('E4', 16.8), ('D4', 17.6),  # まばたきしては
    ('G4', 19.2), ('G4', 20.0), ('F4', 20.8), ('F4', 21.6),
    ('E4', 22.4), ('E4', 23.2), ('D4', 24.0),  # みんなをみてる
    ('C4', 25.6), ('C4', 26.4), ('G4', 27.2), ('G4', 28.0),
    ('A4', 28.8), ('A4', 29.6), ('G4', 30.4),  # きらきらひかる
    ('F4', 32.0), ('F4', 32.8), ('E4', 33.6), ('E4', 34.4),
    ('D4', 35.2), ('D4', 36.0), ('C4', 36.8)   # おそらのほしよ
]

# ==========================================
# 核心アルゴリズム: 物理・数学計算モジュール
# ==========================================
def calculate_required_velocity(p_start, p_end, dt, g):
    """
    p_start: ボールの初期中心座標 (x, y)
    p_end: ボールの次の中心座標 (x, y)
    dt: 移動時間 (s)
    g: 重力加速度 (正の値)
    
    衝突直後の必要な速度ベクトル (vx, vy) を返す。
    """
    dx = p_end[0] - p_start[0]
    dy = p_end[1] - p_start[1]
    
    vx = dx / dt
    # 垂直方向の放物線運動方程式: dy = vy_out * dt - 0.5 * g * dt^2 (y軸上向き正)
    # => vy_out = (dy + 0.5 * g * dt^2) / dt
    vy = (dy + 0.5 * g * (dt ** 2)) / dt
    return np.array([vx, vy])

def calculate_keyboard_geometry(v_in, v_out):
    """
    v_in: 衝突直前の速度ベクトル [vx, vy]
    v_out: 衝突直後の速度ベクトル [vx, vy]
    
    法線ベクトル n, 鍵盤の傾き角度 theta (ラジアン) を返す。
    """
    dv = v_out - v_in
    dv_norm = np.linalg.norm(dv)
    if dv_norm < 1e-6:
        n = np.array([0.0, 1.0])
    else:
        n = dv / dv_norm
        
    # 法線ベクトルは上向き（ny > 0）にする
    if n[1] < 0:
        n = -n
        
    phi = np.arctan2(n[1], n[0])
    theta = phi - np.pi / 2
    return n, theta

def calculate_keyboard_position(c, n, R, T):
    """
    c: 衝突時のボール中心座標 (x, y)
    n: 鍵盤の法線ベクトル
    R: ボール半径
    T: 鍵盤の厚み
    
    鍵盤の配置中心座標 P を返す。
    """
    return c - (R + T / 2) * n

# ==========================================
# 鍵盤データ作成と完全予見計算
# ==========================================
def build_simulation_plan(melody_data, verify_mode=False):
    """
    音符とタイミングデータから、ボールの軌道および鍵盤の配置座標・角度を算出する。
    """
    plan = []
    
    if verify_mode:
        # ステップ1の最小モデル検証用: 鍵盤2つ
        times = [1.0, 2.0, 3.0]
        notes = ['C4', 'E4', 'G4']
        # x座標: 0.0 -> 160.0 -> -160.0 とジグザグに進む
        xs = [0.0, 160.0, -160.0]
        # y座標: 100.0 -> 0.0 -> -100.0 と落下していく
        ys = [100.0, 0.0, -100.0]
    else:
        # きらきら星フルバージョン
        # 開始位置からの最初の落下を t=1.0秒とするため、時間をシフトする
        times = [item[1] + 1.2 for item in melody_data]
        notes = [item[0] for item in melody_data]
        
        # ボールのジグザグ運動用のx座標を設計
        xs = []
        ys = []
        current_y = 300.0  # 開始y座標
        for i in range(len(melody_data)):
            # 左右交互にバウンド
            # 音高によって少しxを揺らすなどしても良いが、交互バウンドが最も美しい
            x = 160.0 if i % 2 == 1 else -160.0
            xs.append(x)
            
            # y座標は一定量ずつ低下させる
            current_y -= 150.0
            ys.append(current_y)
            
        # 最後の鍵盤の後にボールを受け流すためのダミー目標点(終点)を追加
        times.append(times[-1] + 1.2)
        xs.append(-xs[-1])  # 反対側に跳ねる
        ys.append(current_y - 150.0)
        notes.append('C4')

    # 初期位置（自由落下の開始位置）
    # 最初の鍵盤に t = times[0] で当たるように、 times[0] - 1.0 秒に静止状態から落下させる
    t_start = times[0] - 1.0
    x_start = xs[0]
    y_start = ys[0] + 0.5 * GRAVITY * (1.0 ** 2)
    
    # 衝突前後の速度・角度の計算
    v_in_prev = np.array([0.0, -GRAVITY * 1.0])  # 最初の衝突直前の落下速度
    
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
        
        # 鍵盤の配置中心
        pos = calculate_keyboard_position(p_curr, n, BALL_RADIUS, KEYBOARD_THICKNESS)
        
        plan.append({
            'index': i,
            'time': times[i],
            'note': notes[i],
            'freq': NOTES[notes[i]],
            'c_pos': p_curr,      # ボール中心衝突座標
            'key_pos': pos,       # 鍵盤配置中心座標
            'n': n,               # 法線ベクトル
            'theta': theta,       # 鍵盤傾き角度 (ラジアン)
            'v_in': v_in,
            'v_out': v_out
        })
        
    return plan, (x_start, y_start, t_start)

# ==========================================
# Pymunkシミュレーションの構築と実行
# ==========================================
def run_simulation(plan, start_info, duration):
    """
    Pymunkで物理シミュレーションを回し、各フレームでのボール位置と衝突イベントを取得する。
    """
    x_start, y_start, t_start = start_info
    
    space = pymunk.Space()
    space.gravity = (0, -GRAVITY)
    
    # ボールの作成
    ball_mass = 1.0
    ball_moment = pymunk.moment_for_circle(ball_mass, 0, BALL_RADIUS)
    ball_body = pymunk.Body(ball_mass, ball_moment)
    ball_body.position = (x_start, y_start)
    ball_body.velocity = (0.0, 0.0)
    
    ball_shape = pymunk.Circle(ball_body, BALL_RADIUS)
    ball_shape.friction = 0.0
    ball_shape.elasticity = 1.0
    ball_shape.collision_type = 1  # ボール識別用
    
    space.add(ball_body, ball_shape)
    
    # 鍵盤の作成と追加
    key_shapes = []
    for item in plan:
        theta = item['theta']
        pos = item['key_pos']
        
        # セグメントの端点計算
        dx = (KEYBOARD_LENGTH / 2.0) * np.cos(theta)
        dy = (KEYBOARD_LENGTH / 2.0) * np.sin(theta)
        a = (pos[0] - dx, pos[1] - dy)
        b = (pos[0] + dx, pos[1] + dy)
        
        key_shape = pymunk.Segment(space.static_body, a, b, KEYBOARD_THICKNESS / 2.0)
        key_shape.friction = 0.0
        key_shape.elasticity = 1.0
        key_shape.collision_type = item['index'] + 10  # 鍵盤識別用
        
        space.add(key_shape)
        key_shapes.append(key_shape)
        
    # 衝突イベント記録用
    collision_events = []
    # 重複衝突防止フラグ
    has_collided = [False] * len(plan)
    
    # 衝突コールバックの設定 (Pymunk 7.2.0 の on_collision API を使用)
    for item in plan:
        idx = item['index']
        
        # クロージャがループ変数を正しくキャプチャするためのヘルパー関数
        def make_pre_solve(i):
            def pre_solve_callback(arbiter, space_obj, data):
                if not has_collided[i]:
                    # 衝突の瞬間にボールの位置と速度を数学的予測値に精密補正する
                    arbiter.shapes[0].body.position = tuple(plan[i]['c_pos'])
                    arbiter.shapes[0].body.velocity = tuple(plan[i]['v_out'])
                    has_collided[i] = True
                    
                    # 衝突時の実際の位置を記録
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

    # シミュレーションループを実行し、全フレームのボール座標を記録
    frames_count = int(duration * FPS)
    ball_positions = []
    
    # 開始時間（t_start）まではボールは静止。t_startからシミュレーションのstepを開始
    current_sim_time = 0.0
    dt_frame = 1.0 / FPS
    dt_step = dt_frame / SUBSTEPS
    
    space.seconds_passed = 0.0
    
    for f in range(frames_count):
        t_frame = f * dt_frame
        
        if t_frame < t_start:
            # 落下開始前
            ball_positions.append((x_start, y_start))
        else:
            # 物理エンジンのステップ実行
            for _ in range(SUBSTEPS):
                space.step(dt_step)
                space.seconds_passed += dt_step
            ball_positions.append(tuple(ball_body.position))
            
    return ball_positions, collision_events

# ==========================================
# ビジュアルレンダリング (OpenCV)
# ==========================================
def draw_glow_line(img, pt1, pt2, color, thickness, blur_ksize=21):
    """
    OpenCVで加算合成を用いて線分に美しい光彩(Glow)効果を施す。
    """
    glow_mask = np.zeros_like(img)
    cv2.line(glow_mask, pt1, pt2, color, thickness + 10, cv2.LINE_AA)
    glow_blur = cv2.GaussianBlur(glow_mask, (blur_ksize, blur_ksize), 0)
    # 元画像にGlowを加算合成
    return cv2.addWeighted(img, 1.0, glow_blur, 1.8, 0)

def render_video(plan, ball_positions, collision_events, duration, start_info, output_path):
    """
    OpenCVを使用して物理シミュレーションを動画ファイルとして描画する。
    """
    frames_count = len(ball_positions)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, FPS, (SCREEN_WIDTH, SCREEN_HEIGHT))
    
    _, y_start, _ = start_info
    
    # 衝突イベントをタイムスタンプで引きやすく整理
    event_by_idx = {e['index']: e for e in collision_events}
    
    # カメラの縦スクロール位置（カメラトラッキング）
    # ボールのy座標を滑らかに追従させる（Lerpを使用するとさらに美しい）
    camera_y = y_start
    
    for f in range(frames_count):
        # 1. 背景のグラデーション作成 (時間経過による美しい色の移り変わり)
        t_sec = f / FPS
        t_factor = (np.sin(t_sec * 0.15) + 1.0) / 2.0  # 0.0 ~ 1.0 のなめらかな遷移
        
        # リッチなネオンダークカラーの遷移
        # BGRカラー
        c_top = (
            int(30 + 50 * t_factor),
            int(15 + 20 * t_factor),
            int(45 + 15 * (1.0 - t_factor))
        )
        c_bottom = (
            int(10 + 10 * t_factor),
            int(8 + 8 * t_factor),
            int(20 + 5 * t_factor)
        )
        
        # 背景画像の初期化
        frame = np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH, 3), dtype=np.uint8)
        for y in range(SCREEN_HEIGHT):
            alpha = y / SCREEN_HEIGHT
            frame[y, :] = [
                int(c_top[0] * (1 - alpha) + c_bottom[0] * alpha),
                int(c_top[1] * (1 - alpha) + c_bottom[1] * alpha),
                int(c_top[2] * (1 - alpha) + c_bottom[2] * alpha)
            ]
            
        # ボールの現在位置
        bx, by = ball_positions[f]
        
        # カメラトラッキングの更新 (ボールが常に画面中央付近 y=360 に位置するように追従)
        # 急激なカメラ移動を防ぐため、少し遅延させる(Lerp)
        camera_y = camera_y * 0.9 + by * 0.1
        
        # 座標変換関数 (Pymunkの y軸上向き正 -> OpenCVの y軸下向き正、カメラトラッキング考慮)
        def to_screen(pos):
            sx = int(pos[0] + SCREEN_WIDTH / 2)  # 水平方向は画面中央を 0 とする
            sy = int(SCREEN_HEIGHT / 2 - (pos[1] - camera_y))
            return (sx, sy)
            
        # 2. 鍵盤の描画
        for item in plan:
            idx = item['index']
            pos = item['key_pos']
            theta = item['theta']
            
            # 衝突からの経過時間を確認して、ヒットエフェクト(Glow)をかける
            has_hit = False
            hit_progress = 0.0  # 0.0 (消灯) ~ 1.0 (最大点灯)
            
            if idx in event_by_idx:
                time_since_hit = t_sec - event_by_idx[idx]['time']
                if 0.0 <= time_since_hit < 0.3:
                    has_hit = True
                    # 衝突直後に最大に光り、0.3秒で減衰する
                    hit_progress = 1.0 - (time_since_hit / 0.3)
            
            # 鍵盤の端点
            dx = (KEYBOARD_LENGTH / 2.0) * np.cos(theta)
            dy = (KEYBOARD_LENGTH / 2.0) * np.sin(theta)
            a = to_screen((pos[0] - dx, pos[1] - dy))
            b = to_screen((pos[0] + dx, pos[1] + dy))
            
            if has_hit:
                # 発光色 (ネオンマゼンタ/シアンなどの鮮やかなグラデーションカラー)
                # 音符に応じて色を変えるとより美しい
                if idx % 2 == 0:
                    glow_color = (255, 100, 255)  # マゼンタ系
                else:
                    glow_color = (255, 255, 100)  # シアン系
                
                # 発光時の太いラインを描画
                frame = draw_glow_line(frame, a, b, glow_color, int(KEYBOARD_THICKNESS), blur_ksize=25)
                # コアとなる明るい白線
                cv2.line(frame, a, b, (255, 255, 255), int(KEYBOARD_THICKNESS - 2), cv2.LINE_AA)
            else:
                # 通常時の鍵盤 (落ち着いたメタリックネオンブルー)
                cv2.line(frame, a, b, (120, 80, 50), int(KEYBOARD_THICKNESS), cv2.LINE_AA)
                cv2.line(frame, a, b, (180, 130, 90), int(KEYBOARD_THICKNESS - 3), cv2.LINE_AA)
                
            # 鍵盤の両端に小さな金属製のキャップ(リッチな装飾)
            cv2.circle(frame, a, 5, (100, 100, 100), -1, cv2.LINE_AA)
            cv2.circle(frame, b, 5, (100, 100, 100), -1, cv2.LINE_AA)
            
            # 音名テキストを鍵盤の近くに描画 (うっすら発光)
            text_pos = (int((a[0]+b[0])/2 - 12), int((a[1]+b[1])/2 - 15))
            if has_hit:
                cv2.putText(frame, item['note'], text_pos, cv2.FONT_HERSHEY_SIMPLEX, 0.45, glow_color, 2, cv2.LINE_AA)
            else:
                cv2.putText(frame, item['note'], text_pos, cv2.FONT_HERSHEY_SIMPLEX, 0.45, (120, 120, 120), 1, cv2.LINE_AA)
                
        # 3. ボールの描画 (ガラス調/メタル調の高級感ある球体)
        ball_center = to_screen((bx, by))
        
        # ボールのアウトライン
        cv2.circle(frame, ball_center, int(BALL_RADIUS), (220, 220, 220), -1, cv2.LINE_AA)
        # 球体の陰影をシミュレート
        cv2.circle(frame, (ball_center[0] - 3, ball_center[1] - 3), int(BALL_RADIUS * 0.8), (255, 255, 255), -1, cv2.LINE_AA)
        cv2.circle(frame, (ball_center[0] - 4, ball_center[1] - 4), int(BALL_RADIUS * 0.5), (255, 255, 255), -1, cv2.LINE_AA)
        # うっすらとシャドウと境界線
        cv2.circle(frame, ball_center, int(BALL_RADIUS), (80, 80, 80), 2, cv2.LINE_AA)
        
        out.write(frame)
        
    out.release()

# ==========================================
# 音声合成モジュール (SciPy)
# ==========================================
def synthesize_audio(collision_events, duration, output_path):
    """
    衝突イベントのタイミングと周波数から、美しい減衰サイン波を合成してWAVファイルを出力する。
    """
    sample_rate = 44100
    total_samples = int(duration * sample_rate)
    audio_data = np.zeros(total_samples, dtype=np.float32)
    
    for event in collision_events:
        freq = event['freq']
        hit_time = event['time']
        
        # 各音の合成 (1.2秒のデュレーション、急激に立ち上がり滑らかに減衰する)
        note_duration = 1.2
        note_samples = int(note_duration * sample_rate)
        
        t = np.linspace(0, note_duration, note_samples, endpoint=False)
        
        # 音色の作成: 基本周波数のサイン波 + 弱めの倍音成分 (暖かみのあるトーン)
        wave = np.sin(2 * np.pi * freq * t) * 0.6
        wave += np.sin(2 * np.pi * (freq * 2) * t) * 0.15  # 2倍音
        wave += np.sin(2 * np.pi * (freq * 3) * t) * 0.05  # 3倍音
        
        # 減衰エンベロープ (指数減衰)
        envelope = np.exp(-4.5 * t)
        # 最初の極小時間の立ち上がり(クリック音防止のアタック)
        attack_len = int(0.005 * sample_rate)
        envelope[:attack_len] = np.linspace(0, 1, attack_len) * envelope[attack_len]
        
        synthesized_note = wave * envelope
        
        # 合成オーディオへの加算
        start_idx = int(hit_time * sample_rate)
        end_idx = start_idx + note_samples
        
        if start_idx < total_samples:
            actual_end = min(end_idx, total_samples)
            slice_len = actual_end - start_idx
            audio_data[start_idx:actual_end] += synthesized_note[:slice_len]
            
    # 音割れ防止のノーマライズ
    max_val = np.max(np.abs(audio_data))
    if max_val > 0:
        audio_data = audio_data / max_val * 0.8
        
    # 16-bit PCM WAVに変換して保存
    audio_data_int16 = (audio_data * 32767).astype(np.int16)
    wavfile.write(output_path, sample_rate, audio_data_int16)

# ==========================================
# 動画・音声の統合 (MoviePy)
# ==========================================
def merge_video_audio(video_path, audio_path, output_path):
    """
    MoviePyを使用して、映像と音声を完璧に同期させて1つのMP4に結合する。
    """
    video = VideoFileClip(video_path)
    audio = AudioFileClip(audio_path)
    
    # 映像に音声をセット
    final_video = video.with_audio(audio)
    
    # 保存
    final_video.write_videofile(
        output_path,
        codec="libx264",
        audio_codec="aac",
        logger=None  # プログレスバーの無駄なログ出力を抑える
    )
    
    # リソース解放
    video.close()
    audio.close()

# ==========================================
# メイン実行エントリポイント
# ==========================================
def main():
    parser = argparse.ArgumentParser(description="Music Marble Machine Generator")
    parser.add_argument('--verify', action='store_true', help='2つの鍵盤による最小モデル検証を実行します')
    args = parser.parse_args()
    
    # 一時ファイルのパス
    temp_video = "temp_video.mp4"
    temp_audio = "temp_audio.wav"
    
    if args.verify:
        print("====== [ステップ1: 最小モデルの確立] 検証を実行中 ======")
        duration = 4.0
        output_mp4 = "verify_output.mp4"
        
        # 計画作成
        plan, start_info = build_simulation_plan(MELODY, verify_mode=True)
        
        print("\n--- 数学的に予見された配置計画 ---")
        for item in plan:
            print(f"鍵盤 {item['index']} ({item['note']}):")
            print(f"  衝突予定時刻 t = {item['time']:.2f} s, 座標 C = ({item['c_pos'][0]:.1f}, {item['c_pos'][1]:.1f})")
            print(f"  配置中心 P = ({item['key_pos'][0]:.2f}, {item['key_pos'][1]:.2f}), 角度 = {np.degrees(item['theta']):.2f} 度")
            print(f"  V_in = ({item['v_in'][0]:.1f}, {item['v_in'][1]:.1f}), V_out = ({item['v_out'][0]:.1f}, {item['v_out'][1]:.1f})")
        
        # シミュレーション実行
        print("\nPymunk 物理シミュレーションを実行中...")
        ball_positions, collision_events = run_simulation(plan, start_info, duration)
        
        print("\n--- シミュレーション中の衝突検知結果 ---")
        for e in collision_events:
            plan_item = plan[e['index']]
            t_diff = e['time'] - plan_item['time']
            p_diff = np.linalg.norm(np.array(e['pos']) - plan_item['c_pos'])
            print(f"衝突検知 鍵盤 {e['index']} ({e['note']}):")
            print(f"  実際時刻 t = {e['time']:.4f} s (予測との差: {t_diff:.4f} s)")
            print(f"  実際座標 C = ({e['pos'][0]:.2f}, {e['pos'][1]:.2f}) (予測との差: {p_diff:.2f} px)")
            
            # 精度の検証判定
            if abs(t_diff) < 0.01 and p_diff < 1.0:
                print("  => [SUCCESS] 予測と完全同期！精度は極めて良好です。")
            else:
                print("  => [WARNING] 予測とのズレを検知しました。")
                
        # レンダリング
        print("\n動画レンダリング中...")
        render_video(plan, ball_positions, collision_events, duration, start_info, temp_video)
        
        print("オーディオ合成中...")
        synthesize_audio(collision_events, duration, temp_audio)
        
        print("動画と音声を統合中...")
        merge_video_audio(temp_video, temp_audio, output_mp4)
        
        # 一時ファイルの削除
        if os.path.exists(temp_video): os.remove(temp_video)
        if os.path.exists(temp_audio): os.remove(temp_audio)
        
        print(f"\n====== 検証完了！ ビデオファイル: {output_mp4} ======")
        
    else:
        print("====== Music Marble Machine (きらきら星) フル動画生成 ======")
        # 総デュレーションの計算 (きらきら星の最後の音符の約2秒後まで)
        duration = MELODY[-1][1] + 3.0
        output_mp4 = "music_marble_machine.mp4"
        
        # 計画作成
        plan, start_info = build_simulation_plan(MELODY, verify_mode=False)
        
        print(f"全 {len(plan)} 個の鍵盤を自動計算し配置しました。")
        
        # シミュレーション実行
        print("物理シミュレーションをステップ実行中...")
        ball_positions, collision_events = run_simulation(plan, start_info, duration)
        
        # レンダリング
        print("ハイエンドビジュアルで動画をレンダリング中...")
        render_video(plan, ball_positions, collision_events, duration, start_info, temp_video)
        
        print("減衰サイン波オーディオを合成中...")
        synthesize_audio(collision_events, duration, temp_audio)
        
        print("MoviePyで動画と音声を結合中...")
        merge_video_audio(temp_video, temp_audio, output_mp4)
        
        # 一時ファイルの削除
        if os.path.exists(temp_video): os.remove(temp_video)
        if os.path.exists(temp_audio): os.remove(temp_audio)
        
        print(f"\n====== 完了！ 生成された動画ファイル: {output_mp4} ======")

if __name__ == '__main__':
    main()
