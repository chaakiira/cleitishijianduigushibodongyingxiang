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
