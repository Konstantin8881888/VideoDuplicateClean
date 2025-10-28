import sys
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QPushButton,
                             QVBoxLayout, QWidget, QLabel, QFileDialog,
                             QTextEdit)
# Добавляем импорт нашего сканера
from core.file_scanner import FileScanner


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VideoDuplicate Cleaner")
        self.setGeometry(100, 100, 800, 600)

        # Инициализируем сканер
        self.scanner = FileScanner()

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

        self.log_text.append("Начинаем сканирование...")
        self.status_label.setText("Сканирование...")

        # Используем наш сканер
        video_files = self.scanner.find_video_files(self.selected_folder)

        self.log_text.append(f"Найдено видеофайлов: {len(video_files)}")

        # Показываем первые 5 файлов для примера
        for i, file_path in enumerate(video_files[:5]):
            file_info = self.scanner.get_file_info(file_path)
            size_mb = file_info.get('size', 0) / (1024 * 1024)
            self.log_text.append(f"{i + 1}. {os.path.basename(file_path)} ({size_mb:.1f} MB)")

        if len(video_files) > 5:
            self.log_text.append(f"... и еще {len(video_files) - 5} файлов")

        self.status_label.setText(f"Найдено {len(video_files)} видеофайлов")


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()