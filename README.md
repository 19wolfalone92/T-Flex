# T-Flex Figurine Studio 0.3 — профессиональный 3D-конвейер

**Цель:** художественные фигурки людей, персонажей, животных и статуэтки. Для художественной геометрии доступен Tripo H3.1; для сравнения — Meshy 7.1. Blender помогает проверить модель и визуализировать четыре стороны, T-FLEX CAD получает подготовленные STL/OBJ.

## Что действительно работает

| Подсистема | Статус |
| --- | --- |
| Tripo API v3, ключ через GitHub Secret `TRIPO_AL` | ✅ Авторизация проверена через Actions |
| Tripo H3.1 high-detail, multiview, цветные/составные варианты | ✅ Код + offline тесты; платную генерацию не запускали |
| Meshy 7.1 Ultra single 4K / multiview 2K | ✅ Опциональный API-адаптер; GitHub требует отдельный MESHY_API_KEY; Meshy ChatGPT-плагин подключён независимо |
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

## Критические ограничения

- 8K текстуры **не увеличивают** печатную детализацию STL; для печати важна геометрия и разрешение принтера.
- Гладкие закрытые поверхности **не гарантируют** необходимую толщину, устойчивость и отсутствие самопересечений.
- Tripo / Meshy могут галлюцинировать скрытые стороны и изменять черты лица.
- Blender-скрипт рендерит и анализирует, но **не вносит автоматических разрушительных правок**.
- Полигональная сетка STL/OBJ **не является** параметрической моделью T-FLEX.
- API-ключи и личные фото не помещать в публичный git. `models/`, `exports/`, `reports/`, `builds/`, `private/` исключены через .gitignore.

Детали: **docs/QUALITY_STUDIO.md**, **docs/TRIPO.md**, **docs/TFLEX_IMPORT.md**, **docs/INTEGRATIONS.md**, **docs/ROADMAP.md**.

Обновления проходят через отдельную feature-ветку и PR после успешного CI.
