"""
Простой рабочий тест, который гарантированно должен работать
"""
import os
import sys


def setup_imports():
    """Настраивает пути импорта"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    src_path = os.path.join(current_dir, 'src')

    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    return src_path


def test_basic_functionality():
    """Тестирует базовую функциональность без сложных импортов"""
    print("🧪 Тестируем базовую функциональность...")

    setup_imports()

    try:
        # Тестируем только базовые модули
        from core.file_scanner import FileScanner
        from core.frame_extractor import FrameExtractor

        print("✅ Базовые модули загружены успешно")

        # Тестируем FileScanner
        scanner = FileScanner()
        test_dir = os.path.dirname(__file__)
        videos = scanner.find_video_files(test_dir)
        print(f"✅ FileScanner: Найдено {len(videos)} видеофайлов в тестовой директории")

        # Тестируем FrameExtractor
        extractor = FrameExtractor()
        print("✅ FrameExtractor создан успешно")

        # Если есть видеофайлы, тестируем извлечение кадров
        if videos:
            test_video = videos[0]
            print(f"🔄 Тестируем извлечение кадров из: {os.path.basename(test_video)}")

            frames = extractor.extract_frames(test_video, 3)
            print(f"✅ Успешно извлечено {len(frames)} кадров")
        else:
            print("ℹ️ Видеофайлы для теста не найдены")

        return True

    except Exception as e:
        print(f"❌ Ошибка в базовой функциональности: {e}")
        return False


def test_algorithms_separately():
    """Тестирует алгоритмы по отдельности"""
    print("\n🧪 Тестируем алгоритмы по отдельности...")

    setup_imports()

    try:
        from algorithms.histogram_comparator import HistogramComparator
        from algorithms.phash_comparator import PHashComparator

        print("✅ Алгоритмы загружены успешно")

        # Создаем тестовые изображения
        import cv2
        import numpy as np

        # Простое тестовое изображение 1
        img1 = np.ones((100, 100, 3), dtype=np.uint8) * 255  # Белый квадрат

        # Простое тестовое изображение 2
        img2 = np.ones((100, 100, 3), dtype=np.uint8) * 128  # Серый квадрат

        # Тестируем гистограммы
        hist_comp = HistogramComparator()
        hist_score = hist_comp.compare(img1, img2)
        print(f"✅ HistogramComparator: схожесть = {hist_score:.2%}")

        # Тестируем pHash
        phash_comp = PHashComparator()
        phash_score = phash_comp.compare(img1, img2)
        print(f"✅ PHashComparator: схожесть = {phash_score:.2%}")

        return True

    except Exception as e:
        print(f"❌ Ошибка в алгоритмах: {e}")
        return False


def test_video_comparator_directly():
    """Прямое тестирование VideoComparator"""
    print("\n🧪 Прямое тестирование VideoComparator...")

    setup_imports()

    try:
        # Прямой импорт с полным путем
        import src.core.video_comparator as vc_module
        comparator = vc_module.VideoComparator()
        print("✅ VideoComparator создан успешно!")
        return True

    except Exception as e:
        print(f"❌ Ошибка в VideoComparator: {e}")

        # Пробуем альтернативный способ
        try:
            from src.core.video_comparator import VideoComparator
            comparator = VideoComparator()
            print("✅ VideoComparator создан успешно (альтернативный способ)!")
            return True
        except Exception as e2:
            print(f"❌ Альтернативный способ тоже не сработал: {e2}")
            return False


if __name__ == "__main__":
    print("🎬 VideoDuplicate Cleaner - Комплексный тест")
    print("=" * 60)

    results = []

    results.append(("Базовая функциональность", test_basic_functionality()))
    results.append(("Алгоритмы сравнения", test_algorithms_separately()))
    results.append(("VideoComparator", test_video_comparator_directly()))

    print("\n" + "=" * 60)
    print("📊 ИТОГИ ТЕСТИРОВАНИЯ:")

    all_passed = True
    for test_name, passed in results:
        status = "✅ ПРОЙДЕН" if passed else "❌ НЕ ПРОЙДЕН"
        print(f"  {test_name}: {status}")
        if not passed:
            all_passed = False

    if all_passed:
        print("\n🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
    else:
        print("\n💥 НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОЙДЕНЫ!")

        print("\n🔧 Рекомендации по исправлению:")
        print("1. Проверьте структуру папок и файлы __init__.py")
        print("2. Убедитесь, что все файлы существуют")
        print("3. Попробуйте перезапустить PyCharm")
        print("4. Проверьте, что в настройках проекта правильно указан Python interpreter")