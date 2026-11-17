# T-Flex Figurines — Tripo / Meshy → GLB → T-FLEX CAD

Проект художественных 3D-фигурок: люди, персонажи, животные, статуэтки.

Система содержит **Tripo AI API v3-клиент** для текстовой генерации, создания модели из изображения, проверки задания и скачивания GLB. Meshy 3D можно использовать через подключённый ChatGPT-плагин.

## Быстрая проверка Tripo

    python -m pip install -e ".[dev]"
    tflex-tripo balance

Для проверки должен быть задан **TRIPO_API_KEY** как переменная окружения. В GitHub Actions используется существующий секрет **TRIPO_AL**, который передаётся программе как переменная **TRIPO_API_KEY**; для локального запуска по-прежнему нужна переменная TRIPO_API_KEY. Секрет никогда не коммитить. Подробная настройка Windows и GitHub: **docs/TRIPO.md**.

## Генерация без неожиданного списания

Предпросмотр без обращения к API:

    tflex-tripo submit-text --prompt "Cute fox statue with solid base"

Настоящая кредитная генерация только с флагом:

    tflex-tripo submit-text --prompt "Cute fox statue with solid base" --yes-spend-credits
    tflex-tripo status TASK_ID --wait --timeout 300
    tflex-tripo download TASK_ID --output models/fox.glb

Для фотографии используйте submit-image --image PRIVATE.png --yes-spend-credits.

## Подготовка под T-FLEX

    tflex-figurines inspect models/fox.glb --report reports/fox.json
    tflex-figurines prepare models/fox.glb --height-mm 120 --up-axis y --output-dir exports

На выходе STL/OBJ, координаты с масштабом в мм. При незамкнутой сетке экспорт блокируется; осознанный режим --allow-open не делает сетку готовой к печати.

**Это полигональная сетка, не параметрическая CAD-модель.** Дополнительно проверяйте толщины, нависания, устойчивость в слайсере. T-FLEX Open API пока не интегрирован с установленным CAD.

## Честный статус

- Программная интеграция Tripo v3 и тесты подготовлены.
- Пользователь сообщил о GitHub Secret **TRIPO_AL**. Реальную авторизацию проверяет workflow; сам ключ из чата недоступен.
- Реальные кредитные генерации Tripo не запускались.
- Работу на компьютере в T-FLEX надо проверить отдельно.

Документация: **docs/TRIPO.md**, **docs/TFLEX_IMPORT.md**, **docs/INTEGRATIONS.md**, **docs/ROADMAP.md**.

## Тесты

    python -m pip install -e ".[dev]"
    pytest -q

Основной CI использует только моки, не требует ключа и не расходует кредиты. Отдельная ручная GitHub Actions проверка TRIPO_API_KEY выполняет только GET /account/balance.
