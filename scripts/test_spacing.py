from rich.console import Console
from rich.table import Table

console = Console(width=80)

table = Table(
    box=None,
    show_header=False,
    show_edge=False,
    pad_edge=False,
    padding=(0, 1),
)

for _ in range(10):
    table.add_column(justify="center", width=3)

for y in range(1):
    row = ["[bold green]✓[/bold green]"] * 10
    table.add_row(*row)

import io
buf = io.StringIO()
c2 = Console(file=buf, width=80)
c2.print(table)
result = buf.getvalue().strip()
print("REPR:")
print(repr(result))
