# Tripo AI API v3: настройка 3D-фигурок

Документация Tripo: https://developers.tripo3d.ai/en/docs/quick-start

**Tripo API не является плагином внутри T-FLEX CAD.** Этот репозиторий содержит отдельный Python-клиент для внешней AI-генерации, импорта в T-FLEX через сеточные форматы и последующей проверки геометрии.

## 1. Безопасно подключить созданный ключ

В Windows PowerShell:

    $env:TRIPO_API_KEY = "ВАШ_КЛЮЧ_TRIPO"
    python -m pip install -e ".[dev]"
    tflex-tripo balance

Не вставляйте реальный ключ в GitHub README, issue, PR или чат и не публикуйте его на скриншотах.

**GitHub Actions:** в 19wolfalone92/T-Flex откройте Settings → Secrets and variables → Actions → New repository secret. Имя: **TRIPO_API_KEY**. Значение: созданный ключ. Затем откройте Actions → Tripo v3 check key (read-only) → Run workflow. Эта ручная проверка использует GET /account/balance; генерации моделей и расхода кредитов нет.

Важно: добавление GitHub Secret **не подключает Tripo напрямую к ChatGPT**. У ChatGPT пока нет подключённого Tripo-плагина, а секрет из GitHub нельзя прочесть обратно через чат.

## 2. Генерация по тексту

Предпросмотр параметров, без обращения к API и списаний:

    tflex-tripo submit-text --prompt "Cute seated fox figurine on a solid base, printable, no thin parts"

После явного разрешения списания кредитов добавьте флаг:

    tflex-tripo submit-text --prompt "Cute seated fox figurine on a solid base, printable, no thin parts" --yes-spend-credits

Команда выдаёт **task_id**. Сохраните его. Важно: если POST потерял ответ по сети, не отправляйте заявку повторно автоматически — возможна повторная оплата.

## 3. Генерация по фотографии

Файл остаётся локальным в публичном GitHub, но будет передан Tripo при настоящем запуске:

    tflex-tripo submit-image --image "C:\Private\ref.png"
    tflex-tripo submit-image --image "C:\Private\ref.png" --yes-spend-credits

Допускаются PNG/JPEG не более 20 МиБ. Перед передачей изображений людей убедитесь в наличии необходимых прав и согласий.

## 4. Забрать результат и обработать под T-FLEX

    tflex-tripo status TASK_ID --wait --timeout 300
    tflex-tripo download TASK_ID --output models/fox.glb
    tflex-figurines inspect models/fox.glb --report reports/fox.json
    tflex-figurines prepare models/fox.glb --height-mm 120 --up-axis y --output-dir exports

Если нужны текстуры, у команды submit-text / submit-image есть --texture. Для обычной 3D-печати текстуры отключены по умолчанию.

Ссылки Tripo на сгенерированные файлы могут быстро истекать; скачайте GLB вскоре после генерации. Программа не перезаписывает уже существующий файл.

**Ограничения:** GLB/STL/OBJ — полигональные файлы. Это не параметрическая CAD-модель T-FLEX. Полноценная проверка пригодности к печати требует оценки толщин, устойчивости, опор и слайсера, а реальный импорт в T-FLEX требует установленного CAD.

## Команды

| Команда | Эффект | Новые генерационные списания |
| --- | --- | --- |
| tflex-tripo balance | Проверка авторизации и баланса | Нет |
| tflex-tripo submit-text | Dry-run по умолчанию | Только --yes-spend-credits |
| tflex-tripo submit-image | Dry-run по умолчанию | Только --yes-spend-credits |
| tflex-tripo status TASK_ID | Проверка/ожидание статуса | Нет |
| tflex-tripo download TASK_ID --output FILE.glb | Скачивание модели | Нет |

Мок-тесты в CI не доказывают, что ключ пользователя уже подключён. Для этого нужна отдельная ручная проверка через GitHub Secret или локальный PowerShell.
