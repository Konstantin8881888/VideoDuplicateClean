import os
from typing import List, Dict, Tuple
from src.config import Config

# Абсолютные импорты вместо относительных
from src.algorithms.comparison_manager import ComparisonManager
from src.core.frame_extractor import FrameExtractor


class VideoComparator:
    """Сравнивает два видеофайла используя несколько алгоритмов"""

    def __init__(self):
        self.frame_extractor = FrameExtractor()
        self.comparison_manager = ComparisonManager()
        self.num_frames_to_compare = Config.DEFAULT_FRAMES_TO_COMPARE  # Количество кадров для сравнения

    def compare_videos(self, video_path1: str, video_path2: str) -> Dict:
        """
        Сравнивает два видеофайла
        Возвращает детализированные результаты сравнения
        """
        print(f"Сравниваем видео: {os.path.basename(video_path1)} и {os.path.basename(video_path2)}")

        # Извлекаем кадры из обоих видео
        frames1 = self.frame_extractor.extract_frames(video_path1, self.num_frames_to_compare)
        frames2 = self.frame_extractor.extract_frames(video_path2, self.num_frames_to_compare)

        if not frames1 or not frames2:
            return {
                'similarity': 0.0,
                'error': 'Не удалось извлечь кадры из одного из видео',
                'details': {}
            }

        print(f"Извлечено {len(frames1)} кадров из первого видео и {len(frames2)} из второго")

        # Сравниваем кадры
        frame_comparisons = []
        total_similarity = 0.0
        compared_pairs = 0

        for i, frame1 in enumerate(frames1):
            best_similarity = 0.0
            best_comparison_details = {}

            for j, frame2 in enumerate(frames2):
                # Сравниваем два кадра
                comparison_result = self.comparison_manager.compare_images(frame1, frame2)
                similarity = comparison_result.get('overall', 0.0)

                if similarity > best_similarity:
                    best_similarity = similarity
                    best_comparison_details = {
                        'frame1_index': i,
                        'frame2_index': j,
                        'similarity': similarity,
                        'algorithm_details': comparison_result
                    }

            if best_comparison_details:
                frame_comparisons.append(best_comparison_details)
                total_similarity += best_similarity
                compared_pairs += 1

        # Вычисляем общую схожесть
        overall_similarity = total_similarity / compared_pairs if compared_pairs > 0 else 0.0

        return {
            'similarity': overall_similarity,
            'frame_comparisons': frame_comparisons,
            'frames_extracted': {
                'video1': len(frames1),
                'video2': len(frames2)
            },
            'algorithm_weights': {comp.name: comp.weight for comp in self.comparison_manager.comparators}
        }

    def find_similar_videos(self, video_files: List[str], similarity_threshold: float = None) -> List[Tuple]:
        """
        Находит похожие видео среди списка файлов
        Возвращает список кортежей (video1, video2, similarity)
        """
        if similarity_threshold is None:
            similarity_threshold = Config.SIMILARITY_THRESHOLD

        similar_pairs = []

        for i in range(len(video_files)):
            for j in range(i + 1, len(video_files)):
                video1 = video_files[i]
                video2 = video_files[j]

                print(f"Сравниваем {i + 1}/{len(video_files)}: {os.path.basename(video1)} и {os.path.basename(video2)}")

                result = self.compare_videos(video1, video2)
                similarity = result['similarity']

                if similarity >= similarity_threshold:
                    similar_pairs.append((video1, video2, similarity, result))

        # Сортируем по убыванию схожести
        similar_pairs.sort(key=lambda x: x[2], reverse=True)

        return similar_pairs