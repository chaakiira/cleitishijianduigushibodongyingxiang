#!/usr/bin/env python3
"""问题1：高速 PCB 数控钻孔最短闭合路径优化。"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from openpyxl import Workbook


@dataclass
class GAConfig:
    """保存遗传算法可调参数。"""

    population_size: int = 50
    generations: int = 160
    elite_size: int = 4
    tournament_size: int = 4
    crossover_rate: float = 0.90
    mutation_rate: float = 0.20
    two_opt_elites: int = 2
    two_opt_trials: int = 2500
    stagnation_limit: int = 45
    seed: int = 42


@dataclass
class DatasetResult:
    """保存单个数据集的实验结果。"""

    name: str
    scale: int
    distance: float
    move_time: float
    runtime: float
    output_dir: Path


def read_drill_data(csv_path: Path) -> tuple[list[str], np.ndarray]:
    """读取 CSV，自动识别 ID、X、Y 字段并返回节点编号和坐标。"""

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames:
            raise ValueError(f"CSV 没有表头：{csv_path}")
        fields = {field.strip().lower(): field for field in reader.fieldnames}
        missing = [field for field in ("x", "y") if field not in fields]
        if missing:
            raise ValueError(f"CSV 缺少字段 {missing}：{csv_path}")
        id_field = fields.get("id")
        node_ids, coordinates = [], []
        for row_number, row in enumerate(reader, start=1):
            node_ids.append(str(row[id_field]).strip() if id_field else str(row_number))
            coordinates.append((float(row[fields["x"]]), float(row[fields["y"]])))
    if not coordinates:
        raise ValueError(f"CSV 没有数据：{csv_path}")
    return node_ids, np.asarray(coordinates, dtype=np.float64)


def calculate_distance_matrix(coordinates: np.ndarray) -> np.ndarray:
    """按欧氏距离生成包含原点在内的完整距离矩阵。"""

    all_coordinates = np.vstack((np.zeros((1, 2)), coordinates))
    differences = all_coordinates[:, None, :] - all_coordinates[None, :, :]
    return np.sqrt(np.sum(differences * differences, axis=2))


def route_length(route: np.ndarray, distance_matrix: np.ndarray) -> float:
    """计算 O→全部孔位→O 的闭合路径长度。"""

    if route.size == 0:
        return 0.0
    return float(
        distance_matrix[0, route[0] + 1]
        + distance_matrix[route[-1] + 1, 0]
        + np.sum(distance_matrix[route[:-1] + 1, route[1:] + 1])
    )


def population_lengths(population: np.ndarray, distance_matrix: np.ndarray) -> np.ndarray:
    """向量化计算整个种群中每条路径的长度。"""

    shifted = population + 1
    middle = distance_matrix[shifted[:, :-1], shifted[:, 1:]].sum(axis=1)
    return distance_matrix[0, shifted[:, 0]] + middle + distance_matrix[shifted[:, -1], 0]


def nearest_neighbor_route(distance_matrix: np.ndarray, start: int | None = None) -> np.ndarray:
    """使用最近邻法生成一条高质量初始路径。"""

    node_count = distance_matrix.shape[0] - 1
    unvisited = np.ones(node_count, dtype=bool)
    route = np.empty(node_count, dtype=np.int32)
    current = 0
    if start is not None:
        route[0] = start
        unvisited[start] = False
        current = start + 1
        begin = 1
    else:
        begin = 0
    for position in range(begin, node_count):
        candidates = np.flatnonzero(unvisited)
        selected = candidates[np.argmin(distance_matrix[current, candidates + 1])]
        route[position] = selected
        unvisited[selected] = False
        current = selected + 1
    return route


def initialize_population(node_count: int, distance_matrix: np.ndarray, config: GAConfig,
                          rng: np.random.Generator) -> np.ndarray:
    """混合最近邻解、扰动解和随机排列建立初始种群。"""

    population = np.empty((config.population_size, node_count), dtype=np.int32)
    base = nearest_neighbor_route(distance_matrix)
    population[0] = base
    nn_count = min(max(2, config.population_size // 8), node_count)
    starts = rng.choice(node_count, size=nn_count - 1, replace=False)
    for index, start in enumerate(starts, start=1):
        population[index] = nearest_neighbor_route(distance_matrix, int(start))
    perturb_count = min(config.population_size // 3, config.population_size - nn_count)
    for index in range(nn_count, nn_count + perturb_count):
        candidate = base.copy()
        for _ in range(max(2, node_count // 100)):
            left, right = sorted(rng.choice(node_count, size=2, replace=False))
            candidate[left:right + 1] = candidate[left:right + 1][::-1]
        population[index] = candidate
    for index in range(nn_count + perturb_count, config.population_size):
        population[index] = rng.permutation(node_count)
    return population


def tournament_select(lengths: np.ndarray, config: GAConfig,
                      rng: np.random.Generator) -> int:
    """通过锦标赛选择返回父代下标。"""

    candidates = rng.integers(0, len(lengths), size=config.tournament_size)
    return int(candidates[np.argmin(lengths[candidates])])


def ordered_crossover(parent1: np.ndarray, parent2: np.ndarray,
                      rng: np.random.Generator) -> np.ndarray:
    """使用有序交叉 OX 生成合法的排列子代。"""

    node_count = len(parent1)
    left, right = sorted(rng.choice(node_count, size=2, replace=False))
    child = np.full(node_count, -1, dtype=np.int32)
    child[left:right + 1] = parent1[left:right + 1]
    used = np.zeros(node_count, dtype=bool)
    used[child[left:right + 1]] = True
    fill_positions = np.concatenate((np.arange(right + 1, node_count), np.arange(0, left)))
    parent_order = np.concatenate((parent2[right + 1:], parent2[:right + 1]))
    remaining = parent_order[~used[parent_order]]
    child[fill_positions] = remaining
    return child


def mutate(route: np.ndarray, mutation_rate: float, rng: np.random.Generator) -> None:
    """按概率执行逆序变异或交换变异。"""

    if rng.random() >= mutation_rate:
        return
    left, right = sorted(rng.choice(len(route), size=2, replace=False))
    if rng.random() < 0.75:
        route[left:right + 1] = route[left:right + 1][::-1]
    else:
        route[left], route[right] = route[right], route[left]


def two_opt_random(route: np.ndarray, distance_matrix: np.ndarray, trials: int,
                   rng: np.random.Generator) -> np.ndarray:
    """随机抽样 2-opt 邻域，以可控时间持续消除交叉边。"""

    improved = route.copy()
    node_count = len(improved)
    no_improvement = 0
    for _ in range(trials):
        left, right = sorted(rng.choice(node_count, size=2, replace=False))
        if right - left < 2:
            continue
        previous_node = 0 if left == 0 else improved[left - 1] + 1
        first_node = improved[left] + 1
        last_node = improved[right] + 1
        next_node = 0 if right == node_count - 1 else improved[right + 1] + 1
        old_edges = distance_matrix[previous_node, first_node] + distance_matrix[last_node, next_node]
        new_edges = distance_matrix[previous_node, last_node] + distance_matrix[first_node, next_node]
        if new_edges + 1e-12 < old_edges:
            improved[left:right + 1] = improved[left:right + 1][::-1]
            no_improvement = 0
        else:
            no_improvement += 1
        if no_improvement >= min(800, trials):
            break
    return improved


def genetic_algorithm(distance_matrix: np.ndarray, config: GAConfig) -> tuple[np.ndarray, float, list[float]]:
    """运行带精英保留和 2-opt 强化的遗传算法。"""

    rng = np.random.default_rng(config.seed)
    node_count = distance_matrix.shape[0] - 1
    population = initialize_population(node_count, distance_matrix, config, rng)
    best_route, best_length = population[0].copy(), math.inf
    history, stagnant = [], 0
    for generation in range(config.generations):
        lengths = population_lengths(population, distance_matrix)
        order = np.argsort(lengths)
        if lengths[order[0]] + 1e-10 < best_length:
            best_length = float(lengths[order[0]])
            best_route = population[order[0]].copy()
            stagnant = 0
        else:
            stagnant += 1
        history.append(best_length)
        if stagnant >= config.stagnation_limit:
            break
        next_population = [population[index].copy() for index in order[:config.elite_size]]
        if generation % 8 == 0:
            for index in range(min(config.two_opt_elites, len(next_population))):
                next_population[index] = two_opt_random(
                    next_population[index], distance_matrix, config.two_opt_trials, rng
                )
        while len(next_population) < config.population_size:
            parent1 = population[tournament_select(lengths, config, rng)]
            parent2 = population[tournament_select(lengths, config, rng)]
            child = (ordered_crossover(parent1, parent2, rng)
                     if rng.random() < config.crossover_rate else parent1.copy())
            mutate(child, config.mutation_rate, rng)
            next_population.append(child)
        population = np.asarray(next_population, dtype=np.int32)
    final_route = two_opt_random(best_route, distance_matrix, config.two_opt_trials * 4, rng)
    final_length = route_length(final_route, distance_matrix)
    return final_route, final_length, history


def scaled_config(node_count: int, base: GAConfig) -> GAConfig:
    """按数据规模调整默认计算量，同时保留命令行显式参数。"""

    config = GAConfig(**asdict(base))
    if node_count >= 1000:
        config.population_size = min(config.population_size, 36)
        config.generations = min(config.generations, 100)
        config.two_opt_trials = min(config.two_opt_trials, 1800)
    elif node_count >= 400:
        config.population_size = min(config.population_size, 44)
        config.generations = min(config.generations, 130)
    return config


def write_route_csv(output_path: Path, route: np.ndarray, node_ids: Sequence[str],
                    coordinates: np.ndarray) -> None:
    """输出含起终原点的最终钻孔顺序 CSV。"""

    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["序号", "节点编号", "X", "Y"])
        writer.writerow([0, "O", 0, 0])
        for sequence, index in enumerate(route, start=1):
            writer.writerow([sequence, node_ids[index], coordinates[index, 0], coordinates[index, 1]])
        writer.writerow([len(route) + 1, "O", 0, 0])


def plot_route(output_path: Path, route: np.ndarray, coordinates: np.ndarray,
               title: str) -> None:
    """绘制孔位、闭合最优路径和原点。"""

    ordered = np.vstack((np.zeros((1, 2)), coordinates[route], np.zeros((1, 2))))
    fig, axis = plt.subplots(figsize=(10, 8), dpi=160)
    axis.plot(ordered[:, 0], ordered[:, 1], color="#2878B5", linewidth=0.65, alpha=0.72)
    axis.scatter(coordinates[:, 0], coordinates[:, 1], s=9, color="#F05A28", zorder=3, label="Drill holes")
    axis.scatter([0], [0], s=70, marker="*", color="#111111", zorder=4, label="Origin O")
    axis.set(title=title, xlabel="X (mm)", ylabel="Y (mm)")
    axis.axis("equal")
    axis.grid(alpha=0.2)
    axis.legend()
    fig.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)


def write_single_summary(output_path: Path, result: DatasetResult) -> None:
    """输出单个数据集的 Excel 汇总表。"""

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "问题1结果"
    sheet.append(["数据规模", "最优路径长度(mm)", "移动时间(s)", "运行时间(s)"])
    sheet.append([result.scale, result.distance, result.move_time, result.runtime])
    workbook.save(output_path)


def solve_dataset(csv_path: Path, results_root: Path, base_config: GAConfig) -> DatasetResult:
    """求解一个 CSV 并生成该数据集的全部结果文件。"""

    started = time.perf_counter()
    node_ids, coordinates = read_drill_data(csv_path)
    config = scaled_config(len(coordinates), base_config)
    distance_matrix = calculate_distance_matrix(coordinates)
    route, distance, history = genetic_algorithm(distance_matrix, config)
    runtime = time.perf_counter() - started
    dataset_name = csv_path.stem
    output_dir = results_root / dataset_name
    output_dir.mkdir(parents=True, exist_ok=True)
    result = DatasetResult(dataset_name, len(coordinates), distance, distance / 100.0, runtime, output_dir)
    write_route_csv(output_dir / "route_result.csv", route, node_ids, coordinates)
    write_single_summary(output_dir / "summary.xlsx", result)
    plot_route(output_dir / "route_plot.png", route, coordinates, f"TSP Route - {len(coordinates)} holes")
    log_lines = [
        f"数据文件: {csv_path}", f"数据规模: {result.scale}", f"随机种子: {config.seed}",
        f"算法参数: {json.dumps(asdict(config), ensure_ascii=False)}",
        f"实际迭代代数: {len(history)}", f"最优路径长度(mm): {distance:.6f}",
        f"移动时间(s): {result.move_time:.6f}", f"运行时间(s): {runtime:.6f}",
    ]
    (output_dir / "log.txt").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    return result


def write_batch_summary(output_path: Path, results: Sequence[DatasetResult]) -> None:
    """输出四组实验结果的总汇总 Excel。"""

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "批量实验结果"
    sheet.append(["规模", "最优距离(mm)", "移动时间(s)", "运行时间(s)"])
    for result in sorted(results, key=lambda item: item.scale):
        sheet.append([result.scale, result.distance, result.move_time, result.runtime])
    workbook.save(output_path)


def discover_csv_files(data_dir: Path) -> list[Path]:
    """自动发现四个约定命名的数据文件。"""

    expected = [50, 198, 442, 1173]
    files = [data_dir / f"Q1_Q2_drill_data{scale}.csv" for scale in expected]
    missing = [str(path) for path in files if not path.is_file()]
    if missing:
        raise FileNotFoundError("未找到数据文件：\n" + "\n".join(missing))
    return files


def parse_args() -> argparse.Namespace:
    """解析输入路径和遗传算法参数。"""

    parser = argparse.ArgumentParser(description="PCB 钻孔 TSP 遗传算法求解器")
    parser.add_argument("csv_files", nargs="*", type=Path, help="一个或多个 CSV 文件")
    parser.add_argument("--data-dir", type=Path, default=Path("data"), help="批量数据目录")
    parser.add_argument("--results-dir", type=Path, default=Path("results/problem1"), help="结果目录")
    parser.add_argument("--population", type=int, default=50, help="种群规模")
    parser.add_argument("--generations", type=int, default=160, help="最大迭代代数")
    parser.add_argument("--mutation-rate", type=float, default=0.20, help="变异概率")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    return parser.parse_args()


def main() -> None:
    """执行单文件或四文件批量实验。"""

    args = parse_args()
    random.seed(args.seed)
    np.random.seed(args.seed)
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
        print(f"规模={result.scale}, 距离={result.distance:.3f} mm, "
              f"移动时间={result.move_time:.3f} s, 运行时间={result.runtime:.3f} s", flush=True)
    write_batch_summary(args.results_dir / "summary.xlsx", results)
    print(f"结果已保存至：{args.results_dir.resolve()}")


if __name__ == "__main__":
    main()
