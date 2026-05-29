# 🚀 Next-Gen Music Marble Machine (v2)
### *Intelligent Audio Analyzer & Beautiful 2.5D Physics Simulation Video Generator*

[English](#english) | [日本語](#日本語)

---

## 日本語

音声ファイル（WAV/MP3/M4Aなど）からメロディをAI自動解析し、美しい2.5D立体グラフィックスと極めて精密な物理演算を組み合わせて、魅惑的な「音を奏でるマーブルマシン」のシミュレーション動画を自動生成するPythonシステムです。

### 🌟 特長

- **🎧 インテリジェント・メロディ解析**: `librosa` の高精度ピッチ検出（pYINアルゴリズム）を用いて、音声から主要な音高と打鍵タイミングを自動抽出。
- **📐 数学的予見物理演算 (誤差 0.00px)**: Pymunk 7.2.0 の衝突コールバック内でボールの位置と速度を理論値へ精密に補正。どれだけ長いメロディでも、寸分狂わず鍵盤にバウンドし続けます。
- **🛤️ ネオン・ガイドレール**: ボールの放物線落下軌道に沿って、物理挙動を乱さない「視覚的装飾としての曲線レール（ベジェ状点群）」を数学的に自動生成。
- **🎨 高品位2.5D擬似3Dグラフィックス**:
  - **立体鍵盤**: 簡易ランバート反射モデル（光源計算）を適用した等角投影法ポリゴンにより、奥行きと陰影のある3D鍵盤を描画。
  - **ガラスのボール**: 背面シャドウ、半透明同心円グラデーション、鋭いハイライトで透過屈折するガラスの質感を表現。
  - **火花パーティクル**: 衝突の瞬間に、重力や寿命、減衰、Glow効果を持った輝くパーティクルが爆発。
  - **衝撃フラッシュ背景**: 衝突と連動して背景が一瞬白熱明滅するダイナミックなビジュアル演出。
- **🔊 ステレオ・ディレイ音響空間**:
  - 複数音色切り替え（電子シンセ、木製マリンバ、金属オルゴール）。
  - 左右チャンネルのディレイ時間をわずかにずらしたステレオ・フィードバックディレイをNumPyで直接合成し、大聖堂のような広がりを表現。
- **🐳 簡単Dockerポータビリティ**: ローカル環境を汚さず、`docker-compose`だけで完結。

---

## English

A highly advanced Python system that intelligently analyzes melody from any audio file (WAV/MP3/M4A) and generates a stunning 2.5D physics-simulated "Music Marble Machine" video with premium graphics and perfectly synchronized spatial acoustics.

### 🌟 Key Features

- **🎧 Intelligent Audio Analyzer**: Automatically detects pitch and note timing using the high-precision pYIN algorithm (`librosa`).
- **📐 Fully Predictive Core Physics (0.00px Error)**: Integrates mathematical inverse calculations with Pymunk 7.2.0. Resolves numerical integration steps inside `on_collision` to lock coordinates, ensuring 100% bounce precision over long compositions.
- **🛤️ Neon Guide Rails**: Mathematically computes bezier-like curve offsets along the parabolic path. Serves as a fluid visual guide without interfering with raw ball physics.
- **🎨 Modern 2.5D Pseudo-3D Visuals**:
  - **3D-Shaded Keyboards**: Renders isometric polygons with directional shading (Lambertian reflectance) for incredible tactile depth.
  - **Glass Marbles**: Simulates light refraction with smooth concentric gradients, drop shadows, and sharp specular highlights.
  - **Dynamic Particles**: Spawns glowing physics sparks with gravity, decay, and neon Glow filters upon impact.
  - **Impact Flashing**: Pulses the background color with brightness spikes synchronized to melody impacts.
- **🔊 Spatial Stereo Delay**:
  - Switchable instruments: Electronic Synth, Wooden Marimba, and Metal Music Box.
  - Mixes custom stereo feedback delay directly in NumPy, slightly offset in time between L/R channels for a cathedral-like auditory landscape.
- **🐳 Zero-Install Docker Support**: Run everything in an isolated sandbox with single-command `docker-compose`.

---

## 🚀 クイックスタート / Quick Start

### 1. ローカル環境での実行 / Run Locally

**依存ライブラリのインストール / Install Dependencies**:
```bash
pip3 install -r requirements.txt
```

**テストメロディで動作確認 / Run Verification Test**:
```bash
python3 main.py --test
```

**ご自身の音声ファイルを解析して動画を生成 / Generate from your Audio File**:
```bash
# マリンバ音色でディレイ付きの動画を生成 / Generate with Marimba tone & spatial delay
python3 main.py --input your_song.mp3 --instrument marimba --output output_v2.mp4
```

---

### 2. Dockerでの実行 / Run with Docker (Zero Installation)

ホスト側の音声ファイルをコンテナに渡し、動画を直接取り出せます。
Docker makes it incredibly easy without installing FFmpeg or system-level GUI packages locally.

**テスト動画の作成 / Build & Generate Test Video**:
```bash
docker-compose up --build
```

**ご自身の曲を解析させる場合 / Custom Audio Generation via Docker**:
```bash
# 'shared' ディレクトリに音源を配置し実行します / Place your audio inside directory and run:
docker-compose run generator --input /app/shared/your_song.wav --output /app/shared/my_marble_machine.mp4 --instrument musicbox
```

---

## 📐 数学的アルゴリズム / Mathematical Overview

### 1. 衝突直後の必要速度 / Required Post-Collision Velocity
ボールの落下（Pymunk 座標系： $y$ 軸上向き正）は、重力 $g$ において以下の方程式に従います。
The trajectory of the ball is constrained by gravity $g$:

$$v_{x,out} = \frac{\Delta x}{\Delta t}$$
$$v_{y,out} = \frac{\Delta y + \frac{1}{2} g \Delta t^2}{\Delta t}$$

### 2. 鏡面反射による鍵盤の傾き決定 / Angle Determination by Specular Reflection
衝突前後の速度変化 $\Delta \vec{V} = \vec{V}_{out} - \vec{V}_{in}$ より、滑らかな衝突における法線 $\vec{n}$ および鍵盤の傾き $\theta$ が一意に定まります。
For friction-free elastic bounce, the keyboard surface normal $\vec{n}$ must be parallel to the velocity delta $\Delta \vec{V}$:

$$\vec{n} = \frac{\Delta \vec{V}}{\|\Delta \vec{V}\|}$$
$$\theta = \operatorname{atan2}(n_y, n_x) - \frac{\pi}{2}$$

---

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
