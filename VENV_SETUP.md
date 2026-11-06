# Python Virtual Environment Setup

本项目使用 `uv` 进行 Python 包管理，替代了原有的 miniconda 环境 (`wisecollectionenv`).

## 虚拟环境信息

- **位置**: `.venv/` (项目根目录)
- **Python 版本**: 3.12.3
- **包管理器**: uv

## 激活虚拟环境

### Bash/Zsh:
```bash
source .venv/bin/activate
```

### Fish:
```bash
source .venv/bin/activate.fish
```

### PowerShell:
```powershell
.venv\bin\Activate.ps1
```

## 安装依赖

使用 uv 安装/更新依赖:

```bash
# 从 requirements.txt 安装
uv pip install -r reddit_pain_finder/requirements.txt

# 安装单个包
uv pip install <package-name>

# 升级包
uv pip install --upgrade <package-name>
```

## 查看已安装的包

```bash
uv pip list
```

## 退出虚拟环境

```bash
deactivate
```

## 与 Miniconda 环境对比

原 conda 环境: `/home/ubuntu/miniconda3/envs/wisecollectionenv` (Python 3.12.12)
新 uv 环境: `.venv/` (Python 3.12.3)

两个环境使用相同的依赖包，新环境使用 uv 进行更快速的包管理。
