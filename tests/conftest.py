# conftest.py — 共享 fixtures 和 BDD 配置
import os
import sys

# 项目根目录加入 path，使 examples/ 可导入
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
