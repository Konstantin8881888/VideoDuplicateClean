from src.core.optimized_comparator import OptimizedVideoComparator

class SimpleAlgorithm:
    """
    Адаптер-обёртка над существующим OptimizedVideoComparator из репозитория.
    Обеспечивает единый интерфейс для фабрики алгоритмов.
    """
    def __init__(self):
        self._impl = OptimizedVideoComparator()
        self.name = 'simple'
        self.implemented = True

    def find_similar_videos_optimized(self, video_files, similarity_threshold=None):
        """
        Делегируем в оригинальный optimized comparator.
        """
        # сохранение совместимости по параметрам
        if similarity_threshold is None:
            return self._impl.find_similar_videos_optimized(video_files)
        return self._impl.find_similar_videos_optimized(video_files, similarity_threshold)

    def compare_videos(self, video1_path, video2_path, *args, **kwargs):
        """
        Делегируем вызов compare_videos, поддерживаем вариативные сигнатуры.
        """
        try:
            return self._impl.compare_videos(video1_path, video2_path, *args, **kwargs)
        except TypeError:
            # Попытка вызвать без дополнительных аргументов
            return self._impl.compare_videos(video1_path, video2_path)