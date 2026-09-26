# Встроенные шрифты

Картинка расписания рисуется шрифтом из этого каталога, а не системным,
поэтому она выглядит одинаково на любом компьютере.

| Файл | Начертание |
|------|------------|
| `Roboto-Regular.ttf` | обычный |
| `Roboto-Bold.ttf` | полужирный (заголовки, дни, предметы) |

## Лицензия

Roboto распространяется по SIL Open Font License 1.1 — текст лицензии
в `OFL.txt`. Шрифт можно свободно использовать, в том числе в коммерческих
проектах; менять файлы нельзя, но их можно переименовать.

## Как обновить

Файлы — статические начертания, полученные из вариативного
`Roboto[wdth,wght].ttf` из репозитория Google Fonts.

```bash
curl -sLO "https://raw.githubusercontent.com/google/fonts/main/ofl/roboto/Roboto%5Bwdth%2Cwght%5D.ttf"
curl -sLO "https://raw.githubusercontent.com/google/fonts/main/ofl/roboto/OFL.txt"

fonttools varLib.instancer "Roboto[wdth,wght].ttf" wdth=100 wght=400 \
    -o Roboto-Regular.ttf --update-name-table
fonttools varLib.instancer "Roboto[wdth,wght].ttf" wdth=100 wght=700 \
    -o Roboto-Bold.ttf --update-name-table
```

После замены файлов стоит убедиться, что кириллица на месте:

```bash
python -m pytest tests/test_schedule_image_fonts.py
```

## Если файлов нет

`ulstu/schedule_image.py` сначала ищет шрифт здесь, и только если файла нет —
использует системный (`Arial`, `DejaVu Sans`, `Liberation Sans`).
В этом случае в лог пишется предупреждение `Не найден шрифт`.
Файл `.gitignore` не исключает `.ttf`, поэтому при клонировании репозитория
шрифты должны попасть на диск.
