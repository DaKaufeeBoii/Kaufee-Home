# Example: Draw a Triangle in Python

This example demonstrates the core end-to-end MVP workflow of Kaufee-Home:
1. Translating a plain-English request into structured steps.
2. Generating a Python script within workspace boundaries.
3. Executing the program with bounded limits and capturing output.
4. Independently verifying postconditions (syntax validity, non-empty file, exit code 0, and output pattern).

## CLI Command

```bash
kaufee run "Create a Python program that draws a triangle, run it, and fix any errors."
```

## Sample Generated Code (`triangle.py`)

```python
def draw_triangle(height=5):
    for i in range(1, height + 1):
        print(" " * (height - i) + "*" * (2 * i - 1))

if __name__ == "__main__":
    draw_triangle()
```

## Sample Execution Output

```
[PLAN]  1: Create triangle.py that outputs an ASCII triangle (write_file)
        2: Execute triangle.py and inspect output (python_runner)
[ACT]   write_file(path='triangle.py', content=...)
        + Successfully wrote 166 characters to 'triangle.py'. (1.4ms)
[ACT]   python_runner(script_path='triangle.py')
        + OK (42.5ms)
[CHECK] Inspecting verification postconditions:
        [+] file_exists_triangle.py: File exists on disk
        [+] file_non_empty_triangle.py: File 'triangle.py' exists with size 166 bytes
        [+] syntax_valid_triangle.py: Python syntax parsed cleanly for 'triangle.py'
        [+] code_execution: Python script executed successfully with exit code 0
        [+] triangle_pattern_output: Triangle output verified
[RESULT] Task Completed Successfully!
```
