# -*- coding: utf-8 -*-
import sys
import io

# 强制使用UTF-8编码输出
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import pandas as pd
print("✅ pandas 导入成功!")
print(f"pandas 版本: {pd.__version__}")
print("✅ test1.py 运行正常!") 