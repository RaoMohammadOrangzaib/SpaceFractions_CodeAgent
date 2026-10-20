"""Entry point for the double-click Windows app (PyInstaller target)."""
import sys

if len(sys.argv) > 1:  # allow `CodeAgent.exe --doc ... --views ... --out ...` for headless use
    from codeagent.cli import main
    raise SystemExit(main())

from codeagent.gui import main

if __name__ == "__main__":
    main()
