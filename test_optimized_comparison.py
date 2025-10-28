import os
import sys
import time

# Настраиваем пути
current_dir = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(current_dir, 'src')
sys.path.insert(0, src_path)

from core.optimized_comparator import OptimizedVideoComparator
from core.file_scanner import FileScanner


def test_optimized_comparison():
    """Тестирует оптимизированную версию сравнения"""
    print("🚀 Тестирование ОПТИМИЗИРОВАННОЙ системы сравнения")

    # Создаем компаратор
    comparator = OptimizedVideoComparator()

    # Получаем папку для тестирования
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
    print("⏱️ Запускаем оптимизированный поиск...")

    start_time = time.time()

    # Ищем похожие видео
    similar_pairs = comparator.find_similar_videos_optimized(video_files, threshold)

    end_time = time.time()
    execution_time = end_time - start_time

    print(f"\n✅ Поиск завершен за {execution_time:.1f} секунд")
    print(f"📊 Найдено похожих пар: {len(similar_pairs)}")

    for i, (video1, video2, similarity, details) in enumerate(similar_pairs):
        print(f"\n{i + 1}. {os.path.basename(video1)} <-> {os.path.basename(video2)}")
        print(f"   Схожесть: {similarity:.2%}")

        if 'type' in details:
            print(f"   Тип: {details['type']}")
        else:
            print(f"   Детали: {len(details['frame_comparisons'])} сравнений кадров")


def compare_with_old_version():
    """Сравнивает производительность со старой версией"""
    print("\n🔍 Сравнение производительности")

    from core.video_comparator import VideoComparator

    folder = input("Введите путь к папке с видео (для теста): ").strip('"\'')

    if not os.path.exists(folder):
        print("❌ Папка не найдена!")
        return

    scanner = FileScanner()
    video_files = scanner.find_video_files(folder)

    if len(video_files) > 20:
        print(f"⚠️ Слишком много файлов ({len(video_files)}). Берем первые 20 для теста.")
        video_files = video_files[:20]

    print(f"📁 Тестируем на {len(video_files)} файлах")

    # Тестируем старую версию
    print("\n🧪 Тестируем СТАРУЮ версию...")
    old_comparator = VideoComparator()
    start_time = time.time()
    old_results = old_comparator.find_similar_videos(video_files, 0.7)
    old_time = time.time() - start_time

    print(f"⏱️ Старая версия: {old_time:.1f} сек, найдено пар: {len(old_results)}")

    # Тестируем новую версию
    print("\n🧪 Тестируем НОВУЮ версию...")
    new_comparator = OptimizedVideoComparator()
    start_time = time.time()
    new_results = new_comparator.find_similar_videos_optimized(video_files, 0.7)
    new_time = time.time() - start_time

    print(f"⏱️ Новая версия: {new_time:.1f} сек, найдено пар: {len(new_results)}")

    print(f"\n📈 Ускорение: {old_time / new_time:.1f}x")

    # Сравниваем результаты
    old_pairs = set((min(v1, v2), max(v1, v2)) for v1, v2, _, _ in old_results)
    new_pairs = set((min(v1, v2), max(v1, v2)) for v1, v2, _, _ in new_results)

    common_pairs = old_pairs & new_pairs
    only_old = old_pairs - new_pairs
    only_new = new_pairs - old_pairs

    print(f"\n📊 Сравнение результатов:")
    print(f"  Общие пары: {len(common_pairs)}")
    print(f"  Только в старой версии: {len(only_old)}")
    print(f"  Только в новой версии: {len(only_new)}")


if __name__ == "__main__":
    print("🎬 VideoDuplicate Cleaner - Оптимизированное сравнение")

    while True:
        print("\n" + "=" * 50)
        print("Выберите тип теста:")
        print("1 - Оптимизированный поиск в папке")
        print("2 - Сравнение старой и новой версии")
        print("q - Выход")
        print("=" * 50)

        choice = input("Ваш выбор: ").strip()

        if choice == '1':
            test_optimized_comparison()
        elif choice == '2':
            compare_with_old_version()
        elif choice.lower() in ['q', 'quit', 'exit']:
            print("👋 До свидания!")
            break
        else:
            print("❌ Неверный выбор, попробуйте снова")