"""
VideoDuplicate Cleaner - Main Entry Point
"""
import sys
import os

# Добавляем текущую директорию в путь для импортов
sys.path.insert(0, os.path.dirname(__file__))

from core.file_scanner import FileScanner
from core.frame_extractor import FrameExtractor
from core.video_comparator import VideoComparator


def main():
    print("VideoDuplicate Cleaner - Консольная версия")
    print("=" * 50)

    scanner = FileScanner()
    extractor = FrameExtractor()
    comparator = VideoComparator()

    while True:
        print("\nВыберите действие:")
        print("1 - Найти видеофайлы в папке")
        print("2 - Сравнить два видеофайла")
        print("3 - Найти похожие видео в папке")
        print("q - Выход")

        choice = input("Ваш выбор: ").strip()

        if choice == '1':
            folder = input("Введите путь к папке: ").strip('"\'')
            if os.path.exists(folder):
                videos = scanner.find_video_files(folder)
                print(f"Найдено видеофайлов: {len(videos)}")
                for video in videos:
                    print(f"  - {video}")
            else:
                print("Папка не найдена!")

        elif choice == '2':
            video1 = input("Введите путь к первому видео: ").strip('"\'')
            video2 = input("Введите путь ко второму видео: ").strip('"\'')

            if os.path.exists(video1) and os.path.exists(video2):
                result = comparator.compare_videos(video1, video2)
                print(f"Схожесть: {result['similarity']:.2%}")
            else:
                print("Один из файлов не найден!")

        elif choice == '3':
            folder = input("Введите путь к папке: ").strip('"\'')
            threshold = float(input("Порог схожести (0.1-1.0): ") or "0.7")

            if os.path.exists(folder):
                videos = scanner.find_video_files(folder)
                similar_pairs = comparator.find_similar_videos(videos, threshold)

                print(f"Найдено похожих пар: {len(similar_pairs)}")
                for video1, video2, similarity, _ in similar_pairs:
                    print(f"  {os.path.basename(video1)} <-> {os.path.basename(video2)}: {similarity:.2%}")
            else:
                print("Папка не найдена!")

        elif choice.lower() == 'q':
            print("До свидания!")
            break
        else:
            print("Неверный выбор!")


if __name__ == "__main__":
    main()