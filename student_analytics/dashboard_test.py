"""Headless render test for every dashboard page.

Executes each Streamlit script with the AppTest harness and reports any
exception, so page-level bugs are caught without clicking through a browser.

    python -m student_analytics.dashboard_test
"""
from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

DASH = Path(__file__).resolve().parent / "dashboard"
TIMEOUT = 300


def pages() -> list[Path]:
    return [DASH / "Home.py"] + sorted((DASH / "pages").glob("*.py"))


def main() -> int:
    failures = []
    for page in pages():
        at = AppTest.from_file(str(page), default_timeout=TIMEOUT).run()
        if at.exception:
            failures.append((page.name, [e.message for e in at.exception]))
            print(f"  FAIL {page.name}")
            for e in at.exception:
                print(f"       {e.message}")
                if e.stack_trace:
                    print("       " + "\n       ".join(e.stack_trace[-6:]))
        else:
            n = (len(at.dataframe) + len(at.metric) + len(at.markdown)
                 + len(at.tabs) + len(at.columns))
            print(f"  OK   {page.name:38s} widgets={n:3d} charts={len(at.dataframe):2d} "
                  f"st.error={len(at.error)} st.warning={len(at.warning)}")
            # st.error/st.warning are used intentionally for red/amber insight cards,
            # so they are informational here rather than failures.
            for e in at.error:
                print(f"       error card: {str(e.value)[:110]}")
    print()
    if failures:
        print(f"{len(failures)} page(s) failed to render.")
        return 1
    print(f"All {len(pages())} pages render cleanly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
