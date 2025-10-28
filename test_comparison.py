import os
import sys

# Правильно добавляем путь к src
current_dir = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(current_dir, 'src')
sys.path.insert(0, src_path)

try:
    # Используем абсолютные импорты через пакет src
    from src.core.video_comparator import VideoComparator
    from src.core.file_scanner import FileScanner

    print("✅ Импорты успешны!")
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print("🔄 Пробуем альтернативный способ импорта...")

    # Альтернативный способ
    try:
        from core.video_comparator import VideoComparator
        from core.file_scanner import FileScanner

        print("✅ Импорты успешны (альтернативный способ)!")
    except ImportError as e2:
        print(f"❌ Альтернативный импорт тоже не сработал: {e2}")
        sys.exit(1)


def test_video_comparison():
    """Тестирует сравнение видеофайлов"""
    print("🎬 Тестирование системы сравнения видео")

    # Создаем компаратор
    comparator = VideoComparator()

    # Получаем пути к тестовым видео
    print("\n=== ПЕРВОЕ ВИДЕО ===")
    video1 = input("Введите путь к первому видеофайлу: ").strip('"\'')

    if not os.path.exists(video1):
        print("❌ Первый файл не найден!")
        return

    print("\n=== ВТОРОЕ ВИДЕО ===")
    video2 = input("Введите путь ко второму видеофайлу: ").strip('"\'')

    if not os.path.exists(video2):
        print("❌ Второй файл не найден!")
        return

    print(f"\n🔄 Сравниваем:\n  1. {os.path.basename(video1)}\n  2. {os.path.basename(video2)}")

    # Сравниваем видео
    result = comparator.compare_videos(video1, video2)

    # Выводим результаты
    print("\n📊 РЕЗУЛЬТАТЫ СРАВНЕНИЯ:")
    print(f"🎯 Общая схожесть: {result['similarity']:.2%}")

    if 'error' in result:
        print(f"❌ Ошибка: {result['error']}")
        return

    print(f"📹 Извлечено кадров: {result['frames_extracted']['video1']} и {result['frames_extracted']['video2']}")

    print("\n🔍 Детали по кадрам:")
    for i, comparison in enumerate(result['frame_comparisons']):
        print(f"  Кадр {i + 1}: схожесть {comparison['similarity']:.2%}")
        for algo_name, algo_score in comparison['algorithm_details'].items():
            if algo_name != 'overall':
                print(f"    - {algo_name}: {algo_score:.2%}")

    print(f"\n⚖️ Веса алгоритмов:")
    for algo_name, weight in result['algorithm_weights'].items():
        print(f"  - {algo_name}: {weight:.0%}")


def test_multiple_videos():
    """Тестирует поиск похожих видео в папке"""
    print("\n🔍 Тестирование поиска похожих видео в папке")

    folder = input("Введите путь к папке с видео: ").strip('"\'')

    if not os.path.exists(folder):
        print("❌ Папка не найдена!")
        return

    scanner = FileScanner()
    video_files = scanner.find_video_files(folder)

    if not video_files:
        print("❌ В папке не найдено видеофайлов!")
        return

    print(f"📁 Найдено видеофайлов: {len(video_files)}")

    # Запрашиваем порог схожести
    try:
        threshold = float(input("Введите порог схожести (0.1-1.0, по умолчанию 0.7): ") or "0.7")
        threshold = max(0.1, min(1.0, threshold))
    except:
        threshold = 0.7

    print(f"🎯 Порог схожести: {threshold:.0%}")

    # Ищем похожие видео
    comparator = VideoComparator()
    similar_pairs = comparator.find_similar_videos(video_files, threshold)

    print(f"\n📊 НАЙДЕНО ПОХОЖИХ ПАР: {len(similar_pairs)}")

    for i, (video1, video2, similarity, details) in enumerate(similar_pairs):
        print(f"\n{i + 1}. {os.path.basename(video1)} <-> {os.path.basename(video2)}")
        print(f"   Схожесть: {similarity:.2%}")
        print(f"   Детали: {len(details['frame_comparisons'])} сравнений кадров")


if __name__ == "__main__":
    print("🎬 VideoDuplicate Cleaner - Тестирование алгоритмов сравнения")

    while True:
        print("\n" + "=" * 50)
        print("Выберите тип теста:")
        print("1 - Сравнить два конкретных видео")
        print("2 - Найти похожие видео в папке")
        print("q - Выход")
        print("=" * 50)

        choice = input("Ваш выбор: ").strip()

        if choice == '1':
            test_video_comparison()
        elif choice == '2':
            test_multiple_videos()
        elif choice.lower() in ['q', 'quit', 'exit']:
            print("👋 До свидания!")
            break
        else:
            print("❌ Неверный выбор, попробуйте снова")