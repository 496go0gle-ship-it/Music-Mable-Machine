import numpy as np
import scipy.io.wavfile as wavfile

def generate_tone(freq, instrument, duration, sample_rate=44100):
    """
    指定された楽器(音色)で単一の音高波形を生成し、アタック・減衰エンベロープを適用する。
    """
    note_samples = int(duration * sample_rate)
    t = np.linspace(0, duration, note_samples, endpoint=False)
    
    if instrument == 'marimba':
        # マリンバ風: 基本波が強く、少々の2倍音、急激な減衰
        wave = np.sin(2 * np.pi * freq * t) * 0.7
        wave += np.sin(2 * np.pi * (freq * 2) * t) * 0.1
        # 急激に減衰するエンベロープ
        envelope = np.exp(-6.0 * t)
        
    elif instrument == 'musicbox':
        # オルゴール風: 非常に高い周波数が特徴、金属系の奇数・偶数倍音
        wave = np.sin(2 * np.pi * freq * t) * 0.4
        wave += np.sin(2 * np.pi * (freq * 2) * t) * 0.25
        wave += np.sin(2 * np.pi * (freq * 3) * t) * 0.12
        wave += np.sin(2 * np.pi * (freq * 5) * t) * 0.08
        # 長めの余韻
        envelope = np.exp(-3.2 * t)
        
    else:  # 'synth'
        # FMシンセ/電子音風: 豊かな倍音、暖かみのあるトーン
        wave = np.sin(2 * np.pi * freq * t) * 0.5
        wave += np.sin(2 * np.pi * (freq * 2) * t) * 0.15
        wave += np.sin(2 * np.pi * (freq * 3) * t) * 0.08
        wave += np.sin(2 * np.pi * (freq * 4) * t) * 0.04
        # 適度な減衰
        envelope = np.exp(-4.2 * t)
        
    # クリックノイズ防止のためのアタック処理 (0.006秒のフェードイン)
    attack_len = int(0.006 * sample_rate)
    if attack_len < note_samples:
        envelope[:attack_len] = np.linspace(0, 1, attack_len) * envelope[attack_len]
        
    return wave * envelope

def apply_stereo_delay(audio_mono, delay_l=0.25, delay_r=0.38, feedback=0.38, sample_rate=44100):
    """
    NumPy上で直接ステレオ・フィードバックディレイ（空間系残響エコー）を適用する。
    左右のディレイ時間をわずかに変えることで、圧倒的な広がりと立体感のあるステレオ音響を作る。
    """
    total_len = len(audio_mono)
    # ステレオ配列 (L, R) を初期化
    audio_stereo = np.zeros((total_len, 2), dtype=np.float32)
    
    # 左右それぞれディレイサンプル数
    s_l = int(delay_l * sample_rate)
    s_r = int(delay_r * sample_rate)
    
    # 元のモノラル音声を左右に薄くパンして割り当てる (L: 55%, R: 45%)
    audio_stereo[:, 0] = audio_mono * 0.55
    audio_stereo[:, 1] = audio_mono * 0.45
    
    # 左チャンネルのディレイ処理 (フィードバックループ)
    for i in range(s_l, total_len):
        audio_stereo[i, 0] += audio_stereo[i - s_l, 0] * feedback
        
    # 右チャンネルのディレイ処理 (フィードバックループ)
    for i in range(s_r, total_len):
        audio_stereo[i, 1] += audio_stereo[i - s_r, 1] * feedback
        
    return audio_stereo

def synthesize_audio(collision_events, duration, output_path, instrument='synth', enable_delay=True):
    """
    衝突イベントからオーディオ波形を合成し、ステレオディレイ加工を施して高音質WAVとして保存する。
    """
    sample_rate = 44100
    total_samples = int((duration + 2.0) * sample_rate) # 残響が綺麗に切れるように2秒延長
    audio_mono = np.zeros(total_samples, dtype=np.float32)
    
    note_duration = 1.5  # 各音の最大残響時間
    
    for event in collision_events:
        freq = event['freq']
        hit_time = event['time']
        
        # 音色の生成
        tone = generate_tone(freq, instrument, note_duration, sample_rate)
        
        # 加算合成
        start_idx = int(hit_time * sample_rate)
        end_idx = start_idx + len(tone)
        
        if start_idx < total_samples:
            actual_end = min(end_idx, total_samples)
            slice_len = actual_end - start_idx
            audio_mono[start_idx:actual_end] += tone[:slice_len]
            
    # モノラル波形のクリッピング（音割れ）防止ノーマライズ
    max_val = np.max(np.abs(audio_mono))
    if max_val > 0:
        audio_mono = audio_mono / max_val * 0.75
        
    # ステレオディレイ・リバーブ効果の適用
    if enable_delay:
        audio_out = apply_stereo_delay(audio_mono, delay_l=0.25, delay_r=0.38, feedback=0.35, sample_rate=sample_rate)
    else:
        # ディレイ無効時はシンプルなモノラルからステレオ化
        audio_out = np.zeros((total_samples, 2), dtype=np.float32)
        audio_out[:, 0] = audio_mono * 0.5
        audio_out[:, 1] = audio_mono * 0.5
        
    # 最終ステレオノーマライズ
    max_stereo = np.max(np.abs(audio_out))
    if max_stereo > 0:
        audio_out = audio_out / max_stereo * 0.85
        
    # 16-bit PCM WAVに変換して書き出し
    audio_int16 = (audio_out * 32767).astype(np.int16)
    wavfile.write(output_path, sample_rate, audio_int16)
    print(f"🎵 高音質ステレオオーディオ合成完了 ('{instrument}' 音色, ディレイ={'ON' if enable_delay else 'OFF'}): '{output_path}'")
