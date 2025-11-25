import cv2
import numpy as np
from src.algorithms.base_comparator import BaseComparator


class HistogramComparator(BaseComparator):
    """Сравнивает изображения с помощью гистограмм в HSV пространстве"""

    def __init__(self, weight: float = 1.0):
        super().__init__("Histogram", weight)
        # Параметры для вычисления гистограмм
        self.h_bins = 50
        self.s_bins = 50
        self.hist_size = [self.h_bins, self.s_bins]
        self.ranges = [0, 180, 0, 256]  # HSV диапазоны

    def compare(self, image1: np.ndarray, image2: np.ndarray) -> float:
        """
        Сравнивает два изображения с помощью гистограмм HSV
        Возвращает оценку схожести от 0 до 1
        """
        try:
            # Нормализуем размер изображений
            image1_norm = self.normalize_image(image1)
            image2_norm = self.normalize_image(image2)

            # Конвертируем в HSV
            hsv1 = cv2.cvtColor(image1_norm, cv2.COLOR_BGR2HSV)
            hsv2 = cv2.cvtColor(image2_norm, cv2.COLOR_BGR2HSV)

            # Вычисляем гистограммы для каналов H и S
            hist1 = cv2.calcHist([hsv1], [0, 1], None, self.hist_size, self.ranges)
            hist2 = cv2.calcHist([hsv2], [0, 1], None, self.hist_size, self.ranges)

            # Нормализуем гистограммы
            cv2.normalize(hist1, hist1, 0, 1, cv2.NORM_MINMAX)
            cv2.normalize(hist2, hist2, 0, 1, cv2.NORM_MINMAX)

            # Сравниваем гистограммы методом корреляции
            similarity = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)

            # Преобразуем в диапазон 0-1 (корреляция может быть от -1 до 1)
            return max(0.0, (similarity + 1) / 2)

        except Exception as e:
            print(f"Ошибка в HistogramComparator: {e}")
            return 0.0