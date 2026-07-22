# 高速 PCB 数控钻孔路径优化（问题1）

本程序将原点 `O(0,0)` 作为固定起终点，使用遗传算法求解欧氏距离下的闭合 TSP 路径，并结合最近邻初始化和随机 2-opt 局部搜索提高解的质量。

## 环境安装

建议使用 Python 3.10 或更高版本：

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 数据准备

默认在项目的 `data/` 目录中放置以下文件：

- `Q1_Q2_drill_data50.csv`
- `Q1_Q2_drill_data198.csv`
- `Q1_Q2_drill_data442.csv`
- `Q1_Q2_drill_data1173.csv`

CSV 至少需要包含 `X`、`Y` 字段，建议包含 `ID` 字段；字段名大小写不敏感。程序只读取这三个字段，其余字段会被忽略。

## 运行命令

批量运行四组数据：

```bash
python problem1_TSP.py
```

指定数据目录：

```bash
python problem1_TSP.py --data-dir "你的数据目录"
```

运行一个或多个指定文件：

```bash
python problem1_TSP.py data/Q1_Q2_drill_data50.csv
```

调整算法参数：

```bash
python problem1_TSP.py --population 60 --generations 200 --mutation-rate 0.25 --seed 42
```

程序对 442 和 1173 点数据自动限制默认计算量，以保证大规模实例可运行。显式参数仍作为上限使用。

## 输出文件

结果默认保存在 `results/problem1/`。每个数据集有独立子目录，包含：

- `route_result.csv`：含起点和返回原点的完整钻孔顺序。
- `summary.xlsx`：规模、路径长度、移动时间和运行时间。
- `route_plot.png`：钻孔点、路径和原点图。
- `log.txt`：数据文件、算法参数、随机种子及最终结果。

根结果目录中的 `summary.xlsx` 汇总所有本次实验。移动时间按钻头速度 `100 mm/s` 计算。

## 算法说明

路径染色体是所有孔位下标的排列，原点不参与编码并固定在路径首尾。初始种群混合最近邻路径、最近邻扰动路径和随机排列；每代采用锦标赛选择、有序交叉（OX）、逆序/交换变异和精英保留。算法定期对精英执行受限随机 2-opt，并在结束时强化当前最优解。固定随机种子默认为 `42`，相同环境与参数下结果可复现。
