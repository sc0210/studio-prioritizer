import sys

from .cli import main

# Guarded because spawned worker processes re-import this module.
if __name__ == "__main__":
    sys.exit(main())
