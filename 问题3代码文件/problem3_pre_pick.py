#!/usr/bin/env python3
"""问题3(2)：吸嘴容量为2的 SMT 预拾取配对路径优化。"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

import numpy as np

from problem3_SMT import (
    GAConfig,
    Point,
    SMTResult,
    balanced_feeder_assignment,
    genetic_algorithm,
    load_data,
    manhattan,
    save_assignment,
    save_log,
    save_mount_order,
    save_route_plot,
    save_summary,
)


def pre_pick_distance(chromosome: np.ndarray, assignment: np.ndarray,
                      feeder_coordinates: np.ndarray,
                      mount_coordinates: np.ndarray) -> float:
    """计算 P1→P2→M1→M2 配对路径及组间衔接的曼哈顿总距离。"""

    total_distance = 0.0
    pair_starts = range(0, len(chromosome), 2)
    for start in pair_starts:
        first = chromosome[start]
        first_pick = feeder_coordinates[assignment[first]]
        first_mount = mount_coordinates[first]
        if start + 1 < len(chromosome):
            second = chromosome[start + 1]
            second_pick = feeder_coordinates[assignment[second]]
            second_mount = mount_coordinates[second]
            total_distance += float(manhattan(first_pick, second_pick))
            total_distance += float(manhattan(second_pick, first_mount))
            total_distance += float(manhattan(first_mount, second_mount))
            current_end = second_mount
        else:
            total_distance += float(manhattan(first_pick, first_mount))
            current_end = first_mount
        next_start = start + 2
        if next_start < len(chromosome):
            next_component = chromosome[next_start]
            next_pick = feeder_coordinates[assignment[next_component]]
            total_distance += float(manhattan(current_end, next_pick))
    return total_distance


def solve_pre_pick(feeders: Sequence[Point], mounts: Sequence[Point],
                   config: GAConfig) -> SMTResult:
    """用排列相邻元素表示二元配对，并联合优化送料器分配。"""

    import time

    feeder_coordinates = np.asarray([(point.x, point.y) for point in feeders], dtype=np.float64)
    mount_coordinates = np.asarray([(point.x, point.y) for point in mounts], dtype=np.float64)

    assignment = balanced_feeder_assignment(feeder_coordinates, mount_coordinates)

    def objective(chromosome: np.ndarray) -> float:
        return pre_pick_distance(chromosome, assignment, feeder_coordinates, mount_coordinates)

    started = time.perf_counter()
    chromosome, distance, history = genetic_algorithm(len(mounts), objective, config)
    runtime = time.perf_counter() - started
    return SMTResult("pre_pick_capacity_2", chromosome, assignment, distance, runtime, history)


def pre_pick_execution_rows(result: SMTResult, feeders: Sequence[Point],
                            mounts: Sequence[Point]) -> list[list[object]]:
    """将配对染色体展开为 P1、P2、M1、M2 的逐步动作记录。"""

    rows = []
    step = 1
    for start in range(0, len(result.chromosome), 2):
        pair = result.chromosome[start:start + 2]
        for component_index in pair:
            feeder = feeders[result.assignment[component_index]]
            mount = mounts[component_index]
            rows.append([step, "P", feeder.point_id, feeder.x, feeder.y, mount.point_id])
            step += 1
        for component_index in pair:
            mount = mounts[component_index]
            rows.append([step, "M", mount.point_id, mount.x, mount.y, mount.point_id])
            step += 1
    return rows


def save_pre_pick_results(output_dir: Path, result: SMTResult, feeders: Sequence[Point],
                          mounts: Sequence[Point], config: GAConfig) -> None:
    """保存预拾取模型的分配、执行顺序、汇总、路径图和日志。"""

    output_dir.mkdir(parents=True, exist_ok=True)
    rows = pre_pick_execution_rows(result, feeders, mounts)
    save_assignment(output_dir / "assignment.csv", result, feeders, mounts)
    save_mount_order(output_dir / "mount_order.csv", rows)
    save_summary(output_dir / "summary.xlsx", result, feeders, mounts)
    save_route_plot(output_dir / "route_plot.png", rows, feeders, mounts,
                    "SMT Pre-Pick Route (Capacity = 2)")
    save_log(output_dir / "log.txt", result, config, feeders)


def parse_args() -> argparse.Namespace:
    """解析预拾取模型的数据、输出和 GA 参数。"""

    parser = argparse.ArgumentParser(description="问题3(2) SMT 双元件预拾取优化")
    parser.add_argument("--feeder", type=Path, default=Path("data/Q3_feeder_data.csv"))
    parser.add_argument("--mount", type=Path, default=Path("data/Q3_mount_data.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/problem3/pre_pick"))
    parser.add_argument("--population", type=int, default=100)
    parser.add_argument("--generations", type=int, default=400)
    parser.add_argument("--mutation-rate", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    """运行问题3(2)并生成结果。"""

    args = parse_args()
    config = GAConfig(args.population, args.generations, mutation_rate=args.mutation_rate,
                      seed=args.seed)
    feeders, mounts = load_data(args.feeder, args.mount)
    result = solve_pre_pick(feeders, mounts, config)
    save_pre_pick_results(args.output_dir, result, feeders, mounts, config)
    print(f"预拾取总曼哈顿距离: {result.total_distance:.3f}")
    print(f"运行时间: {result.runtime:.3f} s")
    print(f"结果目录: {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
