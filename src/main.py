import sys
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QPushButton,
                             QVBoxLayout, QWidget, QLabel, QFileDialog,
                             QTextEdit, QProgressBar, QHBoxLayout, QTabWidget)
from PyQt6.QtCore import QThread, pyqtSignal
import time

from core.file_scanner import FileScanner
from core.frame_extractor import FrameExtractor
from src.core.video_comparator import VideoComparator


# Класс для выполнения сканирования в отдельном потоке
class ScanThread(QThread):
    progress_signal = pyqtSignal(int)
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(list)

    def __init__(self, scanner, frame_extractor, folder_path):
        super().__init__()
        self.scanner = scanner
        self.frame_extractor = frame_extractor
        self.folder_path = folder_path

    def run(self):
        try:
            self.log_signal.emit("Начинаем сканирование папки...")

            # Находим видеофайлы
            video_files = self.scanner.find_video_files(self.folder_path)
            self.log_signal.emit(f"Найдено видеофайлов: {len(video_files)}")

            if not video_files:
                self.finished_signal.emit([])
                return

            results = []
            total_files = len(video_files)

            for i, file_path in enumerate(video_files):
                # Обновляем прогресс
                progress = int((i / total_files) * 100)
                self.progress_signal.emit(progress)

                self.log_signal.emit(f"Обрабатываем: {os.path.basename(file_path)}")

                # Получаем информацию о файле
                file_info = self.scanner.get_file_info(file_path)

                # Получаем информацию о видео
                video_info = self.frame_extractor.get_video_info(file_path)

                # Извлекаем кадры (пока только информацию о том, что можем)
                frames_count = 10  # Мы будем извлекать 10 кадров, но пока не сохраняем их

                result = {
                    'path': file_path,
                    'file_info': file_info,
                    'video_info': video_info,
                    'frames_count': frames_count
                }
                results.append(result)

                # Имитируем обработку для демонстрации
                time.sleep(0.1)

            self.progress_signal.emit(100)
            self.finished_signal.emit(results)

        except Exception as e:
            self.log_signal.emit(f"Ошибка при сканировании: {e}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # ... (предыдущий код инициализации)

        # Добавляем компаратор
        self.comparator = VideoComparator()

        # Создаем вкладки
        self.setup_tabs()

    def setup_tabs(self):
        """Создает вкладки для разных функций"""
        self.tabs = QTabWidget()

        # Вкладка сканирования
        self.scan_tab = self.create_scan_tab()
        self.tabs.addTab(self.scan_tab, "Сканирование")

        # Вкладка сравнения
        self.compare_tab = self.create_compare_tab()
        self.tabs.addTab(self.compare_tab, "Сравнение")

        self.setCentralWidget(self.tabs)

    def create_compare_tab(self):
        """Создает вкладку для сравнения видео"""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        # Кнопки выбора файлов для сравнения
        compare_layout = QHBoxLayout()

        self.select_video1_btn = QPushButton("Выбрать первое видео")
        self.select_video1_btn.clicked.connect(lambda: self.select_video_for_comparison(1))
        compare_layout.addWidget(self.select_video1_btn)

        self.select_video2_btn = QPushButton("Выбрать второе видео")
        self.select_video2_btn.clicked.connect(lambda: self.select_video_for_comparison(2))
        compare_layout.addWidget(self.select_video2_btn)

        layout.addLayout(compare_layout)

        # Поля для отображения выбранных файлов
        self.video1_label = QLabel("Первое видео: не выбрано")
        self.video2_label = QLabel("Второе видео: не выбрано")
        layout.addWidget(self.video1_label)
        layout.addWidget(self.video2_label)

        # Кнопка сравнения
        self.compare_btn = QPushButton("Сравнить видео")
        self.compare_btn.clicked.connect(self.compare_selected_videos)
        layout.addWidget(self.compare_btn)

        # Результаты сравнения
        self.compare_results = QTextEdit()
        self.compare_results.setPlaceholderText("Здесь будут результаты сравнения...")
        layout.addWidget(self.compare_results)

        self.video1_path = ""
        self.video2_path = ""

        return widget

    def select_video_for_comparison(self, video_num: int):
        """Выбирает видеофайл для сравнения"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            f"Выберите видео файл #{video_num}",
            "",
            "Video Files (*.mp4 *.avi *.mov *.mkv *.wmv)"
        )

        if file_path:
            if video_num == 1:
                self.video1_path = file_path
                self.video1_label.setText(f"Первое видео: {os.path.basename(file_path)}")
            else:
                self.video2_path = file_path
                self.video2_label.setText(f"Второе видео: {os.path.basename(file_path)}")

    def compare_selected_videos(self):
        """Сравнивает выбранные видеофайлы"""
        if not self.video1_path or not self.video2_path:
            self.compare_results.append("❌ Ошибка: выберите оба видеофайла!")
            return

        self.compare_results.clear()
        self.compare_results.append("🔄 Начинаем сравнение...")

        # Запускаем сравнение в отдельном потоке
        self.compare_thread = CompareThread(self.comparator, self.video1_path, self.video2_path)
        self.compare_thread.result_signal.connect(self.show_comparison_result)
        self.compare_thread.start()

    def show_comparison_result(self, result):
        """Показывает результаты сравнения"""
        self.compare_results.append("\n📊 РЕЗУЛЬТАТЫ СРАВНЕНИЯ:")
        self.compare_results.append(f"🎯 Общая схожесть: {result['similarity']:.2%}")

        if 'error' in result:
            self.compare_results.append(f"❌ Ошибка: {result['error']}")
            return

        for i, comparison in enumerate(result['frame_comparisons']):
            self.compare_results.append(f"\n🔍 Сравнение кадров #{i + 1}:")
            self.compare_results.append(f"   Общая схожесть: {comparison['similarity']:.2%}")
            for algo_name, algo_score in comparison['algorithm_details'].items():
                if algo_name != 'overall':
                    self.compare_results.append(f"   - {algo_name}: {algo_score:.2%}")


# Добавляем класс для потока сравнения
class CompareThread(QThread):
    result_signal = pyqtSignal(dict)

    def __init__(self, comparator, video1_path, video2_path):
        super().__init__()
        self.comparator = comparator
        self.video1_path = video1_path
        self.video2_path = video2_path

    def run(self):
        result = self.comparator.compare_videos(self.video1_path, self.video2_path)
        self.result_signal.emit(result)

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()