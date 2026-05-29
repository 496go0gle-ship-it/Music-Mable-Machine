import os
import sys
import argparse
import pymunk
import numpy as np

# coreモジュールのインポート
from core import (
    analyze_audio,
    build_simulation_plan,
    run_simulation,
    render_video,
    synthesize_audio
)
from moviepy import VideoFileClip, AudioFileClip

# テスト用のシンプルなメロディ
TEST_MELODY = [
    ('C4', 0.0), ('E4', 0.8), ('G4', 1.6), ('C5', 2.4)
]

def merge_video_audio(video_path, audio_path, output_path):
    """
    MoviePyを用いて映像と音声を統合する。
    """
    print(f"🎬 映像と音声を結合中: '{output_path}'...")
    try:
        video = VideoFileClip(video_path)
        audio = AudioFileClip(audio_path)
        
        final_video = video.with_audio(audio)
        final_video.write_videofile(
            output_path,
            codec="libx264",
            audio_codec="aac",
            logger=None
        )
        
        video.close()
        audio.close()
        print("🎉 動画の生成が完了しました！")
    except Exception as e:
        print(f"❌ 映像と音声の結合中にエラーが発生しました: {e}")

def main():
    parser = argparse.ArgumentParser(
        description="次世代 Music Marble Machine (v2) - 自動メロディ解析 & 美麗2.5Dシミュレーション生成"
    )
    parser.add_argument('--input', type=str, default=None, help='解析する入力音声ファイル(WAV/MP3/M4Aなど)のパス')
    parser.add_argument('--instrument', type=str, default='synth', choices=['synth', 'marimba', 'musicbox'], help='鍵盤の音色タイプ')
    parser.add_argument('--no-delay', action='store_true', help='ステレオディレイ（残響エフェクト）を無効化する')
    parser.add_argument('--output', type=str, default='output_v2.mp4', help='出力する動画ファイル(MP4)のパス')
    parser.add_argument('--test', action='store_true', help='テスト用メロディによる動作確認モードを実行する')
    args = parser.parse_args()

    print("======================================================================")
    print("🚀  次世代 Music Marble Machine (v2) - 音声自動解析 & 2.5D物理動画生成システム")
    print("======================================================================")

    # 一時ファイルのパス
    temp_video = "temp_render.mp4"
    temp_audio = "temp_synth.wav"

    # 1. 音声解析によるメロディデータの取得
    if args.test:
        print("🧪 [テストモード] 4つの鍵盤からなるテスト用メロディを使用します。")
        melody = TEST_MELODY
    else:
        # 音声ファイルを解析 (ファイルがなければ自動でデフォルトのきらきら星にフォールバック)
        melody = analyze_audio(args.input)

    # 2. 数学的配置計画の算出 (完全予見配置 + レール点群計算)
    print("\n📐 物理配置とガイドレールの数学的計算を開始します...")
    plan, start_info = build_simulation_plan(melody)
    
    # 3. 物理シミュレーションのステップ実行 (Pymunkによる精密衝突補正)
    # 総デュレーションの算出 (最後の音符の1.8秒後まで)
    duration = melody[-1][1] + 3.0
    
    print("⚙️ Pymunk 物理シミュレーションをステップ実行中...")
    ball_positions, collision_events = run_simulation(plan, start_info, duration)
    
    # 衝突誤差の検証ログ出力
    print("\n--- 🎯 物理シミュレーションと数学的予測の同期検証 ---")
    all_success = True
    for e in collision_events:
        plan_item = plan[e['index']]
        t_diff = e['time'] - plan_item['time']
        p_diff = np.linalg.norm(np.array(e['pos']) - plan_item['c_pos'])
        
        # 物理誤差判定
        if abs(t_diff) < 1e-4 and p_diff < 1e-3:
            status = "SUCCESS (完全同期)"
        else:
            status = f"WARNING (ズレ検知: dt={t_diff:.4f}s, dp={p_diff:.2f}px)"
            all_success = False
            
        print(f"  鍵盤 {e['index']:02d} ({e['note']}) | 実際衝突 t = {e['time']:.4f}s | 補正後座標 = ({e['pos'][0]:.2f}, {e['pos'][1]:.2f}) -> {status}")
        
    if all_success:
        print("  => ✅ [SYSTEM] 数値誤差はすべて完全に補正されました。物理挙動の精度は極めて良好です。")

    # 4. 美麗2.5Dグラフィックスによる動画レンダリング (OpenCV)
    print(f"\n🎨 OpenCV 2.5D グラフィックレンダリングを開始します ({len(ball_positions)} フレーム)...")
    render_video(plan, ball_positions, collision_events, duration, start_info, temp_video)

    # 5. エフェクト付きステレオ音声の合成 (SciPy)
    print("\n🔊 ステレオ音響の加算合成と空間処理を実行します...")
    synthesize_audio(
        collision_events, duration, temp_audio,
        instrument=args.instrument, enable_delay=(not args.no_delay)
    )

    # 6. 音声と動画の結合 (MoviePy)
    merge_video_audio(temp_video, temp_audio, args.output)

    # 7. 一時ファイルのクリーンアップ
    print("\n🧹 一時ファイルをクリーンアップしています...")
    if os.path.exists(temp_video):
        os.remove(temp_video)
    if os.path.exists(temp_audio):
        os.remove(temp_audio)

    print(f"✨ 完了！ 成果物: '{args.output}'")
    print("======================================================================")

if __name__ == '__main__':
    main()
