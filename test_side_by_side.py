import os
import sys

# Настраиваем пути
current_dir = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(current_dir, 'src')
sys.path.insert(0, src_path)

from src.gui.comparison_dialog import ComparisonDialog
from PyQt6.QtWidgets import QApplication


def test_side_by_side():
    """Тестирует side-by-side сравнение"""
    app = QApplication(sys.argv)

    print("🎬 Тестирование Side-by-Side сравнения")

    # Запрашиваем пути к видеофайлам
    video1 = input("Введите путь к первому видеофайлу: ").strip('"\'')
    video2 = input("Введите путь ко второму видеофайлу: ").strip('"\'')

    if not os.path.exists(video1) or not os.path.exists(video2):
        print("❌ Один из файлов не найден!")
        return

    # Создаем и показываем диалог сравнения
    dialog = ComparisonDialog([video1, video2])
    dialog.show()

    print("✅ Диалог сравнения открыт. Закройте его чтобы завершить тест.")

    app.exec()


if __name__ == "__main__":
    test_side_by_side()