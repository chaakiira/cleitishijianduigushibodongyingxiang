# 高速 PCB 数控钻孔与贴装路径优化

本项目包含数学建模竞赛 B 题的问题1与问题2程序。问题2不重复实现 TSP，而是从 `problem1_TSP.py` 导入距离矩阵、遗传算法、2-opt 和路径长度函数。

## 环境安装

建议使用 Python 3.10 或更高版本：

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 输入数据

默认将以下文件放入项目相对目录 `data/`：

- `Q1_Q2_drill_data50.csv`
- `Q1_Q2_drill_data198.csv`
- `Q1_Q2_drill_data442.csv`
- `Q1_Q2_drill_data1173.csv`

问题2的 CSV 至少包含 `X`、`Y`、`Type` 字段，建议包含 `ID`。字段名大小写不敏感。`Type` 允许 `A`、`B`、`C`，分别表示 0.3 mm、0.5 mm、1.0 mm 孔径。

## 问题2模型思想

同孔径孔位必须连续加工，每一孔径组都从原点 `O(0,0)` 出发并返回原点。总完工时间为：

```text
总时间 = 总移动距离 / 100 + 5 × 换刀次数 + 各类型孔数 × 对应钻孔时间
```

其中 A、B、C 单孔钻孔时间分别为 0.15 s、0.20 s、0.30 s。若存在三种孔径，换刀次数为 2。

## 算法流程

1. 根据 `Type` 将孔位分为 A、B、C 组。
2. 每组调用问题1的 GA + 2-opt TSP 求解器，获得 `O → 组内孔位 → O` 路径。
3. 直接枚举所有非空孔径组排列，计算移动、换刀、钻孔和总时间。
4. 选择总时间最小的排列；完全并列时按字典序选择，保证结果稳定。

由于每组均返回原点，各排列的移动距离、换刀次数和钻孔时间通常完全相同。程序仍按题意枚举并在 `group_order.txt` 中记录全部排列。

## 运行方法

批量运行默认四组数据：

```bash
python problem2_group_TSP.py
```

指定数据目录或具体文件：

```bash
python problem2_group_TSP.py --data-dir "你的数据目录"
python problem2_group_TSP.py data/Q1_Q2_drill_data50.csv
```

调整复用的问题1 GA 参数：

```bash
python problem2_group_TSP.py --population 60 --generations 200 --mutation-rate 0.25 --seed 42
```

问题1仍可独立运行：

```bash
python problem1_TSP.py
```

## 问题2输出

结果默认保存在 `results/problem2/`：

- `problem2_summary.xlsx`：四组 PCB 的数量、最佳顺序、距离和各项时间汇总。
- `<数据文件名>/best_order.csv`：最终连续分组的全部孔位加工顺序。
- `<数据文件名>/group_order.txt`：最佳组顺序和所有排列的评价。
- `<数据文件名>/route_plot.png`：不同孔径按不同颜色绘制的分组闭合路径。
- `<数据文件名>/log.txt`：运行时间、随机种子、GA 参数和最终结果。

问题1结果默认保存在 `results/problem1/`，包括路线 CSV、汇总 Excel、路径图和日志。

## 问题3：SMT 拾取-贴装优化

问题3包含两个程序：

- `problem3_SMT.py`：严格执行 `P1 → M1 → P2 → M2` 的单元件交替模式。
- `problem3_pre_pick.py`：吸嘴最多携带两个元件，执行 `P1 → P2 → M1 → M2` 的预拾取模式。

### 模型思想

两个模型均使用长度为元件数的排列染色体，染色体只决定元件加工顺序。送料器分配先在均衡容量约束下，按送料器到贴装点的曼哈顿距离执行最小距离贪心。对于100个元件和30个送料器，10个送料器分配4个元件，其余20个分配3个元件，因此每槽非空且数量差不超过1。

目标函数采用整条执行路径的曼哈顿距离。标准模式计算所有 `P→M` 和 `M→下一P` 距离；预拾取模式将染色体相邻元件组成二元组，计算组内 `P1→P2→M1→M2` 及 `M2→下一组P1` 距离。GA 使用锦标赛选择、有序交叉、逆序/交换变异、精英保留和固定随机种子42。

输入文件默认放在 `data/`：

- `Q3_feeder_data.csv`：包含 `Feeder_ID,X,Y`。
- `Q3_mount_data.csv`：包含 `Mount_ID,X,Y`；若额外存在原始 `Feeder_ID` 列，程序按题意重新优化而不固定使用该列。

### 运行方法

```bash
python problem3_SMT.py
python problem3_pre_pick.py
```

指定数据文件：

```bash
python problem3_SMT.py --feeder "数据目录/Q3_feeder_data.csv" --mount "数据目录/Q3_mount_data.csv"
python problem3_pre_pick.py --feeder "数据目录/Q3_feeder_data.csv" --mount "数据目录/Q3_mount_data.csv"
```

可使用 `--population`、`--generations`、`--mutation-rate`、`--seed` 调整算法参数。

### 问题3输出

标准模式保存在 `results/problem3/standard/`，预拾取模式保存在 `results/problem3/pre_pick/`。各自包含：

- `assignment.csv`：元件与优化送料器的对应关系。
- `mount_order.csv`：逐步 P/M 动作、点坐标及对应元件。
- `summary.xlsx`：总距离、运行时间和每槽分配结果。
- `route_plot.png`：送料器、贴装点和完整执行路径。
- `log.txt`：随机种子、GA 参数、迭代信息和最终结果。
