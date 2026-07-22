#!/usr/bin/env python3
"""问题3(1)：SMT 送料器分配与严格拾取-贴装交替路径优化。"""

from __future__ import annotations

import argparse
import csv
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from openpyxl import Workbook


@dataclass(frozen=True)
class Point:
    """保存送料器或贴装点的编号和二维坐标。"""

    point_id: str
    x: float
    y: float


@dataclass
class GAConfig:
    """保存问题3遗传算法的可调参数。"""

    population_size: int = 100
    generations: int = 400
    elite_size: int = 6
    tournament_size: int = 5
    crossover_rate: float = 0.90
    mutation_rate: float = 0.25
    stagnation_limit: int = 90
    seed: int = 42


@dataclass
class SMTResult:
    """保存一次 SMT 优化的完整结果。"""

    mode: str
    chromosome: np.ndarray
    assignment: np.ndarray
    total_distance: float
    runtime: float
    history: list[float]


def load_points(csv_path: Path, id_candidates: Sequence[str]) -> list[Point]:
    """读取坐标 CSV，并按候选字段名自动识别编号列。"""

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames:
            raise ValueError(f"CSV 没有表头：{csv_path}")
        fields = {field.strip().lower(): field for field in reader.fieldnames}
        missing = [field for field in ("x", "y") if field not in fields]
        if missing:
            raise ValueError(f"CSV 缺少字段 {missing}：{csv_path}")
        id_field = next((fields[name.lower()] for name in id_candidates if name.lower() in fields), None)
        points = []
        for row_number, row in enumerate(reader, start=1):
            point_id = str(row[id_field]).strip() if id_field else str(row_number)
            points.append(Point(point_id, float(row[fields["x"]]), float(row[fields["y"]])))
    if not points:
        raise ValueError(f"CSV 没有数据：{csv_path}")
    return points


def load_data(feeder_path: Path, mount_path: Path) -> tuple[list[Point], list[Point]]:
    """读取送料器和贴装点数据并检查基本规模约束。"""

    feeders = load_points(feeder_path, ("Feeder_ID", "ID"))
    mounts = load_points(mount_path, ("Mount_ID", "ID"))
    if len(mounts) < len(feeders):
        raise ValueError("元件数少于送料器数，无法保证每个槽位至少分配一个元件")
    return feeders, mounts


def manhattan(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    """计算坐标间曼哈顿距离，支持 NumPy 广播。"""

    return np.abs(first - second).sum(axis=-1)


def balanced_capacities(component_count: int, feeder_count: int) -> np.ndarray:
    """生成数量差不超过1且每个槽位非空的均衡容量。"""

    base, remainder = divmod(component_count, feeder_count)
    capacities = np.full(feeder_count, base, dtype=np.int32)
    capacities[:remainder] += 1
    return capacities


def balanced_feeder_assignment(feeder_coordinates: np.ndarray,
                               mount_coordinates: np.ndarray) -> np.ndarray:
    """在3/4均衡容量约束下按拾取到贴装距离贪心分配元件。"""

    feeder_count = len(feeder_coordinates)
    component_count = len(mount_coordinates)
    capacities = balanced_capacities(component_count, feeder_count)
    distances = manhattan(
        feeder_coordinates[:, None, :], mount_coordinates[None, :, :]
    )
    assignment = np.full(component_count, -1, dtype=np.int32)
    remaining = capacities.copy()
    for flat_index in np.argsort(distances, axis=None):
        feeder_index, component_index = np.unravel_index(flat_index, distances.shape)
        if assignment[component_index] < 0 and remaining[feeder_index] > 0:
            assignment[component_index] = feeder_index
            remaining[feeder_index] -= 1
        if np.all(assignment >= 0):
            break
    if np.any(assignment < 0) or np.any(remaining != 0):
        raise RuntimeError("均衡送料器分配失败")
    return assignment


def alternating_distance(chromosome: np.ndarray, assignment: np.ndarray,
                         feeder_coordinates: np.ndarray,
                         mount_coordinates: np.ndarray) -> float:
    """计算 P1→M1→P2→M2…严格交替路径的曼哈顿总距离。"""

    feeders = feeder_coordinates[assignment[chromosome]]
    mounts = mount_coordinates[chromosome]
    pick_to_mount = manhattan(feeders, mounts).sum()
    mount_to_next_pick = manhattan(mounts[:-1], feeders[1:]).sum()
    return float(pick_to_mount + mount_to_next_pick)


def initialize_population(component_count: int, config: GAConfig,
                          rng: np.random.Generator) -> np.ndarray:
    """使用随机元件排列建立初始种群。"""

    return np.asarray(
        [rng.permutation(component_count) for _ in range(config.population_size)],
        dtype=np.int32,
    )


def ordered_crossover(parent1: np.ndarray, parent2: np.ndarray,
                      rng: np.random.Generator) -> np.ndarray:
    """执行有序交叉 OX，确保子代仍为合法元件排列。"""

    size = len(parent1)
    left, right = sorted(rng.choice(size, size=2, replace=False))
    child = np.full(size, -1, dtype=np.int32)
    child[left:right + 1] = parent1[left:right + 1]
    used = np.zeros(size, dtype=bool)
    used[child[left:right + 1]] = True
    positions = np.concatenate((np.arange(right + 1, size), np.arange(left)))
    source = np.concatenate((parent2[right + 1:], parent2[:right + 1]))
    child[positions] = source[~used[source]]
    return child


def mutate(chromosome: np.ndarray, mutation_rate: float,
           rng: np.random.Generator) -> None:
    """按概率执行区段逆序或双点交换变异。"""

    if rng.random() >= mutation_rate:
        return
    left, right = sorted(rng.choice(len(chromosome), size=2, replace=False))
    if rng.random() < 0.65:
        chromosome[left:right + 1] = chromosome[left:right + 1][::-1]
    else:
        chromosome[left], chromosome[right] = chromosome[right], chromosome[left]


def tournament_select(fitness: np.ndarray, config: GAConfig,
                      rng: np.random.Generator) -> int:
    """使用锦标赛选择返回较优父代下标。"""

    candidates = rng.integers(0, len(fitness), size=config.tournament_size)
    return int(candidates[np.argmin(fitness[candidates])])


def genetic_algorithm(component_count: int, objective: Callable[[np.ndarray], float],
                      config: GAConfig) -> tuple[np.ndarray, float, list[float]]:
    """运行选择、交叉、变异和精英保留组成的排列遗传算法。"""

    rng = np.random.default_rng(config.seed)
    population = initialize_population(component_count, config, rng)
    best = population[0].copy()
    best_distance = float("inf")
    history, stagnant = [], 0
    for _ in range(config.generations):
        fitness = np.asarray([objective(chromosome) for chromosome in population])
        ranking = np.argsort(fitness)
        if fitness[ranking[0]] + 1e-9 < best_distance:
            best = population[ranking[0]].copy()
            best_distance = float(fitness[ranking[0]])
            stagnant = 0
        else:
            stagnant += 1
        history.append(best_distance)
        if stagnant >= config.stagnation_limit:
            break
        next_population = [population[index].copy() for index in ranking[:config.elite_size]]
        while len(next_population) < config.population_size:
            parent1 = population[tournament_select(fitness, config, rng)]
            parent2 = population[tournament_select(fitness, config, rng)]
            child = (ordered_crossover(parent1, parent2, rng)
                     if rng.random() < config.crossover_rate else parent1.copy())
            mutate(child, config.mutation_rate, rng)
            next_population.append(child)
        population = np.asarray(next_population, dtype=np.int32)
    return best, best_distance, history


def solve_smt(feeders: Sequence[Point], mounts: Sequence[Point], config: GAConfig) -> SMTResult:
    """先均衡分配送料器，再用 GA 优化严格交替贴装顺序。"""

    feeder_coordinates = np.asarray([(point.x, point.y) for point in feeders], dtype=np.float64)
    mount_coordinates = np.asarray([(point.x, point.y) for point in mounts], dtype=np.float64)

    assignment = balanced_feeder_assignment(feeder_coordinates, mount_coordinates)

    def objective(chromosome: np.ndarray) -> float:
        return alternating_distance(chromosome, assignment, feeder_coordinates, mount_coordinates)

    started = time.perf_counter()
    chromosome, distance, history = genetic_algorithm(len(mounts), objective, config)
    runtime = time.perf_counter() - started
    return SMTResult("alternating", chromosome, assignment, distance, runtime, history)


def execution_rows(result: SMTResult, feeders: Sequence[Point],
                   mounts: Sequence[Point]) -> list[list[object]]:
    """将交替路径展开为逐步 P、M 执行记录。"""

    rows = []
    step = 1
    for component_index in result.chromosome:
        feeder = feeders[result.assignment[component_index]]
        mount = mounts[component_index]
        rows.append([step, "P", feeder.point_id, feeder.x, feeder.y, mount.point_id])
        rows.append([step + 1, "M", mount.point_id, mount.x, mount.y, mount.point_id])
        step += 2
    return rows


def save_assignment(output_path: Path, result: SMTResult, feeders: Sequence[Point],
                    mounts: Sequence[Point]) -> None:
    """保存每个元件对应的优化送料器编号。"""

    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["元件ID", "送料器编号"])
        for component_index, mount in enumerate(mounts):
            writer.writerow([mount.point_id, feeders[result.assignment[component_index]].point_id])


def save_mount_order(output_path: Path, rows: Sequence[Sequence[object]]) -> None:
    """保存包含 P 点和 M 点的逐步执行顺序。"""

    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["执行顺序", "动作", "点编号", "X", "Y", "元件ID"])
        writer.writerows(rows)


def save_summary(output_path: Path, result: SMTResult, feeders: Sequence[Point],
                 mounts: Sequence[Point]) -> None:
    """保存总距离、运行时间和各槽位分配数量。"""

    workbook = Workbook()
    summary = workbook.active
    summary.title = "优化结果"
    summary.append(["模式", "元件数", "送料器数", "总曼哈顿距离", "运行时间(s)"])
    summary.append([result.mode, len(mounts), len(feeders), result.total_distance, result.runtime])
    assignment_sheet = workbook.create_sheet("槽位分配结果")
    assignment_sheet.append(["送料器编号", "分配数量", "元件ID列表"])
    for feeder_index, feeder in enumerate(feeders):
        indices = np.flatnonzero(result.assignment == feeder_index)
        assignment_sheet.append([
            feeder.point_id,
            len(indices),
            ",".join(mounts[index].point_id for index in indices),
        ])
    workbook.save(output_path)


def save_route_plot(output_path: Path, rows: Sequence[Sequence[object]],
                    feeders: Sequence[Point], mounts: Sequence[Point], title: str) -> None:
    """绘制送料器、贴装点以及完整拾取-贴装路径。"""

    route = np.asarray([(float(row[3]), float(row[4])) for row in rows])
    feeder_coordinates = np.asarray([(point.x, point.y) for point in feeders])
    mount_coordinates = np.asarray([(point.x, point.y) for point in mounts])
    fig, axis = plt.subplots(figsize=(11, 8), dpi=160)
    axis.plot(route[:, 0], route[:, 1], color="#7A5195", linewidth=0.55, alpha=0.60)
    axis.scatter(feeder_coordinates[:, 0], feeder_coordinates[:, 1], marker="s", s=24,
                 color="#EF5675", label="Feeders", zorder=3)
    axis.scatter(mount_coordinates[:, 0], mount_coordinates[:, 1], s=12,
                 color="#2F4B7C", label="Mount points", zorder=3)
    axis.set(title=title, xlabel="X", ylabel="Y")
    axis.grid(alpha=0.2)
    axis.legend()
    axis.axis("equal")
    fig.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)


def save_log(output_path: Path, result: SMTResult, config: GAConfig,
             feeders: Sequence[Point]) -> None:
    """保存算法参数、随机种子、收敛代数和最终结果。"""

    counts = np.bincount(result.assignment, minlength=len(feeders)).tolist()
    lines = [
        f"模式: {result.mode}",
        f"随机种子: {config.seed}",
        f"算法参数: {json.dumps(asdict(config), ensure_ascii=False)}",
        f"实际迭代代数: {len(result.history)}",
        f"总曼哈顿距离: {result.total_distance:.6f}",
        f"运行时间(s): {result.runtime:.6f}",
        f"槽位分配数量: {counts}",
        "说明: Q3_mount_data.csv 中已有的 Feeder_ID 列未固定使用，程序按题意重新优化分配。",
    ]
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def save_results(output_dir: Path, result: SMTResult, feeders: Sequence[Point],
                 mounts: Sequence[Point], config: GAConfig) -> None:
    """创建结果目录并保存问题3(1)的全部文件。"""

    output_dir.mkdir(parents=True, exist_ok=True)
    rows = execution_rows(result, feeders, mounts)
    save_assignment(output_dir / "assignment.csv", result, feeders, mounts)
    save_mount_order(output_dir / "mount_order.csv", rows)
    save_summary(output_dir / "summary.xlsx", result, feeders, mounts)
    save_route_plot(output_dir / "route_plot.png", rows, feeders, mounts,
                    "SMT Alternating Pick-and-Place Route")
    save_log(output_dir / "log.txt", result, config, feeders)


def parse_args() -> argparse.Namespace:
    """解析相对数据路径、输出目录和 GA 参数。"""

    parser = argparse.ArgumentParser(description="问题3(1) SMT 严格交替拾取-贴装优化")
    parser.add_argument("--feeder", type=Path, default=Path("data/Q3_feeder_data.csv"))
    parser.add_argument("--mount", type=Path, default=Path("data/Q3_mount_data.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/problem3/standard"))
    parser.add_argument("--population", type=int, default=100)
    parser.add_argument("--generations", type=int, default=400)
    parser.add_argument("--mutation-rate", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    """运行问题3(1)并生成结果。"""

    args = parse_args()
    config = GAConfig(args.population, args.generations, mutation_rate=args.mutation_rate,
                      seed=args.seed)
    feeders, mounts = load_data(args.feeder, args.mount)
    result = solve_smt(feeders, mounts, config)
    save_results(args.output_dir, result, feeders, mounts, config)
    print(f"总曼哈顿距离: {result.total_distance:.3f}")
    print(f"运行时间: {result.runtime:.3f} s")
    print(f"结果目录: {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
