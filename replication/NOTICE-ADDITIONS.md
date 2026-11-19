OOOSplat Replication Notes
Copyright 2026 Xinlanmy

本仓库包含的原创内容（tools/、docs/、figures/、results/ 中的图表与文字）
以 Apache License 2.0 授权，全文见 LICENSE。

------------------------------------------------------------------
一、运行时依赖的第三方项目
------------------------------------------------------------------

本仓库**不包含**下列项目的源代码或二进制文件。它们由 tools/setup.sh
从各自的官方渠道获取，使用时须遵守各自的许可条款。

1. OOOSplat
   Copyright ooolabdev
   License: Apache-2.0
   https://github.com/ooolabdev/ooosplat
   版本: v0.8.1

   本仓库的 tools/run-dev.sh 通过调用 OOOSplat 自身的
   scripts/local-tauri.mjs 导出启动配置，未复制其源码。

2. OOOBrush
   Copyright ooolabdev
   License: Apache-2.0
   https://github.com/ooolabdev/OOOBrush
   版本: ooo-v1.0.0

3. Brush
   Copyright Arthur Brussee
   License: Apache-2.0
   https://github.com/ArthurBrussee/brush
   OOOBrush 为其维护分支。

4. COLMAP
   Copyright Johannes L. Schönberger and the COLMAP contributors
   License: BSD-3-Clause
   https://github.com/colmap/colmap
   版本: 4.2.1

5. FFmpeg / FFprobe
   Copyright the FFmpeg developers
   License: LGPL-2.1-or-later（本项目使用的 macOS 构建）
   https://ffmpeg.org
   版本: 8.1.2

   注意：FFmpeg 的 LGPL 许可要求，再分发二进制时须同时提供
   许可证全文与获取对应源码的方式。本仓库因此不包含 FFmpeg 二进制。

6. PlayCanvas Engine
   Copyright PlayCanvas Ltd.
   License: MIT
   https://github.com/playcanvas/engine
   OOOSplat 的前端预览使用该引擎；本仓库未直接引用。

------------------------------------------------------------------
二、算法来源（学术引用，非代码许可）
------------------------------------------------------------------

3D Gaussian Splatting:

  Bernhard Kerbl, Georgios Kopanas, Thomas Leimkühler, George Drettakis.
  "3D Gaussian Splatting for Real-Time Radiance Field Rendering."
  ACM Transactions on Graphics 42(4), SIGGRAPH 2023.
  DOI: 10.1145/3592433
  arXiv: https://arxiv.org/abs/2308.04079
  项目页: https://repo-sam.inria.fr/fungraph/3d-gaussian-splatting/
  参考实现: https://github.com/graphdeco-inria/gaussian-splatting

NeRF（3DGS 所取代的隐式表示方法）:

  Ben Mildenhall, Pratul P. Srinivasan, Matthew Tancik, Jonathan T. Barron,
  Ravi Ramamoorthi, Ren Ng.
  "NeRF: Representing Scenes as Neural Radiance Fields for View Synthesis."
  ECCV 2020. arXiv: https://arxiv.org/abs/2003.08934

Splatting 术语来源:

  Lee Westover.
  "Footprint Evaluation for Volume Rendering."
  SIGGRAPH '90. DOI: 10.1145/97880.97906

------------------------------------------------------------------
三、素材声明
------------------------------------------------------------------

results/ 中的示例素材为作者本人拍摄的实体玩具照片与由其重建的模型。
所涉角色形象的著作权归原权利人所有。这些素材仅用于技术演示，
不构成对任何角色形象的使用授权，也不得用于商业用途。
