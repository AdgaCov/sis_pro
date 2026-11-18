"""Paginación de una lista ya cargada (las alertas se calculan en Python, no en SQL)."""
from math import ceil


class Pagina:
    def __init__(self, elementos: list, pagina: int, por_pagina: int):
        self.total = len(elementos)
        self.per_page = por_pagina
        self.pages = max(1, ceil(self.total / por_pagina))
        self.page = min(max(1, pagina), self.pages)
        inicio = (self.page - 1) * por_pagina
        self.items = elementos[inicio:inicio + por_pagina]

    def iter_pages(self, borde: int = 2, alrededor: int = 2):
        ultimo = 0
        for n in range(1, self.pages + 1):
            if n <= borde or n > self.pages - borde or abs(n - self.page) <= alrededor:
                if ultimo and n - ultimo > 1:
                    yield None
                yield n
                ultimo = n
