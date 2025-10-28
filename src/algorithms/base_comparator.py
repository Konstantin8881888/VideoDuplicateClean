import cv2
import numpy as np
from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseComparator(ABC):
    """Базовый класс для всех алгоритмов сравнения изображений"""

    def __init__(self, name: str, weight: float = 1.0):
        self.name = name
        self.weight = weight

    @abstractmethod
    def compare(self, image1: np.ndarray, image2: np.ndarray) -> float:
        """
        Сравнивает два изображения и возвращает оценку схожести (0-1)
        где 1 - идентичные, 0 - совершенно разные
        """
        pass

    def normalize_image(self, image: np.ndarray, target_size: tuple = (256, 256)) -> np.ndarray:
        """Нормализует изображение к стандартному размеру"""
        if len(image.shape) == 3:
            # Цветное изображение
            return cv2.resize(image, target_size)
        else:
            # ЧБ изображение
            return cv2.resize(image, target_size)