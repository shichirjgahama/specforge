## запуск

```bash
pip install -r requirements.txt
python run.py
Windows: SpecForge.cmd
CLI
python -m specforge.cli demo          # полный демо-прогон и отчеты
python -m specforge.cli test          # 60 тестов
python -m specforge.cli trace         # матрица трассируемости
python -m specforge.cli properties    # 8 свойств
python -m specforge.cli impact CR-003 --reset
python -m specforge.cli report --run-tests --out data/report.html
тесты
python -m pytest
