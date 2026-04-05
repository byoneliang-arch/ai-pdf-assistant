import random

import matplotlib.pyplot as plt


def main() -> None:
    numbers = [random.randint(1, 100) for _ in range(100)]
    average = sum(numbers) / len(numbers)

    plt.figure(figsize=(10, 5))
    plt.plot(range(1, 101), numbers, marker="o", linewidth=1.5)
    plt.title(f"100 Random Numbers (Average: {average:.2f})")
    plt.xlabel("Index")
    plt.ylabel("Value")
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.savefig("result.png", dpi=150)

    print(f"平均值: {average:.2f}")
    print("图片已保存为 result.png")


if __name__ == "__main__":
    main()
