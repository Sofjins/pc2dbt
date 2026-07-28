"""Per-transformation-type SQL fragment generation.

Each function takes a Transformation (plus whatever upstream context it
needs) and returns the SELECT list / FROM / JOIN / GROUP BY pieces for that
transformation's CTE. generators.py never touches XML or does topological
sorting - that's parser.py and graph.py's job.
"""

from pc2dbt.ir import Transformation
