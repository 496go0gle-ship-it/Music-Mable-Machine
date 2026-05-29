import os
import numpy as np
import librosa

# 平均律の音高周波数テーブル
NOTES_FREQ = {
    'C4': 261.63, 'D4': 293.66, 'E4': 329.63, 'F4': 349.23,
    'G4': 392.00, 'A4': 440.00, 'B4': 493.88, 'C5': 523.25,
    'D5': 587.33, 'E5': 659.25, 'F5': 698.46, 'G5': 783.99,
    'A5': 880.00, 'B5': 987.77, 'C6': 1046.50
}

# 最小限のフォールバックメロディ (きらきら星の前半)
DEFAULT_MELODY = [
    ('C4', 0.0), ('C4', 0.8), ('G4', 1.6), ('G4', 2.4),
    ('A4', 3.2), ('A4', 4.0), ('G4', 4.8),
    ('F4', 6.4), ('F4', 7.2), ('E4', 8.0), ('E4', 8.8),
    ('D4', 9.6), ('D4', 10.4), ('C4', 11.2)
]

def hz_to_note_name(hz):
    """
    周波数(Hz)から最も近い定義済み音名を返す。
    """
    if hz is None or np.isnan(hz) or hz < 100.0:
        return 'C4'
    
    best_note = 'C4'
    min_diff = float('inf')
    
    for note, freq in NOTES_FREQ.items():
        diff = abs(freq - hz)
        if diff < min_diff:
            min_diff = diff
            best_note = note
            
    return best_note

def analyze_audio(audio_path=None):
    """
    音声ファイルからピッチと打鍵タイミングを解析・抽出する。
    ファイルが指定されない、または解析に失敗した場合は、デフォルトのきらきら星を返す。
    """
    print("\n" + "=" * 65)
    print("📢  [法的遵守および著作権に関する重要なお知らせ]")
    print("  メロディ自動解析エンジンをご使用になる際は、ご自身が著作権を所有している")
    print("  音源、またはパブリックドメイン（著作権フリー）の音源のみをご使用ください。")
    print("  著作権で保護された音源の無許可での解析・二次利用は法律で制限されています。")
    print("=" * 65 + "\n")

    if audio_path is None or not os.path.exists(audio_path):
        if audio_path is not None:
            print(f"⚠️ 指定されたファイルが見つかりません: '{audio_path}'")
        print("💡 デフォルトのテストメロディ（きらきら星）をロードします。")
        return DEFAULT_MELODY

    print(f"🔍 音声ファイルを解析中: '{audio_path}'...")
    
    try:
        # 音声のロード (サンプリングレート 22050Hz モノラル)
        y, sr = librosa.load(audio_path, sr=22050)
        
        # pYINアルゴリズムによる高精度なピッチ検出
        # 対象音域: C3 (約130Hz) から C6 (約1047Hz)
        fmin = librosa.note_to_hz('C3')
        fmax = librosa.note_to_hz('C6')
        
        f0, voiced_flag, voiced_probs = librosa.pyin(
            y, fmin=fmin, fmax=fmax, sr=sr,
            frame_length=2048, hop_length=512
        )
        
        # フレームごとの時間
        times = librosa.times_like(f0, sr=sr, hop_length=512)
        
        # ピッチ検出データから有声（音符がある）区間をセグメント化
        melody_data = []
        in_note = False
        note_start_time = 0.0
        note_pitches = []
        
        # 最低限音符として認識する閾値
        min_note_duration = 0.15  # 秒
        
        for i in range(len(f0)):
            pitch = f0[i]
            is_voiced = voiced_flag[i] and (not np.isnan(pitch))
            
            if is_voiced:
                if not in_note:
                    in_note = True
                    note_start_time = times[i]
                    note_pitches = [pitch]
                else:
                    # ピッチが急激に変化した（全音以上変化した）場合は別の音符とみなす
                    median_pitch = np.median(note_pitches)
                    semitones_diff = abs(12 * np.log2(pitch / median_pitch))
                    if semitones_diff > 1.2:
                        # 現在の音符を保存し、新しい音符を開始
                        duration = times[i] - note_start_time
                        if duration >= min_note_duration:
                            avg_pitch = np.median(note_pitches)
                            note_name = hz_to_note_name(avg_pitch)
                            melody_data.append((note_name, float(note_start_time)))
                        
                        note_start_time = times[i]
                        note_pitches = [pitch]
                    else:
                        note_pitches.append(pitch)
            else:
                if in_note:
                    in_note = False
                    duration = times[i] - note_start_time
                    if duration >= min_note_duration:
                        avg_pitch = np.median(note_pitches)
                        note_name = hz_to_note_name(avg_pitch)
                        # 重複に近い非常に短い間隔の連打をまとめる
                        if len(melody_data) == 0 or (note_start_time - melody_data[-1][1] > 0.1):
                            melody_data.append((note_name, float(note_start_time)))
                            
        # 音符が全く検出されなかった場合、または極端に少ない場合は警告し、フォールバック
        if len(melody_data) < 3:
            print("⚠️ 解析されたノート数が少なすぎます（メロディが検出できませんでした）。")
            print("💡 デフォルトのテストメロディ（きらきら星）に自動フォールバックします。")
            return DEFAULT_MELODY
        
        # 開始時間を0.0秒基準に揃え、適度な間隔（最小間隔0.4秒など）にスケーリング
        raw_starts = [item[1] for item in melody_data]
        min_start = min(raw_starts)
        
        # 音符の間隔を美しくするためのタイミング整形（あまりに細かいズレをクオンタイズ）
        quantized_melody = []
        for i, (note_name, start_time) in enumerate(melody_data):
            relative_start = start_time - min_start
            
            # クオンタイズ処理（約0.2秒単位にクオンタイズして、物理演算でバウンドしやすくする）
            q_start = round(relative_start * 2.5) / 2.5
            
            # 直前の音符とタイミングが被らないようにする
            if i > 0 and q_start <= quantized_melody[-1][1]:
                q_start = quantized_melody[-1][1] + 0.4
                
            quantized_melody.append((note_name, q_start))
            
        print(f"✅ 音声解析成功！ {len(quantized_melody)} 個の音符を抽出しました。")
        return quantized_melody
        
    except Exception as e:
        print(f"❌ 音声解析中にエラーが発生しました: {e}")
        print("💡 デフォルトのテストメロディ（きらきら星）に自動フォールバックします。")
        return DEFAULT_MELODY
