"""Example triangle program generated and verified by Kaufee-Home."""

def draw_triangle(height: int = 5) -> None:
    for i in range(1, height + 1):
        print(" " * (height - i) + "*" * (2 * i - 1))


if __name__ == "__main__":
    draw_triangle()
