"""
Простой тест для проверки импортов
"""
import os
import sys

def test_imports():
    print("🧪 Тестирование импортов...")

    # Добавляем src в путь
    current_dir = os.path.dirname(os.path.abspath(__file__))
    src_path = os.path.join(current_dir, 'src')
    sys.path.insert(0, src_path)

    tests = [
        ("src.core", "FileScanner"),
        ("src.core", "FrameExtractor"),
        ("src.core", "VideoComparator"),
        ("src.algorithms", "BaseComparator"),
        ("src.algorithms", "HistogramComparator"),
        ("src.algorithms", "PHashComparator"),
        ("src.algorithms", "ComparisonManager"),
    ]

    all_passed = True

    for package_name, class_name in tests:
        try:
            # Импортируем весь пакет
            module = __import__(package_name, fromlist=[class_name])
            # Получаем класс из модуля
            cls = getattr(module, class_name)
            # Пробуем создать экземпляр (кроме BaseComparator, так как он абстрактный)
            if class_name != "BaseComparator":
                instance = cls()
                print(f"✅ {package_name}.{class_name} - УСПЕХ (создан экземпляр)")
            else:
                print(f"✅ {package_name}.{class_name} - УСПЕХ (абстрактный класс)")
        except Exception as e:
            print(f"❌ {package_name}.{class_name} - ОШИБКА: {e}")
            all_passed = False

    if all_passed:
        print("\n🎉 Все импорты работают корректно!")
    else:
        print("\n💥 Некоторые импорты не работают!")

    return all_passed

if __name__ == "__main__":
    test_imports()