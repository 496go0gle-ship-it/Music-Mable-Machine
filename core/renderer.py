import numpy as np
import cv2
import random

# 定数定義
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
FPS = 60
BALL_RADIUS = 14.0
KEYBOARD_THICKNESS = 10.0 # 少し厚みを持たせる
KEYBOARD_LENGTH = 70.0

# 3D等角投影のパラメータ (2.5D奥行き表現用)
# Z軸（奥行き）を斜め右奥 (X += 0.5, Y -= 0.3) に射影する
Z_DEPTH = 10.0
PROJ_X = 0.5
PROJ_Y = -0.3

# 光源の位置ベクトル (右上遠方)
LIGHT_DIR = np.array([-0.5, 0.86])

# パーティクル管理用リスト
particles = []

# 音高名から割り当てるポップで鮮やかな鍵盤のベースカラー (BGR)
NOTE_COLORS = {
    'C4': (60, 60, 240),     # 赤
    'D4': (40, 120, 240),    # オレンジ
    'E4': (40, 220, 240),    # 黄
    'F4': (80, 220, 100),    # 黄緑
    'G4': (100, 200, 40),    # 緑
    'A4': (240, 150, 40),    # 青
    'B4': (200, 50, 160),    # 紫
    'C5': (40, 40, 190)      # 深い赤
}

def add_hit_particles(pos, color, count=25):
    """
    衝突時に放出される火花パーティクル。
    明るい背景で映えるよう、鮮やかで半透明な火花を生成。
    """
    for _ in range(count):
        angle = random.uniform(0, 2 * np.pi)
        speed = random.uniform(60.0, 240.0)
        vel = [speed * np.cos(angle), speed * np.sin(angle) + 80.0]
        
        particles.append({
            'pos': list(pos),
            'vel': vel,
            'color': color,
            'size': random.uniform(3.0, 6.0),
            'alpha': 1.0,
            'decay': random.uniform(1.8, 3.2),
            'gravity_factor': random.uniform(0.4, 0.8)
        })

def update_and_draw_particles(frame, shadow_mask, to_screen_func, dt):
    """
    パーティクルを物理更新し、シャドウマスクと実描画の両方に反映する。
    """
    global particles
    active_particles = []
    
    # パーティクル自体の光彩用
    glow_mask = np.zeros_like(frame, dtype=np.uint8)
    
    for p in particles:
        p['pos'][0] += p['vel'][0] * dt
        p['pos'][1] += p['vel'][1] * dt
        p['vel'][1] -= 900.0 * p['gravity_factor'] * dt  # 重力
        p['vel'][0] *= 0.95  # 空気抵抗
        p['alpha'] -= p['decay'] * dt
        p['size'] = max(1.0, p['size'] - 1.5 * dt)
        
        if p['alpha'] > 0:
            active_particles.append(p)
            
            scr_pos = to_screen_func(p['pos'])
            px, py = int(scr_pos[0]), int(scr_pos[1])
            
            if 0 <= px < SCREEN_WIDTH and 0 <= py < SCREEN_HEIGHT:
                size = int(p['size'])
                color_bright = tuple(int(c * p['alpha'] + 255 * (1 - p['alpha'])) for c in p['color'])
                
                # シャドウマスクに影を描画
                cv2.circle(shadow_mask, (px, py), size + 2, 255, -1)
                
                # 本体
                cv2.circle(frame, (px, py), size, p['color'], -1, cv2.LINE_AA)
                cv2.circle(frame, (px, py), max(1, size - 2), (255, 255, 255), -1, cv2.LINE_AA)
                
    particles = active_particles

def draw_shadow_ball(shadow_mask, center, radius):
    """
    シャドウマスクにボールの影を描画。
    """
    bx, by = int(center[0]), int(center[1])
    cv2.circle(shadow_mask, (bx, by), int(radius + 1), 255, -1)

def draw_glass_ball(frame, center, radius):
    """
    透過・屈折・強烈な右上ハイライトを重ねた、ポップで美しい「ガラス/アクリル調のシアンブルー球体」を描画。
    """
    bx, by = int(center[0]), int(center[1])
    
    # ボールのベースカラー (鮮やかな明るいシアンブルー)
    ball_color = (245, 210, 60) # BGR: 明るい水色
    
    # 1. 外輪郭の少し暗いエッジ
    cv2.circle(frame, (bx, by), int(radius), (180, 140, 20), 2, cv2.LINE_AA)
    
    # 2. 内側の半透明グラデーション
    ball_mask = np.zeros_like(frame)
    cv2.circle(ball_mask, (bx, by), int(radius), ball_color, -1, cv2.LINE_AA)
    # 立体感を出すために中心を少し明るく、下部に光の反射を入れる
    cv2.circle(ball_mask, (bx + 2, by + 2), int(radius * 0.75), (255, 255, 120), -1, cv2.LINE_AA)
    
    # 半透過ブレンド
    cv2.addWeighted(frame, 1.0, ball_mask, 0.75, 0, dst=frame)
    
    # 3. 屈折ハイライト (左上の強いSpecular)
    cv2.circle(frame, (bx - 4, by - 4), int(radius * 0.35), (255, 255, 255), -1, cv2.LINE_AA)
    cv2.circle(frame, (bx - 5, by - 5), int(radius * 0.15), (255, 255, 255), -1, cv2.LINE_AA)

def get_sink_offset(has_hit, hit_progress, theta):
    """
    鍵盤が衝突した瞬間に、物理的に下に一瞬「沈み込む」クッション効果のオフセットベクトルを計算する。
    """
    if not has_hit or hit_progress <= 0:
        return np.array([0.0, 0.0])
    
    # 衝突直後に急激に沈み込み、その後なめらかに戻るサインカーブ
    # hit_progress は 1.0 (衝突直後) -> 0.0 (消灯)
    # 沈み込み量 (最大 6.0 px)
    sink_amount = 6.0 * np.sin(hit_progress * np.pi)
    
    # 鍵盤の法線下向き方向
    # 法線 n = (nx, ny) は上向き。沈む方向は -n
    # 画面上の座標系（y軸下向き正）に合わせる
    # Pymunkの n_y > 0 は上向き。画面上では「上」へ行くので、沈むのは n_y の逆、すなわち y軸正方向（下向き）
    # 法線ベクトルから画面上の下向きベクトルを算出
    normal_down = np.array([np.sin(theta), -np.cos(theta)])
    if normal_down[1] < 0:
        normal_down = -normal_down
        
    return normal_down * sink_amount

def draw_shadow_3d_keyboard(shadow_mask, key_pos, theta, length, thickness, sink_offset):
    """
    シャドウマスクに立体鍵盤の影をオフセット付きで描画。
    """
    dx = (length / 2.0) * np.cos(theta)
    dy = (length / 2.0) * np.sin(theta)
    
    # 沈み込みを加味した座標
    pos = key_pos + sink_offset
    
    p1_front = np.array([pos[0] - dx, pos[1] - dy])
    p2_front = np.array([pos[0] + dx, pos[1] + dy])
    
    proj_dx = PROJ_X * Z_DEPTH
    proj_dy = PROJ_Y * Z_DEPTH
    p1_back = p1_front + np.array([proj_dx, proj_dy])
    p2_back = p2_front + np.array([proj_dx, proj_dy])
    
    pt1_f = (int(p1_front[0]), int(p1_front[1]))
    pt2_f = (int(p2_front[0]), int(p2_front[1]))
    pt1_b = (int(p1_back[0]), int(p1_back[1]))
    pt2_b = (int(p2_back[0]), int(p2_back[1]))
    
    # 天面の影
    top_poly = np.array([pt1_f, pt2_f, pt2_b, pt1_b], dtype=np.int32)
    cv2.fillPoly(shadow_mask, [top_poly], 255)
    
    # 厚み前面の影
    thickness_vec = np.array([np.sin(theta) * thickness, -np.cos(theta) * thickness])
    pt1_f_bottom = (int(p1_front[0] + thickness_vec[0]), int(p1_front[1] + thickness_vec[1]))
    pt2_f_bottom = (int(p2_front[0] + thickness_vec[0]), int(p2_front[1] + thickness_vec[1]))
    front_poly = np.array([pt1_f, pt2_f, pt2_f_bottom, pt1_f_bottom], dtype=np.int32)
    cv2.fillPoly(shadow_mask, [front_poly], 255)

def draw_3d_keyboard(frame, key_pos, theta, length, thickness, has_hit, hit_progress, note_name, sink_offset):
    """
    明るいグレーの背景に美しく映える、角丸ポップカラープレートの立体鍵盤を描画。
    ネジピン（黒2本）およびインダストリアルな背面金属支柱構造を描画する。
    """
    # 沈み込みオフセットを適用
    pos = key_pos + sink_offset
    
    # 音名に応じたポップカラーの取得
    base_color = NOTE_COLORS.get(note_name, (100, 100, 100))
    if has_hit:
        # ヒット時は光を浴びて少し明るく白熱化する
        color = tuple(int(c * 0.7 + 255 * 0.3 * hit_progress) for c in base_color)
    else:
        color = base_color
        
    dx = (length / 2.0) * np.cos(theta)
    dy = (length / 2.0) * np.sin(theta)
    
    p1_front = np.array([pos[0] - dx, pos[1] - dy])
    p2_front = np.array([pos[0] + dx, pos[1] + dy])
    
    # 2.5D 後面射影座標
    proj_dx = PROJ_X * Z_DEPTH
    proj_dy = PROJ_Y * Z_DEPTH
    p1_back = p1_front + np.array([proj_dx, proj_dy])
    p2_back = p2_front + np.array([proj_dx, proj_dy])
    
    pt1_f = (int(p1_front[0]), int(p1_front[1]))
    pt2_f = (int(p2_front[0]), int(p2_front[1]))
    pt1_b = (int(p1_back[0]), int(p1_back[1]))
    pt2_b = (int(p2_back[0]), int(p2_back[1]))
    
    # --- 金属製の黒い背面支柱ピンの描画 (インダストリアル構造表現) ---
    # 鍵盤を地面や壁から固定する金属支柱パイプ
    支柱カラー = (45, 45, 45) # 鉄黒
    # 鍵盤の真下方向
    thickness_vec = np.array([np.sin(theta) * thickness, -np.cos(theta) * thickness])
    
    # 天面と前面ポリゴンの描画
    top_poly = np.array([pt1_f, pt2_f, pt2_b, pt1_b], dtype=np.int32)
    
    # 鍵盤の傾きに基づき、上面の明暗を設定 (右上光源)
    face_normal = np.array([-np.sin(theta), np.cos(theta)])
    light_intensity = max(0.4, np.dot(face_normal, LIGHT_DIR))
    
    # 明るい天面
    top_color = tuple(int(c * (0.8 + 0.2 * light_intensity)) for c in color)
    # 少し影になる前面
    front_normal = np.array([np.cos(theta), np.sin(theta)])
    front_intensity = max(0.2, np.dot(front_normal, LIGHT_DIR))
    front_color = tuple(int(c * (0.55 + 0.3 * front_intensity)) for c in color)
    # 最も影になる右側面
    side_color = tuple(int(c * 0.45) for c in color)
    
    # 1. 支柱の描画 (鍵盤の裏側)
    pin_center = (int((pt1_f[0] + pt2_f[0]) / 2), int((pt1_f[1] + pt2_f[1]) / 2))
    pin_bottom = (pin_center[0] - 12, pin_center[1] + 32)
    cv2.line(frame, pin_center, pin_bottom, 支柱カラー, 6, cv2.LINE_AA)
    
    # 2. 立体プレート描画
    # A. 天面 (丸みを出すため、太線によるカプセル描画を応用)
    # OpenCVのアンチエイリアス太線で描くことで、完璧に滑らかな角丸プレートを再現
    cv2.fillPoly(frame, [top_poly], top_color)
    
    # B. 前面 (厚み)
    pt1_f_bottom = (int(p1_front[0] + thickness_vec[0]), int(p1_front[1] + thickness_vec[1]))
    pt2_f_bottom = (int(p2_front[0] + thickness_vec[0]), int(p2_front[1] + thickness_vec[1]))
    front_poly = np.array([pt1_f, pt2_f, pt2_f_bottom, pt1_f_bottom], dtype=np.int32)
    cv2.fillPoly(frame, [front_poly], front_color)
    
    # C. 右端面 (奥行きと厚み)
    pt2_b_bottom = (int(p2_back[0] + thickness_vec[0]), int(p2_back[1] + thickness_vec[1]))
    side_poly = np.array([pt2_f, pt2_b, pt2_b_bottom, pt2_f_bottom], dtype=np.int32)
    cv2.fillPoly(frame, [side_poly], side_color)
    
    # 輪郭に上品なエッジを立てる
    cv2.polylines(frame, [top_poly], True, (255, 255, 255), 1, cv2.LINE_AA)
    
    # 3. 2本のネジピン (黒い丸ネジ)
    # 鍵盤プレートの左右に対称にボルトネジを描く
    bolt_offset_x = dx * 0.7
    bolt_offset_y = dy * 0.7
    bolt1_pos = (int(pos[0] - bolt_offset_x), int(pos[1] - bolt_offset_y))
    bolt2_pos = (int(pos[0] + bolt_offset_x), int(pos[1] + bolt_offset_y))
    
    # ネジの金属感
    cv2.circle(frame, bolt1_pos, 4, (35, 35, 35), -1, cv2.LINE_AA)
    cv2.circle(frame, bolt2_pos, 4, (35, 35, 35), -1, cv2.LINE_AA)
    cv2.circle(frame, bolt1_pos, 2, (100, 100, 100), -1, cv2.LINE_AA)
    cv2.circle(frame, bolt2_pos, 2, (100, 100, 100), -1, cv2.LINE_AA)
    
    # 音名テキストのレンダリング (上品なダークグレー)
    text_pos = (int((pt1_f[0] + pt2_f[0])/2 - 10), int((pt1_f[1] + pt2_f[1])/2 - 15))
    cv2.putText(frame, note_name, text_pos, cv2.FONT_HERSHEY_SIMPLEX, 0.4, (45, 45, 45), 1, cv2.LINE_AA)

def draw_shadow_rails(shadow_mask, plan, to_screen_func):
    """
    シャドウマスクに2本並行レールの影を描画。
    """
    for item in plan:
        points = item['rail_points']
        if len(points) > 1:
            scr_points = [to_screen_func(p) for p in points]
            pts = np.array(scr_points, dtype=np.int32)
            
            # 手前側と奥側の2本のレール
            offset_dist = 5.0
            pts_l = pts - np.array([int(offset_dist * np.sin(item['theta'])), int(-offset_dist * np.cos(item['theta']))])
            pts_r = pts + np.array([int(offset_dist * np.sin(item['theta'])), int(-offset_dist * np.cos(item['theta']))])
            
            cv2.polylines(shadow_mask, [pts_l], False, 255, 6)
            cv2.polylines(shadow_mask, [pts_r], False, 255, 6)

def draw_real_rails(frame, plan, to_screen_func):
    """
    インダストリアル感を高める、2本並行する黒い鉄製レールを描画する。
    """
    for item in plan:
        points = item['rail_points']
        if len(points) > 1:
            scr_points = [to_screen_func(p) for p in points]
            pts = np.array(scr_points, dtype=np.int32)
            
            # 鍵盤の傾き方向と直交する方向に、4pxずつ左右にずらして2本の並行レールを作成
            theta = item['theta']
            offset_x = int(4.5 * np.sin(theta))
            offset_y = int(-4.5 * np.cos(theta))
            
            pts_l = pts + np.array([offset_x, offset_y])
            pts_r = pts - np.array([offset_x, offset_y])
            
            # 鉄黒パイプの描画 (太さ3px)
            rail_color = (30, 30, 30)
            cv2.polylines(frame, [pts_l], False, rail_color, 3, cv2.LINE_AA)
            cv2.polylines(frame, [pts_r], False, rail_color, 3, cv2.LINE_AA)
            
            # ハイライトラインを薄く入れて金属パイプの丸みをシミュレート
            cv2.polylines(frame, [pts_l], False, (80, 80, 80), 1, cv2.LINE_AA)
            cv2.polylines(frame, [pts_r], False, (80, 80, 80), 1, cv2.LINE_AA)

def render_video(plan, ball_positions, collision_events, duration, start_info, output_path):
    """
    明るいミニマル・インダストリアルスタイルと、右上から大きく伸びるリアルで超ソフトな影
    を実装したハイエンド・レンダリングエンジン。
    """
    frames_count = len(ball_positions)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, FPS, (SCREEN_WIDTH, SCREEN_HEIGHT))
    
    _, y_start, _ = start_info
    event_by_idx = {e['index']: e for e in collision_events}
    
    camera_y = y_start
    dt = 1.0 / FPS
    
    global particles
    particles = []
    particle_triggered = [False] * len(plan)
    
    # リアル影(シャドウ)の投影オフセットパラメータ (右上から左下へ大きく流れるソフトな影)
    SOX = -32  # Shadow Offset X
    SOY = 48   # Shadow Offset Y
    
    for f in range(frames_count):
        t_sec = f * dt
        
        # 1. 衝突時の衝撃明滅フラッシュ
        flash_intensity = 0.0
        active_color = (255, 255, 255)
        
        for e in collision_events:
            time_since_hit = t_sec - e['time']
            if 0.0 <= time_since_hit < 0.2:
                # 衝突時に背景を一瞬「フワッ」と明るくする衝撃演出
                flash_intensity = max(flash_intensity, (1.0 - time_since_hit / 0.2) * 0.08)
                active_color = NOTE_COLORS.get(e['note'], (255, 255, 255))
                
                # パーティクルの追加
                idx = e['index']
                if not particle_triggered[idx]:
                    add_hit_particles(e['pos'], active_color, count=25)
                    particle_triggered[idx] = True
                    
        # --- 背景グラデーション (明るいミニマルなグレーブルー) ---
        # 右上は明るく、左下は少し深みのあるスタイリッシュなグレーホワイト
        bg_color_top = (236, 238, 240)    # BGR
        bg_color_bottom = (206, 210, 215) # BGR
        
        frame = np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH, 3), dtype=np.uint8)
        for y in range(SCREEN_HEIGHT):
            alpha = y / SCREEN_HEIGHT
            frame[y, :] = [
                int(bg_color_top[0] * (1 - alpha) + bg_color_bottom[0] * alpha),
                int(bg_color_top[1] * (1 - alpha) + bg_color_bottom[1] * alpha),
                int(bg_color_top[2] * (1 - alpha) + bg_color_bottom[2] * alpha)
            ]
            
        # 衝撃フラッシュのブレンド
        if flash_intensity > 0:
            flash_layer = np.zeros_like(frame)
            flash_layer[:] = active_color
            cv2.addWeighted(frame, 1.0, flash_layer, flash_intensity, 0, dst=frame)
            
        # ボール追従カメラトラッキング
        bx, by = ball_positions[f]
        camera_y = camera_y * 0.9 + by * 0.1
        
        # 射影座標変換
        def to_screen(pos):
            sx = int(pos[0] + SCREEN_WIDTH / 2)
            sy = int(SCREEN_HEIGHT / 2 - (pos[1] - camera_y))
            return (sx, sy)
            
        # 2D影用座標変換 (影のオフセットSOX, SOYを適用)
        def to_screen_shadow(pos):
            sx = int(pos[0] + SCREEN_WIDTH / 2 + SOX)
            sy = int(SCREEN_HEIGHT / 2 - (pos[1] - camera_y) + SOY)
            return (sx, sy)

        # ==========================================
        # 2. シャドウバッファ (リアルな柔らかい影) の生成と描画
        # ==========================================
        shadow_mask = np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH), dtype=np.uint8)
        
        # 2-A. レールの影
        draw_shadow_rails(shadow_mask, plan, to_screen_shadow)
        
        # 2-B. 立体鍵盤の影
        for item in plan:
            idx = item['index']
            pos = item['key_pos']
            theta = item['theta']
            
            has_hit = False
            hit_progress = 0.0
            if idx in event_by_idx:
                time_since_hit = t_sec - event_by_idx[idx]['time']
                if 0.0 <= time_since_hit < 0.4:
                    has_hit = True
                    hit_progress = 1.0 - (time_since_hit / 0.4)
            
            # 沈み込みクッション効果
            sink_offset = get_sink_offset(has_hit, hit_progress, theta)
            key_scr_shadow = to_screen_shadow(pos)
            
            draw_shadow_3d_keyboard(shadow_mask, key_scr_shadow, theta, KEYBOARD_LENGTH, KEYBOARD_THICKNESS, sink_offset)
            
            # 支柱の影
            pin_center = (int(key_scr_shadow[0] + sink_offset[0]), int(key_scr_shadow[1] + sink_offset[1]))
            pin_bottom = (pin_center[0] - 12, pin_center[1] + 32)
            cv2.line(shadow_mask, pin_center, pin_bottom, 255, 6)
            
        # 2-C. パーティクルの影
        update_and_draw_particles(frame, shadow_mask, to_screen, dt)
        
        # 2-D. ボールの影
        ball_scr_shadow = to_screen_shadow((bx, by))
        draw_shadow_ball(shadow_mask, ball_scr_shadow, BALL_RADIUS)
        
        # --- シャドウのブラー処理と背景へのソフトブレンド ---
        # 非常に大きなガウシアンブラーをかけて影を極限まで柔らかくボケさせる
        shadow_blur = cv2.GaussianBlur(shadow_mask, (65, 65), 18)
        
        # 背景画像に対して、ぼかした影の部分をソフトに減算（暗化）ブレンドする
        # 影の濃さ (最大28%輝度を下げる)
        shadow_factor = 1.0 - (shadow_blur / 255.0) * 0.28
        for c in range(3):
            frame[:, :, c] = (frame[:, :, c] * shadow_factor).astype(np.uint8)

        # ==========================================
        # 3. オブジェクト実体のカラー描画 (影の上から重ねる)
        # ==========================================
        # 3-A. 2本並行する黒い鉄製レール
        draw_real_rails(frame, plan, to_screen)
        
        # 3-B. 立体鍵盤 (丸みを帯びたポッププレート + 金属支柱)
        for item in plan:
            idx = item['index']
            pos = item['key_pos']
            theta = item['theta']
            
            has_hit = False
            hit_progress = 0.0
            if idx in event_by_idx:
                time_since_hit = t_sec - event_by_idx[idx]['time']
                if 0.0 <= time_since_hit < 0.4:
                    has_hit = True
                    hit_progress = 1.0 - (time_since_hit / 0.4)
            
            sink_offset = get_sink_offset(has_hit, hit_progress, theta)
            key_scr = to_screen(pos)
            
            draw_3d_keyboard(
                frame, key_scr, theta, KEYBOARD_LENGTH, KEYBOARD_THICKNESS,
                has_hit, hit_progress, item['note'], sink_offset
            )
            
        # 3-C. シアンブルーのガラス球
        ball_scr = to_screen((bx, by))
        draw_glass_ball(frame, ball_scr, BALL_RADIUS)
        
        out.write(frame)
        
    out.release()
