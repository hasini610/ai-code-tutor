"""
Populate processed_problems.json test_cases from problem descriptions.

Stdin (space-separated unless noted):
  Array + target:  n v1 v2 ... vn target
  Array only:      n v1 v2 ... vn
  Grid:            rows cols then row-major values (-1 = null)
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
PROCESSED_PATH = PROJECT_ROOT / "processed_problems.json"

# Manual test cases when descriptions use non-standard Example formats.
MANUAL_OVERRIDES: dict[int, list[dict[str, str]]] = {
    176: [{"input": "1", "expected_output": "null"}],
    155: [
        {"input": "push -2\npush 0\npush -3\nget_min\npop\ntop\nget_min", "expected_output": "0"},
    ],
    412: [
        {"input": "3", "expected_output": "['1', '2', 'Fizz']"},
        {"input": "5", "expected_output": "['1', '2', 'Fizz', '4', 'Buzz']"},
        {"input": "15", "expected_output": "['1', '2', 'Fizz', '4', 'Buzz', 'Fizz', '7', '8', 'Fizz', 'Buzz', '11', 'Fizz', '13', '14', 'FizzBuzz']"},
    ],
    706: [
        {"input": "put 1 1\nget 1", "expected_output": "1"},
        {"input": "put 2 2\nget 2\nremove 2\nget 2", "expected_output": "-1"},
    ],
    175: [{"input": "1", "expected_output": "1"}],
    572: [
        {"input": "3 4 5 1 2 4 1 2", "expected_output": "True"},
        {"input": "3 4 5 1 2 0 4 1 2", "expected_output": "False"},
    ],
    716: [
        {"input": "push 5\npush 2\npush 3\nmax\npop\nmax", "expected_output": "3"},
    ],
    359: [
        {"input": "print 1\ngreen 1\nprint 2", "expected_output": "True\nFalse"},
    ],
    346: [
        {"input": "3 1 10 3 5", "expected_output": "1.0"},
    ],
    146: [
        {"input": "2 1 1 2 2 1 3 3 2 4 4 1 3 4", "expected_output": "1"},
    ],
    380: [
        {"input": "insert 1\ninsert 2\nremove 1\nrandom", "expected_output": "2"},
    ],
    528: [{"input": "1 1", "expected_output": "0"}],
    1348: [{"input": "tweet 1\nget 1", "expected_output": "1"}],
    695: [
        {
            "input": "7 13 0 0 1 0 0 0 1 1 1 0 0 0 0 0 0 0 1 1 1 0 1 1 0 1 0 0 0 0 0 0 1 0 1 0 1 1 0 0 1 0 1 1 0 0 1 1 1 0 0 0 0 0 1 0 0 0 0 0 0 1 1 1 0 0 0 0 0 0 0 1 1 0 0 0",
            "expected_output": "6",
        },
        {
            "input": "1 8 0 0 0 0 0 0 0",
            "expected_output": "0",
        },
    ],
    739: [
        {
            "input": "8 73 74 75 71 69 72 76 73",
            "expected_output": "[1, 1, 4, 2, 1, 1, 0, 0]",
        },
    ],
    445: [
        {"input": "2 7 8 4 5 6 9 4 3", "expected_output": "[7, 8, 0, 0]"},
    ],
}


def fizzbuzz_list(n: int) -> str:
    out = []
    for i in range(1, n + 1):
        if i % 15 == 0:
            out.append("FizzBuzz")
        elif i % 3 == 0:
            out.append("Fizz")
        elif i % 5 == 0:
            out.append("Buzz")
        else:
            out.append(str(i))
    return str(out)


def parse_leetcode_array(text: str) -> list | None:
    text = text.strip().replace("null", "None")
    try:
        return ast.literal_eval(text)
    except (SyntaxError, ValueError):
        return None


def extract_examples(description: str) -> list[dict[str, str]]:
    examples: list[dict[str, str]] = []

    pattern = re.compile(
        r"Example\s+\d+:\s*\nInput:?\s*(.*?)\nOutput:\s*(.*?)"
        r"(?=\n(?:Explanation|Example|Constraints|Notes|Follow up)|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    for match in pattern.finditer(description):
        inp = match.group(1).strip()
        out = match.group(2).strip().split("\n")[0].strip()
        if inp and out:
            examples.append({"input_raw": inp, "output_raw": out})

    # Fizz Buzz style: Example:\nn = 15,\nReturn:\n[...]
    if not examples:
        m = re.search(
            r"Example:\s*\n\s*n\s*=\s*(\d+)\s*,\s*\nReturn:\s*\n(\[.*?\])",
            description,
            re.DOTALL | re.IGNORECASE,
        )
        if m:
            n = int(m.group(1))
            examples.append({"input_raw": str(n), "output_raw": fizzbuzz_list(n)})

    # Grid-only example: Example 1:\n[[0,0,1,...]]\n... return `6`
    if not examples:
        for m in re.finditer(
            r"Example\s+\d+:\s*\n(\[\[.*?\]\])\s*\n.*?return\s+`?(\d+)`?",
            description,
            re.DOTALL | re.IGNORECASE,
        ):
            examples.append({"input_raw": m.group(1), "output_raw": m.group(2)})

    # Daily Temperatures prose: T = [73, 74, ...]
    if not examples:
        m = re.search(r"`T\s*=\s*(\[[^\]]+\])`", description)
        if m:
            arr = parse_leetcode_array(m.group(1))
            if arr:
                out_m = re.search(r"output should be\s+`(\[[^\]]+\])`", description, re.I)
                out = out_m.group(1) if out_m else str([0] * len(arr))
                examples.append(
                    {
                        "input_raw": array_stdin(arr),
                        "output_raw": out,
                    }
                )

    return examples[:3]


def parse_bracket_value(text: str) -> list | None:
    return parse_leetcode_array(text)


def parse_quoted_string(text: str) -> str | None:
    text = text.strip()
    if (text.startswith('"') and text.endswith('"')) or (
        text.startswith("'") and text.endswith("'")
    ):
        return ast.literal_eval(text)
    return text if text else None


def parse_scalar(text: str):
    text = text.strip()
    if text.lower() in ("true", "false"):
        return text.lower() == "true"
    try:
        return ast.literal_eval(text)
    except (SyntaxError, ValueError):
        return text


def parse_input_fields(input_raw: str) -> dict:
    fields: dict = {}
    if "\n" in input_raw and "=" not in input_raw.split("\n")[0]:
        fields["_raw_multiline"] = input_raw
        return fields

    for part in re.split(r",\s*(?=[A-Za-z_][\w]*\s*=)", input_raw):
        part = part.strip()
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        fields[key.strip()] = value.strip()
    return fields


def array_stdin(values: list) -> str:
    serialized = [(-1 if v is None else v) for v in values]
    return f"{len(serialized)} " + " ".join(str(v) for v in serialized)


def grid_stdin(grid: list) -> str:
    if not grid or not isinstance(grid[0], (list, tuple)):
        return array_stdin(grid) if isinstance(grid, list) else "0 0"
    parts = [str(len(grid)), str(len(grid[0]))]
    for row in grid:
        if not isinstance(row, (list, tuple)):
            return array_stdin([item for sub in grid for item in (sub if isinstance(sub, list) else [sub])])
        parts.extend(str(c) for c in row)
    return " ".join(parts)


def normalize_expected(output_raw: str) -> str:
    output_raw = output_raw.strip().rstrip(".")
    low = output_raw.lower()
    if low in ("true", "false"):
        return "True" if low == "true" else "False"

    if output_raw.startswith("["):
        parsed = parse_bracket_value(output_raw)
        if parsed is not None:
            return str(parsed)

    if (output_raw.startswith('"') and output_raw.endswith('"')) or (
        output_raw.startswith("'") and output_raw.endswith("'")
    ):
        return str(ast.literal_eval(output_raw))

    return str(parse_scalar(output_raw))


def build_test_case(input_raw: str, output_raw: str) -> dict | None:
    input_raw = input_raw.strip()
    expected = normalize_expected(output_raw)

    if "image" in input_raw and "newColor" in input_raw:
        combined = re.sub(r"\n\s*", ", ", input_raw)
        fields = parse_input_fields(combined)
        grid = parse_bracket_value(fields.get("image", ""))
        if isinstance(grid, list):
            sr = parse_scalar(fields.get("sr", "0"))
            sc = parse_scalar(fields.get("sc", "0"))
            color = parse_scalar(fields.get("newColor", "0"))
            return {
                "input": grid_stdin(grid) + f" {sr} {sc} {color}",
                "expected_output": expected,
            }

    # Bare quoted string
    if (input_raw.startswith('"') or input_raw.startswith("'")) and "=" not in input_raw:
        s = parse_quoted_string(input_raw)
        if s is not None:
            return {"input": s, "expected_output": expected}

    # Bare list (cpdomains etc.)
    if input_raw.startswith("["):
        first_line = input_raw.split("\n")[0].strip()
        arr = parse_bracket_value(first_line)
        if isinstance(arr, list):
            if arr and isinstance(arr[0], str):
                return {
                    "input": f"{len(arr)}\n" + "\n".join(arr),
                    "expected_output": expected,
                }
            if arr and isinstance(arr[0], (int, float)):
                nested = isinstance(arr[0], list)
                if nested:
                    return {"input": grid_stdin(arr), "expected_output": expected}
                return {"input": array_stdin(arr), "expected_output": expected}

    # Already formatted as n v1 v2 ... (from extract)
    if re.match(r"^\d+(\s+-?\d+)+\s*$", input_raw.replace("\n", " ")):
        return {"input": input_raw.replace("\n", " ").strip(), "expected_output": expected}

    fields = parse_input_fields(input_raw)

    if "_raw_multiline" in fields:
        raw = fields["_raw_multiline"]
        lines = [ln.strip() for ln in raw.split("\n") if ln.strip()]
        if lines and lines[0].startswith("["):
            arr = parse_bracket_value(lines[0])
            if isinstance(arr, list) and arr and isinstance(arr[0], str):
                return {
                    "input": f"{len(arr)}\n" + "\n".join(arr),
                    "expected_output": expected,
                }

    if "nums" in fields and "target" in fields:
        nums = parse_bracket_value(fields["nums"])
        target = parse_scalar(fields["target"])
        if isinstance(nums, list):
            return {"input": array_stdin(nums) + f" {target}", "expected_output": expected}

    if "s" in fields and "t" in fields:
        s = parse_quoted_string(fields["s"])
        t = parse_quoted_string(fields["t"])
        if s is not None and t is not None:
            return {"input": f"{s}\n{t}", "expected_output": expected}

    if "a" in fields and "b" in fields:
        a = parse_quoted_string(fields["a"])
        b = parse_quoted_string(fields["b"])
        if a is not None and b is not None:
            return {"input": f"{a}\n{b}", "expected_output": expected}

    if "S" in fields and len(fields) == 1:
        s = parse_quoted_string(fields["S"])
        if s is not None:
            return {"input": s, "expected_output": expected}

    if "digits" in fields:
        raw_digits = fields["digits"].strip()
        if raw_digits in ('""', "''"):
            return {"input": "0", "expected_output": expected}
        d = parse_quoted_string(fields["digits"])
        if d is not None:
            return {"input": d if d else "0", "expected_output": expected}

    if "instructions" in fields:
        ins = parse_quoted_string(fields["instructions"])
        if ins is not None:
            return {"input": ins, "expected_output": expected}

    if "root" in fields and "low" in fields and "high" in fields:
        root = parse_bracket_value(fields["root"])
        low = parse_scalar(fields["low"])
        high = parse_scalar(fields["high"])
        if isinstance(root, list):
            return {
                "input": array_stdin(root) + f" {low} {high}",
                "expected_output": expected,
            }

    if "image" in fields:
        grid = parse_bracket_value(fields["image"])
        sr = parse_scalar(fields.get("sr", "0"))
        sc = parse_scalar(fields.get("sc", "0"))
        color = parse_scalar(fields.get("newColor", "0"))
        if isinstance(grid, list):
            return {
                "input": grid_stdin(grid) + f" {sr} {sc} {color}",
                "expected_output": expected,
            }

    if "n" in fields and "bad" in fields:
        return {
            "input": f"{parse_scalar(fields['n'])} {parse_scalar(fields['bad'])}",
            "expected_output": expected,
        }

    if "numRows" in fields:
        return {"input": str(parse_scalar(fields["numRows"])), "expected_output": expected}

    if "x" in fields and "y" in fields:
        return {
            "input": f"{parse_scalar(fields['x'])} {parse_scalar(fields['y'])}",
            "expected_output": expected,
        }

    if "s" in fields and "k" in fields:
        s = parse_quoted_string(fields["s"])
        k = parse_scalar(fields["k"])
        if s is not None:
            return {"input": f"{s}\n{k}", "expected_output": expected}

    for key in ("prices", "nums", "height", "heights", "stones", "piles", "arr", "T"):
        if key in fields and "target" not in fields:
            arr = parse_bracket_value(fields[key])
            if isinstance(arr, list) and arr and not isinstance(arr[0], list):
                return {"input": array_stdin(arr), "expected_output": expected}

    if "head" in fields:
        arr = parse_bracket_value(fields["head"])
        if isinstance(arr, list):
            return {"input": array_stdin(arr), "expected_output": expected}

    if "grid" in fields or "matrix" in fields:
        key = "grid" if "grid" in fields else "matrix"
        grid = parse_bracket_value(fields[key])
        if isinstance(grid, list) and grid:
            return {"input": grid_stdin(grid), "expected_output": expected}

    if "num1" in fields and "num2" in fields:
        a = parse_quoted_string(fields["num1"])
        b = parse_quoted_string(fields["num2"])
        if a is not None and b is not None:
            return {"input": f"{a}\n{b}", "expected_output": expected}

    if "words" in fields and "order" in fields:
        words = parse_bracket_value(fields["words"])
        order = parse_quoted_string(fields["order"])
        if isinstance(words, list) and order is not None:
            return {
                "input": f"{len(words)}\n" + "\n".join(words) + f"\n{order}",
                "expected_output": expected,
            }

    if "haystack" in fields and "needle" in fields:
        h = parse_quoted_string(fields["haystack"])
        n = parse_quoted_string(fields["needle"])
        if h is not None and n is not None:
            return {"input": f"{h}\n{n}", "expected_output": expected}

    if "cpdomains" in fields:
        domains = parse_bracket_value(fields["cpdomains"])
        if isinstance(domains, list):
            return {
                "input": f"{len(domains)}\n" + "\n".join(domains),
                "expected_output": expected,
            }

    if "intervals" in fields:
        intervals = parse_bracket_value(fields["intervals"])
        if isinstance(intervals, list):
            parts = [str(len(intervals))]
            for a, b in intervals:
                parts.extend((str(a), str(b)))
            return {"input": " ".join(parts), "expected_output": expected}

    if "h" in fields and "w" in fields and "horizontalCuts" in fields:
        h = parse_scalar(fields["h"])
        w = parse_scalar(fields["w"])
        hc = parse_bracket_value(fields["horizontalCuts"])
        vc = parse_bracket_value(fields["verticalCuts"])
        if isinstance(hc, list) and isinstance(vc, list):
            stdin = f"{h} {w} {len(hc)} " + " ".join(map(str, hc)) + f" {len(vc)} " + " ".join(map(str, vc))
            return {"input": stdin, "expected_output": expected}

    for key in ("x", "n", "k"):
        if key in fields and len(fields) == 1:
            return {"input": str(parse_scalar(fields[key])), "expected_output": expected}

    if "s" in fields and len(fields) == 1:
        s = parse_quoted_string(fields["s"])
        if s is not None:
            return {"input": s, "expected_output": expected}

    list_keys = [k for k, v in fields.items() if str(v).strip().startswith("[")]
    scalar_keys = [k for k, v in fields.items() if not str(v).strip().startswith("[")]
    if list_keys:
        arr = parse_bracket_value(fields[list_keys[0]])
        if isinstance(arr, list):
            if arr and isinstance(arr[0], list):
                return {"input": grid_stdin(arr), "expected_output": expected}
            stdin = array_stdin(arr)
            if scalar_keys:
                stdin += " " + " ".join(str(parse_scalar(fields[sk])) for sk in scalar_keys)
            return {"input": stdin, "expected_output": expected}

    return None


def populate_problem(problem: dict) -> list[dict]:
    pid = problem.get("id")
    if pid in MANUAL_OVERRIDES:
        return MANUAL_OVERRIDES[pid]

    description = problem.get("description") or ""
    test_cases: list[dict] = []

    for ex in extract_examples(description):
        case = build_test_case(ex["input_raw"], ex["output_raw"])
        if case and is_configured(case):
            test_cases.append(case)

    if not test_cases:
        return [{"input": "", "expected_output": ""}]

    return test_cases


def is_configured(case: dict) -> bool:
    return bool((case.get("input") or "").strip() or (case.get("expected_output") or "").strip())


def main() -> None:
    data = json.loads(PROCESSED_PATH.read_text(encoding="utf-8"))
    populated = 0
    failed: list[str] = []

    for problem in data.get("problems", []):
        problem["test_cases"] = populate_problem(problem)
        if problem["test_cases"] and is_configured(problem["test_cases"][0]):
            populated += 1
        else:
            failed.append(f"{problem.get('id')}:{problem.get('title', '?')}")

    PROCESSED_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Wrote {PROCESSED_PATH}")
    print(f"  Configured: {populated}/{len(data.get('problems', []))}")
    if failed:
        print(f"  Still empty ({len(failed)}): {', '.join(failed)}")


if __name__ == "__main__":
    main()
