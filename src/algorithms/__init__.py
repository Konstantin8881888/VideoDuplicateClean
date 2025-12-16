from .simple import SimpleAlgorithm

# Попытаемся импортировать phash (если зависимости установлены)
try:
    from .phash import PHashAlgorithm
    PHASH_AVAILABLE = True
except Exception:
    PHashAlgorithm = None
    PHASH_AVAILABLE = False

def create_algorithm(name: str = 'simple'):
    """
    Factory for algorithms.
    Возвращает объект с интерфейсом используемым main.py
    """
    n = (name or '').strip().lower()
    if n in ('simple', 'original'):
        return SimpleAlgorithm()

    if n in ('phash', 'pHash'.lower()):
        if PHASH_AVAILABLE and PHashAlgorithm is not None:
            return PHashAlgorithm()
        else:
            # возвращаем simple, но помечаем как unimplemented, чтобы GUI предупредил пользователя
            alg = SimpleAlgorithm()
            alg.name = 'phash'
            alg.implemented = False
            return alg

    if n in ('cnn_faiss', 'cnn-faiss', 'cnn'):
        # Пока не реализован — возвращаем simple с отметкой unimplemented
        alg = SimpleAlgorithm()
        alg.name = n
        alg.implemented = False
        return alg

    # По умолчанию — simple
    alg = SimpleAlgorithm()
    alg.name = n
    alg.implemented = False
    return alg