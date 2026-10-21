# Example: Bounded Syntax Error Repair

This example shows how Kaufee-Home diagnoses and repairs code errors with bounded retries:
1. Detects failures through concrete execution outcomes rather than imagined behavior.
2. Captures stderr, syntax errors, or runtime exceptions.
3. Automatically triggers targeted repair actions (`write_file` or `edit_file`).
4. Re-runs execution and independently verifies that the error has been eliminated.

## CLI Command

```bash
kaufee run "Fix the syntax error in broken.py, run it, and verify the output."
```

## Before Repair (`broken.py`)

```python
# Intentionally broken syntax: missing colon and closing parenthesis
def greet(name
    print "Hello, " + name
```

## After Repair (`repaired.py`)

```python
def greet(name: str) -> str:
    return f"Hello, {name}!"

if __name__ == "__main__":
    print(greet("World"))
```
