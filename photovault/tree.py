"""Дерево папок пользователя: путь, вложенность, подсчёт файлов."""

from collections import defaultdict


class Tree:
    """Все папки пользователя в памяти: путь, вложенность, подсчёт файлов."""

    def __init__(self, folders: list[dict], own: dict[int, int]):
        self.by_id = {f["id"]: f for f in folders}
        self.children: dict[int, list[dict]] = defaultdict(list)
        for f in folders:
            self.children[f["parent_id"]].append(f)
        self.own = own

    def subtree_ids(self, fid: int) -> list[int]:
        out, stack = [], [fid]
        while stack:
            cur = stack.pop()
            out.append(cur)
            stack.extend(c["id"] for c in self.children.get(cur, []))
        return out

    def total(self, fid: int) -> int:
        return sum(self.own.get(i, 0) for i in self.subtree_ids(fid))

    def path(self, fid: int) -> str:
        names, cur = [], fid
        while cur and cur in self.by_id:
            names.append(self.by_id[cur]["name"])
            cur = self.by_id[cur]["parent_id"]
        return " / ".join(reversed(names))

    def depth(self, fid: int) -> int:
        d, cur = 0, fid
        while cur and cur in self.by_id:
            d += 1
            cur = self.by_id[cur]["parent_id"]
        return d  # корневая папка = 1

    def walk(self, root_id: int) -> list[tuple[dict, str]]:
        """Обход в глубину: (папка, путь относительно корня обхода, включая её имя)."""
        out: list[tuple[dict, str]] = []

        def rec(fid: int, prefix: str) -> None:
            f = self.by_id[fid]
            p = f["name"] if not prefix else f"{prefix} / {f['name']}"
            out.append((f, p))
            for c in self.children.get(fid, []):
                rec(c["id"], p)

        rec(root_id, "")
        return out