"""
Конфигурация приложения VideoDuplicate Cleaner
"""


class Config:
    """Настройки приложения"""

    # Настройки сравнения
    DEFAULT_FRAMES_TO_COMPARE = 10
    SIMILARITY_THRESHOLD = 0.7
    OPTIMIZED_COMPARISON_FRAMES = 3

    # Настройки алгоритмов
    ALGORITHM_WEIGHTS = {
        'Histogram': 0.4,
        'Perceptual Hash': 0.6
    }

    # Настройки памяти
    MAX_MEMORY_USAGE_MB = 1024
    FRAME_CACHE_SIZE = 50
    METADATA_CACHE_SIZE = 100

    # Поддерживаемые форматы видео
    SUPPORTED_FORMATS = {'.mp4', '.avi', '.mov', '.mkv', '.wmv'}

    # Настройки интерфейса
    MAX_VIDEOS_IN_GROUP = 10
    PROGRESS_UPDATE_INTERVAL_MS = 100

    # Настройки производительности
    MAX_CONCURRENT_THREADS = 2
    THREAD_TIMEOUT_SECONDS = 30

    @classmethod
    def validate(cls):
        """Проверка корректности настроек"""
        assert 0 < cls.DEFAULT_FRAMES_TO_COMPARE <= 50, "Некорректное количество кадров"
        assert 0.0 <= cls.SIMILARITY_THRESHOLD <= 1.0, "Порог схожести должен быть от 0 до 1"
        assert cls.MAX_MEMORY_USAGE_MB > 0, "Максимальное использование памяти должно быть положительным"

        total_weight = sum(cls.ALGORITHM_WEIGHTS.values())
        assert abs(total_weight - 1.0) < 0.001, "Сумма весов алгоритмов должна быть равна 1"