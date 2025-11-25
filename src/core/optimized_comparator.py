import os
import hashlib
from typing import List, Dict, Tuple, Optional
from src.core.frame_extractor import FrameExtractor
from src.algorithms.comparison_manager import ComparisonManager
from src.config import Config


class OptimizedVideoComparator:
    """
    Оптимизированный компаратор видео с предварительной фильтрацией и кэшированием
    """

    def __init__(self):
        self.frame_extractor = FrameExtractor()
        self.comparison_manager = ComparisonManager()
        self.num_frames_to_compare = Config.OPTIMIZED_COMPARISON_FRAMES  # Уменьшаем количество кадров для скорости
        self.similarity_threshold = Config.SIMILARITY_THRESHOLD

        # Кэши для ускорения повторных операций
        self._frame_cache = {}  # Кэш кадров: video_path -> [frames]
        self._metadata_cache = {}  # Кэш метаданных: video_path -> metadata
        self._file_hash_cache = {}  # Кэш хэшей файлов для быстрого определения точных дубликатов

    def _get_file_hash(self, file_path: str) -> str:
        """Быстрое вычисление хэша файла для определения точных дубликатов"""
        if file_path in self._file_hash_cache:
            return self._file_hash_cache[file_path]

        try:
            file_size = os.path.getsize(file_path)
            # Для больших файлов берем хэш только от первых 1MB и размера
            with open(file_path, 'rb') as f:
                if file_size > 1024 * 1024:
                    content = f.read(1024 * 1024)  # Первые 1MB
                    content += str(file_size).encode()  # Добавляем размер файла
                else:
                    content = f.read()

            file_hash = hashlib.md5(content).hexdigest()
            self._file_hash_cache[file_path] = file_hash
            return file_hash
        except Exception as e:
            print(f"Ошибка при вычислении хэша файла {file_path}: {e}")
            return ""

    def _get_video_metadata(self, video_path: str) -> Dict:
        """Получает и кэширует метаданные видео"""
        if video_path in self._metadata_cache:
            return self._metadata_cache[video_path]

        metadata = self.frame_extractor.get_video_info(video_path)
        file_info = {
            'size': os.path.getsize(video_path),
            'duration': metadata.get('duration', 0),
            'width': metadata.get('width', 0),
            'height': metadata.get('height', 0),
            'file_hash': self._get_file_hash(video_path)
        }

        self._metadata_cache[video_path] = file_info
        return file_info

    def _get_cached_frames(self, video_path: str) -> List:
        """Получает кадры из кэша или извлекает их"""
        if video_path in self._frame_cache:
            return self._frame_cache[video_path]

        frames = self.frame_extractor.extract_frames(video_path, self.num_frames_to_compare)
        self._frame_cache[video_path] = frames
        return frames

    def _are_metadata_similar(self, meta1: Dict, meta2: Dict) -> bool:
        """
        Быстрая проверка по метаданным - отфильтровываем заведомо разные видео
        """
        # Если хэши файлов совпадают - это точные дубликаты
        if meta1['file_hash'] and meta2['file_hash'] and meta1['file_hash'] == meta2['file_hash']:
            return True

        # Разница в размере файла больше 50% - скорее всего разные видео
        size_ratio = min(meta1['size'], meta2['size']) / max(meta1['size'], meta2['size'])
        if size_ratio < 0.5:
            return False

        # Разница в длительности больше 30% - скорее всего разные видео
        if meta1['duration'] > 0 and meta2['duration'] > 0:
            duration_ratio = min(meta1['duration'], meta2['duration']) / max(meta1['duration'], meta2['duration'])
            if duration_ratio < 0.7:
                return False

        # Сильно различающееся разрешение
        if meta1['width'] > 0 and meta2['width'] > 0:
            width_ratio = min(meta1['width'], meta2['width']) / max(meta1['width'], meta2['width'])
            if width_ratio < 0.7:
                return False

        return True

    def find_similar_videos_optimized(self, video_files: List[str], similarity_threshold: float = 0.7) -> List[Tuple]:
        """
        Оптимизированный поиск похожих видео
        """
        self.similarity_threshold = similarity_threshold
        similar_pairs = []

        print(f"🔍 Анализируем {len(video_files)} видеофайлов...")

        # Шаг 1: Собираем метаданные для всех файлов
        print("📊 Собираем метаданные...")
        video_metadata = {}
        for video_path in video_files:
            video_metadata[video_path] = self._get_video_metadata(video_path)

        # Шаг 2: Группируем по хэшам для быстрого нахождения точных дубликатов
        print("🎯 Ищем точные дубликаты...")
        hash_groups = {}
        for video_path, meta in video_metadata.items():
            if meta['file_hash']:
                if meta['file_hash'] not in hash_groups:
                    hash_groups[meta['file_hash']] = []
                hash_groups[meta['file_hash']].append(video_path)

        # Добавляем точные дубликаты в результаты
        for file_hash, group in hash_groups.items():
            if len(group) > 1:
                for i in range(len(group)):
                    for j in range(i + 1, len(group)):
                        similar_pairs.append((group[i], group[j], 1.0, {'type': 'exact_duplicate'}))

        # Шаг 3: Предварительная фильтрация по метаданным
        print("⚡ Фильтруем по метаданным...")
        candidate_pairs = []
        processed_pairs = set()

        for i, video1 in enumerate(video_files):
            meta1 = video_metadata[video1]

            for j, video2 in enumerate(video_files[i + 1:], i + 1):
                # Пропускаем если уже нашли как точные дубликаты
                if (video1, video2) in processed_pairs or (video2, video1) in processed_pairs:
                    continue

                meta2 = video_metadata[video2]

                # Быстрая проверка по метаданным
                if self._are_metadata_similar(meta1, meta2):
                    candidate_pairs.append((video1, video2))

                processed_pairs.add((video1, video2))

        print(f"🎯 Кандидатов для глубокого анализа: {len(candidate_pairs)}")

        # Шаг 4: Глубокий анализ только кандидатов
        print("🔍 Запускаем глубокий анализ...")
        for idx, (video1, video2) in enumerate(candidate_pairs):
            if idx % 10 == 0:
                print(f"📈 Обработано {idx}/{len(candidate_pairs)} пар...")

            result = self.compare_videos(video1, video2)
            similarity = result['similarity']

            if similarity >= similarity_threshold:
                similar_pairs.append((video1, video2, similarity, result))

        # Сортируем по убыванию схожести
        similar_pairs.sort(key=lambda x: x[2], reverse=True)

        return similar_pairs

    def compare_videos(self, video_path1: str, video_path2: str) -> Dict:
        """
        Оптимизированное сравнение двух видео
        """
        # Используем кэшированные кадры
        frames1 = self._get_cached_frames(video_path1)
        frames2 = self._get_cached_frames(video_path2)

        if not frames1 or not frames2:
            return {
                'similarity': 0.0,
                'error': 'Не удалось извлечь кадры',
                'details': {}
            }

        # Упрощенное сравнение - берем только лучшие совпадения
        frame_comparisons = []
        total_similarity = 0.0
        compared_pairs = 0

        # Сравниваем только ограниченное количество комбинаций
        max_comparisons = min(len(frames1), len(frames2), 3)

        for i in range(max_comparisons):
            frame1 = frames1[i] if i < len(frames1) else frames1[0]
            frame2 = frames2[i] if i < len(frames2) else frames2[0]

            comparison_result = self.comparison_manager.compare_images(frame1, frame2)
            similarity = comparison_result.get('overall', 0.0)

            frame_comparisons.append({
                'frame1_index': i,
                'frame2_index': i,
                'similarity': similarity,
                'algorithm_details': comparison_result
            })

            total_similarity += similarity
            compared_pairs += 1

        # Вычисляем общую схожесть
        overall_similarity = total_similarity / compared_pairs if compared_pairs > 0 else 0.0

        return {
            'similarity': overall_similarity,
            'frame_comparisons': frame_comparisons,
            'frames_extracted': {
                'video1': len(frames1),
                'video2': len(frames2)
            }
        }

    def clear_cache(self):
        """Очищает кэши"""
        self._frame_cache.clear()
        self._metadata_cache.clear()
        self._file_hash_cache.clear()