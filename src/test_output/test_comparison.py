import os
import sys

# Правильно добавляем путь к src
current_dir = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(current_dir, 'src')
sys.path.insert(0, src_path)


def test_pair_comparison():
    """Тестирует сравнение конкретной пары"""
    print("\n🔍 Тестирование сравнения пары видео")

    video1 = input("Введите путь к первому видео: ").strip('"\'')
    video2 = input("Введите путь ко второму видео: ").strip('"\'')

    if not os.path.exists(video1) or not os.path.exists(video2):
        print("❌ Один из файлов не найден!")
        return

    try:
        from src.gui.comparison_dialog import ComparisonDialog
        from PyQt6.QtWidgets import QApplication

        app = QApplication(sys.argv)
        dialog = ComparisonDialog([video1, video2])
        dialog.show()
        print("✅ Диалог сравнения открыт успешно! Закройте окно чтобы завершить тест.")
        app.exec()

    except Exception as e:
        print(f"❌ Ошибка при открытии диалога: {e}")


# ДОБАВЬТЕ ЭТОТ ВЫЗОВ В КОНЦЕ ФАЙЛА:
if __name__ == "__main__":
    test_pair_comparison()