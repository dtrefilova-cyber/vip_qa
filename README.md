# VIP QA

Streamlit-застосунок оцінки коротких VIP-дзвінків (вердикт red/green).

Структура файлів повторює [QA-10](https://github.com/dtrefilova-cyber/QA-10):
точка входу `app.py`, картки `upload_cards.py`, оркестрація `app_vip.py`,
допоміжний шар `vip_ui.py`, архів `vip_archive.py`, спільний chrome/тема.

Ядро скорингу перенесено 1:1 з qa-deterministic:
`core/vip_short_scoring.py`, `vip_short_ai_assistant.py`, `prompts_vip_short.py`.

У VIP немає типів «Знайомство» і «Сервісні дзвінки».

## Деплой (Streamlit Cloud)

- **Repository:** `dtrefilova-cyber/vip_qa`
- **Branch:** `feature/vip-structure-qa10-style` (для тесту) або `main` після мерджу
- **Main file path:** `streamlit_app.py` (або `app.py`)

Секрети: `DEEPGRAM_API_KEY`, `OPENAI_API_KEY`, `gcp_service_account`, `SUPABASE_URL`, ключ Supabase.
