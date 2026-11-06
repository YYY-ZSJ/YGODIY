"""先于 PyInstaller 的 Qt 运行钩子载入模型，沙盒子进程跳过模型。"""

import sys
from sandbox import WORKER_ARGUMENT


if sys.argv[1:2] != [WORKER_ARGUMENT]:
    from ygo_translator import neural

    neural.preload()
