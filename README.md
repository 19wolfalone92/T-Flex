# T-Flex Figurine Studio 0.4 — Hi3D 3.0 / монохромная печать / T-FLEX CAD 18

> **Quality-first policy (18.11.2026):** no new generator joins production without a same-reference blind test, neutral-clay geometry review and printer/slicer acceptance. Independent 2026 comparisons disagree on the universal winner; **Hi3D v3.0 is an optional third, credit-guarded candidate, not a guarantee of model quality**. [Evidence and gates](docs/QUALITY_FIRST_RESEARCH_20261118.md).

**Цель:** художественные фигурки людей, персонажей, животных и статуэтки. Для художественной геометрии доступен Tripo H3.1; для сравнения — Meshy 7.1. Blender помогает проверить модель и визуализировать четыре стороны, T-FLEX CAD получает подготовленные STL/OBJ.

## Что действительно работает

| Подсистема | Статус |
| --- | --- |
| Tripo API v3, ключ через GitHub Secret `TRIPO_AL` | ✅ Авторизация проверена через Actions |
| Tripo H3.1 high-detail, multiview, цветные/составные варианты | ✅ Код + offline тесты; платную генерацию не запускали |
| Meshy 7.1 Ultra single 4K / multiview 2K | ✅ Опциональный API-адаптер; GitHub требует отдельный MESHY_API_KEY; Meshy ChatGPT-плагин подключён независимо |
| Hi3D v3.0 (AK/SK) | ✅ Клиент официального API / 2048quality и 2048master / реальная авторизация проверяется отдельно read-only workflow |
| 1-цветная печать по частям | ✅ Скрипт Blender: две половины, 2 штифта, посадочные отверстия, калибровочная деталь, STL для печати и CAD |
| T-FLEX CAD 18 | ✅ Windows-подключение как внешняя пользовательская команда; это **не нативная CAD DLL**, нужен реальный Windows CAD для приёмки |
| Проверка фотографий и их согласованности | ✅ Измеримая диагностика, а не биометрическая проверка идентичности |
| Проверка STL/GLB/OBJ и масштабирование в мм | ✅ Python / тесты |
| Единый безопасный конвейер подготовки | ✅ QA → STL/OBJ → диагностический manifest |
| Скрипт Blender для 4 кадров | ✅ Код, **в установленном Blender пользователя не испытан** |
| Прямой нативный T-FLEX Open API | ⏳ Не реализован, нужна версия и Windows/лицензия |
| Автоматический контроль похожести на человека | ⏳ Не подтверждён, нужен визуальный контроль |
| Сертификация пригодности к 3D-печати | ⏳ Слайсер, материал и реальные испытания необходимы |

## Установка

Python 3.10–3.12:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux: source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest -q
```

### 1. Исходные фотографии

Для лучшей геометрии используйте **настоящие** фотографии спереди, сзади и по бокам с согласованными освещением и масштабом. Генерируемые нейросетью боковые ракурсы могут придумывать детали, которых нет в реальности.

```bash
tflex-reference --front private/front.png --left private/left.png --back private/back.png --right private/right.png --report reports/references.json
```

### 2. Tripo H3.1 — высокодетализированная геометрия

```bash
tflex-studio profiles
tflex-studio multiview --front private/front.png --back private/back.png --profile sculpt
```

По умолчанию это **dry-run**, ничего не списывается. После отдельного решения о платной генерации:

```bash
tflex-studio multiview --front private/front.png --back private/back.png --profile sculpt --yes-spend-credits
tflex-studio status TASK_ID --wait
tflex-studio download TASK_ID --output models/figurine.glb
```

Для цветного экранного 3D-персонажа вместо `sculpt` используйте `display` (8K texture, PBR; дороже). Для отдельных деталей — `parts` (без текстур). Список комбинаций и ограничения: **docs/QUALITY_STUDIO.md**.

Если фотография одна, можно сначала отдельно создать **предположительные** дополнительные виды с помощью `tflex-studio auto-views --image private/front.png --yes-spend-credits` и затем отдельно вызвать `tflex-studio from-views-task --task-id TASK_ID --yes-spend-credits`. **Это два платных задания**, а не бесплатное достраивание фактов.

### 3. Meshy 7.1 — альтернативный движок

Подключённый Meshy ChatGPT-плагин может генерировать модели по пользовательскому запросу. Для автономного GitHub/Windows-клиента требуется **отдельный** `MESHY_API_KEY`.

```bash
tflex-meshy submit --images private/front.png private/back.png --mode sculpt
```

Dry-run покажет максимальную поддерживаемую геометрию: **4K для одного изображения, 2K для нескольких**. Реальное создание только после `--yes-spend-credits`.

### 4. Независимый аудит / выбор

```bash
tflex-audit models/figurine.glb --report reports/mesh.json
tflex-audit models/tripo.glb models/meshy.glb --report reports/compare.json
```

Техническая проверка показывает замкнутость, разные оболочки и вырожденные грани. **Она не выбирает художественно лучший вариант автоматически.** Для этого требуется сравнение референса и четырёх рендеров.

### 5. Подготовка для T-FLEX

```bash
tflex-pipeline models/figurine.glb --height-mm 120 --up-axis y --output-dir builds/figurine_120
```

Результат: `exports/figurine.stl`, `exports/figurine.obj`, `manifest.json`, технические QA-отчёты. Если проверка сетки провалена, экспорт блокируется до исправления геометрии.

Опционально **при установленном Blender**:

```bash
tflex-pipeline models/figurine.glb --height-mm 120 --up-axis y --output-dir builds/figurine_120 --blender "C:/Program Files/Blender Foundation/Blender 4.5/blender.exe"
tflex-contact-sheet builds/figurine_120/turntable --output builds/figurine_120/turntable/comparison.png
```

Запускайте для каждого нового результата в **новой папке**, чтобы сохранить прежние отчёты.


## Hi3D 3.0 + разделение под одноцветный 3D-принтер

```bash
tflex-hi3d submit --front private/front.png --profile quality
# default dry run; actual generation only after explicit --yes-spend-credits
tflex-pipeline models/model.glb --height-mm 120 --up-axis y --output-dir builds/prepared-120
tflex-split builds/prepared-120/exports/model.stl --output-dir builds/split-120 --cut-ratio 0.50 --clearance-mm 0.20
```

**Подготовка состоит из реальных раздельных STL:** нижняя и верхняя половины, 2 отдельных соединительных штифта, пробная деталь для проверки зазора; `assembly/*.stl` содержат исходные координаты для установки в T-FLEX CAD 18. Программная топология не гарантирует пригодности к физической печати: требуется слайсер и тестовая посадка. Геометрический разрез пока **один плоский**, не автоматическое отделение головы, рук и волос.

Для интеграции без нативного T-FLEX Open API воспользуйтесь в CAD 18 командой **Настройка → Команды пользователя → Внешнее приложение** и укажите `scripts/windows/tflex18_prepare.cmd`. Она запустит генерацию STL на вашем компьютере через установленные Python и Blender (которых нет на стороне GitHub). [Подробная инструкция](docs/MONO_PRINT_TFLEX18.md).

## Разноцветная статуэтка на одноэкструдерном принтере

**Предпочтительнее делить фигурку по смысловым деталям, а не горизонтально через лицо/одежду.** Hi3D предлагает отдельную платную функцию `Split-to-Print`: 2–6 частей и штифтовые (`pin`) либо другие соединения.

```bash
tflex-hi3d split --mesh models/figurine.glb --kind character --template a --joint pin
# default DRY RUN, no credits; actual vendor split separately:
tflex-hi3d split --mesh models/figurine.glb --kind character --template a --joint pin --yes-spend-credits
tflex-hi3d split-status TASK_ID --wait
tflex-hi3d split-download TASK_ID --output models/figurine_parts.glb
tflex-extract-parts models/figurine_parts.glb --height-mm 120 --output-dir builds/figurine_parts
```

Получаем для каждого замкнутого элемента независимый `print/part_XX.stl` и синхронизированный `assembly/part_XX.stl`. Сами штифты, форма соединения и допуски ещё должны быть проверены на реальном принтере. Не нужно менять принтер на многоцветный: отдельные элементы можно печатать разными катушками по очереди.

**Альтернатива без оплаты Hi3D Split** — локальный `tflex-split`, который делает две части с двумя штифтами в Blender. Оба способа доступны, но ни один пока не сертифицирован реальной печатью.

## Критические ограничения

- 8K текстуры **не увеличивают** печатную детализацию STL; для печати важна геометрия и разрешение принтера.
- Гладкие закрытые поверхности **не гарантируют** необходимую толщину, устойчивость и отсутствие самопересечений.
- Tripo / Meshy могут галлюцинировать скрытые стороны и изменять черты лица.
- Blender-скрипт рендерит и анализирует, но **не вносит автоматических разрушительных правок**.
- Полигональная сетка STL/OBJ **не является** параметрической моделью T-FLEX.
- API-ключи и личные фото не помещать в публичный git. `models/`, `exports/`, `reports/`, `builds/`, `private/` исключены через .gitignore.

Монохромная печать, Hi3D, сборка и подключение CAD 18: **docs/MONO_PRINT_TFLEX18.md**. Детали: **docs/QUALITY_STUDIO.md**, **docs/TRIPO.md**, **docs/TFLEX_IMPORT.md**, **docs/INTEGRATIONS.md**, **docs/ROADMAP.md**.

Обновления проходят через отдельную feature-ветку и PR после успешного CI.


## Native Blender verification (Linux CI, without API charges)

The workflow `.github/workflows/blender-native-smoke.yml` installs **actual Blender** and processes a **synthetic 120-mm OBJ**, then produces eight matching views: textured front/left/back/right and `clay_` front/left/back/right. A grayscale clay pass deliberately removes the illusion of geometric detail painted into textures or normal maps. The workflow validates that rendered PNGs are nonblank and uploads both 2x2 contact sheets.

For a local figurine, generate geometry-only contact sheets with:

```bash
tflex-contact-sheet /path/to/blender/review --output clay_grid.png --prefix clay_
```

A successful native Blender CI proves only that the scripted Blender build can load and render **our synthetic test geometry**, not that your actual 3D sculpture is faithful or printable. Real AI-model and T-FLEX Windows import remain separate acceptance gates. Input images under 256px, invalid PNG/JPEG/WebP payloads, and corrupt uploads are rejected before credit-consuming API submission.
