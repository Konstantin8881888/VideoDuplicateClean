import sys
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QPushButton,
                             QVBoxLayout, QWidget, QLabel, QFileDialog,
                             QTextEdit, QProgressBar)
from PyQt6.QtCore import QThread, pyqtSignal
import time

from core.file_scanner import FileScanner
from core.frame_extractor import FrameExtractor


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
        self.setWindowTitle("VideoDuplicate Cleaner")
        self.setGeometry(100, 100, 800, 600)

        # Инициализируем компоненты
        self.scanner = FileScanner()
        self.frame_extractor = FrameExtractor()
        self.scan_thread = None

        # Создаем центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Создаем layout
        layout = QVBoxLayout()
        central_widget.setLayout(layout)

        # Добавляем элементы
        label = QLabel("VideoDuplicate Cleaner - поиск похожих видеофайлов")
        layout.addWidget(label)

        self.select_button = QPushButton("Выбрать папку для сканирования")
        self.select_button.clicked.connect(self.select_folder)
        layout.addWidget(self.select_button)

        self.scan_button = QPushButton("Начать сканирование")
        self.scan_button.clicked.connect(self.start_scan)
        layout.addWidget(self.scan_button)

        # Прогресс-бар
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.log_text = QTextEdit()
        self.log_text.setPlaceholderText("Здесь будут отображаться результаты...")
        layout.addWidget(self.log_text)

        self.status_label = QLabel("Готов к работе")
        layout.addWidget(self.status_label)

        self.selected_folder = ""

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку для сканирования")
        if folder:
            self.selected_folder = folder
            self.log_text.append(f"Выбрана папка: {folder}")
            self.status_label.setText(f"Выбрана папка: {os.path.basename(folder)}")

    def start_scan(self):
        if not self.selected_folder:
            self.log_text.append("ОШИБКА: Сначала выберите папку!")
            return

        # Блокируем кнопки во время сканирования
        self.scan_button.setEnabled(False)
        self.select_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        self.log_text.clear()
        self.log_text.append("Начинаем сканирование...")
        self.status_label.setText("Сканирование...")

        # Создаем и запускаем поток сканирования
        self.scan_thread = ScanThread(self.scanner, self.frame_extractor, self.selected_folder)
        self.scan_thread.progress_signal.connect(self.update_progress)
        self.scan_thread.log_signal.connect(self.update_log)
        self.scan_thread.finished_signal.connect(self.scan_finished)
        self.scan_thread.start()

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def update_log(self, message):
        self.log_text.append(message)

    def scan_finished(self, results):
        # Разблокируем кнопки
        self.scan_button.setEnabled(True)
        self.select_button.setEnabled(True)
        self.progress_bar.setVisible(False)

        self.log_text.append("\n=== СКАНИРОВАНИЕ ЗАВЕРШЕНО ===")
        self.status_label.setText(f"Обработано файлов: {len(results)}")

        # Показываем результаты
        for result in results[:10]:  # Показываем первые 10 результатов
            path = result['path']
            file_info = result['file_info']
            video_info = result['video_info']

            size_mb = file_info.get('size', 0) / (1024 * 1024)
            duration = video_info.get('duration', 0)
            resolution = f"{video_info.get('width', 0)}x{video_info.get('height', 0)}"

            self.log_text.append(f"\n{os.path.basename(path)}")
            self.log_text.append(f"  Размер: {size_mb:.1f} MB")
            self.log_text.append(f"  Длительность: {duration:.1f} сек")
            self.log_text.append(f"  Разрешение: {resolution}")
            self.log_text.append(f"  Будет извлечено кадров: {result['frames_count']}")

        if len(results) > 10:
            self.log_text.append(f"\n... и еще {len(results) - 10} файлов")


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()