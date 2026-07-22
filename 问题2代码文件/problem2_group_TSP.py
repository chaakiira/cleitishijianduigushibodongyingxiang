#!/usr/bin/env python3
"""问题2：考虑不同孔径、换刀和钻孔时间的分组路径优化。"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from openpyxl import Workbook

from problem1_TSP import (
    GAConfig,
    calculate_distance_matrix,
    genetic_algorithm,
    route_length,
    scaled_config,
)


DRILL_TIME = {"A": 0.15, "B": 0.20, "C": 0.30}
DIAMETER = {"A": 0.3, "B": 0.5, "C": 1.0}
TYPE_COLORS = {"A": "#2878B5", "B": "#F05A28", "C": "#43A047"}
MOVE_SPEED = 100.0
TOOL_CHANGE_TIME = 5.0


@dataclass(frozen=True)
class DrillPoint:
    """保存一个孔位的编号、坐标和孔径类型。"""

    node_id: str
    x: float
    y: float
    hole_type: str


@dataclass
class GroupSolution:
    """保存一个孔径组的 TSP 求解结果。"""

    hole_type: str
    points: list[DrillPoint]
    route: np.ndarray
    distance: float


@dataclass
class TimeBreakdown:
    """保存完工时间的各组成部分。"""

    move_distance: float
    move_time: float
    tool_changes: int
    tool_change_time: float
    drilling_time: float
    total_time: float


@dataclass
class Problem2Result:
    """保存单个 PCB 数据集的问题2实验结果。"""

    name: str
    counts: dict[str, int]
    best_order: tuple[str, ...]
    group_solutions: dict[str, GroupSolution]
    timing: TimeBreakdown
    runtime: float
    output_dir: Path


def load_data(csv_path: Path) -> list[DrillPoint]:
    """读取 CSV 并自动识别 ID、X、Y、Type 字段。"""

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames:
            raise ValueError(f"CSV 没有表头：{csv_path}")
        fields = {field.strip().lower(): field for field in reader.fieldnames}
        missing = [field for field in ("x", "y", "type") if field not in fields]
        if missing:
            raise ValueError(f"CSV 缺少必要字段 {missing}：{csv_path}")
        id_field = fields.get("id")
        points = []
        for row_number, row in enumerate(reader, start=1):
            hole_type = str(row[fields["type"]]).strip().upper()
            if hole_type not in DRILL_TIME:
                raise ValueError(f"第 {row_number + 1} 行存在未知孔径类型：{hole_type}")
            node_id = str(row[id_field]).strip() if id_field else str(row_number)
            points.append(
                DrillPoint(node_id, float(row[fields["x"]]), float(row[fields["y"]]), hole_type)
            )
    if not points:
        raise ValueError(f"CSV 没有孔位数据：{csv_path}")
    return points


def split_by_type(points: Sequence[DrillPoint]) -> dict[str, list[DrillPoint]]:
    """按照 Type 字段将孔位分为 A、B、C 三组。"""

    groups = {hole_type: [] for hole_type in DRILL_TIME}
    for point in points:
        groups[point.hole_type].append(point)
    return groups


def solve_group_TSP(hole_type: str, points: Sequence[DrillPoint],
                    base_config: GAConfig) -> GroupSolution:
    """调用问题1的距离矩阵、GA、2-opt 和路径长度函数求解单组 TSP。"""

    if not points:
        return GroupSolution(hole_type, [], np.asarray([], dtype=np.int32), 0.0)
    coordinates = np.asarray([(point.x, point.y) for point in points], dtype=np.float64)
    distance_matrix = calculate_distance_matrix(coordinates)
    if len(points) == 1:
        route = np.asarray([0], dtype=np.int32)
        distance = route_length(route, distance_matrix)
    else:
        config = scaled_config(len(points), base_config)
        route, _, _ = genetic_algorithm(distance_matrix, config)
        distance = route_length(route, distance_matrix)
    return GroupSolution(hole_type, list(points), route, distance)


def calculate_total_time(order: Sequence[str], group_solutions: dict[str, GroupSolution]) -> TimeBreakdown:
    """计算指定孔径顺序的移动、换刀、钻孔和总完工时间。"""

    move_distance = sum(group_solutions[hole_type].distance for hole_type in order)
    move_time = move_distance / MOVE_SPEED
    tool_changes = max(0, len(order) - 1)
    tool_change_time = tool_changes * TOOL_CHANGE_TIME
    drilling_time = sum(
        len(group_solutions[hole_type].points) * DRILL_TIME[hole_type] for hole_type in order
    )
    return TimeBreakdown(
        move_distance,
        move_time,
        tool_changes,
        tool_change_time,
        drilling_time,
        move_time + tool_change_time + drilling_time,
    )


def enumerate_group_order(group_solutions: dict[str, GroupSolution]) -> tuple[
        tuple[str, ...], TimeBreakdown, dict[tuple[str, ...], TimeBreakdown]]:
    """枚举所有非空孔径组排列并返回总时间最小的加工顺序。"""

    active_types = tuple(
        hole_type for hole_type in DRILL_TIME if group_solutions[hole_type].points
    )
    evaluations = {
        order: calculate_total_time(order, group_solutions)
        for order in itertools.permutations(active_types)
    }
    best_order = min(evaluations, key=lambda order: (evaluations[order].total_time, order))
    return best_order, evaluations[best_order], evaluations


def ordered_points(result: Problem2Result) -> list[DrillPoint]:
    """按照最优组顺序和组内路径展开最终钻孔顺序。"""

    ordered = []
    for hole_type in result.best_order:
        solution = result.group_solutions[hole_type]
        ordered.extend(solution.points[index] for index in solution.route)
    return ordered


def save_best_order_csv(output_path: Path, result: Problem2Result) -> None:
    """保存不含原点停靠记录的最终孔位加工顺序。"""

    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["序号", "ID", "X", "Y", "Type"])
        for sequence, point in enumerate(ordered_points(result), start=1):
            writer.writerow([sequence, point.node_id, point.x, point.y, point.hole_type])


def save_group_order(output_path: Path, result: Problem2Result,
                     evaluations: dict[tuple[str, ...], TimeBreakdown]) -> None:
    """保存最优加工顺序和全部排列的评价结果。"""

    lines = [
        "最佳孔径加工顺序：",
        " → ".join(result.best_order),
        "",
        "全部排列评价：",
    ]
    for order, timing in evaluations.items():
        lines.append(
            f"{' → '.join(order)}: 总时间={timing.total_time:.6f}s, "
            f"移动距离={timing.move_distance:.6f}mm, 换刀={timing.tool_changes}次"
        )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def save_route_plot(output_path: Path, result: Problem2Result) -> None:
    """按孔径着色绘制各组从原点出发并返回原点的路径。"""

    fig, axis = plt.subplots(figsize=(10, 8), dpi=160)
    for hole_type in result.best_order:
        solution = result.group_solutions[hole_type]
        coordinates = np.asarray([(point.x, point.y) for point in solution.points])
        route_coordinates = np.vstack(
            (np.zeros((1, 2)), coordinates[solution.route], np.zeros((1, 2)))
        )
        color = TYPE_COLORS[hole_type]
        axis.plot(route_coordinates[:, 0], route_coordinates[:, 1], color=color,
                  linewidth=0.7, alpha=0.75)
        axis.scatter(coordinates[:, 0], coordinates[:, 1], color=color, s=11,
                     label=f"{hole_type} ({DIAMETER[hole_type]} mm)", zorder=3)
    axis.scatter([0], [0], color="#111111", marker="*", s=85, label="Origin O", zorder=4)
    axis.set(
        title=f"Grouped TSP Route - {result.name}",
        xlabel="X (mm)",
        ylabel="Y (mm)",
    )
    axis.axis("equal")
    axis.grid(alpha=0.2)
    axis.legend()
    fig.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)


def save_log(output_path: Path, csv_path: Path, result: Problem2Result,
             config: GAConfig) -> None:
    """记录运行时间、参数、随机种子和最终结果。"""

    timing = result.timing
    lines = [
        f"数据文件: {csv_path}",
        f"运行时间(s): {result.runtime:.6f}",
        f"随机种子: {config.seed}",
        f"算法参数: {json.dumps(asdict(config), ensure_ascii=False)}",
        f"各类型数量: {json.dumps(result.counts, ensure_ascii=False)}",
        f"最佳孔径顺序: {' → '.join(result.best_order)}",
        f"移动距离(mm): {timing.move_distance:.6f}",
        f"移动时间(s): {timing.move_time:.6f}",
        f"换刀次数: {timing.tool_changes}",
        f"换刀时间(s): {timing.tool_change_time:.6f}",
        f"钻孔时间(s): {timing.drilling_time:.6f}",
        f"总完工时间(s): {timing.total_time:.6f}",
    ]
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def save_results(csv_path: Path, result: Problem2Result, config: GAConfig,
                 evaluations: dict[tuple[str, ...], TimeBreakdown]) -> None:
    """保存单个数据集的顺序、说明、路径图和日志。"""

    result.output_dir.mkdir(parents=True, exist_ok=True)
    save_best_order_csv(result.output_dir / "best_order.csv", result)
    save_group_order(result.output_dir / "group_order.txt", result, evaluations)
    save_route_plot(result.output_dir / "route_plot.png", result)
    save_log(result.output_dir / "log.txt", csv_path, result, config)


def solve_dataset(csv_path: Path, results_root: Path, config: GAConfig) -> Problem2Result:
    """完成一个数据集的分组、组内 TSP、顺序枚举和结果保存。"""

    started = time.perf_counter()
    groups = split_by_type(load_data(csv_path))
    group_solutions = {
        hole_type: solve_group_TSP(hole_type, points, config)
        for hole_type, points in groups.items()
    }
    best_order, timing, evaluations = enumerate_group_order(group_solutions)
    result = Problem2Result(
        csv_path.stem,
        {hole_type: len(groups[hole_type]) for hole_type in DRILL_TIME},
        best_order,
        group_solutions,
        timing,
        time.perf_counter() - started,
        results_root / csv_path.stem,
    )
    save_results(csv_path, result, config, evaluations)
    return result


def save_summary(output_path: Path, results: Sequence[Problem2Result]) -> None:
    """将四组 PCB 实验结果写入问题2汇总表。"""

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "问题2实验结果"
    sheet.append([
        "文件", "A数量", "B数量", "C数量", "最佳顺序", "移动距离(mm)",
        "移动时间(s)", "换刀时间(s)", "钻孔时间(s)", "总时间(s)", "运行时间(s)",
    ])
    for result in sorted(results, key=lambda item: sum(item.counts.values())):
        sheet.append([
            result.name,
            result.counts["A"],
            result.counts["B"],
            result.counts["C"],
            " → ".join(result.best_order),
            result.timing.move_distance,
            result.timing.move_time,
            result.timing.tool_change_time,
            result.timing.drilling_time,
            result.timing.total_time,
            result.runtime,
        ])
    workbook.save(output_path)


def discover_csv_files(data_dir: Path) -> list[Path]:
    """在指定相对目录中发现四个约定数据文件。"""

    files = [data_dir / f"Q1_Q2_drill_data{scale}.csv" for scale in (50, 198, 442, 1173)]
    missing = [str(path) for path in files if not path.is_file()]
    if missing:
        raise FileNotFoundError("未找到数据文件：\n" + "\n".join(missing))
    return files


def parse_args() -> argparse.Namespace:
    """解析数据路径、输出路径和复用的 GA 参数。"""

    parser = argparse.ArgumentParser(description="PCB 不同孔径分组路径优化")
    parser.add_argument("csv_files", nargs="*", type=Path, help="一个或多个 CSV 文件")
    parser.add_argument("--data-dir", type=Path, default=Path("data"), help="批量数据目录")
    parser.add_argument("--results-dir", type=Path, default=Path("results/problem2"), help="结果目录")
    parser.add_argument("--population", type=int, default=50, help="问题1 GA 种群规模")
    parser.add_argument("--generations", type=int, default=160, help="问题1 GA 最大迭代代数")
    parser.add_argument("--mutation-rate", type=float, default=0.20, help="问题1 GA 变异概率")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    return parser.parse_args()


def main() -> None:
    """自动运行单个文件或四组标准实验。"""

    args = parse_args()
    config = GAConfig(
        population_size=args.population,
        generations=args.generations,
        mutation_rate=args.mutation_rate,
        seed=args.seed,
    )
    csv_files = args.csv_files or discover_csv_files(args.data_dir)
    args.results_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for csv_path in csv_files:
        print(f"正在求解：{csv_path}", flush=True)
        result = solve_dataset(csv_path, args.results_dir, config)
        results.append(result)
        print(
            f"规模={sum(result.counts.values())}, 顺序={'-'.join(result.best_order)}, "
            f"距离={result.timing.move_distance:.3f} mm, 总时间={result.timing.total_time:.3f} s, "
            f"运行时间={result.runtime:.3f} s",
            flush=True,
        )
    save_summary(args.results_dir / "problem2_summary.xlsx", results)
    print(f"结果已保存至：{args.results_dir.resolve()}")


if __name__ == "__main__":
    main()
