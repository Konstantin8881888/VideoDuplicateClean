from typing import List, Dict
import numpy as np
from src.algorithms.base_comparator import BaseComparator
from src.algorithms.histogram_comparator import HistogramComparator
from src.algorithms.phash_comparator import PHashComparator
from src.config import Config


class ComparisonManager:
    """Управляет всеми алгоритмами сравнения и агрегирует результаты"""

    def __init__(self):
        self.comparators: List[BaseComparator] = []
        self.setup_comparators()

    def setup_comparators(self):
        """Настраивает компараторы с весами из конфигурации"""
        weights = Config.ALGORITHM_WEIGHTS

        self.comparators = [
            HistogramComparator(weight=weights.get('Histogram', 0.4)),
            PHashComparator(weight=weights.get('Perceptual Hash', 0.6))
        ]

    def compare_images(self, image1: np.ndarray, image2: np.ndarray) -> Dict[str, float]:
        """
        Сравнивает два изображения всеми доступными алгоритмами
        Возвращает словарь с результатами каждого алгоритма и общим счетом
        """
        results = {}
        total_score = 0.0
        total_weight = 0.0

        for comparator in self.comparators:
            try:
                score = comparator.compare(image1, image2)
                results[comparator.name] = score
                total_score += score * comparator.weight
                total_weight += comparator.weight
            except Exception as e:
                print(f"Ошибка в компараторе {comparator.name}: {e}")
                results[comparator.name] = 0.0

        # Вычисляем общий взвешенный счет
        if total_weight > 0:
            results['overall'] = total_score / total_weight
        else:
            results['overall'] = 0.0

        return results

    def get_comparator_names(self) -> List[str]:
        """Возвращает список имен всех компараторов"""
        return [comp.name for comp in self.comparators]

    def set_weights(self, weights: Dict[str, float]):
        """Устанавливает веса для компараторов"""
        for comp in self.comparators:
            if comp.name in weights:
                comp.weight = weights[comp.name]