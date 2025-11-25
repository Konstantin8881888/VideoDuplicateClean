import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QTabWidget, QWidget, QProgressBar, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from src.config import Config


class ComparisonWorker(QThread):
    """Поток для выполнения сравнения видео"""

    progress_signal = pyqtSignal(int, str)
    result_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)

    def __init__(self, video_paths):
        super().__init__()
        self.video_paths = video_paths

    def run(self):
        try:
            from src.core.video_comparator import VideoComparator
            from src.core.frame_extractor import FrameExtractor

            self.progress_signal.emit(10, "Инициализация компаратора...")
            comparator = VideoComparator()
            extractor = FrameExtractor()

            self.progress_signal.emit(30, "Извлечение кадров...")

            # Извлекаем кадры из обоих видео
            frames_data = {}
            for i, video_path in enumerate(self.video_paths):
                self.progress_signal.emit(30 + i * 20, f"Извлекаем кадры из {os.path.basename(video_path)}...")
                frames = extractor.extract_frames(video_path, Config.SAFE_COMPARISON_FRAMES)
                frames_data[video_path] = frames

            self.progress_signal.emit(70, "Сравниваем видео...")
            result = comparator.compare_videos(self.video_paths[0], self.video_paths[1])

            self.progress_signal.emit(100, "Готово!")
            self.result_signal.emit(result)

        except Exception as e:
            self.error_signal.emit(f"Ошибка при сравнении: {str(e)}")


class SimpleComparisonDialog(QDialog):
    """Упрощенный диалог для сравнения видео с прогресс-баром"""

    def __init__(self, video_paths, parent=None):
        super().__init__(parent)
        self.video_paths = video_paths[:2]  # Берем только первые 2 видео

        self.setWindowTitle("Сравнение видео")
        self.setGeometry(100, 100, 800, 600)
        self.setup_ui()

    def setup_ui(self):
        """Создает улучшенный интерфейс"""
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Заголовок
        title = QLabel("🎬 Сравнение видео")
        title.setStyleSheet("font-size: 16pt; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Информация о файлах
        self.info_text = QTextEdit()
        self.info_text.setPlainText(self.get_comparison_info())
        self.info_text.setReadOnly(True)
        layout.addWidget(self.info_text)

        # Прогресс-бар
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Статус
        self.status_label = QLabel("Готов к сравнению")
        layout.addWidget(self.status_label)

        # Кнопки
        button_layout = QHBoxLayout()

        self.compare_btn = QPushButton("🔍 Начать сравнение")
        self.compare_btn.clicked.connect(self.start_comparison)
        button_layout.addWidget(self.compare_btn)

        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.close)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

        # Область для результатов
        self.results_text = QTextEdit()
        self.results_text.setPlaceholderText("Результаты сравнения появятся здесь...")
        self.results_text.setReadOnly(True)
        layout.addWidget(self.results_text)

    def get_comparison_info(self):
        """Получает информацию о сравниваемых файлах"""
        from src.core.frame_extractor import FrameExtractor
        extractor = FrameExtractor()

        info = "Сравниваемые файлы:\n\n"

        for i, video_path in enumerate(self.video_paths):
            if os.path.exists(video_path):
                video_info = extractor.get_video_info(video_path)
                file_size = os.path.getsize(video_path) / (1024 * 1024)

                info += f"Видео {i + 1}:\n"
                info += f"📁 Файл: {os.path.basename(video_path)}\n"
                info += f"📏 Размер: {file_size:.2f} MB\n"
                info += f"🎞️ Разрешение: {video_info.get('width', 'N/A')}x{video_info.get('height', 'N/A')}\n"
                info += f"⏱️ Длительность: {video_info.get('duration', 0):.1f} сек\n"
                info += f"📊 FPS: {video_info.get('fps', 0):.1f}\n"
                info += f"🖼️ Всего кадров: {video_info.get('total_frames', 0)}\n\n"
            else:
                info += f"Видео {i + 1}: ФАЙЛ НЕ НАЙДЕН - {video_path}\n\n"

        info += f"🔍 Будет извлечено и сравнено по {Config.SAFE_COMPARISON_FRAMES} кадров из каждого видео"
        return info

    def start_comparison(self):
        """Запускает сравнение видео"""
        self.compare_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("Начинаем сравнение...")
        self.results_text.clear()

        # Запускаем сравнение в отдельном потоке
        self.worker = ComparisonWorker(self.video_paths)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.result_signal.connect(self.show_results)
        self.worker.error_signal.connect(self.show_error)
        self.worker.start()

    def update_progress(self, value: int, message: str):
        """Обновляет прогресс"""
        self.progress_bar.setValue(value)
        self.status_label.setText(message)

    def show_results(self, result: dict):
        """Показывает результаты сравнения"""
        self.progress_bar.setVisible(False)
        self.compare_btn.setEnabled(True)
        self.status_label.setText("Сравнение завершено!")

        output = "📊 РЕЗУЛЬТАТЫ СРАВНЕНИЯ:\n\n"
        output += f"🎯 Общая схожесть: {result['similarity']:.2%}\n\n"

        if 'error' in result:
            output += f"❌ Ошибка: {result['error']}\n"
        else:
            output += f"📹 Извлечено кадров: {result['frames_extracted']['video1']} и {result['frames_extracted']['video2']}\n\n"

            if 'frame_comparisons' in result:
                output += "🔍 Детали по кадрам:\n"
                for i, comparison in enumerate(result['frame_comparisons'], 1):
                    output += f"\nКадр {i}:\n"
                    output += f"   Схожесть: {comparison['similarity']:.2%}\n"

                    # Детали по алгоритмам
                    for algo_name, algo_score in comparison['algorithm_details'].items():
                        if algo_name != 'overall':
                            output += f"   - {algo_name}: {algo_score:.2%}\n"

        self.results_text.setText(output)

    def show_error(self, error_message: str):
        """Показывает ошибку"""
        self.progress_bar.setVisible(False)
        self.compare_btn.setEnabled(True)
        self.status_label.setText("Ошибка!")
        self.results_text.setText(f"❌ ОШИБКА:\n{error_message}")