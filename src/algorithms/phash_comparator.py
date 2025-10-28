import cv2
import numpy as np
from .base_comparator import BaseComparator


class PHashComparator(BaseComparator):
    """Сравнивает изображения с помощью perceptual hashing (pHash)"""

    def __init__(self, weight: float = 1.0, hash_size: int = 16):
        super().__init__("Perceptual Hash", weight)
        self.hash_size = hash_size

    def _compute_phash(self, image: np.ndarray) -> str:
        """Вычисляет perceptual hash для изображения"""
        try:
            # Нормализуем размер
            resized = self.normalize_image(image, (self.hash_size, self.hash_size))

            # Конвертируем в grayscale если нужно
            if len(resized.shape) == 3:
                gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
            else:
                gray = resized

            # Вычисляем DCT (Discrete Cosine Transform)
            dct = cv2.dct(np.float32(gray))

            # Берем верхний левый квадрат 8x8 (игнорируем низкочастотные компоненты)
            dct_roi = dct[:8, :8]

            # Вычисляем среднее значение (игнорируя первый элемент)
            mean_val = np.mean(dct_roi[1:, 1:])

            # Создаем хэш: 1 если значение > среднего, 0 иначе
            hash_array = dct_roi > mean_val
            hash_str = ''.join(['1' if bit else '0' for row in hash_array for bit in row])

            return hash_str

        except Exception as e:
            print(f"Ошибка при вычислении pHash: {e}")
            return ""

    def compare(self, image1: np.ndarray, image2: np.ndarray) -> float:
        """Сравнивает два изображения с помощью pHash"""
        try:
            hash1 = self._compute_phash(image1)
            hash2 = self._compute_phash(image2)

            if not hash1 or not hash2 or len(hash1) != len(hash2):
                return 0.0

            # Вычисляем расстояние Хэмминга
            hamming_distance = sum(c1 != c2 for c1, c2 in zip(hash1, hash2))

            # Преобразуем в схожесть (0-1)
            max_distance = len(hash1)
            similarity = 1.0 - (hamming_distance / max_distance)

            return max(0.0, similarity)

        except Exception as e:
            print(f"Ошибка в PHashComparator: {e}")
            return 0.0