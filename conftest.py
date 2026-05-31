"""pytest 配置:确保项目根目录在 sys.path,使 `import qqfetch` 在未安装时也可用。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
