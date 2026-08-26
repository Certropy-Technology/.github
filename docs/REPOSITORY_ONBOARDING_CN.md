# Certropy 仓库静态审查接入方案

## 1. 目标与范围

本方案用于让 `Certropy-Technology` 组织成员将各自维护的 Python 仓库接入统一静态审查。接入后，仓库在以下事件发生时自动运行 CI：

- 创建或更新 Pull Request；
- 代码推送到默认分支 `main`。

统一 CI 由 `Certropy-Technology/.github` 维护，包含：

- Ruff：基础错误、无效导入和代码格式；
- mypy：Python 类型检查；
- pytest：自动化测试；
- pip-audit：Python 依赖漏洞检查。

业务仓库只保存调用入口和项目路径配置，不复制审查脚本，也不能通过配置注入任意 Shell 命令。

## 2. 当前能力边界

- Public 和 Private 仓库都能自动运行 CI。
- GitHub Free 组织只能为 Public 仓库免费启用完整 Branch protection。
- Private 仓库的失败检查会在 PR 中明确报红，但 GitHub Free 无法强制禁止有合并权限的用户继续合并。
- 当前自动扫描器能够生成接入 PR，但无人值守运行仍依赖 `.github` 仓库配置 `ORG_BOOTSTRAP_TOKEN`。
- 在自动扫描凭据配置完成前，由各仓库维护者按本文手动接入。

## 3. 接入职责

共享 Workflow 维护者负责：

- 维护 `.github/.github/workflows/python-static-review.yml`；
- 维护安全的配置解析和固定安装 profile；
- 先在 `test-workflow` 和代表性 Harbor 仓库验证共享变更；
- 避免共享变更一次性破坏所有已接入仓库。

业务仓库维护者负责：

- 提供可安装的 Python 项目和有效测试；
- 添加调用文件与仓库配置；
- 修复本仓库 PR 中发现的问题；
- 对暂时豁免的历史格式或类型债务建立后续修复事项。

## 4. 所有仓库必须添加的文件

### 4.1 Workflow 调用入口

创建 `.github/workflows/static-review.yml`：

```yaml
name: Python static review

on:
  pull_request:
  push:
    branches:
      - main

permissions:
  contents: read

jobs:
  static-review:
    uses: Certropy-Technology/.github/.github/workflows/python-static-review.yml@main
    with:
      config-path: .github/static-review.json
      python-version: "3.12"
```

如果默认分支不是 `main`，将 `push.branches` 改成实际默认分支，例如 `master`。

### 4.2 仓库审查配置

标准 `src/` 布局的新仓库可创建 `.github/static-review.json`：

```json
{
  "schema_version": 1,
  "project_root": ".",
  "install_profile": "editable",
  "ruff_config": "pyproject.toml",
  "ruff_paths": [
    "src",
    "tests"
  ],
  "ruff_format": true,
  "mypy_paths": [
    "src"
  ],
  "pytest_paths": [
    "tests"
  ],
  "audit_requirements": [
    "requirements.txt"
  ]
}
```

不存在 `requirements.txt` 时，将 `audit_requirements` 设置为空数组。配置中的所有路径必须真实存在、相对仓库根目录，并且不能包含 `..`。

支持的 `install_profile`：

| Profile | 用途 |
| --- | --- |
| `none` | 只有独立脚本，没有可安装 Python 包 |
| `editable` | 执行 `pip install -e <project_root>` |
| `harbor-020` | 安装 Harbor 0.20 兼容依赖后，再执行 editable 安装 |

## 5. 存量仓库接入流程

存量仓库通常存在历史格式或类型债务，应先建立可持续基线，不在接入 PR 中进行大规模无关重构。

### 5.1 盘点项目结构

接入前确认：

- Python 包根目录和 `pyproject.toml` 位置；
- Ruff 应覆盖的源码、测试和脚本目录；
- mypy 当前能够稳定检查的模块；
- pytest 测试目录；
- 需要进行漏洞审计的 requirements 文件；
- Python 3.12 是否兼容。

### 5.2 创建接入分支

```bash
git switch -c chore/enable-static-review
```

添加第 4 节的两个文件，然后提交 PR。不要直接在默认分支调试 CI。

### 5.3 建立增量基线

推荐处理顺序：

1. 保持 Ruff 覆盖所有业务源码和测试目录，修复 `F401`、`F841`、`E702` 等明确错误。
2. 如果 Ruff format 会一次修改大量历史文件，可暂时设置 `"ruff_format": false`，另开纯格式化 PR。
3. 如果全包 mypy 存在大量历史问题，先选择稳定核心模块作为 `mypy_paths`，记录未覆盖文件并逐步扩大范围。
4. pytest 必须执行真实测试目录，不能用空测试或永远成功的脚本代替。
5. pip-audit 应覆盖项目实际安装使用的 requirements 文件。

增量配置示例：

```json
{
  "schema_version": 1,
  "project_root": "harbor-secure-runner",
  "install_profile": "editable",
  "ruff_config": "harbor-secure-runner/pyproject.toml",
  "ruff_paths": [
    "harbor-secure-runner/src",
    "harbor-secure-runner/tests",
    "harbor_runtime",
    "harbor-conformance",
    "benchmarks"
  ],
  "ruff_format": false,
  "mypy_paths": [
    "harbor-secure-runner/src/harbor_secure/provider.py",
    "harbor-secure-runner/src/harbor_secure/profiles.py"
  ],
  "pytest_paths": [
    "harbor-secure-runner/tests"
  ],
  "audit_requirements": []
}
```

### 5.4 合并条件

接入 PR 满足以下条件后才能合并：

- GitHub Actions 中出现 `static-review / Ruff, mypy, pytest, pip-audit`；
- 检查结论为绿色 `Success`；
- 配置覆盖真实源码和测试，而非为了变绿排除主要业务目录；
- 临时关闭格式检查或缩小 mypy 路径时，PR 描述中记录原因和后续计划。

## 6. 新建仓库接入流程

新仓库不应继承历史债务，建议从第一次提交就采用严格基线。

推荐目录：

```text
repository/
├── .github/
│   ├── static-review.json
│   └── workflows/
│       └── static-review.yml
├── src/
│   └── package_name/
├── tests/
├── pyproject.toml
├── requirements.txt
└── README.md
```

新仓库操作顺序：

1. 创建 `pyproject.toml`、源码目录和至少一个真实测试。
2. 在初始提交中加入 Workflow 调用入口和严格配置。
3. 保持 `ruff_format: true`，mypy 覆盖完整 `src`。
4. 创建第一个功能 PR，确认四项检查均被触发。
5. Public 仓库可由管理员将该检查设置为 required status check。

不要先积累大量代码再接入 CI，否则新仓库会迅速变成存量治理问题。

## 7. PR 失败时如何处理

在 PR 的 `Checks` 或 `Actions` 页面打开：

```text
static-review / Ruff, mypy, pytest, pip-audit
```

根据最后执行的命令判断失败阶段：

| 日志命令 | 处理方向 |
| --- | --- |
| `ruff check` | 修复未使用导入、未定义名称、语法和基础样式错误 |
| `ruff format --check` | 执行 Ruff format，或为存量仓库建立格式化基线计划 |
| `mypy` | 修复类型标注和 `None` 分支，或采用有记录的增量路径 |
| `pytest` | 修复功能回归、导入路径或测试依赖 |
| `pip-audit` | 升级、替换或有依据地处理存在漏洞的依赖 |

CI 只负责发现和报告问题，不会自动修改业务代码，也不会自动合并 PR。

## 8. 权限和安全要求

- 业务仓库不需要保存模型 API Key 或审查系统 Secret。
- PR Workflow 仅申请 `contents: read`。
- 仓库 JSON 只允许固定字段和安全相对路径，不能配置任意安装命令。
- 共享 Workflow 的修改会影响所有使用 `@main` 的仓库，必须先完成代表性回归。
- Private 仓库仅向被授权的组织成员和协作者可见；可见权限不等于 push 权限。

## 9. 自动接入演进

当前 `Certropy-Technology/.github` 已提供 `Bootstrap organization static review`：

- 扫描组织内 Python 仓库；
- 推断项目根目录、Ruff、mypy、pytest 和依赖文件；
- 为未接入仓库创建 `automation/static-review` 分支和接入 PR；
- 将旧的独立 `static-review.yml` 迁移到共享 Workflow。

管理员配置专用 `ORG_BOOTSTRAP_TOKEN` 后，可启用每日扫描和手动指定仓库扫描。在此之前，本文的手动接入流程是正式流程。

## 10. 验收清单

- [ ] `.github/workflows/static-review.yml` 已进入默认分支
- [ ] `.github/static-review.json` 所有路径真实存在
- [ ] PR 事件能够自动触发共享 Workflow
- [ ] 默认分支 push 能够自动触发共享 Workflow
- [ ] Ruff 检查覆盖源码和测试目录
- [ ] mypy 覆盖范围与仓库当前基线一致
- [ ] pytest 执行真实测试
- [ ] pip-audit 覆盖真实依赖文件，或明确声明无 requirements 文件
- [ ] CI 检查为绿色
- [ ] Public 仓库按需配置 Branch protection
- [ ] 存量豁免项已记录后续治理计划
