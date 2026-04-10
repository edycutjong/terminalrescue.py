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

for y in range(4):
    row = ["[bold green]✓[/bold green]"] * 10
    table.add_row(*row)

print("WITH pad_edge=False, padding=(0,1), width=3")
console.print(table)


table2 = Table(
    box=None,
    show_header=False,
    show_edge=False,
    pad_edge=True,
    padding=(0, 1),
)

for _ in range(10):
    table2.add_column(justify="center", width=3)

for y in range(4):
    row2 = ["[bold green]✓[/bold green]"] * 10
    table2.add_row(*row2)

print("WITH pad_edge=True, padding=(0,1), width=3")
console.print(table2)
