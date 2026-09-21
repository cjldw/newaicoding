"""Runner 测试环境:把 runner 目录加入 sys.path(不依赖 docker SDK 安装)"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
