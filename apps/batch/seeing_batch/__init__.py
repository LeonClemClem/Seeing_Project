# psycopg-binary and eccodeslib/eckitlib bundle conflicting native libraries: when ecCodes is
# loaded first, the process segfaults at interpreter exit (exit code 139, i.e. a failed Cloud Run
# task even after a successful run). Loading psycopg first avoids it.
import psycopg  # noqa: F401  (must stay before any seeing_core / eccodes import)
