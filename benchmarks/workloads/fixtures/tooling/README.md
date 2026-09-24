# Tooling workload fixtures

These fixtures are a checked-in, purpose-built catalog/index service used by
the source tooling workloads. The Python package is split into domain,
storage, query, and adapter modules so pylint and compileall traverse a real
import graph rather than a generated single-file loop. The C inputs are
preprocessed translation units: includes and macros have already been
expanded, and each file contains the declarations and inline code needed to
parse it independently.

The fixtures are benchmark inputs. Do not replace them with the live
repository tree or modify them during a run. Changes to this corpus change
benchmark results and should be reviewed like changes to any other benchmark
input.

The Python fixture code and C declarations were written for this benchmark.
They do not contain copied third-party source.
