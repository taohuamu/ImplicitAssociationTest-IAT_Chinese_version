# IAT 中文版 · 配置驱动实现

内隐联想测验（Implicit Association Test）的中文可运行版本，基于 PsychoPy。
实验内容（概念词、属性词、指导语）全部写在 `config.yaml` 里，换实验材料不需要改代码。

原仓库的 `IAT.py` / `IAT.psyexp` / 三个 xlsx 文件**保持原样未改动**，作为存档保留。

---

## 一、跟原版的区别

| 项 | 原版 | 本版 |
|---|---|---|
| 运行环境 | Python 2，现代 PsychoPy 打不开 | Python 3.10–3.12，PsychoPy 2021 之后的版本 |
| 改实验材料 | 改 3 个 xlsx，左右位置靠约定 | 改 `config.yaml`，程序启动时校验 |
| 中文显示 | 字体写死 Arial，中文变方框 | 自动选系统中文字体 |
| 试次平衡 | 每个类别必须正好 5 个例子 | 任意数量，自动平衡 |
| 配对顺序 | 靠被试编号奇偶反推 | 编号前缀 T/F 显式指定，且写入数据 |
| 计分 | 需要装 R + RStudio | `score.py`，纯 Python |
| 数据列 | `accuracy` 是反向的（1 = 错） | 拆成 `first_key_correct`（1 = 首答正确）等自解释列 |

---

## 二、装环境

> **本机已完成配置，可以直接用。**
> 便携式 Python 3.11.9 + PsychoPy 2026.2.5，装在
> `C:\Users\mahogany\.workbuddy\binaries\python\versions\3.11.9\`
> 不污染系统 Python，也不改 PATH。
>
> 直接双击 `run.cmd`，或在命令行里：
> ```
> run.cmd --check-only
> run.cmd --id T001
> ```
> `run.cmd` 里写死了上面那个路径；如果哪天路径变了，它会自动退回用 PATH 上的 `python`。

以下是从零安装的两种方式，换机器时看。

### 方案 A：PsychoPy 独立版（实验室最省事）

从 <https://www.psychopy.org/download.html> 下载 Windows 版安装包，一路默认安装即可。
它自带 Python 3.12 和所有依赖，不用另外装东西。

装完后打开 PsychoPy 的 **Coder**，把 `iat/` 目录拖进去，运行 `run.py`。
或者在系统命令行里用它的 Python：

```
"C:\Program Files\PsychoPy\python.exe" run.py --check-only
```

> 若提示缺少 `yaml`，执行：
> `"C:\Program Files\PsychoPy\python.exe" -m pip install pyyaml`

### 方案 B：自己建 Python 环境

需要 Python 3.10–3.12（PsychoPy 目前不支持 3.13 及以上）。

```
python -m venv .venv
.venv\Scripts\activate
pip install psychopy pyyaml
```

---

## 三、跑起来

### 1. 自检（改完配置必做）

```
python run.py --check-only
```

不弹窗口，只打印区块结构和刺激分配，用来确认配置没写错。
配置有问题会直接告诉你哪一行错了，例如：

```
配置有 1 处问题，已停止：
  1) 两个概念词必须在不同侧（现在都在 right 侧）
```

也可以指定顺序：`python run.py --check-only --id F001`

### 2. 正式施测

```
python run.py --id T001
```

不写 `--id` 会弹出输入框。

**编号规则**：`T` 或 `F` 开头 + 数字。

- `T001`、`T2`、T012…… → **正顺序**：花在右（与积极同侧），先做相容配对
- `F001`、`F12`、F003…… → **反顺序**：花在左，先做不相容配对

这是配对顺序的平衡机制。奇偶不重要，前缀决定一切。编号会被写进数据，计分时不用再猜。

### 3. 计分

```
python score.py
```

默认读 `iat/data/` 下所有 csv，输出 `iat/data/processed.csv`。

---

## 四、改配置

只改 `config.yaml`。三个地方最常用：

**换概念词**

```yaml
concepts:
  - name: 花
    side: right
    exemplars: [玫瑰, 百合, 兰花, 荷花, 菊花]
```

`side` 表示"正顺序（T）时它在哪一侧"。反顺序会自动左右互换。

**换属性词**

```yaml
attributes:
  - name: 积极
    side: right
    exemplars: [喜爱, 和平, 愉快, 快乐, 拥抱]
```

属性词的左右位置**全程固定**，不参与互换。

**换指导语**

`instructions` 下面每一段对应一个屏幕。`{L}` `{R}` 会自动替换成当前左右两侧的类别名，
`{KEY_L}` `{KEY_R}` 替换成实际按键，**这几个占位符要保留**。

### 配置的硬性规则

程序启动时会检查，不满足就停下：

1. 概念、属性各正好 2 个
2. 两个概念分居两侧；两个属性分居两侧
3. 每个概念的 `side` 必须与某个属性相同（否则不存在相容配对）
4. `keys.left` 与 `keys.right` 不能相同，且都是单字符
5. 同一类别的 `exemplars` 不能重复、不能为空

---

## 五、当前默认值

下面这些是没经过讨论、按惯例定的，需要修改请直接说：

| 项 | 当前值 | 说明 |
|---|---|---|
| 布局 | `nosek7` | Nosek(2007) 七区块，200 试次，约 5 分钟 |
| 按键 | `e` / `i` | 左右食指 |
| 刺激延迟 | 0.3 秒 | 即 ITI，与 Nosek 一致 |
| 作答时限 | 不限 | IAT 标准做法：必须按对键才能继续 |
| 错误反馈 | 屏幕下方红色 X | 按对键后消失 |
| 剔除标准 | 正确率 < 80%，或快速试次（<300ms）> 10% | 见 `score.py` 顶部常量 |
| 主指标 | D1 | 同时输出 Greenwald 1998 对数法作参考 |
| 人口学变量 | 只记被试编号 | 如需性别/年龄，告诉我加 |
| 分辨率 | 1366×768 全屏 | 改 `window.size` |

**词表说明**：属性词全部是双字（喜爱/和平/…），这是为了避免词长这个混淆变量。
蔡华俭原文用的是「爱」，单字，如果你要严格复现可以改成 `爱`，但那样词长就不齐了。

---

## 六、数据格式

每次施测生成两个文件：

- `data/T001_20261027_153012.csv` — 逐试次数据，UTF-8 BOM 编码，Excel 可直接打开
- `data/T001_20261027_153012.json` — 本次实验的完整配置快照，便于复现

CSV 每行一个试次，列的含义：

| 列 | 含义 |
|---|---|
| `participant` | 被试编号 |
| `order` | T / F，配对顺序 |
| `block` | 区块序号 1–7 |
| `block_kind` | `concept` / `attribute` / `combined` |
| `pairing` | `compatible` / `incompatible`，单类别区块为空 |
| `trial_in_block` | 区块内第几个试次 |
| `trial_type` | `concept_1` / `concept_2` / `attribute_1` / `attribute_2` |
| `stimulus` | 实际呈现的词语 |
| `stim_side` | 该词应该归到哪一侧 |
| `correct_key` | 正确按键 |
| `first_key` | 被试第一次按的键 |
| `first_key_correct` | 1 = 首答正确，0 = 首答错误 |
| `rt_first` | 首次按键的反应时（秒） |
| `rt_correct` | 改正后正确反应的反应时（秒），计分用这个 |
| `n_errors` | 该试次按错的次数 |

---

## 七、计分说明

`score.py` 输出的 `processed.csv` 一行一个被试，关键列：

- `D1` — **主指标**。正值表示相容条件（花-积极）反应更快，即对花有更积极的内隐态度
- `D1a` / `D1b` — 短块对、长块对的 D 值，D1 是两者的平均
- `D_1998_log` — Greenwald(1998) 对数法，只作参考，**数值与 D1 不可比**
- `exclude` / `exclude_reason` — 是否建议剔除及原因

D1 算法：剔除 rt > 10000ms 的试次；错误试次用改正后的正确反应时；
按区块长度配对，各自用合并标准差归一化后取平均。与仓库原有 `data/processing.rmd` 的算法一致。

---

## 八、常见问题

**中文显示成方框**
字体没找到。在 `config.yaml` 里把 `font: auto` 改成具体字体名，例如 `font: SimHei`。

**按 E/I 没反应**
中文输入法会吞掉按键。施测前务必关闭输入法（切到英文状态不够，要彻底退出）。

**中途按了 Esc**
数据会写到当前试次，但后续区块缺失，该被试需重做。

**换了词表，旧数据还能一起分析吗**
不能。不同词表的 D 值不可比，请分开存放、分开分析。

**想改成 Greenwald(1998) 五部分布局**
把 `experiment.layout` 改成 `greenwald5`，试次变成 140，其余不变。

**启动时报 `the environment variable is longer than 32767 characters`**
这是 PsychoPy 初始化时往环境变量里塞第三方包路径导致的，Windows 单变量上限 32767 字符。
本项目的 `run.cmd` 里已经设了 `PSYCHOPYNOPACKAGES=1` 规避。
如果用别的方式启动，自己加这个环境变量，或者在 Python 里 `os.environ['PSYCHOPYNOPACKAGES']='1'` 后再 import psychopy。
